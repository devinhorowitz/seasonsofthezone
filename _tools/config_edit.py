"""Read and write seasons_config.py for configure.py, the window and its commands.

The config stays a Python file people can edit by hand. This rewrites only the two tables
it manages, TOGGLE_MODS and EVENTS, and inside them only the entries that changed: the rest
of the file, comments included, stays as written. A new file is checked with season.py's
own rules before it replaces the old one, and the old one is kept as seasons_config.py.bak.
"""
import ast
import codecs
import difflib
import io
import json
import os
import shutil

import season

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(HERE, "seasons_config.py")

MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
DAYS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

# what people type for the seasons on the command line
ALIASES = {"deep winter": "winter_snow", "deep_winter": "winter_snow",
           "deepwinter": "winter_snow", "late winter": "late_winter",
           "latewinter": "late_winter", "fall": "autumn"}

TEMPLATE = '''"""Which mods this install stages, and when.

Written by configure.py (configure.bat), and still yours to edit by hand: the tool only
rewrites the entries it changes. The full reference is docs/CONFIGURING.md.
"""

LAYOUT = {}
TOGGLE_MODS = {}
SOUND_SRC = None
PERIODS = {}
EVENTS = {}
'''


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
    Separators are left out; files are read the first time they are asked for."""

    def __init__(self):
        self.order = [(l[1:], l[:1] == "+") for l in (season._modlist_lines() or [])
                      if l[:1] in ("+", "-") and not l.endswith("_separator")]
        self.names = [n for n, _ in self.order]
        self.enabled = {n for n, on in self.order if on}
        self._files = {}

    def files(self, name):
        if name not in self._files:
            self._files[name] = mod_files(name)
        return self._files[name]

    def match(self, name):
        """(the mod as MO2 names it, []) or (None, close names)."""
        if name in self.names:
            return name, []
        low = {n.lower(): n for n in self.names}
        if name.lower() in low:
            return low[name.lower()], []
        return None, difflib.get_close_matches(name, self.names, n=5, cutoff=0.5)


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


def anchor_for(inst, name, when, toggle):
    """(anchor, reason, rivals) for putting `name` on the calendar in `when`.

    The anchor is the highest enabled mod that ships any of the same files: directly above
    it, `name` is above every mod it has to beat. Other calendar mods are left out, because
    which of two seasonal mods should win is the user's call; the ones on in a season
    `name` is also on in come back as rivals, [(mod, files shared, seasons)]. With nothing
    to beat, the anchor is the mod just under `name`, so it stays where it is."""
    mine = inst.files(name)
    others = set(toggle) - {name}
    skip = others | {name, season.SOUND_MOD}
    rivals = []
    for other in inst.names:
        if other in others:
            both = set(when) & set(periods_of(toggle[other]))
            n = len(mine & inst.files(other)) if both and mine else 0
            if n:
                rivals.append((other, n, sorted(both, key=order_key)))
    for other, on in inst.order:
        if on and other not in skip and mine:
            n = len(mine & inst.files(other))
            if n:
                return other, "ships %d of the same files" % n, rivals
    i = inst.names.index(name) if name in inst.names else len(inst.names)
    below = [o for o, on in inst.order[i + 1:] if on and o not in skip]
    if below:
        return below[0], "nothing else ships its files, so it stays where it is", rivals
    above = [o for o, on in reversed(inst.order[:i]) if on and o not in skip]
    if above:
        return above[0], "nothing else ships its files", rivals
    return None, "there is no other enabled mod to place it by", rivals


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


def resolve(name, known):
    """A period name as the config spells it, from what someone typed, or None."""
    n = name.strip()
    if n in known:
        return n
    n = ALIASES.get(n.lower(), n.lower().replace(" ", "_"))
    return n if n in known else None


def parse_day(text):
    """(month, day) from "12-24" or "12/24", or None."""
    for sep in ("-", "/", "."):
        if sep in text:
            try:
                m, d = (int(x) for x in text.strip().split(sep))
            except ValueError:
                return None
            if 1 <= m <= 12 and 1 <= d <= DAYS[m - 1]:
                return (m, d)
    return None


def day_text(md):
    return "%s %d" % (MONTHS[md[0] - 1], md[1])


def window_text(win):
    a, b = tuple(win[0]), tuple(win[1])
    return day_text(a) if a == b else "%s - %s" % (day_text(a), day_text(b))


def season_windows():
    """{season: "Apr 15 - May 19"}, from season.py's own start dates."""
    starts = sorted((m, d, s) for s, m, d in season.PHENO)
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


def entry_text(name, when, above):
    """A TOGGLE_MODS entry as the tool writes it, unindented."""
    w = ('(%s,)' % _q(when[0])) if len(when) == 1 else "(%s)" % ", ".join(_q(p) for p in when)
    return ["%s: {" % _q(name), '    "when": %s,' % w, '    "above": %s,' % _q(above), "},"]


