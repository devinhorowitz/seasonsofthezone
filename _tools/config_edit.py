"""Read and write seasons_config.py for configure.py, the window and its commands.

The config stays a Python file people can edit by hand. This rewrites only the tables that
change, and inside them only the entries that changed: the rest of the file, comments
included, stays as written. A new file is checked with season.py's own rules before it
replaces the old one, and the old one is kept as seasons_config.py.bak. A save that could
not keep every comment, and starting over from a file that could not be read, also keep a
dated copy that no later save touches.

Presets are whole setups kept under a name in _tools/presets/, as JSON: plain data, so a
preset someone posts can be loaded without running anything they wrote. Loading one sets
the parts chosen and nothing else, and like any change here it is written only on Save.

It refuses what it cannot edit safely rather than guess: a file in an encoding it would
have to mangle, a table that shares its line with another statement, a table the lines
below it change again, or a file that changed on disk since it was read.
"""
import ast
import codecs
import copy
import datetime
import difflib
import io
import json
import os
import re
import shutil
import stat
import tokenize

import lang
import season
from lang import _, N_, ngettext, pgettext

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "seasons_config.py")

# as the date pickers list them and people type them; lang.month() is what to show
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# what people type for the seasons on the command line
ALIASES = {"deep winter": "winter_snow", "deep_winter": "winter_snow",
           "deepwinter": "winter_snow", "late winter": "late_winter",
           "latewinter": "late_winter", "fall": "autumn"}

# written above CALENDAR and NAMES, in a new file and when the tool adds one to an old file
CALENDAR_HEAD = [
    "# The seasons that are on and the day each starts, (month, day). configure.bat",
    "# writes this; None is Polesia's dates with all six seasons on.",
]
NAMES_HEAD = [
    "# Names of your own for the seasons, shown in game in place of the usual ones.",
    "# configure.bat writes this; None keeps the usual names.",
]
PLACE_HEAD = [
    "# Where the real weather comes from: {\"name\": ..., \"lat\": ..., \"lon\": ...}.",
    "# configure.bat writes this; None is Chornobyl.",
]
OWN_HEAD = [
    "# Seasons of your own: {name: ((month, day), (month, day))}, the first day and the last,",
    "# a week or longer. Each runs on top of the season it falls in. configure.bat writes this.",
]
SPELLS_HEAD = [
    "# Spells: short stretches that start by chance. \"in\" is the seasons one can start in,",
    "# \"chance\" the percent chance each day, \"days\" how long it runs (fewest, most, up to 6),",
    "# \"as\" the season it brings, or None. configure.bat writes this.",
]

TEMPLATE = '''"""Which mods this install stages, and when.

Written by configure.py (configure.bat), and still yours to edit by hand: the tool only
rewrites the entries it changes. The full reference is docs/CONFIGURING.md.
"""

LAYOUT = {}
TOGGLE_MODS = {}
SOUND_SRC = None
PERIODS = {}
EVENTS = {}

%s
CALENDAR = None

%s
NAMES = None

%s
WEATHER_PLACE = None

%s
OWN_SEASONS = {}

%s
SPELLS = {}
''' % ("\n".join(CALENDAR_HEAD), "\n".join(NAMES_HEAD), "\n".join(PLACE_HEAD),
       "\n".join(OWN_HEAD), "\n".join(SPELLS_HEAD))


# --- the install ----------------------------------------------------------------------

def mod_files(name):
    """Every file the mod ships, as lower-case gamedata paths with forward slashes."""
    base = os.path.join(season.MODS, name, "gamedata")
    out = set()
    for r, _, fs in os.walk(base):
        rel = os.path.relpath(r, base).replace(os.sep, "/")
        pre = "" if rel == "." else rel.lower() + "/"
        for f in fs:
            out.add(pre + f.lower())
    return out


class Install(object):
    """MO2's side: the mod list in priority order, highest first, and what each mod ships.
    Separators are kept apart, since an anchor may name one; a mod listed twice counts once.
    Files are read the first time they are asked for."""

    def __init__(self):
        order, seen = [], set()
        for l in (season._modlist_lines() or []):
            if l[:1] in ("+", "-") and l[1:] not in seen:
                seen.add(l[1:])
                order.append((l[1:], l[:1] == "+"))
        self.separators = {n for n, _ in order if n.endswith("_separator")}
        # modlist.txt's order, separators in place: highest priority first
        self.lines = [(n, on, n in self.separators) for n, on in order]
        self.order = [(n, on) for n, on in order if n not in self.separators]
        self.names = [n for n, _ in self.order]
        self.enabled = {n for n, on in self.order if on}
        self._files = {}

    def pane_order(self):
        """(name, enabled, is a separator) as MO2's left pane lists them: lowest priority
        at the top, each separator above its own mods - modlist.txt read backwards."""
        return list(reversed(self.lines))

    def listed(self, name):
        """Is `name` a line in MO2's list, a mod or a separator?"""
        return name in self.names or name in self.separators

    def files(self, name):
        if name not in self._files:
            self._files[name] = mod_files(name)
        return self._files[name]

    def match(self, name):
        """(the mod as MO2 names it, []) or (None, close names)."""
        if name in self.names:
            return name, []
        low = {n.lower(): n for n in self.names}
        if name.strip().lower() in low:
            return low[name.strip().lower()], []
        return None, difflib.get_close_matches(name, self.names, n=5, cutoff=0.5)


def separator_label(name):
    return name[:-len("_separator")] if name.endswith("_separator") else name


def placed(inst, toggle):
    """MO2's list, highest priority first, as play.bat will leave it: each mod on the
    calendar moved just above its anchor in modlist.txt, which in MO2's left pane is just
    below it. The same moves season.py makes, so the window can say who wins a file."""
    body = [n for n, _, _ in inst.lines]
    for name, c in toggle.items():
        above = c.get("above")
        if name not in body or above not in body:
            continue
        i, ref = body.index(name), body.index(above)
        if i > ref:
            body.pop(i)
            body.insert(body.index(above), name)
    return {n: i for i, n in enumerate(body)}


def loops(toggle, name, above):
    """Would `name` above `above` close a loop of anchors? The chain of mods `above` is
    itself placed above, back to `name`, when it would."""
    chain, cur = [name], above
    while cur in toggle and cur not in chain:
        chain.append(cur)
        cur = toggle[cur].get("above")
    return chain + [cur] if cur == name else None


def overlaps(inst, name):
    """[(mod, files shared)] for every other mod that ships any of the same files, in
    priority order."""
    mine = inst.files(name)
    out = []
    for other in inst.names:
        if other != name:
            n = len(mine & inst.files(other)) if mine else 0
            if n:
                out.append((other, n))
    return out


def anchor_for(inst, name, when, toggle, cal=None):
    """(anchor, reason, rivals) for making `name` seasonal, on in `when`.

    The anchor - the mod it wins over - is the highest enabled mod that ships any of the
    same files: just above it in modlist.txt, `name` wins over every mod it shares files
    with. Other seasonal mods are left out, because which of two seasonal mods should win
    is the player's call; the ones on at a time `name` is on too come back as rivals,
    [(mod, files shared, when both are on)]. With `cal`, that is worked out from its dates,
    so a season of the player's own meets the season it falls in; without, by name alone.
    With nothing to win over, the anchor is the mod just under `name`, so it stays where
    it is."""
    mine = inst.files(name)
    others = set(toggle) - {name}
    skip = others | {name, season.SOUND_MOD}
    rivals = []
    for other in inst.names:
        if other in others:
            theirs = periods_of(toggle[other])
            both = (cal.together(when, theirs) if cal is not None
                    else set(when) & set(theirs))
            n = len(mine & inst.files(other)) if both and mine else 0
            if n:
                rivals.append((other, n, sorted(both, key=order_key)))
    for other, on in inst.order:
        if on and other not in skip and mine:
            n = len(mine & inst.files(other))
            if n:
                # translators: why a mod wins over the one it does; said after that one's name
                return other, ngettext("ships %d of the same files",
                                       "ships %d of the same files", n) % n, rivals
    i = inst.names.index(name) if name in inst.names else len(inst.names)
    below = [o for o, on in inst.order[i + 1:] if on and o not in skip]
    if below:
        return below[0], _("nothing else ships its files, so it stays where it is"), rivals
    above = [o for o, on in reversed(inst.order[:i]) if on and o not in skip]
    if above:
        return above[0], _("nothing else ships its files"), rivals
    # translators: why no mod can be picked for a mod to win over
    return None, _("no other mod is enabled"), rivals


# --- periods and dates -----------------------------------------------------------------

def order_key(name):
    """Calendar order: the seasons as MCM lists them, then everything else by name."""
    return (season.SEASONS.index(name), "") if name in season.SEASONS else (99, name)


def periods_of(cfg):
    """The names a TOGGLE_MODS entry is scoped to, read the way season.py reads them, and
    forgiving the usual mistakes: ("summer,spring") is taken as the two seasons it means."""
    raw = cfg.get("when", cfg.get("seasons")) if isinstance(cfg, dict) else None
    if isinstance(raw, str):
        return [p.strip() for p in raw.split(",") if p.strip()]
    if isinstance(raw, (list, tuple)):
        return [str(p) for p in raw]
    return []


def resolve(name, known, names=None):
    """A season, event or weather name as the config spells it, from what someone typed, or
    None. A name the config has wins over a season's other name, and case does not count.
    With `names`, a season can also be given by the player's own name for it."""
    n = name.strip()
    if n in known:
        return n
    low = {k.lower(): k for k in known}
    if n.lower() in low:
        return low[n.lower()]
    alias = ALIASES.get(n.lower(), n.lower().replace(" ", "_"))
    hit = alias if alias in known else low.get(alias)
    if hit or not names:
        return hit
    return next((s for s, v in names.items() if s in known and v.casefold() == n.casefold()),
                None)


DAY = re.compile(r"^\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*$", re.ASCII)


def parse_day(text):
    """(month, day) from "12-24", "12/24" or "12.24", or None. Only the digits 0-9 count."""
    m = DAY.match(text or "")
    if not m:
        return None
    mo, d = int(m.group(1)), int(m.group(2))
    return (mo, d) if 1 <= mo <= 12 and 1 <= d <= DAYS[mo - 1] else None


def day_text(md):
    return lang.day(md[0], md[1])


def window_text(win):
    """An event in words: its dates, or its rule."""
    return season.event_text(win)


def norm_event(spec):
    """An event as the tool keeps it: a window as ((m, d), (m, d)); a rule as a dict of
    tuples. Lists from a preset or a hand-written file come out the same."""
    if isinstance(spec, (tuple, list)):
        return (tuple(spec[0]), tuple(spec[1]))
    out = {}
    for k in season.EVENT_KEYS:
        if k in spec:
            v = spec[k]
            out[k] = (tuple(v[0]), tuple(v[1])) if k == "within" else tuple(v)
    return out


def norm_spell(spec):
    """A spell as the tool keeps it: "in" a tuple, "days" (fewest, most), "as" None when it
    brings no season."""
    start = spec.get("in")
    lo, hi = season.spell_days(spec)
    return {"in": (start,) if isinstance(start, str) else tuple(start),
            "chance": spec["chance"], "days": (lo, hi), "as": spec.get("as")}


def spell_text(name, spec):
    spec = norm_spell(spec)
    return ["%s: {\"in\": %s, \"chance\": %s, \"days\": %s, \"as\": %s}," % (
        _q(name), literal(spec["in"]), literal(spec["chance"]), literal(spec["days"]),
        literal(spec["as"]))]


def spell_json(spec):
    spec = norm_spell(spec)
    return {"in": list(spec["in"]), "chance": spec["chance"], "days": list(spec["days"]),
            "as": spec["as"]}


def event_json(spec):
    """An event for a preset file: lists where the config has tuples."""
    if isinstance(spec, (tuple, list)):
        return [list(spec[0]), list(spec[1])]
    return {k: ([list(v[0]), list(v[1])] if k == "within" else list(v))
            for k, v in spec.items()}


# what people type for the parts of a rule
WEEKDAY_WORDS = {"weekend": ("sat", "sun"), "weekends": ("sat", "sun"),
                 "workdays": ("mon", "tue", "wed", "thu", "fri"),
                 "weekdays": ("mon", "tue", "wed", "thu", "fri")}
WEEK_WORDS = {"first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5, "last": -1}


DAY_NAMES = {"monday": "mon", "tuesday": "tue", "wednesday": "wed", "thursday": "thu",
             "friday": "fri", "saturday": "sat", "sunday": "sun"}


def parse_weekdays(words):
    """("sat", "sun") from ["Saturday", "sun"] or ["weekends"]; None when a word is no day."""
    out = set()
    for w in words:
        w = w.strip().lower()
        if w in WEEKDAY_WORDS:
            out |= set(WEEKDAY_WORDS[w])
            continue
        if w.endswith("s") and w[:-1] in DAY_NAMES:         # "fridays"
            w = w[:-1]
        if w in season.WEEKDAYS:
            out.add(w)
        elif w in DAY_NAMES:
            out.add(DAY_NAMES[w])
        else:
            return None
    return tuple(d for d in season.WEEKDAYS if d in out) or None


def parse_month_days(words):
    """(1, 15, -1) from ["1", "15", "last"]; None when a word is no day of the month."""
    out = []
    for w in words:
        w = w.strip().lower()
        if w == "last":
            out.append(-1)
        elif re.match(r"^-?\d{1,2}$", w, re.ASCII) and 1 <= abs(int(w)) <= 31:
            out.append(int(w))
        else:
            return None
    return tuple(out) or None


def parse_weeks(words):
    """(1, -1) from ["first", "last"] or ["1", "-1"]; None otherwise."""
    out = []
    for w in words:
        w = w.strip().lower()
        if w in WEEK_WORDS:
            out.append(WEEK_WORDS[w])
        elif re.match(r"^-?[1-5]$", w, re.ASCII):
            out.append(int(w))
        else:
            return None
    return tuple(out) or None


def parse_months(words):
    """(12, 1, 2) from ["dec", "January", "2"]; None when a word is no month."""
    names = [m.lower() for m in MONTHS]
    full = ("january february march april may june july august september october "
            "november december").split()
    out = []
    for w in words:
        w = w.strip().lower()
        if w in names:
            out.append(names.index(w) + 1)
        elif w in full:
            out.append(full.index(w) + 1)
        elif re.match(r"^\d{1,2}$", w, re.ASCII) and 1 <= int(w) <= 12:
            out.append(int(w))
        else:
            return None
    return tuple(out) or None


def norm_place(place):
    """A WEATHER_PLACE as the tool writes it: the name trimmed, degrees to four places."""
    return {"name": place["name"].strip(), "lat": round(float(place["lat"]), 4),
            "lon": round(float(place["lon"]), 4)}


place_text = season.place_words
DEFAULT_PLACE = season.DEFAULT_PLACE


def polesia():
    """{season: (month, day)}: the default calendar, all six on."""
    return {s: (m, d) for s, m, d in season.PHENO}


def meteorological():
    return {s: (m, d) for s, m, d in season.MET}


def season_windows(dates=None):
    """{season: "Apr 15 - May 19"} for each season on in `dates`, {season: (month, day)};
    Polesia's by default."""
    starts = sorted((m, d, s) for s, (m, d) in (dates or polesia()).items())
    out = {}
    for i, (m, d, s) in enumerate(starts):
        nm, nd, _ = starts[(i + 1) % len(starts)]
        nd -= 1
        if nd == 0:
            nm = nm - 1 or 12
            nd = DAYS[nm - 1] if nm != 2 else 28
        out[s] = "%s - %s" % (day_text((m, d)), day_text((nm, nd)))
    return out


# --- the config file -------------------------------------------------------------------

def _char_col(line, byte_col):
    """ast columns count UTF-8 bytes; this is the character index in `line`."""
    return len(line.encode("utf-8")[:byte_col].decode("utf-8", "ignore"))


def _q(s):
    return json.dumps(s, ensure_ascii=False)


def literal(v):
    """A config value as Python source: dates as tuples, folder lists as lists."""
    if isinstance(v, str):
        return _q(v)
    if isinstance(v, tuple):
        return "(%s%s)" % (", ".join(literal(x) for x in v), "," if len(v) == 1 else "")
    if isinstance(v, list):
        return "[%s]" % ", ".join(literal(x) for x in v)
    if isinstance(v, dict):
        return "{%s}" % ", ".join("%s: %s" % (literal(k), literal(x)) for k, x in v.items())
    return repr(v)


def entry_text(name, when, above, extra=()):
    """A TOGGLE_MODS entry as the tool writes it, unindented. `extra` is any other key the
    entry had, kept as it was."""
    w = ('(%s,)' % _q(when[0])) if len(when) == 1 else "(%s)" % ", ".join(_q(p) for p in when)
    return (["%s: {" % _q(name), '    "when": %s,' % w, '    "above": %s,' % _q(above)]
            + ["    %s: %s," % (literal(k), literal(v)) for k, v in extra] + ["},"])


def event_text(name, spec):
    """An EVENTS entry as the tool writes it: a window, or a rule."""
    spec = norm_event(spec)
    if isinstance(spec, tuple):
        (a, b), (c, d) = spec
        return ["%s: ((%d, %d), (%d, %d))," % (_q(name), a, b, c, d)]
    return ["%s: %s," % (_q(name), literal(spec))]


def start_text(name, md):
    return ["%s: (%d, %d)," % (_q(name), md[0], md[1])]


def name_text(key, name):
    return ["%s: %s," % (_q(key), _q(name))]


def layout_text(name, cfg):
    return (["%s: {" % _q(name), '    "archive": %s,' % _q(cfg["archive"]),
             '    "options": {']
            + ["        %s: %s," % (_q(s), literal(list(f))) for s, f in cfg["options"].items()]
            + ["    },", "},"])


def _assignments(tree, var):
    """Top-level statements that set `var`: plain assignments, and annotated ones with a
    value."""
    out = []
    for n in tree.body:
        if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == var
                                             for t in n.targets):
            out.append(n)
        elif (isinstance(n, ast.AnnAssign) and n.value is not None
              and isinstance(n.target, ast.Name) and n.target.id == var):
            out.append(n)
    return out