def event_text(name, win):
    (a, b), (c, d) = win
    return ["%s: ((%d, %d), (%d, %d))," % (_q(name), a, b, c, d)]


def _assignments(tree, var):
    return [n for n in tree.body
            if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == var for t in n.targets)]


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
        col = _char_col(code[-1], v.end_col_offset)
        after = code[-1][col:].strip()
        if not after.startswith(","):
            if after and not after.startswith("#"):
                return None
            code[-1] = code[-1][:col] + "," + code[-1][col:]    # it may not stay last
        first = lines[k.lineno - 1]
        have[k.value] = (lines[prev:k.lineno - 1], code, first[:len(first) - len(first.lstrip())])
        order.append(k.value)
        prev = v.end_lineno
    if order and node.end_lineno <= prev:
        return None
    return have, order, lines[prev:node.end_lineno - 1]


def splice(text, var, plan):
    """`text` with the dict assigned to `var` rewritten to `plan`, [(key, lines, keep)] in
    the order wanted. keep=True uses the file's own text for that key where it has one;
    otherwise `lines` are written. A key the file has and `plan` lacks is dropped, with the
    comments above it. Returns (text, whether every comment in the table was kept)."""
    lines = text.split("\n")
    nodes = _assignments(ast.parse(text), var)
    fresh = ["%s = {" % var] + ["    " + l for _, ls, _ in plan for l in ls] + ["}"]
    if not nodes:
        while lines and lines[-1] == "":
            lines.pop()
        return "\n".join(lines + [""] + fresh + [""]), True
    node = nodes[-1]
    laid = _entries(lines, node)
    if laid is not None and not laid[1] and not plan:
        return text, True                   # empty, and staying empty: as written
    if laid is None or not laid[1]:
        lines[node.lineno - 1:node.end_lineno] = fresh
        return "\n".join(lines), laid is not None
    have, order, tail = laid
    ind = have[order[0]][2]
    body = []
    for key, ls, keep in plan:
        if key in have:
            above, code, own = have[key]
            body += above + (code if keep else [own + l for l in ls])
        else:
            body += [ind + l for l in ls]
    head, close = lines[node.lineno - 1], lines[node.end_lineno - 1]
    lines[node.lineno - 1:node.end_lineno] = [head] + body + tail + [close]
    return "\n".join(lines), True


def _is_empty_literal(node):
    v = node.value
    return (isinstance(v, ast.Dict) and not v.keys) or (
        isinstance(v, ast.Constant) and v.value is None)