def _is_empty_literal(node):
    v = node.value
    return (isinstance(v, ast.Dict) and not v.keys) or (
        isinstance(v, ast.Constant) and v.value is None)


def _comments(lines):
    """Whether any of `lines` holds a comment (a # in a quoted name counts too)."""
    return any("#" in l for l in lines)


def _trailing(lines, node):
    """What follows the statement on its last line: a comment, or nothing."""
    last = lines[node.end_lineno - 1]
    return last[_char_col(last, node.end_col_offset):]


def _drop_comma(line):
    """A line holding only the comma after an entry, which the tool puts on the entry's
    own line instead: it goes, keeping any comment on it. None drops the line."""
    s = line.strip()
    if not s.startswith(","):
        return line
    rest = s[1:].strip()
    if not rest:
        return None
    return line[:len(line) - len(line.lstrip())] + rest if rest.startswith("#") else line


def _entries(lines, node):
    """How the dict literal in `node` is laid out, when it is one entry per block of lines:
    ({key: (lines above it, its own lines, indent)}, keys in order, the tail between the
    last entry and the closing brace). None for any other layout, which is rewritten whole.
    """
    d = node.value
    if not isinstance(d, ast.Dict) or not hasattr(node, "end_lineno"):
        return None
    have, order, prev = {}, [], node.lineno
    for k, v in zip(d.keys, d.values):
        if not (isinstance(k, ast.Constant) and isinstance(k.value, str)) or k.lineno <= prev:
            return None
        code = lines[k.lineno - 1:v.end_lineno]
        # a comma at the start of the key's own line belongs to the entry before, which
        # gets one of its own below
        head = code[0]
        if head.lstrip().startswith(","):
            i = head.index(",")
            code[0] = head[:i] + head[i + 1:].lstrip(" ")
        col = _char_col(lines[v.end_lineno - 1], v.end_col_offset)
        col -= len(lines[v.end_lineno - 1]) - len(code[-1])
        after = code[-1][col:].strip()
        if not after.startswith(","):
            if after and not after.startswith("#"):
                return None
            code[-1] = code[-1][:col] + "," + code[-1][col:]    # it may not stay last
        first = code[0]
        above = [l for l in (_drop_comma(x) for x in lines[prev:k.lineno - 1]) if l is not None]
        have[k.value] = (above, code, first[:len(first) - len(first.lstrip())])
        order.append(k.value)
        prev = v.end_lineno
    if order and node.end_lineno <= prev:
        return None
    tail = [l for l in (_drop_comma(x) for x in lines[prev:node.end_lineno - 1])
            if l is not None]
    return have, order, tail


def splice(text, var, plan):
    """`text` with the dict assigned to `var` rewritten to `plan`, [(key, lines, keep)].
    keep=True uses the file's own text for that key where it has one; otherwise `lines`
    are written. Entries keep the file's order, new ones go at the end, and a key the file
    has and `plan` lacks is dropped - but not the comments above it, which may be about
    the entries around it. Returns (text, whether every comment in the table was kept)."""
    lines = text.split("\n")
    nodes = _assignments(ast.parse(text), var)
    fresh = ["%s = {" % var] + ["    " + l for _, ls, _ in plan for l in ls] + ["}"]
    if not nodes:
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines + [""] + fresh + [""]), True
    node = nodes[-1]
    old = lines[node.lineno - 1:node.end_lineno]
    laid = _entries(lines, node)
    if laid is not None and not laid[1]:
        if not plan:
            return text, True                   # empty, and staying empty: as written
        if node.end_lineno > node.lineno:
            # an empty table over several lines: what sits inside it (a commented-out
            # entry, say) and the comment on its first line stay
            body = ["    " + l for _, ls, _ in plan for l in ls]
            lines[node.lineno - 1:node.end_lineno] = [old[0]] + body + laid[2] + [old[-1]]
            return "\n".join(lines), True
        # "EVENTS = {}  # none yet": the note stays on the table's first line
        fresh[0] += _trailing(lines, node)
        lines[node.lineno - 1:node.end_lineno] = fresh
        return "\n".join(lines), True
    if laid is None:
        # not one entry to a block of lines: rewritten whole, keeping a trailing comment
        tail = _trailing(lines, node)
        fresh[-1] += tail
        kept = not _comments(old[:-1] + [old[-1][:len(old[-1]) - len(tail)]])
        lines[node.lineno - 1:node.end_lineno] = fresh
        return "\n".join(lines), kept
    have, order, tail = laid
    ind = have[order[0]][2]
    planned = {key: (ls, keep) for key, ls, keep in plan}
    body, kept = [], True
    for key in order:
        above, code, own = have[key]
        body += above
        if key in planned:
            ls, keep = planned[key]
            if keep:
                body += code
            else:
                body += [own + l for l in ls]
                kept = kept and not _comments(code)
    for key, ls, keep in plan:
        if key not in have:
            body += [ind + l for l in ls]
    lines[node.lineno - 1:node.end_lineno] = [old[0]] + body + tail + [old[-1]]
    return "\n".join(lines), kept


def set_value(text, var, value):
    """`text` with `var` set to the literal `value`: its last assignment replaced, or a new
    line at the end. Returns (text, whether every comment was kept)."""
    lines = text.split("\n")
    nodes = _assignments(ast.parse(text), var)
    line = "%s = %s" % (var, literal(value))
    if not nodes:
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines + ["", line, ""]), True
    node = nodes[-1]
    old = lines[node.lineno - 1:node.end_lineno]
    tail = _trailing(lines, node)
    lines[node.lineno - 1:node.end_lineno] = [line + tail]
    return "\n".join(lines), not _comments(old[:-1] + [old[-1][:len(old[-1]) - len(tail)]])


def set_none(text, var):
    """`text` with the last assignment to `var` replaced by `var = None`."""
    return set_value(text, var, None)[0]


def _order(new, kept):
    """Keys of `new` in the file's order where the file has them, then by season."""
    kept = kept or {}
    return ([k for k in kept if k in new]
            + sorted((k for k in new if k not in kept), key=order_key))


def _stamp():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _writable(path):
    """Make our own backup file writable again, if something set it read-only."""
    if os.path.isfile(path) and not os.access(path, os.W_OK):
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)


class Calendar(object):
    """seasons_config.py as the tool edits it.

    `toggle` maps each mod on the calendar to {"when": [...], "above": "...", "extra": [...]},
    `events` each event to ((m, d), (m, d)), `own` each season of the player's own to its
    first and last day, `dates` each season that is on to the (m, d) it starts, `names`
    each renamed season to its name, and `place` is where the real weather comes from,
    {"name", "lat", "lon"}, or None for Chornobyl. `periods`, `layout` and
    `sound_src` change only when a preset is loaded. `error` is set, as lines, when the
    file can't be read or edited safely; `problems` lists what season.py would refuse in
    it; `fixes` what saving from the tool repairs, and `fixed_tables` the tables those
    repairs are in, for code to check: the sentences are in the player's language."""

    def __init__(self, path=CONFIG):
        self.path = path
        self.exists = os.path.isfile(path)
        self.error, self.problems, self.fixes = None, [], []
        self.fixed_tables = set()
        self.wrote = False
        self.toggle, self.events = {}, {}
        self.periods, self.layout, self.sound_src = {}, {}, None
        self._kept_toggle, self._kept_events = {}, {}
        self._kept_periods, self._kept_layout, self._kept_sound = {}, {}, None
        self._bad_events = {}           # events the rules refuse, kept as written
        self._kept_bad = set()
        self.own, self._kept_own = {}, {}
        self._bad_own, self._kept_bad_own = {}, set()
        self.spells, self._kept_spells = {}, {}
        self._bad_spells, self._kept_bad_spells = {}, set()
        self.dates, self._kept_dates = polesia(), None     # None: the file has none
        self.calendar_bad, self._replace_calendar = [], False
        self.names, self._kept_names = {}, {}
        self.names_bad, self._replace_names = [], False
        self.place, self._kept_place = None, None
        self.place_bad, self._replace_place = [], False
        self.encoding, self.bom, self.nl = "utf-8", False, "\n"
        self.original, self.text = None, ""
        if self._read():
            self._load()

    # loading

    def _read(self):
        if not self.exists:
            self.text = TEMPLATE
            return True
        try:
            data = open(self.path, "rb").read()
        except OSError as e:
            self.error = [_("seasons_config.py can't be read: %s") % e]
            return False
        self.original = data
        if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
            self.error = [_("seasons_config.py is saved as UTF-16 (\"Unicode\" in Notepad). "
                            "Save it as UTF-8: in Notepad, File > Save as, set Encoding to "
                            "UTF-8, then Save.")]
            return False
        try:
            enc = tokenize.detect_encoding(io.BytesIO(data).readline)[0]
            self.bom = data.startswith(codecs.BOM_UTF8)
            text = data.decode(enc)
        except (SyntaxError, UnicodeDecodeError, LookupError) as e:
            self.error = [season.encoding_problem(e)]
            return False
        if text.startswith("﻿"):
            text = text[1:]
        self.encoding = "utf-8" if enc == "utf-8-sig" else enc
        self.nl = "\r\n" if "\r\n" in text else ("\r" if "\r" in text else "\n")
        self.text = text.replace("\r\n", "\n").replace("\r", "\n")
        return True

    def _load(self):
        try:
            tree = ast.parse(self.text)
        except SyntaxError as e:
            self.error = season._config_error(e)
            return
        lines = self.text.split("\n")
        # a table the tool would have to cut out of a line it shares, or out of a
        # statement that sets something else as well
        for var in season.CONFIG_NAMES:
            for n in _assignments(tree, var):
                before = lines[n.lineno - 1][:_char_col(lines[n.lineno - 1], n.col_offset)]
                after = _trailing(lines, n).strip()
                if before.strip() or (after and not after.startswith("#")):
                    self.error = [_("line %(line)d holds %(table)s and another statement. "
                                    "Give %(table)s a line of its own so configure.bat can "
                                    "edit it.") % {"line": n.lineno, "table": var}]
                    return
                if isinstance(n, ast.Assign) and len(n.targets) > 1:
                    self.error = [_("line %(line)d sets %(table)s and another name at once. "
                                    "Give %(table)s a line of its own so configure.bat can "
                                    "edit it.") % {"line": n.lineno, "table": var}]
                    return
        # An empty table set as well as a real one: the template's own TOGGLE_MODS = {}
        # under an entry typed above it throws the real one away. It is dropped on save.
        drop = []
        for var in season.CONFIG_NAMES:
            nodes = _assignments(tree, var)
            if len(nodes) < 2:
                continue
            full = [n for n in nodes if not _is_empty_literal(n)]
            if len(full) > 1:
                at = [str(n.lineno) for n in full]
                # translators: %(lines)s is two line numbers or more, as in "3, 5 and 9"
                self.error = [_("%(table)s is set on lines %(lines)s, and more than one of "
                                "them has entries. Merge them into one by hand.")
                              % {"table": var, "lines": lang.and_list(at)}]
                return
            keep = full[0] if full else nodes[-1]
            for n in nodes:
                if n is keep:
                    continue
                drop.append((n.lineno, n.end_lineno))
                self.fixed_tables.add(var)
                said = {"line": n.lineno, "table": var, "kept": keep.lineno}
                if n.lineno > keep.lineno:
                    self.fixes.append(_("line %(line)d sets %(table)s again, to nothing, which "
                                        "throws away the one on line %(kept)d; saving removes "
                                        "line %(line)d") % said)
                else:
                    self.fixes.append(_("line %(line)d sets %(table)s to nothing before line "
                                        "%(kept)d sets it; saving removes line %(line)d")
                                      % said)
        for a, b in sorted(drop, reverse=True):
            del lines[a - 1:b]
        self.text = "\n".join(lines)

        ns = {"__file__": self.path}
        try:
            exec(compile(self.text, self.path, "exec"), ns)
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            self.error = season._config_error(e)
            return
        # A table changed by the lines below it - TOGGLE_MODS["x"] = ..., .update(), an
        # if - is not what its literal says, and editing the literal would be undone.
        tree = ast.parse(self.text)
        for var in season.CONFIG_NAMES:
            nodes = _assignments(tree, var)
            if not nodes:
                if var in ns:
                    self.error = [_("%(table)s is set in a way the tool can't edit. Write it "
                                    "as one plain line of its own: %(table)s = {...}")
                                  % {"table": var}]
                    return
                continue
            try:
                written = ast.literal_eval(nodes[-1].value)
            except (ValueError, SyntaxError, TypeError):
                continue            # dict(...) or a name: rewritten whole when it changes
            if written != ns.get(var):
                self.error = [_("%(table)s is changed after its table on line %(line)d, which "
                                "the tool can't edit. Move those entries into the table.")
                              % {"table": var, "line": nodes[-1].lineno}]
                return

        toggle, events = ns.get("TOGGLE_MODS", {}), ns.get("EVENTS", {})
        own, spells = ns.get("OWN_SEASONS", {}), ns.get("SPELLS", {})
        if toggle is None:
            toggle = {}
        if events is None:
            events = {}
        if own is None:
            own = {}
        if spells is None:
            spells = {}
        for var, v in (("TOGGLE_MODS", toggle), ("EVENTS", events), ("OWN_SEASONS", own),
                       ("SPELLS", spells)):
            if not isinstance(v, dict):
                self.error = [_("%s must be a table, {...}.") % var]
                return
        odd = [k for k in list(toggle) + list(events) + list(own) + list(spells)
               if not isinstance(k, str)]
        if odd:
            self.error = [_("%r in TOGGLE_MODS, EVENTS, OWN_SEASONS or SPELLS is not a name "
                            "in quotes. Put it in quotes, or take it out.") % (odd[0],)]
            return
        self.layout = ns.get("LAYOUT", {}) or {}
        self.sound_src = ns.get("SOUND_SRC")
        self.periods = ns.get("PERIODS", {}) or {}
        self._kept_layout, self._kept_sound = self.layout, self.sound_src
        self._kept_periods = self.periods
        calendar, names = ns.get("CALENDAR"), ns.get("NAMES")
        self.problems = season.config_problems(toggle, self.layout, self.sound_src,
                                               self.periods, events, calendar, names, own=own,
                                               spells=spells)

        for name, cfg in toggle.items():
            when = periods_of(cfg)
            above = cfg.get("above", "") if isinstance(cfg, dict) else ""
            extra = ([(k, v) for k, v in cfg.items()
                      if k not in ("when", "seasons", "above")] if isinstance(cfg, dict)
                     else [])
            self.toggle[name] = {"when": when, "above": above if isinstance(above, str) else "",
                                 "extra": extra}
            raw = cfg.get("when", cfg.get("seasons")) if isinstance(cfg, dict) else None
            both = isinstance(cfg, dict) and "when" in cfg and "seasons" in cfg
            if (isinstance(raw, (list, tuple)) and list(raw) == when and isinstance(above, str)
                    and not both):
                self._kept_toggle[name] = (frozenset(when), above)
            elif not season.config_problems(
                    {name: {"when": tuple(when), "above": self.toggle[name]["above"]}}, {},
                    None, self.periods,
                    {n: s for n, s in events.items() if not season.event_problems(n, s)},
                    own={n: w for n, w in own.items() if not season.own_problems({n: w})},
                    spells={n: s for n, s in spells.items()
                            if not season.spell_problems({n: s}, own=own)}):
                # only a repair saving really makes; one it would refuse stays a problem
                self.fixes.append(_("%s: saving rewrites this entry in the right shape")
                                  % name)
                self.fixed_tables.add("TOGGLE_MODS")
        for name, spec in events.items():
            if not season.event_problems(name, spec):
                self.events[name] = norm_event(spec)
                self._kept_events[name] = norm_event(spec)
            else:
                self._bad_events[name] = spec       # the rules name it; saving keeps it
                self._kept_bad.add(name)
        known_names = names if isinstance(names, dict) else {}
        for name, win in own.items():
            if not season.own_problems({name: win}, self.periods, events, known_names):
                self.own[name] = norm_event(win)
                self._kept_own[name] = norm_event(win)
            else:
                self._bad_own[name] = win           # as with events: kept as written
                self._kept_bad_own.add(name)
        on = ([s for s in calendar if s in season.SEASONS]
              if isinstance(calendar, dict) and calendar else list(season.SEASONS))
        for name, spec in spells.items():
            if not season.spell_problems({name: spec}, on, own, self.periods, events,
                                         known_names):
                self.spells[name] = norm_spell(spec)
                self._kept_spells[name] = norm_spell(spec)
            else:
                self._bad_spells[name] = spec
                self._kept_bad_spells.add(name)

        if calendar is not None:
            usable = ({s: tuple(md) for s, md in calendar.items()
                       if s in season.SEASONS and season._is_day(md)}
                      if isinstance(calendar, dict) else {})
            self.calendar_bad = season.calendar_problems(calendar)
            self.dates = dict(usable) if (usable or not self.calendar_bad) else polesia()
            self._kept_dates = dict(self.dates)
        if names is not None:
            self.names_bad = season.names_problems(names)
            self.names = ({s: v.strip() for s, v in names.items()
                           if s in season.SEASONS and isinstance(v, str) and v.strip()}
                          if isinstance(names, dict) else {})
            self._kept_names = dict(self.names)
        place = ns.get("WEATHER_PLACE")
        if place is not None:
            self.place_bad = season.place_problems(place)
            self.place = None if self.place_bad else norm_place(place)
            self._kept_place = self.place

    # what is on the calendar

    def known(self):
        """Every name a mod may be scoped to, in calendar order."""
        return (list(season.SEASONS) + sorted(self.periods) + self.own_order()
                + sorted(self.spells, key=str.casefold) + sorted(self.events)
                + list(season.WEATHER_NAMES))

    def own_order(self):
        """The player's own seasons, by the day each starts."""
        return sorted(self.own, key=lambda n: (self.own[n][0], n.casefold()))

    def days(self, name):
        """The days of a year (2026, which has no February 29) that `name` is on, by this
        calendar, as season.days_on counts them. None for a kind of weather, which can come
        any day."""
        return season.days_on(name, self.base, self.own, self.events, self.spells)

    def together(self, when, other):
        """The names in `when` or `other` that mark the times a mod on in `when` and one on
        in `other` are both on, as season.meet finds them."""
        return season.meet(when, other, self.days, set(season.SEASONS) | set(self.periods),
                           self.spells)

    def put_own(self, name, win, was=None):
        """Add a season of the player's own, or change one. `was` is the name it had, when
        it is renamed: the mods on in it are then on in the new name."""
        if was is not None and was != name:
            self.own.pop(was, None)
            self._bad_own.pop(was, None)
            for c in self.toggle.values():
                c["when"] = [name if p == was else p for p in c["when"]]
            # and the spells that can start in it start in the new name
            for s, spec in list(self.spells.items()):
                if was in spec["in"]:
                    self.spells[s] = dict(spec, **{"in": tuple(
                        name if p == was else p for p in spec["in"])})
        self._bad_own.pop(name, None)
        self.own[name] = norm_event(win)

    def base(self, day):
        """The season or period on `day` by this calendar, or None when it has neither."""
        starts = sorted([(md, s) for s, md in self.dates.items()]
                        + [(tuple(md), p) for p, md in self.periods.items()
                           if season._is_day(md)])
        now = starts[-1][1] if starts else None     # the year starts in the last to start
        for md, s in starts:
            if md <= (day.month, day.day):
                now = s
        return now

    def where(self, day):
        """What a spell can start in on `day` by this calendar: the season or period then,
        and the player's own seasons that cover it."""
        now = self.base(day)
        return ([now] if now else []) + [o for o, w in self.own.items()
                                         if season._in_window(day, *w)]

    def spells_on(self, day):
        """[(name, first day, last day)] for the spells this setup has running on `day`."""
        return season.spells_on(day, self.spells, self.where)

    def put_spell(self, name, spec, was=None):
        """Add a spell, or change one; `was` is the name it had, when it is renamed, and the
        mods on during it follow the new name."""
        if was is not None and was != name:
            self.spells.pop(was, None)
            self._bad_spells.pop(was, None)
            for c in self.toggle.values():
                c["when"] = [name if p == was else p for p in c["when"]]
        self._bad_spells.pop(name, None)
        self.spells[name] = norm_spell(spec)

    def take_spell(self, name):
        """Take a spell off, and off every mod on during it. A mod on in nothing else comes
        off the calendar too; those are returned."""
        self.spells.pop(name, None)
        self._bad_spells.pop(name, None)
        return self._drop_everywhere(name)

    def _drop_everywhere(self, name):
        gone = []
        for n, c in list(self.toggle.items()):
            if name in c["when"]:
                c["when"] = [p for p in c["when"] if p != name]
                if not c["when"]:
                    self.toggle.pop(n)
                    gone.append(n)
        return gone

    def take_own(self, name):
        """Take a season of the player's own off the calendar, and off every mod on in it.
        A mod on in nothing else comes off the calendar too; those are returned."""
        self.own.pop(name, None)
        self._bad_own.pop(name, None)
        gone = []
        # a spell that could start only in it has nowhere left to start, and goes too
        for s, spec in list(self.spells.items()):
            if name in spec["in"]:
                rest = tuple(p for p in spec["in"] if p != name)
                if rest:
                    self.spells[s] = dict(spec, **{"in": rest})
                else:
                    gone += self.take_spell(s)
        return self._drop_everywhere(name) + gone

    def spells_only_in(self, name):
        """The spells that can start in the player's own season `name` and nowhere else."""
        return [s for s, spec in self.spells.items() if tuple(spec["in"]) == (name,)]

    def put(self, name, when, above):
        known = self.known()
        extra = self.toggle.get(name, {}).get("extra", [])
        self.toggle[name] = {"when": sorted(set(when), key=lambda p: (
            known.index(p) if p in known else len(known), p)), "above": above, "extra": extra}

    def take(self, name):
        self.toggle.pop(name, None)

    def users_of(self, period):
        return [n for n, cfg in self.toggle.items() if period in cfg["when"]]

    def set_dates(self, dates):
        """The calendar as the player set it. It replaces a CALENDAR the file had that
        could not be used, even when the dates are the same."""
        if self.calendar_bad:
            self._replace_calendar = True
            self.calendar_bad = []
        self.dates = dict(dates)

    def set_names(self, names):
        """{season: name}. A name that is empty, or the usual one in any case - in English or
        in the player's language, as a window shows it - is none."""
        if self.names_bad:
            self._replace_names = True
            self.names_bad = []
        self.names = {s: v.strip() for s, v in names.items()
                      if isinstance(v, str) and v.strip()
                      and v.strip().casefold() not in (season.default_label(s).casefold(),
                                                        season.usual_name(s).casefold())}

    def set_place(self, place):
        """{name, lat, lon}, or None for Chornobyl. It replaces a WEATHER_PLACE the file had
        that could not be used."""
        if self.place_bad:
            self._replace_place = True
            self.place_bad = []
        self.place = norm_place(place) if place else None

    def place_changed(self):
        return self._replace_place or self.place != self._kept_place

    def custom(self):
        """Is the calendar anything but Polesia's, all six on?"""
        return self.dates != polesia()

    def dates_changed(self):
        return self._replace_calendar or self.dates != (
            polesia() if self._kept_dates is None else self._kept_dates)

    def names_changed(self):
        return self._replace_names or self.names != self._kept_names

    def dirty(self):
        return (self.fixes != [] or set(self.toggle) != set(self._kept_toggle)
                or any((frozenset(c["when"]), c["above"]) != self._kept_toggle.get(n)
                       for n, c in self.toggle.items())
                or self.events != self._kept_events or self.dates_changed()
                or set(self._bad_events) != self._kept_bad
                or self.own != self._kept_own or set(self._bad_own) != self._kept_bad_own
                or self.spells != self._kept_spells
                or set(self._bad_spells) != self._kept_bad_spells
                or self.names_changed() or self.place_changed()
                or self.periods != self._kept_periods
                or self.layout != self._kept_layout or self.sound_src != self._kept_sound)

    # writing

    def render(self):
        """The file as it would be saved, and whether every comment could be kept."""
        plan = [(n, entry_text(n, c["when"], c["above"], c.get("extra", ())),
                 self._kept_toggle.get(n) == (frozenset(c["when"]), c["above"]))
                for n, c in self.toggle.items()]
        text, kept = splice(self.text, "TOGGLE_MODS", plan)
        eplan = [(n, event_text(n, w), self._kept_events.get(n) == w)
                 for n, w in self.events.items()]
        eplan += [(n, ["%s: %s," % (_q(n), literal(w))], True)
                  for n, w in self._bad_events.items()]
        if eplan or _assignments(ast.parse(text), "EVENTS"):
            text, k = splice(text, "EVENTS", eplan)
            kept = kept and k
        oplan = [(n, event_text(n, w), self._kept_own.get(n) == w) for n, w in self.own.items()]
        oplan += [(n, ["%s: %s," % (_q(n), literal(w))], True)
                  for n, w in self._bad_own.items()]
        splan = [(n, spell_text(n, s), self._kept_spells.get(n) == s)
                 for n, s in self.spells.items()]
        splan += [(n, ["%s: %s," % (_q(n), literal(s))], True)
                  for n, s in self._bad_spells.items()]
        for var, head, plan in (("OWN_SEASONS", OWN_HEAD, oplan),
                                ("SPELLS", SPELLS_HEAD, splan)):
            if plan or _assignments(ast.parse(text), var):
                if not _assignments(ast.parse(text), var):
                    # a file from before it gets the table, with what it is
                    lines = text.rstrip("\n").split("\n")
                    text = "\n".join(lines + [""] + head + ["%s = {}" % var, ""])
                text, k = splice(text, var, plan)
                kept = kept and k
        if self.periods != self._kept_periods:
            text, k = splice(text, "PERIODS", [
                (n, start_text(n, md), self._kept_periods.get(n) == md)
                for n, md in self.periods.items()])
            kept = kept and k
        if self.layout != self._kept_layout:
            text, k = splice(text, "LAYOUT", [
                (n, layout_text(n, c), self._kept_layout.get(n) == c)
                for n, c in self.layout.items()])
            kept = kept and k
        if self.sound_src != self._kept_sound:
            text, k = set_value(text, "SOUND_SRC", self.sound_src)
            kept = kept and k
        if self.dates_changed():
            text, k = self._table(text, "CALENDAR", CALENDAR_HEAD, self.custom(), [
                (s, start_text(s, self.dates[s]), (self._kept_dates or {}).get(s) == self.dates[s])
                for s in _order(self.dates, self._kept_dates)])
            kept = kept and k
        if self.names_changed():
            text, k = self._table(text, "NAMES", NAMES_HEAD, bool(self.names), [
                (s, name_text(s, self.names[s]), self._kept_names.get(s) == self.names[s])
                for s in _order(self.names, self._kept_names)])
            kept = kept and k
        if self.place_changed():
            text, k = self._setting(text, "WEATHER_PLACE", PLACE_HEAD, self.place)
            kept = kept and k
        return text, kept

    @staticmethod
    def _table(text, var, head, wanted, plan):
        """A table the tool may add to a file: written with `plan`, or set to None."""
        have = _assignments(ast.parse(text), var)
        if wanted:
            if not have:
                lines = text.rstrip("\n").split("\n")
                text = "\n".join(lines + [""] + head + ["%s = None" % var, ""])
            return splice(text, var, plan)
        if have and not (isinstance(have[-1].value, ast.Constant)
                         and have[-1].value.value is None):
            return set_value(text, var, None)
        return text, True

    @staticmethod
    def _setting(text, var, head, value):
        """A single value the tool may add to a file: set where it is, or added at the end
        under `head` when the file has none. None where the file has none leaves it be."""
        if not _assignments(ast.parse(text), var):
            if value is None:
                return text, True
            lines = text.rstrip("\n").split("\n")
            return "\n".join(lines + [""] + head + ["%s = %s" % (var, literal(value)), ""]), True
        return set_value(text, var, value)

    def check(self, text):
        """What season.py would refuse in `text`, as sentences."""
        ns = {"__file__": self.path}
        try:
            exec(compile(text, self.path, "exec"), ns)
        except (Exception, SystemExit, KeyboardInterrupt) as e:
            return season._config_error(e)
        return season._set_twice(text) + season.config_problems(
            ns.get("TOGGLE_MODS", {}), ns.get("LAYOUT", {}), ns.get("SOUND_SRC"),
            ns.get("PERIODS", {}), ns.get("EVENTS", {}), ns.get("CALENDAR"),
            ns.get("NAMES"), ns.get("WEATHER_PLACE"), ns.get("OWN_SEASONS"), ns.get("SPELLS"))

    def _keepsake(self, why):
        """A dated copy of the file as it is, which no later save touches."""
        base = "%s.%s-%s" % (self.path, why, _stamp())
        dst, n = base + ".bak", 1
        while os.path.exists(dst):
            dst, n = "%s-%d.bak" % (base, n), n + 1
        shutil.copyfile(self.path, dst)
        return os.path.basename(dst)

    def save(self):
        """Write the file. Returns (saved, lines to show); `wrote` says afterwards whether
        anything was written, as the lines, in the player's language, can't."""
        self.wrote = False
        if self.error:
            return False, [_("seasons_config.py can't be edited here:")] + self.error
        if not self.dirty():
            return True, [_("Nothing to save.")]
        fixes = list(self.fixes)
        text, kept = self.render()
        problems = self.check(text)
        if problems:
            return False, ([_("Not saved, because play.bat would refuse the result:")]
                           + problems)
        try:
            data = text.replace("\n", self.nl).encode(self.encoding)
        except UnicodeEncodeError as e:
            return False, [_("Not saved: \"%(text)s\" can't be written in this file's encoding "
                             "(%(encoding)s). Delete the # coding line at the top of "
                             "seasons_config.py, save it as UTF-8 (Notepad: File > Save as, "
                             "Encoding: UTF-8), then try again.")
                           % {"text": e.object[e.start:e.end], "encoding": self.encoding}]
        # the file as it is now: if it changed since it was read - by hand, or a command
        # run while the window was open - writing would throw that change away
        try:
            now = open(self.path, "rb").read() if os.path.isfile(self.path) else None
        except OSError as e:
            return False, [_("Not saved: seasons_config.py can't be read: %s") % e]
        if now != self.original:
            return False, [_("Not saved: seasons_config.py has changed since it was read (by "
                             "hand, or by a configure command). Close configure.bat and open "
                             "it again, or run the command again, then redo your change.")]
        if now is not None and not os.access(self.path, os.W_OK):
            return False, [_("Not saved: seasons_config.py is read-only. Right-click it (in "
                             "_tools), choose Properties, uncheck Read-only, then save "
                             "again.")]
        notes = []
        try:
            if now is not None:
                bak = self.path + ".bak"
                _writable(bak)
                shutil.copyfile(self.path, bak)
                notes.append(_("The previous file is %s.") % os.path.basename(bak))
                if not kept:
                    notes.append(_("Comments inside the tables could not be kept, because of "
                                   "how they were laid out; %s has them, and no later save "
                                   "touches it.") % self._keepsake("before"))
            with open(self.path, "wb") as f:
                f.write((codecs.BOM_UTF8 if self.bom else b"") + data)
        except OSError as e:
            return False, [_("Not saved: %s. Close any program that has seasons_config.py "
                             "open, then try again.") % e]
        self.__init__(self.path)
        self.wrote = True
        return True, ([_("Saved %s.") % os.path.basename(self.path)] + notes
                      + ([_("Also fixed:")] + ["  " + f for f in fixes] if fixes else []))

    def start_over(self):
        """Replace a file that can't be read with a new, empty one. The old one is kept,
        dated, where no later save touches it; its name is returned."""
        kept = self._keepsake("unreadable") if self.exists else None
        with open(self.path, "wb") as f:
            f.write(TEMPLATE.replace("\n", self.nl if self.nl else "\n").encode("utf-8"))
        self.__init__(self.path)
        return kept