class Calendar(object):
    """seasons_config.py as the tool edits it.

    `toggle` maps each mod on the calendar to {"when": [...], "above": "..."} and `events`
    each event to ((m, d), (m, d)). Everything else in the file is read only. `error` is
    set, as lines, when Python cannot run the file; `problems` lists what season.py would
    refuse in it; `fixes` what saving from the tool repairs."""

    def __init__(self, path=CONFIG):
        self.path = path
        self.exists = os.path.isfile(path)
        raw = open(path, "rb").read() if self.exists else TEMPLATE.encode("utf-8")
        self.bom = raw.startswith(codecs.BOM_UTF8)
        text = raw.decode("utf-8-sig", "replace")
        self.nl = "\r\n" if "\r\n" in text else "\n"
        self.original = text
        self.text = text.replace("\r\n", "\n")
        self.error, self.problems, self.fixes = None, [], []
        self.toggle, self.events = {}, {}
        self.periods, self.layout, self.sound_src = {}, {}, None
        self._kept_toggle, self._kept_events = {}, {}
        self._load()

    # loading

    def _load(self):
        try:
            tree = ast.parse(self.text)
        except SyntaxError as e:
            self.error = season._config_error(e)
            return
        # An empty table left below a real one - the template's own TOGGLE_MODS = {} under
        # an entry typed above it - throws the real one away. It is dropped on save.
        lines = self.text.split("\n")
        drop = []
        for var in season.CONFIG_NAMES:
            nodes = _assignments(tree, var)
            if len(nodes) < 2:
                continue
            full = [n for n in nodes if not _is_empty_literal(n)]
            if len(full) > 1:
                self.error = ["%s is set on lines %s, and more than one of them has entries."
                              " Merge them into one by hand."
                              % (var, ", ".join(str(n.lineno) for n in full))]
                return
            keep = full[0] if full else nodes[0]
            for n in nodes:
                if n is not keep:
                    drop.append((n.lineno, getattr(n, "end_lineno", n.lineno)))
                    self.fixes.append("line %d set %s again and threw the table away; "
                                      "saving removes that line" % (n.lineno, var))
        for a, b in sorted(drop, reverse=True):
            del lines[a - 1:b]
        self.text = "\n".join(lines)
        ns = {"__file__": self.path}
        try:
            exec(compile(self.text, self.path, "exec"), ns)
        except Exception as e:
            self.error = season._config_error(e)
            return
        self.layout = ns.get("LAYOUT", {}) or {}
        self.sound_src = ns.get("SOUND_SRC")
        self.periods = ns.get("PERIODS", {}) or {}
        toggle, events = ns.get("TOGGLE_MODS", {}) or {}, ns.get("EVENTS", {}) or {}
        self.problems = season.config_problems(toggle, self.layout, self.sound_src,
                                               self.periods, events)
        if not isinstance(toggle, dict) or not isinstance(events, dict):
            self.error = ["TOGGLE_MODS and EVENTS must each be a table, {...}."]
            return
        for name, cfg in toggle.items():
            when = periods_of(cfg)
            above = cfg.get("above", "") if isinstance(cfg, dict) else ""
            self.toggle[name] = {"when": when, "above": above if isinstance(above, str) else ""}
            raw = cfg.get("when", cfg.get("seasons")) if isinstance(cfg, dict) else None
            if isinstance(raw, (list, tuple)) and list(raw) == when and isinstance(above, str):
                self._kept_toggle[name] = (frozenset(when), above)
            else:
                self.fixes.append("%s: saving rewrites this entry in the right shape" % name)
        for name, win in events.items():
            try:
                (a, b), (c, d) = win
                w = ((int(a), int(b)), (int(c), int(d)))
            except (TypeError, ValueError):
                self.problems.append("EVENTS[%r] must be ((month, day), (month, day))" % name)
                continue
            self.events[name] = w
            self._kept_events[name] = w

    # what is on the calendar

    def known(self):
        """Every name a mod may be scoped to, in calendar order."""
        return (list(season.SEASONS) + sorted(self.periods) + sorted(self.events))

    def put(self, name, when, above):
        known = self.known()
        self.toggle[name] = {"when": sorted(set(when), key=lambda p: (
            known.index(p) if p in known else len(known), p)), "above": above}

    def take(self, name):
        self.toggle.pop(name, None)

    def users_of(self, period):
        return [n for n, cfg in self.toggle.items() if period in cfg["when"]]

    def dirty(self):
        return (self.fixes != [] or set(self.toggle) != set(self._kept_toggle)
                or any((frozenset(c["when"]), c["above"]) != self._kept_toggle.get(n)
                       for n, c in self.toggle.items())
                or self.events != self._kept_events)

    # writing

    def render(self):
        """The file as it would be saved, and whether every comment could be kept."""
        plan = [(n, entry_text(n, c["when"], c["above"]),
                 self._kept_toggle.get(n) == (frozenset(c["when"]), c["above"]))
                for n, c in self.toggle.items()]
        text, kept = splice(self.text, "TOGGLE_MODS", plan)
        eplan = [(n, event_text(n, w), self._kept_events.get(n) == w)
                 for n, w in self.events.items()]
        if eplan or _assignments(ast.parse(text), "EVENTS"):
            text, kept_e = splice(text, "EVENTS", eplan)
            kept = kept and kept_e
        return text, kept

    def check(self, text):
        """What season.py would refuse in `text`, as sentences."""
        ns = {"__file__": self.path}
        try:
            exec(compile(text, self.path, "exec"), ns)
        except Exception as e:
            return season._config_error(e)
        return season._set_twice(text) + season.config_problems(
            ns.get("TOGGLE_MODS", {}), ns.get("LAYOUT", {}), ns.get("SOUND_SRC"),
            ns.get("PERIODS", {}), ns.get("EVENTS", {}))

    def save(self):
        """Write the file. Returns (saved, lines to show)."""
        if self.error:
            return False, ["seasons_config.py can't be read, so it can't be edited here:"]\
                + self.error
        text, kept = self.render()
        problems = self.check(text)
        if problems:
            return False, ["Not saved - season.py would refuse the result:"] + problems
        out = text.replace("\n", self.nl)
        if out == self.original:
            return True, ["Nothing to save."]
        notes = []
        if self.exists:
            shutil.copy2(self.path, self.path + ".bak")
            notes.append("The previous file is %s.bak." % os.path.basename(self.path))
        data = out.encode("utf-8")
        with open(self.path, "wb") as f:
            f.write((codecs.BOM_UTF8 if self.bom else b"") + data)
        if not kept:
            notes.append("Comments inside the tables could not be kept, because of how they "
                         "were laid out; the .bak has them.")
        self.__init__(self.path)
        return True, ["Saved %s." % os.path.basename(self.path)] + notes

    def start_over(self):
        """Replace a file that can't be read with a new, empty one. The old one is kept."""
        if self.exists:
            shutil.copy2(self.path, self.path + ".bak")
        with open(self.path, "wb") as f:
            f.write(TEMPLATE.replace("\n", self.nl).encode("utf-8"))
        self.__init__(self.path)