# --- presets -----------------------------------------------------------------------------
#
# A preset holds any of four parts of a setup. Loading replaces the parts chosen:
#   calendar  - CALENDAR and NAMES: when each season starts, which are on, their names
#   events    - OWN_SEASONS, EVENTS and PERIODS: what is added to the calendar
#   mods      - TOGGLE_MODS: the mods on the calendar, and when each is on
#   textures  - LAYOUT and SOUND_SRC: texture sets swapped from archives, the ambience mod
# A mod this install does not have is left out, and an anchor it does not have is worked
# out again, so a preset made on one install loads on another.

PRESETS = os.path.join(HERE, "presets")
PRESET_KEY = "seasons_of_the_zone_preset"
PARTS = ("calendar", "events", "mods", "textures")
PART_KEYS = {"calendar": ("calendar", "names"),
             "events": ("events", "periods", "own_seasons", "spells"),
             "mods": ("mods",), "textures": ("layout", "sound_src")}
# the parts in words, in English: _(PART_TEXT[p]) shows one in the player's language
PART_TEXT = {"calendar": N_("calendar and season names"),
             "events": N_("seasons of your own, spells, events and periods"),
             "mods": N_("seasonal mods"), "textures": N_("texture sets and ambient sound")}
PRESET_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.,'()-]{0,39}$")


def preset_files():
    """{name: path} for every preset, by name."""
    try:
        files = sorted(f for f in os.listdir(PRESETS) if f.lower().endswith(".json"))
    except OSError:
        return {}
    return {f[:-5]: os.path.join(PRESETS, f) for f in files}


def _days(v):
    return tuple(v) if isinstance(v, list) else v


def read_preset(path):
    """(preset, problems): the preset's parts, with dates as tuples, and what is wrong
    with it. A preset with problems is not loaded."""
    try:
        data = json.loads(io.open(path, encoding="utf-8-sig").read())
    except (OSError, ValueError) as e:
        return None, [_("It can't be read (%s). Check it is valid JSON, or delete it from "
                        "_tools\\presets.") % e]
    if not isinstance(data, dict) or data.get(PRESET_KEY) != 1:
        return None, [_("It is not a Seasons of the Zone preset.")]
    out = {"about": data.get("about") if isinstance(data.get("about"), str) else "",
           "shipped": data.get("shipped") is True}
    problems = []
    if "calendar" in data:
        cal = data["calendar"]
        if cal is not None:
            cal = ({s: _days(md) for s, md in cal.items()} if isinstance(cal, dict) else cal)
            problems += season.calendar_problems(cal)
        out["calendar"] = cal
    if "names" in data:
        names = data["names"]
        if names is not None:
            problems += season.names_problems(names)
        out["names"] = names or {}
    events = data.get("events", {})
    periods = data.get("periods", {})
    own = data.get("own_seasons", {})
    spells = data.get("spells", {})
    if isinstance(events, dict):
        events = {n: norm_event(w) if not season.event_problems(n, w) else w
                  for n, w in events.items()}
    if isinstance(periods, dict):
        periods = {n: _days(md) for n, md in periods.items()}
    if isinstance(own, dict):
        own = {n: norm_event(w) if not season.own_problems({n: w}) else w
               for n, w in own.items()}
    if isinstance(spells, dict):
        spells = {n: norm_spell(s) if not season.spell_problems(
            {n: s}, own=own if isinstance(own, dict) else {}) else s for n, s in spells.items()}
    # a spell is checked against the calendar that comes with it, when one does
    dates = out.get("calendar")
    dates = dates if isinstance(dates, dict) and dates else None
    if any(k in data for k in PART_KEYS["events"]):
        problems += season.config_problems({}, {}, None, periods, events, own=own,
                                           spells=spells, calendar=dates)
        out["events"], out["periods"], out["own_seasons"] = events, periods, own
        out["spells"] = spells
    # what a preset of the mods alone brings for them to be on in
    needs = data.get("needs", {})
    if not isinstance(needs, dict) or not all(isinstance(needs.get(k, {}), dict)
                                              for k in PART_KEYS["events"]):
        problems.append("needs: " + _("it must be a table of own_seasons, spells, events "
                                      "and periods."))
        needs = {}
    needs = {"own_seasons": {n: norm_event(w) if not season.own_problems({n: w}) else w
                             for n, w in needs.get("own_seasons", {}).items()},
             "spells": {n: norm_spell(s) if not season.spell_problems({n: s}) else s
                        for n, s in needs.get("spells", {}).items()},
             "events": {n: norm_event(w) if not season.event_problems(n, w) else w
                        for n, w in needs.get("events", {}).items()},
             "periods": {n: _days(md) for n, md in needs.get("periods", {}).items()}}
    if any(needs.values()):
        problems += season.config_problems({}, {}, None, needs["periods"], needs["events"],
                                           own=needs["own_seasons"], spells=needs["spells"],
                                           calendar=dates)
        out["needs"] = needs

    def both(mine, key):
        table = dict(needs[key])
        table.update(mine if isinstance(mine, dict) else {})
        return table
    if "mods" in data:
        mods = data["mods"]
        if isinstance(mods, dict):
            mods = {n: dict(c, when=tuple(c["when"])) if isinstance(c, dict)
                    and isinstance(c.get("when"), list) else c for n, c in mods.items()}
        problems += [p for p in season.config_problems(
            mods, {}, None, both(periods, "periods"), both(events, "events"),
            own=both(own, "own_seasons"), spells=both(spells, "spells"))
            if p.startswith("TOGGLE_MODS")]
        out["mods"] = mods
    if "layout" in data or "sound_src" in data:
        layout = data.get("layout", {})
        problems += [p for p in season.config_problems(
            {}, layout, data.get("sound_src"), {}, {}) if not p.startswith(("PERIODS",
                                                                              "EVENTS"))]
        out["layout"], out["sound_src"] = layout, data.get("sound_src")
    return out, problems


def preset_parts(preset):
    return [p for p in PARTS if any(k in preset for k in PART_KEYS[p])]


def parts_with_content(cal):
    """The parts of a setup worth keeping in a preset: those with something in them. An
    empty part would, loaded elsewhere, empty that part of someone else's setup."""
    out = [p for p, has in (("calendar", cal.custom() or cal.names),
                            ("events", cal.events or cal.periods or cal.own or cal.spells),
                            ("mods", cal.toggle),
                            ("textures", cal.layout or cal.sound_src)) if has]
    return out or ["calendar"]


def preset_from(cal, parts):
    """A preset of `parts` of the setup `cal` holds, as JSON-ready data."""
    out = {PRESET_KEY: 1}
    if "calendar" in parts:
        out["calendar"] = ({s: list(md) for s, md in cal.dates.items()} if cal.custom()
                           else None)
        out["names"] = dict(cal.names)
    if "events" in parts:
        out["own_seasons"] = {n: event_json(w) for n, w in cal.own.items()}
        out["spells"] = {n: spell_json(s) for n, s in cal.spells.items()}
        out["events"] = {n: event_json(w) for n, w in cal.events.items()}
        out["periods"] = {n: list(md) for n, md in cal.periods.items()}
    if "mods" in parts:
        out["mods"] = {n: {"when": list(c["when"]), "above": c["above"]}
                       for n, c in cal.toggle.items()}
        if "events" not in parts:
            need = {k: v for k, v in needed(cal).items() if v}
            if need:
                out["needs"] = need
    if "textures" in parts:
        out["layout"] = {n: {"archive": c["archive"],
                             "options": {s: list(f) for s, f in c["options"].items()}}
                         for n, c in cal.layout.items()}
        out["sound_src"] = cal.sound_src
    return out


def needed(cal):
    """What the mods on the calendar are on in, beyond the seasons and the weather: each
    season of one's own, spell, event and period they name, and the seasons of one's own
    those spells start in. A preset of the mods alone carries these, to load elsewhere."""
    names = {p for c in cal.toggle.values() for p in c["when"]}
    spells = {n: s for n, s in cal.spells.items() if n in names}
    for s in spells.values():
        names |= set(s["in"])
    return {"own_seasons": {n: event_json(w) for n, w in cal.own.items() if n in names},
            "spells": {n: spell_json(s) for n, s in spells.items()},
            "events": {n: event_json(w) for n, w in cal.events.items() if n in names},
            "periods": {n: list(md) for n, md in cal.periods.items() if n in names}}


def preset_path(name):
    return os.path.join(PRESETS, name + ".json")


def preset_json(v, ind=0):
    """A preset as JSON people can read and post: a table to a line per entry, and a date
    or a list of folders on one line, [5, 20], not four."""
    pad = "  " * ind
    if isinstance(v, dict) and v:
        return "{\n" + ",\n".join("%s  %s: %s" % (pad, json.dumps(k, ensure_ascii=False),
                                                   preset_json(x, ind + 1))
                                   for k, x in v.items()) + "\n" + pad + "}"
    return json.dumps(v, ensure_ascii=False)


def write_preset(name, about, data):
    """Write a preset. Returns its path."""
    data = dict(data)
    data["about"] = about or ""
    os.makedirs(PRESETS, exist_ok=True)
    path = preset_path(name)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(preset_json(data) + "\n")
    return path


def bring(cal, preset, p, mod):
    """Add `p`, which `mod` is on in, to `cal` from `preset` - its events part or what a
    preset of the mods alone needs - when `cal` lacks it; a spell brings the seasons of
    one's own it starts in. Returns what came, as lines."""
    if p in cal.known():
        return []
    needs = preset.get("needs") or {}

    def found(key, n):
        got = (preset.get(key) or {}).get(n)
        return got if got is not None else (needs.get(key) or {}).get(n)
    if found("events", p) is not None:
        cal.events[p] = norm_event(found("events", p))
        return ["  " + _("event %(event)s came with %(mod)s") % {"event": p, "mod": mod}]
    if found("own_seasons", p) is not None:
        cal.own[p] = norm_event(found("own_seasons", p))
        return ["  " + _("season %(season)s came with %(mod)s") % {"season": p, "mod": mod}]
    if found("spells", p) is not None:
        cal.spells[p] = norm_spell(found("spells", p))
        out = ["  " + _("spell %(spell)s came with %(mod)s") % {"spell": p, "mod": mod}]
        for q in cal.spells[p]["in"]:
            out += bring(cal, preset, q, p)
        return out
    if found("periods", p) is not None:
        cal.periods[p] = tuple(found("periods", p))
        return ["  " + _("period %(period)s came with %(mod)s") % {"period": p, "mod": mod}]
    return []


def apply_preset(cal, inst, preset, parts):
    """Set `parts` of `cal` from `preset`. Returns what it did and left out, as lines.
    Nothing is written: that is Save's job, and Save checks the result first."""
    said = []
    if "calendar" in parts and ("calendar" in preset or "names" in preset):
        dates = preset.get("calendar")
        cal.set_dates({s: tuple(md) for s, md in dates.items()} if dates else polesia())
        cal.set_names(preset.get("names") or {})
        said.append(_("calendar: %s") % calendar_words(cal))
    if "events" in parts and any(k in preset for k in PART_KEYS["events"]):
        cal.own = {n: norm_event(w) for n, w in preset.get("own_seasons", {}).items()}
        cal.spells = {n: norm_spell(s) for n, s in preset.get("spells", {}).items()}
        cal.events = {n: norm_event(w) for n, w in preset.get("events", {}).items()}
        cal.periods = {n: tuple(md) for n, md in preset.get("periods", {}).items()}
        dropped = sorted(cal._bad_events) + sorted(cal._bad_own) + sorted(cal._bad_spells)
        cal._bad_events, cal._bad_own, cal._bad_spells = {}, {}, {}
        if cal.own:
            said.append(_("seasons of your own: %s") % commas(cal.own_order()))
        if cal.spells:
            said.append(_("spells: %s") % commas(sorted(cal.spells, key=str.casefold)))
        said.append(_("events: %s") % commas(sorted(cal.events)) if cal.events
                    else _("events: none"))
        if dropped:
            said.append("  " + _("dropped the events seasons_config.py had that could not be "
                                 "used: %s") % commas(dropped))
    if "mods" in parts and "mods" in preset:
        toggle, skipped, moved = {}, [], []
        for name, c in preset["mods"].items():
            if name not in inst.names:
                skipped.append(name)
                continue
            when = list(c["when"])
            # a mod scoped to an event this setup does not have brings the event along,
            # and a season of the player's own, a spell and a period likewise
            for p in when:
                said += bring(cal, preset, p, name)
            above = c["above"]
            if not inst.listed(above):
                above = anchor_for(inst, name, when, dict(toggle, **{name: c}))[0] or above
                moved.append(_("%(mod)s (now wins over %(other)s)")
                             % {"mod": name, "other": above})
            toggle[name] = {"when": when, "above": above, "extra": []}
        cal.toggle = toggle
        said.append(ngettext("seasonal mods: %d", "seasonal mods: %d", len(toggle))
                    % len(toggle))
        if skipped:
            said.append("  " + _("not installed here, left out: %s") % commas(skipped))
        if moved:
            said.append("  " + _("given another mod to win over, since the one they won over "
                                 "is not installed here: %s") % commas(moved))
    if "textures" in parts and ("layout" in preset or "sound_src" in preset):
        layout, left = {}, []
        for name, c in (preset.get("layout") or {}).items():
            archive = os.path.join(season.DOWNLOADS, c["archive"])
            if name not in inst.names:
                left.append(_("%s (not installed here)") % name)
            elif not os.path.isfile(archive):
                left.append(_("%(mod)s (no %(archive)s in downloads)")
                            % {"mod": name, "archive": c["archive"]})
            else:
                layout[name] = c
        cal.layout = layout
        said.append(ngettext("texture sets: %d", "texture sets: %d", len(layout)) % len(layout))
        if left:
            said.append("  " + _("left out: %s") % commas(left))
        src = preset.get("sound_src")
        if src and not inst.listed(src) and cal.sound_src:
            said.append("  " + _("ambient sound: %(mod)s is not installed here, so it stays "
                                 "%(now)s") % {"mod": src, "now": cal.sound_src})
        elif src and not inst.listed(src):
            said.append("  " + _("ambient sound: %s is not installed here, so it stays off")
                        % src)
        else:
            cal.sound_src = src
            said.append(_("ambient sound: %s") % src if src else _("ambient sound: off"))
    return said


def calendar_words(cal):
    """The calendar and names `cal` holds, in a few words."""
    on, total = len(cal.dates), len(season.SEASONS)
    if not cal.custom():
        dates = _("Polesia's dates")
    elif on == total:
        dates = _("own dates")
    else:
        dates = ngettext("own dates, %(on)d of %(all)d seasons on",
                         "own dates, %(on)d of %(all)d seasons on", on) % {
            "on": on, "all": total}
    n = len(cal.names)
    names = (ngettext("%d season renamed", "%d seasons renamed", n) % n if n
             else _("the usual names"))
    # translators: the calendar in a few words: its dates, then its names
    return _("%(dates)s; %(names)s") % {"dates": dates, "names": names}


def commas(names):
    """Names in a list, as the lines here run them: "a, b, c"."""
    return pgettext("between words in a list", ", ").join(names)


def few(names, most=4):
    """A list of names, cut short past `most`."""
    names = sorted(names, key=str.lower)
    if len(names) > most:
        more = len(names) - most
        # translators: a list cut short, as in "a, b, c, d and 2 more"
        return ngettext("%(names)s and %(more)d more", "%(names)s and %(more)d more",
                        more) % {"names": commas(names[:most]), "more": more}
    return commas(names)


def preset_effect(cal, inst, preset, parts):
    """What loading `parts` of `preset` would do to the setup `cal` holds: (lines, losses).
    `losses` names what of the player's own it would take off or change, empty when it
    only adds. Worked out on a copy: `cal` is left as it is."""
    trial = copy.copy(cal)
    for k in ("toggle", "events", "periods", "layout", "dates", "names", "_bad_events",
              "own", "_bad_own", "spells", "_bad_spells"):
        setattr(trial, k, copy.deepcopy(getattr(cal, k)))
    parts = [p for p in parts if p in preset_parts(preset)]
    apply_preset(trial, inst, preset, parts)
    out, losses = [], []
    if "calendar" in parts:
        if (trial.dates, trial.names) == (cal.dates, cal.names):
            out.append(_("Calendar: the same as yours."))
        else:
            out.append(_("Calendar: %(theirs)s. Yours now: %(yours)s.")
                       % {"theirs": calendar_words(trial), "yours": calendar_words(cal)})
            if cal.custom() or cal.names:
                # translators: what loading a preset takes the place of, in a list
                losses.append(_("your calendar and names"))
    if "events" in parts:
        mine = dict(cal.periods, **cal.events)
        mine.update(cal.own)
        mine.update(cal.spells)
        theirs = dict(trial.periods, **trial.events)
        theirs.update(trial.own)
        theirs.update(trial.spells)
        gone = set(mine) - set(theirs)
        changed = [n for n in mine if n in theirs and mine[n] != theirs[n]]
        if trial.own:
            out.append(_("Seasons of your own: %s.") % few(trial.own))
        if trial.spells:
            out.append(_("Spells: %s.") % few(trial.spells))
        events = few(set(theirs) - set(trial.own) - set(trial.spells))
        out.append(_("Events: %s.") % events if events else _("Events: none."))
        if gone:
            out.append("  " + _("takes off yours: %s") % few(gone))
        if changed:
            out.append("  " + _("changes yours: %s") % few(changed))
        if gone or changed:
            lost = set(gone) | set(changed)
            one = next(iter(lost))
            if len(lost) > 1 and lost & (set(cal.own) | set(cal.spells)):
                # translators: what loading a preset takes the place of, in a list
                losses.append(ngettext("%d of your seasons, spells and events",
                                       "%d of your seasons, spells and events", len(lost))
                              % len(lost))
            elif len(lost) > 1:
                # translators: what loading a preset takes the place of, in a list
                losses.append(ngettext("%d of your events", "%d of your events", len(lost))
                              % len(lost))
            elif one in cal.own:
                # translators: what loading a preset takes the place of, in a list
                losses.append(_("your season %s") % one)
            elif one in cal.spells:
                # translators: what loading a preset takes the place of, in a list
                losses.append(_("your spell %s") % one)
            else:
                # translators: what loading a preset takes the place of, in a list
                losses.append(_("your event %s") % one)
    if "mods" in parts:
        gone = set(cal.toggle) - set(trial.toggle)
        changed = [n for n in cal.toggle if n in trial.toggle and (
            set(cal.toggle[n]["when"]) != set(trial.toggle[n]["when"])
            or cal.toggle[n]["above"] != trial.toggle[n]["above"])]
        out.append(ngettext("Seasonal mods: %d.", "Seasonal mods: %d.", len(trial.toggle))
                   % len(trial.toggle))
        if gone:
            out.append("  " + ngettext("stops switching %(n)d of yours: %(mods)s",
                                       "stops switching %(n)d of yours: %(mods)s", len(gone))
                       % {"n": len(gone), "mods": few(gone)})
        if changed:
            out.append("  " + ngettext("changes when %(n)d of yours are on: %(mods)s",
                                       "changes when %(n)d of yours are on: %(mods)s",
                                       len(changed)) % {"n": len(changed), "mods": few(changed)})
        left = [n for n in preset.get("mods", {}) if n not in inst.names]
        if left:
            out.append("  " + _("not installed here, so left out: %s") % few(left))
        if gone or changed:
            # translators: what loading a preset takes the place of, in a list
            losses.append(ngettext("%d of your seasonal mods", "%d of your seasonal mods",
                                   len(gone) + len(changed)) % (len(gone) + len(changed)))
    if "textures" in parts:
        sets, sound = few(trial.layout), trial.sound_src
        if sets and sound:
            out.append(_("Texture sets: %(sets)s. Ambient sound: %(sound)s.")
                       % {"sets": sets, "sound": sound})
        elif sets:
            out.append(_("Texture sets: %s. Ambient sound: off.") % sets)
        elif sound:
            out.append(_("Texture sets: none. Ambient sound: %s.") % sound)
        else:
            out.append(_("Texture sets: none. Ambient sound: off."))
        if (set(cal.layout) - set(trial.layout)
                or (cal.sound_src and cal.sound_src != trial.sound_src)):
            # translators: what loading a preset takes the place of, in a list
            losses.append(_("your texture sets or ambient sound"))
    stuck = sorted(n for n, c in trial.toggle.items()
                   if any(p not in trial.known() for p in c["when"]))
    if stuck:
        out.append(ngettext("%s would still be on for events it takes off. Uncheck those "
                            "before saving.",
                            "%s would still be on for events it takes off. Uncheck those "
                            "before saving.", len(stuck)) % few(stuck))
    return out, losses
