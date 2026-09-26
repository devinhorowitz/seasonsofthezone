#!/usr/bin/env python3
r"""Stage the launch-time seasonal layers for today's date.

  py _tools\season.py status                 what the next launch would do
  py _tools\season.py apply                  do it (what play.bat runs)
  py _tools\season.py apply --season winter
  py _tools\season.py apply --dry-run
  py _tools\season.py whowins <path inside gamedata> [--for "<your mod>"]
  py _tools\season.py dial                   send the calendar and names to the game
  py _tools\season.py say checking           a line play.bat shows, in the player's language

The seasonal atmosphere (light, fog, wind, wetness) follows the calendar on its own.
Textures cannot: X-Ray loads them from MO2's virtual file system at level load and keeps
them for the session. So seasonal mods are enabled or disabled here, and texture sets
restaged, before the game starts. Configuration is in seasons_config.py; with none,
nothing is staged.

Seasons (phenological, for Polesia):
  spring       Apr 15 - May 19    35 d   green-up
  summer       May 20 - Sep 14   118 d
  autumn       Sep 15 - Oct 31    47 d
  winter       Nov 01 - Nov 30    30 d   first snowfall, bare ground
  winter_snow  Dec 01 - Mar 04    94 d   snow on the ground
  late_winter  Mar 05 - Apr 14    41 d   the thaw: patchy snow, mud, bare trees
--mapping met uses Ukraine's meteorological convention instead. CALENDAR in
seasons_config.py (configure.bat's Seasons step) moves the dates and turns seasons off; apply
passes it to the game in configs/season_calendar.ltx, with a dial drawn for it.

What is installed is identified by hashing the mod folder against the archive's options,
never by a stored note. The archive side is cached (_baseline/season-archive-hashes.json,
keyed on the archive's size and mtime); the live folder is hashed on every run.
"""
import argparse
import ast
import datetime
import hashlib
import io
import re
import glob
import json
import os
import shutil
import subprocess
import sys
import time
import tokenize
import traceback
import types

import lang
from lang import _, N_, ngettext, pgettext        # noqa: F401 - used as the strings are marked

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# a refusal goes out on stderr, and in another language it has letters cp1252 lacks
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = os.path.join(ROOT, "mods")
DOWNLOADS = os.path.join(ROOT, "downloads")
SOTZ = "Seasons of the Zone"
VERSION = "2.0.0"           # of the tools; build_release.py checks it against CHANGELOG.md
SEASONS = ("spring", "summer", "autumn", "winter", "winter_snow", "late_winter")


def _find_unrar():
    """UnRAR or 7z, from Program Files or PATH; "UnRAR" lets rarfile search for itself."""
    for env in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env)
        if not base:
            continue
        for rel in (("WinRAR", "UnRAR.exe"), ("WinRAR", "Rar.exe"), ("7-Zip", "7z.exe")):
            p = os.path.join(base, *rel)
            if os.path.isfile(p):
                return p
    found = shutil.which("UnRAR") or shutil.which("unrar") or shutil.which("7z")
    return found or "UnRAR"


def _mo2_ini(key, default=None):
    """A value from the portable ModOrganizer.ini. MO2 writes paths as
    key=@ByteArray(D:\\\\ANOMALY) with doubled backslashes."""
    p = os.path.join(ROOT, "ModOrganizer.ini")
    if not os.path.isfile(p):
        return default
    try:
        raw = io.open(p, encoding="utf-8", errors="replace").read()
    except OSError:
        return default
    pat = "(?m)^" + re.escape(key) + r"\s*=\s*(?:@ByteArray\()?([^)\r\n]*)\)?\s*$"
    m = re.search(pat, raw)
    if not m:
        return default
    return m.group(1).strip().replace('\\\\', '\\') or default


def game_dir():
    return _mo2_ini("gamePath", os.path.join(os.path.dirname(ROOT), "ANOMALY"))


def profile_name():
    return _mo2_ini("selected_profile", "G.A.M.M.A")


APPDATA = os.path.join(game_dir(), "appdata")

CONFIG_NAMES = ("LAYOUT", "TOGGLE_MODS", "SOUND_SRC", "PERIODS", "EVENTS", "CALENDAR",
                "NAMES", "WEATHER_PLACE", "OWN_SEASONS", "SPELLS")


def _config_error(e):
    """Lines saying what is wrong with a seasons_config.py Python could not run: the line
    at fault and what Python said. A traceback reads as the tool crashing."""
    end = None
    if isinstance(e, SyntaxError):
        line, text, col = e.lineno, e.text, e.offset
        what = e.msg or _("invalid syntax")
        end = getattr(e, "end_lineno", None)
        if line and end and end > line:
            # a missing comma between two entries is blamed on where the first one starts;
            # the range holds the fault, a caret on its first line would not
            text = None
    else:
        frames = [f for f in traceback.extract_tb(e.__traceback__)
                  if os.path.basename(f.filename) == "seasons_config.py"]
        line = frames[-1].lineno if frames else None
        text = frames[-1].line if frames else None
        col = None
        said = "%s: %s" % (type(e).__name__, e) if str(e) else type(e).__name__
        what = (_("Python can't run this line (%s)") % said if line else
                _("Python can't run seasons_config.py (%s)") % said)
        if isinstance(e, (SystemExit, KeyboardInterrupt)):
            what = _("this stops the program (%s). Take it out.") % type(e).__name__
        if isinstance(e, NameError):
            # translators: the first is what Python said, like: name 'winter' is not defined
            what = _("%(error)s. Names go in quotes: \"%(name)s\".") % {
                "error": e, "name": getattr(e, "name", None) or "winter"}
    if line and end and end > line:
        out = [_("lines %(first)d to %(last)d: %(what)s") % {"first": line, "last": end,
                                                             "what": what}]
    elif line:
        out = [_("line %(line)d: %(what)s") % {"line": line, "what": what}]
    else:
        out = [what]
    if text:
        text = text.rstrip("\r\n")
        out.append(text.expandtabs())
        if col:
            out.append(" " * len(text[:col - 1].expandtabs()) + "^")
    return out


# Install-specific configuration lives in seasons_config.py. Missing or empty is fine:
# the in-engine layer runs with nothing staged. A file Python cannot run is held here and
# reported by _validate_config(), so whowins still works while it is being fixed.
# SEASONS_CONFIG points at another copy: configure.bat previews unsaved changes that way
CONFIG_PATH = (os.environ.get("SEASONS_CONFIG")
               or os.path.join(os.path.dirname(os.path.abspath(__file__)), "seasons_config.py"))
# shown with _() where it is used; season.py itself says it in whole sentences below
SAVE_AS_UTF8 = N_("Save it as UTF-8: in Notepad, File > Save as, set Encoding to UTF-8, then "
                  "Save.")


def _python():
    """How this machine starts Python: the py launcher when there is one, as play.bat and
    configure.bat prefer."""
    return "py" if shutil.which("py") else "python"


def command(tool, args=""):
    """A command to type in the GAMMA folder, as this machine starts Python."""
    return ("%s _tools\\%s %s" % (_python(), tool, args)).rstrip()


def read_config_text(path=CONFIG_PATH):
    """A config's text, decoded the way Python decodes source: a BOM or a coding line
    decides, and UTF-8 otherwise. Raises UnicodeDecodeError for a file that is neither."""
    with tokenize.open(path) as f:
        return f.read()


def _load_config(path=CONFIG_PATH):
    """seasons_config.py, run from its text every time: (module or None, error lines).

    Not imported. An import goes through Python's bytecode cache, which trusts a cached
    copy whose source has the same size and the same whole-second time: configure.py can
    save twice in one second, and the tables it saved first then ran on."""
    if not os.path.isfile(path):
        return None, None
    try:
        head = io.open(path, "rb").read(2)
    except OSError as e:
        return None, [_("seasons_config.py can't be read: %s") % e]
    if head in (b"\xff\xfe", b"\xfe\xff"):
        return None, [utf16_problem()]
    mod = types.ModuleType("seasons_config")
    mod.__file__ = path
    try:
        text = read_config_text(path)
    except (UnicodeDecodeError, SyntaxError) as e:
        return None, [encoding_problem(e)]
    try:
        exec(compile(text, path, "exec"), mod.__dict__)
    except (Exception, SystemExit, KeyboardInterrupt) as e:
        return None, _config_error(e)
    return mod, None


def encoding_problem(e):
    """What to say when a config's bytes do not decode. Python's tokenizer raises a
    SyntaxError, not a decode error, for bytes that are not UTF-8 in the first two lines."""
    if isinstance(e, SyntaxError) and "unknown encoding" in str(e):
        return _("The # coding line at the top of seasons_config.py names an encoding Python "
                 "does not know. Delete that line and save the file as UTF-8: in Notepad, "
                 "File > Save as, set Encoding to UTF-8, then Save.")
    if isinstance(e, UnicodeDecodeError):
        # translators: English says "bytes in" for any number, 1 too
        return ngettext("seasons_config.py is not saved as UTF-8 (byte 0x%(byte)02X, %(at)d "
                        "bytes in). Save it as UTF-8: in Notepad, File > Save as, set Encoding "
                        "to UTF-8, then Save.",
                        "seasons_config.py is not saved as UTF-8 (byte 0x%(byte)02X, %(at)d "
                        "bytes in). Save it as UTF-8: in Notepad, File > Save as, set Encoding "
                        "to UTF-8, then Save.", e.start) % {"byte": e.object[e.start],
                                                          "at": e.start}
    return _("seasons_config.py is not saved as UTF-8. Save it as UTF-8: in Notepad, File > "
             "Save as, set Encoding to UTF-8, then Save.")


def utf16_problem():
    """What to say about a config saved as UTF-16, which Notepad calls Unicode."""
    return _("seasons_config.py is saved as UTF-16 (\"Unicode\" in Notepad). Save it as UTF-8: "
             "in Notepad, File > Save as, set Encoding to UTF-8, then Save.")


_cfg, CONFIG_ERROR = _load_config()
LAYOUT = getattr(_cfg, "LAYOUT", {})
TOGGLE_MODS = getattr(_cfg, "TOGGLE_MODS", {})
SOUND_SRC = getattr(_cfg, "SOUND_SRC", None)
# The calendar itself is configurable. PERIODS adds base periods (they partition the year
# alongside the seasons); EVENTS adds windows that OVERLAY whatever period they fall in,
# which is what lets a one-day event keep the season around it.
PERIODS = getattr(_cfg, "PERIODS", {})
EVENTS = getattr(_cfg, "EVENTS", {})
# The seasons that are on and the day each starts. None is Polesia's dates (PHENO).
CALENDAR = getattr(_cfg, "CALENDAR", None)
# Names of the player's own for the seasons, {season: name}, shown in game in place of
# "Spring" or "Deep winter". The config keeps the season keys either way.
NAMES = getattr(_cfg, "NAMES", None)
# Where the real weather comes from, {"name": ..., "lat": ..., "lon": ...}; None is
# Chornobyl. fetch_weather.py reads it; season.py checks it.
WEATHER_PLACE = getattr(_cfg, "WEATHER_PLACE", None)
# Seasons of the player's own, {name: ((month, day), (month, day))}: stretches of the year,
# each at least a week, that run on top of the season they fall in, as an event does.
OWN_SEASONS = getattr(_cfg, "OWN_SEASONS", None)
OWN_SEASONS = {} if OWN_SEASONS is None else OWN_SEASONS
# Spells, {name: {"in": (seasons...), "chance": percent a day, "days": (fewest, most),
# "as": a season or None}}: short stretches that start by chance in the seasons named, and
# may bring another season with them. The date decides, so every launch that day agrees.
SPELLS = getattr(_cfg, "SPELLS", None)
SPELLS = {} if SPELLS is None else SPELLS


def _q(v):
    """A name or key as the config spells it: in double quotes, or as written if it is
    not a string."""
    return '"%s"' % v if isinstance(v, str) else repr(v)


def _set_twice(text=None):
    """Problems for each table the config sets more than once. Python keeps the last, so a
    table written above the template's own `TOGGLE_MODS = {}` counts for nothing, and
    nothing says so. `text` is a config's source; the default is the installed file."""
    if text is None:
        path = getattr(_cfg, "__file__", None)
        if not path:
            return []
        try:
            text = read_config_text(path)
        except (OSError, SyntaxError, UnicodeDecodeError):
            return []
    try:
        tree = ast.parse(text)
    except Exception:
        return []

    def names(t):
        if isinstance(t, ast.Name):
            return [t.id]
        if isinstance(t, (ast.Tuple, ast.List)):
            return [n for e in t.elts for n in names(e)]
        if isinstance(t, ast.Starred):
            return names(t.value)
        return []

    # Anywhere in the file, not only at the top: an `if` or a tuple assignment replaces a
    # table just as well. A bare annotation (`CALENDAR: dict`) assigns nothing.
    nodes = sorted((n for n in ast.walk(tree)
                    if isinstance(n, (ast.Assign, ast.AnnAssign, ast.NamedExpr))),
                   key=lambda n: (n.lineno, n.col_offset))
    first, out = {}, []
    for node in nodes:
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target] if node.value is not None else []
        else:
            targets = [node.target]
        set_here = [n for t in targets for n in names(t) if n in CONFIG_NAMES]
        for var in set_here:
            if var in first:
                out.append(_("line %(line)d sets %(table)s again, which throws away the one "
                             "on line %(first)d. Keep one.")
                           % {"line": node.lineno, "table": var, "first": first[var]})
            else:
                first[var] = node.lineno
        # the same entry twice in one table: Python keeps the second without a word
        if set_here and isinstance(node.value, ast.Dict):
            seen = {}
            for k in node.value.keys:
                if isinstance(k, ast.Constant) and not isinstance(k.value, bool):
                    if k.value in seen:
                        # the table's name goes first, in English: configure.py reads it
                        out.append(set_here[0] + " " + _(
                            "lists %(key)s twice, on lines %(first)d and %(second)d; only "
                            "the second counts. Keep one.")
                            % {"key": _q(k.value), "first": seen[k.value],
                               "second": k.lineno})
                    else:
                        seen[k.value] = k.lineno
    return out


def _validate_config():
    """Refuse a malformed seasons_config.py with a message naming the entry.

    `"seasons": ("winter")` is a string, not a tuple, and `"winter" in "winter_snow"` is
    true, so without this check that mod would be enabled in deep winter."""
    # the file as the player finds it from the GAMMA folder, unless it is another copy
    here = CONFIG_PATH if os.environ.get("SEASONS_CONFIG") else r"_tools\seasons_config.py"
    head = "  " + _("%s needs fixing before play.bat can switch anything:") % here + "\n"
    if CONFIG_ERROR:
        raise SystemExit(head + "    - " + CONFIG_ERROR[0]
                         + "".join("\n        " + l for l in CONFIG_ERROR[1:])
                         + "\n  " + _("Nothing has been changed."))
    problems = _set_twice() + config_problems(TOGGLE_MODS, LAYOUT, SOUND_SRC, PERIODS, EVENTS,
                                              CALENDAR, NAMES, WEATHER_PLACE, OWN_SEASONS,
                                              SPELLS)
    if problems:
        raise SystemExit(head + "\n".join("    - " + p for p in problems)
                         + "\n  " + _("Nothing has been changed."))


# What weather_flags() can assert about a day; a mod can be scoped to these as well
WEATHER_NAMES = ("freezing", "thaw", "heat")
NAME_CHARS = 20             # the longest season name the dial and the pages have room for
OWN_NAME_CHARS = 24         # the longest name for a season of the player's own
OWN_MIN_DAYS = 7            # a season of one's own runs at least a week,
OWN_MOST = 52               # so the year has room for 52 of them
SPELL_MOST_DAYS = 6         # a spell is shorter than a week; a week or longer is a season
SPELL_KEYS = ("in", "chance", "days", "as")


def _is_day(md, leap=False):
    """Is md a (month, day) of whole numbers naming a day of the year? February 29 only
    with `leap`. Strings, floats and bools are not days, however they print."""
    if not isinstance(md, (tuple, list)) or len(md) != 2:
        return False
    m, d = md
    if not all(isinstance(x, int) and not isinstance(x, bool) for x in (m, d)):
        return False
    return 1 <= m <= 12 and 1 <= d <= (29 if (m == 2 and leap) else MONTH_DAYS[m - 1])


def _folder_problem(name):
    """Why `name` cannot be a mod folder as MO2 lists it, as a sentence, or None."""
    if not isinstance(name, str):
        return _("that is not a name in quotes. Put the mod's folder name in quotes.")
    if not name.strip():
        return _("the name is empty. Put the mod's folder name in the quotes.")
    if name != name.strip():
        return _("the name has spaces at its start or end, which a folder name can't.")
    if name in (".", "..") or name.endswith(".") or any(c in name for c in '/\\:*?"<>|'):
        return _("that can't be a folder name: folder names can't end with a dot or hold "
                 "any of / \\ : * ? \" < > |.")
    return None


def _own_folders():
    """This mod's folders, and the soundscape it generates: never on the calendar."""
    return set(sotz_copies() or [SOTZ]) | {SOTZ, SOUND_MOD}


def config_problems(toggle_mods, layout, sound_src, periods, events, calendar=None,
                    names=None, place=None, own=None, spells=None):
    """What is wrong with a set of config tables, one sentence per entry at fault. The
    configure tool checks a file with this before it writes one."""
    problems = []
    # A problem starts with the table, or the entry, it is about, as the config spells it:
    # configure.py reads that part, so it stays English and outside _().
    if not isinstance(periods, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        problems.append("PERIODS " + _("must be a table, {name: (month, day)}, or {} for "
                                       "none."))
    if not isinstance(events, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        problems.append("EVENTS " + _("must be a table, {name: ((month, day), (month, "
                                      "day))}, or {} for none."))
    periods = periods if isinstance(periods, dict) else {}
    events = events if isinstance(events, dict) else {}
    mine = {} if own is None else own
    problems += own_problems(mine, periods, events, names if isinstance(names, dict) else {})
    mine = mine if isinstance(mine, dict) else {}
    chance = {} if spells is None else spells
    on = ([s for s in calendar if s in SEASONS] if isinstance(calendar, dict) and calendar
          else list(SEASONS))
    problems += spell_problems(chance, on, mine, periods, events,
                               names if isinstance(names, dict) else {})
    chance = chance if isinstance(chance, dict) else {}

    # the names a mod can be scoped to
    for var, table in (("PERIODS", periods), ("EVENTS", events)):
        for name in table:
            where = "%s[%r]" % (var, name)
            if not isinstance(name, str) or not re.match(r"^[A-Za-z0-9_]+$", name):
                problems.append(where + ": " + _("a name is letters, digits and underscores, "
                                                 "like high_summer."))
            elif name in SEASONS:
                problems.append(where + ": " + _("that is already a season. Rename it."))
            elif name in WEATHER_NAMES:
                problems.append(where + ": " + (
                    _("that is already a kind of weather. Rename the event.") if var == "EVENTS"
                    else _("that is already a kind of weather. Rename the period.")))
    for name in sorted(set(periods) & set(events), key=str):
        problems.append("EVENTS: " + _("%s is both a period and an event. Rename one.")
                        % _q(name))

    # when periods start: never on a day a season or another period starts, or one of
    # the two would never run
    table = calendar if (isinstance(calendar, dict) and calendar
                         and not calendar_problems(calendar)) else None
    starts = {tuple(md): s for s, md in table.items()} if table else {
        (m, d): s for s, m, d in PHENO}
    for name, md in periods.items():
        where = "PERIODS[%r]" % (name,)
        if not _is_day(md, leap=True):
            problems.append(where + ": " + _("the start must be (month, day), like (7, 1)."))
        elif tuple(md) == (2, 29):
            # translators: follows an entry, like PERIODS['x'], which stays English
            problems.append(where + " " + _("can't start on February 29, which three years in "
                                            "four don't have. Use February 28 or March 1."))
        elif tuple(md) in starts:
            # translators: follows an entry, like PERIODS['x'], which stays English
            problems.append(where + " " + _("starts on %(day)s, the same day as %(season)s, so "
                                            "one of them would never be on. Give it another "
                                            "day.")
                            % {"day": _md(*md), "season": season_label(starts[tuple(md)])})
        else:
            starts[tuple(md)] = name
    for name, spec in events.items():
        problems += event_problems(name, spec)

    known = (list(SEASONS) + [n for n in periods if isinstance(n, str)]
             + [n for n in mine if isinstance(n, str)]
             + [n for n in chance if isinstance(n, str)]
             + [n for n in events if isinstance(n, str)] + list(WEATHER_NAMES))
    valid = ", ".join(known)
    own = _own_folders()

    if not isinstance(toggle_mods, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        problems.append("TOGGLE_MODS " + _("must be a table, {mod folder: {...}}."))
    else:
        for name, cfg in toggle_mods.items():
            where = "TOGGLE_MODS[%r]" % (name,)
            bad = _folder_problem(name)
            if bad:
                problems.append(where + ": " + bad)
                continue
            if name in own:
                problems.append(where + ": " + (
                    _("that is the soundscape season.py makes, which it switches itself. Take "
                      "the entry out.") if name == SOUND_MOD else
                    _("that is this mod itself, which stays on all year. Take the entry "
                      "out.")))
                continue
            if not isinstance(cfg, dict):
                # translators: follows an entry, like PERIODS['x'], which stays English
                problems.append(where + " " + _("must be {\"when\": (...), \"above\": "
                                                "\"...\"}."))
                continue
            if "when" in cfg and "seasons" in cfg:
                # translators: follows an entry, like PERIODS['x'], which stays English
                problems.append(where + " " + _("has both \"when\" and \"seasons\", which are "
                                                "the same thing. Keep one."))
            raw_when = cfg.get("when", cfg.get("seasons"))
            if raw_when is None:
                other = [k for k in cfg if k != "above"]
                if other:
                    # translators: follows an entry, like PERIODS['x'], which stays English
                    problems.append(where + " " + _(
                        "has no \"when\" (it has %s). It names the seasons, events or weather "
                        "the mod is on in, like \"when\": (\"winter\",).")
                        % ", ".join(_q(k) for k in other))
                else:
                    # translators: follows an entry, like PERIODS['x'], which stays English
                    problems.append(where + " " + _(
                        "has no \"when\". It names the seasons, events or weather the mod is "
                        "on in, like \"when\": (\"winter\",)."))
            elif isinstance(raw_when, str) and "," in raw_when:
                # ("summer,spring") is one name with a comma in it, not two
                parts = [p.strip() for p in raw_when.split(",") if p.strip()]
                problems.append(where + ": " + _("\"when\" is the single name \"%(name)s\". "
                                                 "Give each season its own quotes: "
                                                 "(%(names)s).")
                                % {"name": raw_when,
                                   "names": ", ".join('"%s"' % p for p in parts)})
            elif isinstance(raw_when, str):
                one = raw_when.strip() or "winter"
                problems.append(where + ": " + _("a single name in \"when\" needs a trailing "
                                                 "comma: (\"%(name)s\",), not "
                                                 "(\"%(name)s\").") % {"name": one})
            elif not isinstance(raw_when, (list, tuple)):
                problems.append(where + ": " + _("\"when\" must list seasons, events or "
                                                 "weather in brackets, like (\"winter\", "
                                                 "\"winter_snow\")."))
            elif not raw_when:
                problems.append(where + ": " + _("\"when\" is empty, so the mod would never "
                                                 "be on."))
            else:
                bad = [str(x) for x in raw_when if x not in known]
                if bad:
                    problems.append(where + ": " + ngettext(
                        "\"when\" names %(names)s, which is not a season, an event or "
                        "weather. Valid: %(valid)s.",
                        "\"when\" names %(names)s, which are not seasons, events or weather. "
                        "Valid: %(valid)s.", len(bad))
                        % {"names": ", ".join(bad), "valid": valid})
            above = cfg.get("above")
            if not isinstance(above, str) or not above.strip():
                problems.append(where + ": " + _("\"above\" must name the mod this one wins "
                                                 "over. Pick it in configure.bat, or find it "
                                                 "with: %s.")
                                % command("season.py", "whowins <a file it ships> --for "
                                          "\"%s\"" % name))
            elif above == name:
                problems.append(where + ": " + _("\"above\" is the mod itself. Name the mod it "
                                                 "wins over (%s).")
                                % command("season.py", "whowins <a file it ships> --for "
                                          "\"%s\"" % name))
        # A above B and B above A: each launch would move one above the other, for ever
        looped = set()
        for start in toggle_mods:
            chain, cur = [], start
            while isinstance(cur, str) and cur in toggle_mods and cur not in chain:
                chain.append(cur)
                cfg = toggle_mods[cur]
                cur = cfg.get("above") if isinstance(cfg, dict) else None
            if cur in chain:
                loop = chain[chain.index(cur):]
                if len(loop) > 1 and frozenset(loop) not in looped:
                    looped.add(frozenset(loop))
                    problems.append("TOGGLE_MODS: " + _(
                        "%s each win over the next, in a circle, so play.bat would move them "
                        "at every launch. Make one of them win over a different mod.")
                        % " -> ".join(loop + [loop[0]]))

    stageable = list(SEASONS) + [n for n in periods if isinstance(n, str)]
    if not isinstance(layout, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        problems.append("LAYOUT " + _("must be a table, {mod folder: {...}}."))
    else:
        for name, cfg in layout.items():
            where = "LAYOUT[%r]" % (name,)
            bad = _folder_problem(name)
            if bad:
                problems.append(where + ": " + bad)
                continue
            if not isinstance(cfg, dict):
                # translators: follows an entry, like PERIODS['x'], which stays English
                problems.append(where + " " + _("must be {\"archive\": \"...\", \"options\": "
                                                "{...}}."))
                continue
            archive = cfg.get("archive")
            if not isinstance(archive, str) or not archive:
                problems.append(where + ": " + _("\"archive\" must be the name of a file in "
                                                 "downloads."))
            elif not archive.lower().endswith((".7z", ".rar")):
                problems.append(where + ": " + _("\"archive\" must be a .7z or .rar, which is "
                                                 "what season.py can open."))
            opts = cfg.get("options")
            if not isinstance(opts, dict) or not opts:
                problems.append(where + ": " + _("\"options\" must map each season to a list "
                                                 "of folder names in the archive."))
            else:
                for season, folders in opts.items():
                    if season not in stageable:
                        problems.append(where + ": " + _("%(name)s in \"options\" is not a "
                                                         "season or a period. Valid: "
                                                         "%(valid)s.")
                                        % {"name": _q(season), "valid": ", ".join(stageable)})
                    if (isinstance(folders, str) or not isinstance(folders, (list, tuple))
                            or not folders or not all(isinstance(f, str) for f in folders)):
                        problems.append(where + ": " + _("\"options\" for %s must be a list of "
                                                         "folder names, like [\"Spring\"].")
                                        % _q(season))

    if sound_src is not None:
        bad = _folder_problem(sound_src)
        if bad:
            # translators: follows a table's name, like PERIODS, which stays English
            problems.append("SOUND_SRC " + _("must be None or a mod's folder name in quotes."))
        elif sound_src in own:
            problems.append("SOUND_SRC " + (
                # translators: follows a table's name, like PERIODS, which stays English
                _("names %s, which season.py writes itself. Name the ambient sound mod to "
                  "read from.") if sound_src == SOUND_MOD else
                # translators: follows a table's name, like PERIODS, which stays English
                _("names %s, which is this mod itself. Name the ambient sound mod to read "
                  "from.")) % _q(sound_src))
    if calendar is not None:
        problems += calendar_problems(calendar)
    if names is not None:
        problems += names_problems(names)
    if place is not None:
        problems += place_problems(place)
    return problems


def _detect_nl(raw):
    crlf = chr(13) + chr(10)
    return crlf if crlf in raw else chr(10)


def _modlist_path():
    return os.path.join(ROOT, "profiles", profile_name(), "modlist.txt")


def _modlist_lines():
    try:
        raw = io.open(_modlist_path(), encoding="utf-8", errors="replace", newline="").read()
    except OSError:
        return None
    return raw.split(_detect_nl(raw))


def _mod_enabled(name):
    lines = _modlist_lines()
    return bool(lines) and any(l == "+" + name for l in lines)


# The mod is found by its main script, not its folder name: MO2 names a mod after the
# archive it was installed from, so the folder may be "SeasonsOfTheZone" or anything else.
MARKER = ("gamedata", "scripts", "zzz_seasons_of_the_zone.script")


def sotz_copies():
    """Every folder in mods/ holding this mod, the one MO2 loads first: enabled before
    disabled, then by priority (the top of modlist.txt wins)."""
    try:
        names = [n for n in os.listdir(MODS) if os.path.isfile(os.path.join(MODS, n, *MARKER))]
    except OSError:
        return []
    body = [l for l in (_modlist_lines() or []) if l[:1] in ("+", "-")]
    rank = {l[1:]: i for i, l in enumerate(body)}
    on = {l[1:] for l in body if l[:1] == "+"}
    return sorted(names, key=lambda n: (n not in on, rank.get(n, len(rank)), n))


SOTZ = (sotz_copies() or [SOTZ])[0]
PRESET_DIR = os.path.join(MODS, SOTZ, "gamedata", "configs", "seasons_presets")


def write_staged(season, staging=True):
    """Record which season the textures were staged for. The mod compares it with the
    season it is running and reports a mismatch. `staging` off means the texture layer is
    switched off, and the mod stays quiet about the difference."""
    d = os.path.join(MODS, SOTZ, "gamedata", "configs")
    if not os.path.isdir(d):
        return None
    p = os.path.join(d, "season_staged.ltx")
    body = ("[staged]" + chr(13) + chr(10)
            + "season = " + (season or "unknown") + chr(13) + chr(10)
            + "staging = " + ("on" if staging else "off") + chr(13) + chr(10)
            + "stamped = " + datetime.date.today().isoformat() + chr(13) + chr(10))
    io.open(p, "w", encoding="cp1251", newline="").write(body)
    return p


# --- the player's MCM choices -----------------------------------------------------------
#
# season.py runs before the game exists, so it reads MCM's own store: ui_mcm saves every
# setting into gamedata/configs/axr_options.ltx under [mcm], one line per option as
# "<tree>/<option> = <value>". Two files go the other way, written here and read by the
# mod: season_mods.ltx (the season-scoped mods and their state, which the MCM page is
# built from) and ui_mcm_seasons_mods.xml (their captions).
#
# Preferences only subtract: they can hold a mod back, never force one on out of season.
def _axr_options():
    """MCM's store, by MO2's rules: overwrite/ if it has the file, else the highest-priority
    enabled mod that ships it."""
    ow = os.path.join(ROOT, "overwrite", "gamedata", "configs", "axr_options.ltx")
    if os.path.isfile(ow):
        return ow
    lines = _modlist_lines()
    if lines is None:
        return None
    rank = {l[1:]: i for i, l in enumerate(lines) if l[:1] == "+"}
    best, best_rank = None, None
    for p in glob.glob(os.path.join(glob.escape(MODS), "*", "gamedata", "configs",
                                    "axr_options.ltx")):
        mod = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p))))
        r = rank.get(mod)
        if r is not None and (best_rank is None or r < best_rank):
            best, best_rank = p, r
    return best


def _slug(name):
    """Stable key for a mod folder; it becomes the MCM option id."""
    s = "".join(c if c.isalnum() else "_" for c in name.lower())
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:48]


def _display(name):
    """The folder name without a trailing "(seasonal)"-style suffix."""
    i = name.rfind(" (")
    return name[:i] if i > 0 and name.endswith(")") else name


def _drop_season(name):
    """"Grass and Trees - Summer" -> "Grass and Trees". Every season has its own MCM
    page, so a season in the mod's own name is said twice on screen."""
    low = name.lower()
    for s in SEASONS:
        tail = " - " + default_label(s)
        if low.endswith(tail):
            return name[:-len(tail)]
    return name


def default_label(s):
    """The name a season goes by unless the player gives it one, in English: what people
    type for it, and what names are checked against. season_label() is what to show."""
    return {"winter_snow": "deep winter", "late_winter": "late winter"}.get(s, s)


def usual_name(s):
    """A season's usual name in the player's language; any other name as it is."""
    return {"spring": pgettext("season", "spring"), "summer": pgettext("season", "summer"),
            "autumn": pgettext("season", "autumn"), "winter": pgettext("season", "winter"),
            "winter_snow": pgettext("season", "deep winter"),
            "late_winter": pgettext("season", "late winter")}.get(s, s)


def season_label(s, names=None):
    """How a season is shown: the player's own name for it (NAMES), else its usual one in
    the player's language. Anything else - a season of their own, an event - as it is."""
    names = NAMES if names is None else names
    v = names.get(s) if isinstance(names, dict) else None
    return v.strip() if isinstance(v, str) and v.strip() else usual_name(s)


def english_label(s, names=None):
    """season_label() in English: the player's own name for it, else default_label(). What
    names are checked against, whatever the language, and what the game's files take."""
    names = NAMES if names is None else names
    v = names.get(s) if isinstance(names, dict) else None
    return v.strip() if isinstance(v, str) and v.strip() else default_label(s)


def custom_names(names=None):
    """{season: name} for each season the player has renamed."""
    names = NAMES if names is None else names
    if not isinstance(names, dict):
        return {}
    return {s: v.strip() for s, v in names.items() if s in SEASONS and isinstance(v, str)
            and v.strip() and v.strip() != default_label(s)}


PLACE_CHARS = 24            # the longest place name the PDA's Forecast page has room for
# where the weather comes from unless WEATHER_PLACE says otherwise
DEFAULT_PLACE = {"name": "Chornobyl", "lat": 51.2763, "lon": 30.2219}


def place_words(place=None):
    """Where the weather comes from, in words: "Kyiv (50.45 N, 30.52 E)"."""
    p = place or DEFAULT_PLACE
    north, east = p["lat"] >= 0, p["lon"] >= 0
    # translators: a place and where it is: N north, S south, E east, W west
    text = (_("%(name)s (%(lat).2f N, %(lon).2f E)") if north and east else
            _("%(name)s (%(lat).2f N, %(lon).2f W)") if north else
            _("%(name)s (%(lat).2f S, %(lon).2f E)") if east else
            _("%(name)s (%(lat).2f S, %(lon).2f W)"))
    return text % {"name": p["name"], "lat": abs(p["lat"]), "lon": abs(p["lon"])}


def weather_place():
    """The place the config names, when season.py can use it; Chornobyl otherwise."""
    if isinstance(WEATHER_PLACE, dict) and not place_problems(WEATHER_PLACE):
        return WEATHER_PLACE
    return DEFAULT_PLACE


def place_problems(place):
    """What is wrong with a WEATHER_PLACE, one sentence each: [] for one that can be used."""
    if not isinstance(place, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["WEATHER_PLACE " + _("must be a table like {\"name\": \"Kyiv\", \"lat\": "
                                     "50.45, \"lon\": 30.52}, or None for Chornobyl.")]
    out = []
    extra = sorted((str(k) for k in place if k not in ("name", "lat", "lon")))
    if extra:
        out.append("WEATHER_PLACE: " + ngettext(
            "%s is not one of its parts, which are name, lat and lon.",
            "%s are not one of its parts, which are name, lat and lon.", len(extra))
            % ", ".join(extra))
    name = place.get("name")
    if not isinstance(name, str) or not name.strip():
        out.append("WEATHER_PLACE: " + _("give the place a name in quotes, like \"Kyiv\"."))
    elif len(name.strip()) > PLACE_CHARS:
        out.append("WEATHER_PLACE: " + ngettext(
            "the name \"%(name)s\" is %(n)d character; the PDA has room for %(most)d.",
            "the name \"%(name)s\" is %(n)d characters; the PDA has room for %(most)d.",
            len(name.strip())) % {"name": name.strip(), "n": len(name.strip()),
                                  "most": PLACE_CHARS})
    elif any(ord(c) < 32 for c in name) or any(c in name for c in ";[]="):
        out.append("WEATHER_PLACE: " + _("the name can't contain ; [ ] = or a line break."))
    v = place.get("lat")
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or not -90 <= v <= 90:
        # translators: %s is lat, as the config spells it
        out.append("WEATHER_PLACE: " + _("%s must be the latitude in degrees, -90 to 90, "
                                         "north and east positive, like 50.45.") % "lat")
    v = place.get("lon")
    if (isinstance(v, bool) or not isinstance(v, (int, float)) or v != v
            or not -180 <= v <= 180):
        # translators: %s is lon, as the config spells it
        out.append("WEATHER_PLACE: " + _("%s must be the longitude in degrees, -180 to 180, "
                                         "north and east positive, like 30.52.") % "lon")
    return out


def names_problems(names):
    """What is wrong with a NAMES table, one sentence each."""
    if not isinstance(names, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["NAMES " + _("must be a table, {season: \"its name\"}, or None for the usual "
                             "names.")]
    out = []
    for s, name in names.items():
        where = "NAMES[%r]" % (s,)
        if s not in SEASONS:
            out.append(where + ": " + _("not a season. The seasons are: %s.")
                       % ", ".join(SEASONS))
        elif not isinstance(name, str) or not name.strip():
            out.append(where + ": " + _("give the name in quotes, like \"The Long Cold\", or "
                                        "take the line out."))
        elif len(name.strip()) > NAME_CHARS:
            out.append(where + ": " + ngettext(
                "the name \"%(name)s\" is %(n)d character; the dial and the PDA have room for "
                "%(most)d.",
                "the name \"%(name)s\" is %(n)d characters; the dial and the PDA have room for "
                "%(most)d.", len(name.strip()))
                % {"name": name.strip(), "n": len(name.strip()), "most": NAME_CHARS})
        elif any(ord(c) < 32 for c in name) or any(c in name for c in ";[]"):
            out.append(where + ": " + _("the name can't contain ; [ ] or a line break."))
        else:
            try:
                name.encode("cp1251")
            except UnicodeEncodeError:
                out.append(where + ": " + _("the name \"%s\" has letters the game can't show. "
                                            "Use English or Cyrillic letters.") % name.strip())
    if not out:
        # the names as the config has them, so a name clashes in every language alike
        seen = {}
        for s in SEASONS:
            shown = english_label(s, names)
            if shown.casefold() in seen:
                first, first_shown = seen[shown.casefold()]
                # the name as the player typed it, if either one is theirs
                typed = first_shown if first_shown != default_label(first) else shown
                out.append("NAMES: " + _("%(first)s and %(second)s would both be called "
                                         "\"%(name)s\". Give one of them another name.")
                           % {"first": usual_name(first), "second": usual_name(s),
                              "name": cap_first(typed)})
            seen.setdefault(shown.casefold(), (s, shown))
    return out


def seasons_text(seasons):
    """"winter", "winter and deep winter", "winter, deep winter and late winter", in the
    player's language."""
    return lang.and_list(season_label(s) for s in seasons)


def seasons_english(seasons):
    """seasons_text() in English, for the files the game reads."""
    words = [english_label(s) for s in seasons]
    if len(words) < 3:
        return " and ".join(words)
    return ", ".join(words[:-1]) + " and " + words[-1]


def read_prefs():
    """The MCM choices, from MCM's store. Global switches are seasons_zone/main/<id>; a
    per-season mod hold is seasons_zone/<season>/mod_<slug>. Returns {"stage_textures",
    "stage_sound", "off": {season: set(slug)}}. No file yet means defaults."""
    out = {"stage_textures": True, "stage_sound": True, "mode": "auto",
           "off": {s: set() for s in SEASONS}}
    p = _axr_options()
    if not p:
        return out
    try:
        raw = io.open(p, encoding="cp1251", errors="replace", newline="").read()
    except OSError:
        return out
    for line in raw.splitlines():
        line = line.split(";")[0].strip()
        if not line.startswith("seasons_zone/") or "=" not in line:
            continue
        k, v = [x.strip() for x in line.split("=", 1)]
        page, _, o = k[len("seasons_zone/"):].partition("/")
        off = v.lower() in ("false", "off", "0", "no")
        if page == "main" and o == "mode":
            out["mode"] = v.strip().lower()
        elif page == "main" and o == "stage_textures":
            out["stage_textures"] = not off
        elif page == "main" and o == "stage_sound":
            out["stage_sound"] = not off
        elif o.startswith("mod_") and off and page in out["off"]:
            out["off"][page].add(o[4:])       # a mod held for that one season
    return out


# the seasonal mods apply_toggles() could not place, for the summary line
SKIPPED = []


def _find(body, name):
    """The index of `name`'s line in modlist.txt's lines, or None."""
    return next((i for i, l in enumerate(body) if l[:1] in ("+", "-") and l[1:] == name),
                None)


def _place(body, name, above, want):
    """Put `name` just above `above` in modlist.txt's lines (a lower line has the higher
    priority) and set it to `want`, "+" or "-", as apply does. Returns (was, now) for a
    change, None for none, or False when `above` is not in the list."""
    idx, ref = _find(body, name), _find(body, above)
    if ref is None:
        return False
    if idx is None:
        body.insert(ref, want + name)
        return "absent", want
    if idx > ref:
        body.pop(idx)
        body.insert(_find(body, above), want + name)
        return "misplaced", want
    if body[idx][:1] != want:
        was = body[idx][:1]
        body[idx] = want + name
        return was, want
    return None


def change_text(was, now):
    """A change apply_toggles() makes, in words: "disabled -> enabled", "added, enabled"."""
    return {("absent", "+"): _("added, enabled"), ("absent", "-"): _("added, disabled"),
            ("misplaced", "+"): _("moved, enabled"), ("misplaced", "-"): _("moved, disabled"),
            ("-", "+"): _("disabled -> enabled"), ("+", "-"): _("enabled -> disabled")}[
                (was, now)]


def apply_toggles(active, dry_run=False, prefs=None):
    """Enable or disable the seasonal mods and put each just above the mod it wins over.
    Returns [(name, from, to)] for what changed. With the texture layer off, every
    seasonal mod is disabled."""
    prefs = prefs if prefs is not None else read_prefs()
    active = [active] if isinstance(active, str) else list(active)
    base, active_set = active[0], set(active)
    p = _modlist_path()
    raw = io.open(p, encoding="utf-8", errors="replace", newline="").read()
    nl = _detect_nl(raw)
    lines = raw.split(nl)
    if not lines or not lines[0].startswith("#"):
        raise SystemExit("  " + _("MO2's mod list (%s) does not start with MO2's header "
                                  "line, so no seasonal mod was switched.")
                         % ("profiles\\%s\\modlist.txt" % profile_name()))

    head, body = lines[0], lines[1:]
    changed = []
    folders = _mod_folders()
    del SKIPPED[:]
    for name, cfg in TOGGLE_MODS.items():
        if name not in folders:
            continue
        # A mod is on if ANY period it is scoped to is active today - that is what
        # makes an event additive on top of its season. MCM holds are per base
        # period, because that is what has a page.
        on = (bool(set(_when(cfg)) & active_set)
              and prefs["stage_textures"]
              and _slug(name) not in prefs["off"].get(base, set()))
        got = _place(body, name, cfg["above"], "+" if on else "-")
        if got is False:
            print("  ! " + _("%(mod)s skipped: the mod it wins over, \"%(above)s\", is not in "
                             "MO2's mod list.") % {"mod": name[:40], "above": cfg["above"]})
            print("    " + _("Pick another in its \"Wins over\" box in configure.bat."))
            SKIPPED.append(name)
        elif got:
            changed.append((name,) + got)

    # The generated soundscape is placed too: a folder MO2 finds on its own is added
    # disabled, and it has to sit above its source.
    if SOUND_SRC and _find(body, SOUND_SRC) is not None:
        have = os.path.isdir(os.path.join(MODS, SOUND_MOD))
        if have or _find(body, SOUND_MOD) is not None:
            on = have and prefs["stage_sound"] and _mod_enabled(SOUND_SRC)
            got = _place(body, SOUND_MOD, SOUND_SRC, "+" if on else "-")
            if got:
                changed.append((SOUND_MOD,) + got)

    if changed and not dry_run:
        # MO2 rewrites modlist.txt from memory on exit, so an edit made while it is open
        # is lost.
        busy = running()
        if busy:
            raise SystemExit(close_first(busy))
        bk = os.path.join(ROOT, "_baseline", "modfile-backups")
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(p, os.path.join(bk, "modlist-%s-pre-toggle.txt"
                                     % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
        io.open(p, "w", encoding="utf-8", newline="").write(nl.join([head] + body))
    return changed


def _mod_folders():
    """The folders in mods/, spelled exactly. Windows finds "winter pack" for "Winter
    Pack", but modlist.txt does not, and a line for a name MO2 has no folder under is a
    line MO2 cannot use."""
    try:
        return set(os.listdir(MODS))
    except OSError:
        return set()


def near_folder(name, folders=None):
    """The folder `name` was probably meant to be, or None."""
    folders = _mod_folders() if folders is None else folders
    key = str(name).strip().rstrip(".").lower()
    return next((f for f in sorted(folders) if f.lower() == key), None)


def toggle_status(active, prefs=None):
    """[(name, installed, state, wanted, held)] for each seasonal mod. `held` is why a
    wanted mod stays off: "off" (texture layer off), "mod" (unchecked in MCM), None."""
    prefs = prefs if prefs is not None else read_prefs()
    active = [active] if isinstance(active, str) else list(active)
    base, active_set = active[0], set(active)
    body = (_modlist_lines() or [])[1:]
    folders = _mod_folders()
    out = []
    for name, cfg in TOGGLE_MODS.items():
        installed = name in folders
        state = next((l[:1] for l in body if l[:1] in ("+", "-") and l[1:] == name), None)
        held = None
        if not prefs["stage_textures"]:
            held = "off"
        elif _slug(name) in prefs["off"].get(base, set()):
            held = "mod"
        out.append((name, installed, state, bool(set(_when(cfg)) & active_set), held))
    return out


# --- seasonal soundscape ------------------------------------------------------------------
#
# Ambient presets list their sound channels in plain text:
#     sound_channels_dynamic = wind_normal, birds, Insects, birds_night, ...
# so gating insects out of winter is a text edit. The generated files override the source
# mod's, and are rebuilt per season. SOUND_SRC must be the mod that wins those files.
SOUND_MOD = "Seasonal Soundscape"
SOUND_REL = ("configs", "environment", "ambients", "presets")

# Channels removed per season. Wind, storms, drones and interiors are never touched;
# birds_night (owls and crows) stays all year. The case of "Insects" varies between the
# files, so both spellings are listed.
#
#   spring       crickets are a summer and autumn night sound, so spring nights are owls
#                and the dawn chorus carries the season on its own
#   summer       nothing cut - the full soundscape, and the baseline the rest are read against
#   autumn       day insects are gone by October, but crickets call at night until the
#                first frost, so Insects_night stays; the waders have left the marshes
#   winter       nothing stridulates below freezing
#   winter_snow  corvids and owls only
#   late_winter  the thaw brings the waterfowl back to the marshes before any insect
#                stirs
#
# Each season must leave a different set of channels standing, or two of them sound
# alike; _tools/test_soundscape.py checks that.
SOUND_CUT = {
    "spring":      ("Insects_night",),
    "summer":      (),
    "autumn":      ("Insects", "insects", "birds_swamp"),
    "winter":      ("Insects", "insects", "Insects_night", "birds_swamp"),
    "winter_snow": ("Insects", "insects", "Insects_night", "birds_swamp", "birds"),
    "late_winter": ("Insects", "insects", "Insects_night"),
}

SOUND_TAG = ";; seasonal-soundscape season="
SOUND_SIG = " cuts="


def _sound_signature(season):
    """Short hash of the channels cut for `season`. It goes in the marker so that
    editing SOUND_CUT makes the generated files stale even when the season has not
    moved - otherwise the edit silently does nothing until the season turns."""
    raw = ",".join(sorted(SOUND_CUT.get(season, ())))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]


def _sound_src_dir():
    """The source presets folder, or None when no source is configured or the source mod
    is disabled."""
    if not SOUND_SRC or not _mod_enabled(SOUND_SRC):
        return None
    return os.path.join(MODS, SOUND_SRC, "gamedata", *SOUND_REL)


def _sound_dst_dir():
    return os.path.join(MODS, SOUND_MOD, "gamedata", *SOUND_REL)


def _strip_channels(line, cut):
    """Remove the named channels from one sound_channels_dynamic line, keeping its
    spacing and any trailing ';'."""
    m = re.match(r"^(\s*sound_channels_dynamic\s*=\s*)(.*?)(;?\s*)$", line)
    if not m:
        return line
    head, body, tail = m.group(1), m.group(2), m.group(3)
    kept = [c for c in (x.strip() for x in body.split(",")) if c and c not in cut]
    return head + ", ".join(kept) + tail


def write_soundscape(season, enabled=True):
    """Regenerate the presets for `season`. Returns (files, channels removed). Disabled
    removes the generated folder so the source mod wins again."""
    src = _sound_src_dir()
    if not src or not os.path.isdir(src):
        return None, 0
    dst = _sound_dst_dir()
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    if not enabled:
        return 0, 0
    os.makedirs(dst)
    cut = set(SOUND_CUT.get(season, ()))
    n = removed = 0
    for f in sorted(os.listdir(src)):
        if not f.lower().endswith(".ltx"):
            continue
        raw = io.open(os.path.join(src, f), encoding="cp1251",
                      errors="replace", newline="").read()
        nl = _detect_nl(raw)
        out = []
        for line in raw.split(nl):
            new = _strip_channels(line, cut) if "sound_channels_dynamic" in line else line
            if new != line:
                removed += 1
            out.append(new)
        body = nl.join([SOUND_TAG + season + SOUND_SIG + _sound_signature(season)]
                       + out)
        io.open(os.path.join(dst, f), "w", encoding="cp1251", newline="").write(body)
        n += 1
    return n, removed


def soundscape_installed():
    """The season the generated presets are for, from the marker on their first line."""
    d = _sound_dst_dir()
    if not os.path.isdir(d):
        return None
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".ltx"):
            first = io.open(os.path.join(d, f), encoding="cp1251",
                            errors="replace").readline().strip()
            if first.startswith(SOUND_TAG):
                payload = first[len(SOUND_TAG):].strip()
                return payload.split(SOUND_SIG.strip())[0].strip()
            return None
    return None


def soundscape_signature():
    """The cut signature the generated presets were written with, or None for files
    written before the marker carried one."""
    d = _sound_dst_dir()
    if not os.path.isdir(d):
        return None
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".ltx"):
            first = io.open(os.path.join(d, f), encoding="cp1251",
                            errors="replace").readline().strip()
            if SOUND_SIG.strip() in first:
                return first.split(SOUND_SIG.strip())[1].strip() or None
            return None
    return None


def _mod_weight(folder):
    """(files, bytes) under gamedata/ and db/ - what MO2 mounts, not meta.ini."""
    n, b = 0, 0
    for sub in ("gamedata", "db"):
        for root, _, files in os.walk(os.path.join(folder, sub)):
            for f in files:
                n += 1
                try:
                    b += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass
    return n, b


def _xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def write_mod_panel(active, prefs=None):
    """Write season_mods.ltx and ui_mcm_seasons_mods.xml, which the MCM page is built
    from. Rewritten every launch from what is on disk."""
    prefs = prefs if prefs is not None else read_prefs()
    active = [active] if isinstance(active, str) else list(active)
    base = active[0]
    d = os.path.join(MODS, SOTZ, "gamedata", "configs")
    if not os.path.isdir(d):
        return None
    status = {n: (inst, st, want, held) for n, inst, st, want, held in
              toggle_status(active, prefs)}
    crlf = chr(13) + chr(10)

    rows = []
    for name, cfg in TOGGLE_MODS.items():
        inst, state, want, held = status[name]
        if not inst:
            continue
        n, b = _mod_weight(os.path.join(MODS, name))
        rows.append({
            "key": _slug(name), "name": _display(name), "folder": name,
            "seasons": list(_when(cfg)), "files": n, "mb": b / 1048576.0,
            "enabled": state == "+", "wanted": want, "held": held,
        })

    # Grouped under the first season each mod serves, in calendar order. An MCM option id
    # can exist only once, so a mod spanning seasons is listed once; its span is in the
    # label and hover text.
    rows.sort(key=lambda r: (_order(r["seasons"][0]), r["name"].lower()))
    for r in rows:
        r["group"] = r["seasons"][0]
        r["caption"] = _drop_season(r["name"])

    # Dropping the season can leave two mods on one page reading alike - a user may
    # well have "<something> - Winter" and "<something> - Deep winter" both in winter.
    # Where that happens, both keep their full names.
    # NB: this loop variable must not be called `season`. It once shadowed the season
    # being staged, so every later use read the LAST name in SEASONS instead.
    for s_page in SEASONS:
        by_caption = {}
        for r in rows:
            if s_page in r["seasons"]:
                by_caption.setdefault(r["caption"], []).append(r)
        for clash in by_caption.values():
            if len(clash) > 1:
                for r in clash:
                    r["caption"] = r["name"]

    _ssrc = _sound_src_dir()
    sound_have = bool(_ssrc) and os.path.isdir(_ssrc)
    sound_cuts = 0
    if sound_have and prefs["stage_sound"]:
        cut = set(SOUND_CUT.get(base, ()))
        for f in sorted(os.listdir(_ssrc)):
            if not f.lower().endswith(".ltx"):
                continue
            raw = io.open(os.path.join(_ssrc, f), encoding="cp1251",
                          errors="replace", newline="").read()
            for line in raw.split(_detect_nl(raw)):
                if "sound_channels_dynamic" in line and _strip_channels(line, cut) != line:
                    sound_cuts += 1

    lines = ["; generated by _tools/season.py on every launch - do not edit by hand",
             "[mods]",
             "staged_for = " + (base or "unknown"),
             "stage_textures = " + ("on" if prefs["stage_textures"] else "off"),
             "stage_sound = " + ("on" if prefs["stage_sound"] else "off"),
             "sound_available = " + ("true" if sound_have else "false"),
             "sound_cuts = %d" % sound_cuts,
             "list = " + ",".join(r["key"] for r in rows)]
    for r in rows:
        lines += ["", "[" + r["key"] + "]",
                  "name = " + r["name"],
                  "folder = " + r["folder"],
                  "seasons = " + ",".join(r["seasons"]),
                  "group = " + r["group"],
                  # underscore, not a space: X-Ray strips internal whitespace from an ltx
                  # value. The mod turns it back into a space. English, as the game's files
                  # are: the tools' language is not the game's.
                  "group_label = " + cap_first(english_label(r["group"])).replace(" ", "_"),
                  "span = " + seasons_english(r["seasons"]),
                  "files = %d" % r["files"],
                  "mb = " + ("%.1f" % r["mb"] if r["mb"] < 10 else "%.0f" % r["mb"]),
                  "enabled = " + ("true" if r["enabled"] else "false"),
                  "wanted = " + ("true" if r["wanted"] else "false")]
    manifest = os.path.join(d, "season_mods.ltx")
    io.open(manifest, "w", encoding="cp1251", errors="replace",
            newline="").write(crlf.join(lines) + crlf)

    # Captions. Anomaly loads every .xml under configs/text/<lang>/ by filename.
    x = ['<?xml version="1.0" encoding="windows-1251"?>', "",
         "<!-- generated by _tools/season.py - one entry per installed season-scoped",
         "     mod, so the MCM page lists whatever is actually present. -->",
         "<string_table>"]
    for r in rows:
        seas = seasons_english(r["seasons"])
        mb = ("{:,.1f}".format(r["mb"]) if r["mb"] < 10 else "{:,.0f}".format(r["mb"]))
        desc = ("%s. %s files, %s MB. Uncheck to leave it out of this season."
                % (cap_first(seas), "{:,}".format(r["files"]), mb))
        caption = r["caption"]
        x += ['\t<string id="ui_mcm_seasons_zone_mod_%s"><text>%s</text></string>'
              % (r["key"], _xml_escape(caption)),
              '\t<string id="ui_mcm_seasons_zone_mod_%s_desc"><text>%s</text></string>'
              % (r["key"], _xml_escape(desc))]
    x += ["</string_table>", ""]
    xd = os.path.join(d, "text", "eng")
    os.makedirs(xd, exist_ok=True)
    io.open(os.path.join(xd, "ui_mcm_seasons_mods.xml"),
            "w", encoding="cp1251", errors="replace", newline="").write(chr(10).join(x))
    return manifest


def cap_first(s):
    return s[:1].upper() + s[1:] if s else s


def staged_texture_season(installed):
    """The season the staged textures are, or None if the LAYOUT mods disagree."""
    vals = set(v for v in installed.values() if v)
    return vals.pop() if len(vals) == 1 else None


# (season, month, day) - the start of each season
PHENO = [("winter_snow", 12, 1), ("late_winter", 3, 5), ("spring", 4, 15),
         ("summer", 5, 20), ("autumn", 9, 15), ("winter", 11, 1)]
MET = [("winter_snow", 12, 1), ("late_winter", 3, 1), ("spring", 4, 1),
       ("summer", 6, 1), ("autumn", 9, 1), ("winter", 11, 1)]

# The earlier prototype. It drives the same flora and fog values as the mod, so the two
# must never be enabled together; this name is only used to warn.
FLORA_MOD = "Season Flora"


# --- color grade presets ----------------------------------------------------------------
#
# The mod ships its season grades as cfg_load presets (Seasons_*.ltx). They are copied
# into the game's appdata/ beside Atmospherics' Atmos_*.ltx, so they can be picked per
# season on the MCM page, cfg_load-ed by hand, or edited in place. An existing copy is
# never overwritten.
def install_presets(write):
    """Returns (shipped names, names already in appdata, names copied this run)."""
    if not os.path.isdir(PRESET_DIR):
        return [], [], []
    shipped = sorted(f for f in os.listdir(PRESET_DIR) if f.lower().endswith(".ltx"))
    present = [f for f in shipped if os.path.isfile(os.path.join(APPDATA, f))]
    copied = []
    if write and os.path.isdir(APPDATA):
        for f in shipped:
            if f not in present:
                shutil.copy2(os.path.join(PRESET_DIR, f), os.path.join(APPDATA, f))
                copied.append(f)
    return shipped, present, copied


# --- the calendar -----------------------------------------------------------------------
#
# CALENDAR in seasons_config.py moves the seasons or turns some off. A season it leaves
# out is off, and the one before it runs on until the next starts. The game reads the
# same dates from configs/season_calendar.ltx, which write_calendar() makes at every
# launch, and a custom calendar gets its own dial, drawn here because the shipped one has
# Polesia's season lengths baked in.

MIN_SEASON_DAYS = 14        # every season gets a dial position and a full blend window
MONTH_DAYS = (31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
CALENDAR_REL = ("configs", "season_calendar.ltx")
DIALS = 32
DIAL_PREFIX = "ui_seasons_dial_c"


def _md(m, d):
    """A day of the year in short, in the player's language: "Aug 1"."""
    return lang.day(m, d)


def season_lengths(starts):
    """{season: days} for {season: (month, day)}, measured in a year without Feb 29."""
    order = sorted((int(m), int(d), s) for s, (m, d) in starts.items())
    out = {}
    for i, (m, d, s) in enumerate(order):
        nm, nd, _ = order[(i + 1) % len(order)]
        a = datetime.date(2026, m, d).toordinal()
        b = datetime.date(2026, nm, nd).toordinal()
        out[s] = (b - a) if b > a else (b + 365 - a)
    return out


def calendar_problems(calendar):
    """What is wrong with a CALENDAR table, one sentence each."""
    if not isinstance(calendar, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["CALENDAR " + _("must be a table, {season: (month, day)}, or None for "
                                "Polesia's dates.")]
    if not calendar:
        # translators: follows a table's name, like PERIODS, which stays English
        return ["CALENDAR " + _("turns every season off. At least one has to stay on.")]
    out, seen = [], {}
    for s, md in calendar.items():
        where = "CALENDAR[%r]" % (s,)
        if s not in SEASONS:
            out.append(where + ": " + _("not a season. The seasons are: %s.")
                       % ", ".join(SEASONS))
            continue
        if not _is_day(md, leap=True):
            out.append(where + ": " + _("the start must be (month, day), like (5, 20)."))
            continue
        m, d = md
        if (m, d) == (2, 29):
            # translators: follows an entry, like PERIODS['x'], which stays English
            out.append(where + " " + _("can't start on February 29, which three years in four "
                                       "don't have. Use February 28 or March 1."))
        elif (m, d) in seen:
            out.append("CALENDAR: " + _("%(first)s and %(second)s both start on %(day)s. Give "
                                        "each season its own day.")
                       % {"first": season_label(seen[(m, d)]), "second": season_label(s),
                          "day": _md(m, d)})
        else:
            seen[(m, d)] = s
    if not out and len(seen) > 1:
        for s, days in season_lengths(calendar).items():
            if days < MIN_SEASON_DAYS:
                # translators: English says "days" for 1 too
                out.append("CALENDAR: " + ngettext(
                    "%(season)s would last %(days)d days. A season needs at least %(least)d.",
                    "%(season)s would last %(days)d days. A season needs at least %(least)d.",
                    days) % {"season": season_label(s), "days": days,
                             "least": MIN_SEASON_DAYS})
    return out


def own_days(win):
    """How many days a window ((month, day), (month, day)) covers, both ends counted, in a
    year without February 29. A start after its end runs across the new year."""
    a = datetime.date(2026, *win[0]).toordinal()
    b = datetime.date(2026, *win[1]).toordinal()
    return b - a + 1 if b >= a else b + 365 - a + 1


def _already(kind):
    """The refusal for a name that is taken, by what took it: "season", "own", "period",
    "event" or "weather"."""
    return {"season": _("that is already the name of a season. Give it another name."),
            "own": _("that is already a season of your own. Give it another name."),
            "period": _("that is already a period. Give it another name."),
            "event": _("that is already an event. Give it another name."),
            "weather": _("that is already a kind of weather. Give it another name.")}[kind]


def own_problems(own, periods=(), events=(), names=None):
    """What is wrong with an OWN_SEASONS table, one sentence each. `names` is the NAMES
    table the seasons go by, so a season of one's own can't take one of theirs."""
    if not isinstance(own, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["OWN_SEASONS " + _("must be a table, {name: ((month, day), (month, day))}, "
                                   "or {} for none.")]
    out = []
    if len(own) > OWN_MOST:
        out.append("OWN_SEASONS: " + ngettext(
            "%(n)d season of your own, and the year has room for %(most)d, a week each. Take "
            "some out.",
            "%(n)d seasons of your own, and the year has room for %(most)d, a week each. Take "
            "some out.", len(own)) % {"n": len(own), "most": OWN_MOST})
    # names as the config has them, so a name is taken in every language alike
    taken = {}
    for s in SEASONS:
        for n in (s, default_label(s), english_label(s, names or {})):
            taken[n.casefold()] = "season"
    for what, table in (("period", periods), ("event", events)):
        for n in table:
            if isinstance(n, str):
                taken.setdefault(n.casefold(), what)
    for n in WEATHER_NAMES:
        taken[n] = "weather"
    seen = {}
    for name, win in own.items():
        where = "OWN_SEASONS[%r]" % (name,)
        if not isinstance(name, str) or not name.strip():
            out.append(where + ": " + _("give the season a name in quotes, like \"Wormhole "
                                        "season\"."))
            continue
        if name != name.strip():
            out.append(where + ": " + _("the name has spaces at its start or end. Take them "
                                        "out."))
        elif len(name) > OWN_NAME_CHARS:
            out.append(where + ": " + ngettext(
                "the name is %(n)d character long; it can have %(most)d at most.",
                "the name is %(n)d characters long; it can have %(most)d at most.", len(name))
                % {"n": len(name), "most": OWN_NAME_CHARS})
        elif any(ord(c) < 32 or ord(c) == 127 for c in name):
            out.append(where + ": " + _("the name can't contain a line break or a tab."))
        elif name.casefold() in taken:
            out.append(where + ": " + _already(taken[name.casefold()]))
        elif name.casefold() in seen:
            out.append(where + ": " + _("%s is a season of yours already. Give this one "
                                        "another name.") % _q(seen[name.casefold()]))
        seen.setdefault(name.casefold(), name)
        if not (isinstance(win, (tuple, list)) and len(win) == 2
                and all(_is_day(x, leap=True) for x in win)):
            out.append(where + ": " + _("give its first and last day, like ((8, 1), (8, 31))."))
        elif (2, 29) in (tuple(win[0]), tuple(win[1])):
            # translators: follows an entry, like PERIODS['x'], which stays English
            out.append(where + " " + _("can't start or end on February 29, which three years "
                                       "in four don't have. Use February 28 or March 1."))
        elif own_days(win) < OWN_MIN_DAYS:
            n = own_days(win)
            out.append(where + ": " + ngettext(
                "it runs %(n)d day, %(first)s to %(last)s. A season of your own runs at least "
                "a week.",
                "it runs %(n)d days, %(first)s to %(last)s. A season of your own runs at least "
                "a week.", n) % {"n": n, "first": _md(*win[0]), "last": _md(*win[1])})
    return out


def spell_days(spec):
    """(fewest, most) days a spell runs; "days" is a number or a pair."""
    d = spec.get("days", 1)
    return (d, d) if isinstance(d, int) else (int(d[0]), int(d[1]))


def spell_problems(spells, on=SEASONS, own=(), periods=(), events=(), names=None):
    """What is wrong with a SPELLS table, one sentence each. `on` is the seasons the
    calendar has on; `own` the player's own seasons, which a spell can start in too."""
    if not isinstance(spells, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["SPELLS " + _("must be a table, {name: {\"in\": (\"summer\",), \"chance\": 3, "
                              "\"days\": (1, 2), \"as\": \"winter\"}}, or {} for none.")]
    out = []
    # names as the config has them, so a name is taken in every language alike
    taken = {}
    for s in SEASONS:
        for n in (s, default_label(s), english_label(s, names or {})):
            taken[n.casefold()] = "season"
    for what, table in (("own", own), ("period", periods), ("event", events)):
        for n in table:
            if isinstance(n, str):
                taken.setdefault(n.casefold(), what)
    for n in WEATHER_NAMES:
        taken[n] = "weather"
    seen = {}
    for name, spec in spells.items():
        where = "SPELLS[%r]" % (name,)
        if not isinstance(name, str) or not name.strip():
            out.append(where + ": " + _("give the spell a name in quotes, like \"Summer "
                                        "frost\"."))
            continue
        if name != name.strip():
            out.append(where + ": " + _("the name has spaces at its start or end. Take them "
                                        "out."))
        elif len(name) > OWN_NAME_CHARS:
            out.append(where + ": " + ngettext(
                "the name is %(n)d character long; it can have %(most)d at most.",
                "the name is %(n)d characters long; it can have %(most)d at most.", len(name))
                % {"n": len(name), "most": OWN_NAME_CHARS})
        elif any(ord(c) < 32 for c in name) or any(c in name for c in ";[]="):
            out.append(where + ": " + _("the name can't contain ; [ ] = or a line break."))
        elif not _cp1251(name):
            out.append(where + ": " + _("the name has letters the game can't show. Use "
                                        "English or Cyrillic letters."))
        elif name.casefold() in taken:
            out.append(where + ": " + _already(taken[name.casefold()]))
        elif name.casefold() in seen:
            out.append(where + ": " + _("%s is a spell already. Give this one another name.")
                       % _q(seen[name.casefold()]))
        seen.setdefault(name.casefold(), name)
        if not isinstance(spec, dict):
            # translators: follows an entry, like PERIODS['x'], which stays English
            out.append(where + " " + _("must be {\"in\": (\"summer\",), \"chance\": 3, "
                                       "\"days\": (1, 2), \"as\": \"winter\"}."))
            continue
        odd = [k for k in spec if k not in SPELL_KEYS]
        if odd:
            out.append(where + ": " + ngettext(
                "%(keys)s is not a part of a spell. The parts are %(parts)s.",
                "%(keys)s are not parts of a spell. The parts are %(parts)s.", len(odd))
                % {"keys": _and(_q(k) for k in odd), "parts": _and(SPELL_KEYS)})
        start = spec.get("in")
        start = (start,) if isinstance(start, str) else start
        if not isinstance(start, (tuple, list)) or not start:
            out.append(where + ": " + _("\"in\" names the seasons it can start in, like "
                                        "(\"summer\",)."))
        else:
            bad = [str(x) for x in start if x not in SEASONS and x not in own]
            off = [x for x in start if x in SEASONS and x not in on]
            if bad:
                out.append(where + ": " + ngettext(
                    "\"in\" names %(names)s, which is not a season. The seasons are "
                    "%(seasons)s.",
                    "\"in\" names %(names)s, which are not seasons. The seasons are "
                    "%(seasons)s.", len(bad))
                    % {"names": _and(_q(x) for x in bad), "seasons": _and(SEASONS)})
            elif off and len(off) == len(start):
                out.append(where + ": " + ngettext(
                    "%s is off in your calendar, so it never starts.",
                    "%s are off in your calendar, so it never starts.", len(off))
                    % _and(season_label(x, names or {}) for x in off))
        c = spec.get("chance")
        if (isinstance(c, bool) or not isinstance(c, (int, float)) or c != c
                or not 0 < c <= 100):
            out.append(where + ": " + _("\"chance\" is the percent chance it starts on each "
                                        "day of those seasons, more than 0 and up to 100, "
                                        "like 3."))
        d = spec.get("days", 1)
        pair = (d, d) if isinstance(d, int) and not isinstance(d, bool) else d
        if not (isinstance(pair, (tuple, list)) and len(pair) == 2
                and all(isinstance(x, int) and not isinstance(x, bool) for x in pair)
                and 1 <= pair[0] <= pair[1] <= SPELL_MOST_DAYS):
            out.append(where + ": " + _("\"days\" is how long it runs, 1 to %d, or the fewest "
                                        "and the most, like (1, 2). A week or longer is a "
                                        "season of your own.") % SPELL_MOST_DAYS)
        brings = spec.get("as")
        if brings is not None:
            if brings not in SEASONS:
                out.append(where + ": " + _("\"as\" is the season it brings, one of %s, or "
                                            "None to leave the season as it is.")
                           % _and(SEASONS))
            elif brings not in on:
                out.append(where + ": " + _("it brings %s, which is off in your calendar.")
                           % season_label(brings, names or {}))
            elif isinstance(start, (tuple, list)) and start and all(x == brings
                                                                   for x in start):
                out.append(where + ": " + _("it would bring %(season)s to %(season)s, which "
                                            "changes nothing.")
                           % {"season": season_label(brings, names or {})})
    return out


def _cp1251(text):
    try:
        text.encode("cp1251")
        return True
    except UnicodeEncodeError:
        return False


def spell_draws(name, day):
    """Two numbers from 0 to 1 that the spell `name` draws on `day`: whether it starts, and
    how long it runs. The same name and day draw the same on every machine and every run."""
    h = hashlib.sha256(("%s|%s" % (name, day.isoformat())).encode("utf-8")).digest()
    return (int.from_bytes(h[:8], "big") / 2.0 ** 64,
            int.from_bytes(h[8:16], "big") / 2.0 ** 64)


def spells_on(d, spells=None, where=None):
    """[(name, first day, last day)] for each spell running on d, the earliest first.
    `where(day)` is what a spell can start in on that day: the base period and the player's
    own seasons, by this install's calendar unless another is given. A spell that starts
    again while it runs, or on the day after, runs on: its days are the whole stretch."""
    spells = SPELLS if spells is None else spells
    if where is None:
        def where(day):
            return [season_for(day)] + [o for o, w in OWN_SEASONS.items()
                                        if _in_window(day, *w)]
    one = datetime.timedelta(days=1)
    out = []
    for name, spec in spells.items():
        lo, hi = spell_days(spec)
        start = spec["in"]
        start = {start} if isinstance(start, str) else set(start)
        runs = {}

        def run(first):
            """How many days a start on `first` runs, or 0 when it doesn't start then."""
            if first not in runs:
                begins, length = spell_draws(name, first)
                runs[first] = (lo + min(int(length * (hi - lo + 1)), hi - lo)
                               if begins * 100 < spec["chance"] and start & set(where(first))
                               else 0)
            return runs[first]

        def on(day):
            return any(run(day - datetime.timedelta(days=back)) > back for back in range(hi))

        if not on(d):
            continue
        # a year either way at most: a spell on every day of its seasons runs through them
        first, last = d, d
        while (d - first).days < 366 and on(first - one):
            first -= one
        while (last - d).days < 366 and on(last + one):
            last += one
        out.append((name, first, last))
    return sorted(out, key=lambda t: (t[1], t[0].casefold()))


def spell_season(d, spells=None, where=None):
    """(season, (name, first day, last day)) for the spell that brings a season on d - the
    one that started first - or (None, None)."""
    spells = SPELLS if spells is None else spells
    for name, first, last in spells_on(d, spells, where):
        if spells[name].get("as"):
            return spells[name]["as"], (name, first, last)
    return None, None


def spells_a_year(spec, where):
    """How many times a year a spell comes, on average: over the days of 2026, the chance
    it starts on each day it can, while it isn't running already. `where(day)` as for
    spells_on."""
    try:
        p = float(spec["chance"]) / 100.0
    except (KeyError, TypeError, ValueError, OverflowError):
        return 0.0
    if not 0 < p <= 1:                      # nan too; spell_problems says what is wrong
        return 0.0
    lo, hi = spell_days(spec)
    start = spec["in"]
    start = {start} if isinstance(start, str) else set(start)
    # the chance a start still runs k days later: it runs lo to hi days, each as likely
    lasts = [1.0 if k < lo else (hi - k) / float(hi - lo + 1) for k in range(hi)]
    can = {}

    def chance(d):
        if d not in can:
            can[d] = p if start & set(where(d)) else 0.0
        return can[d]

    total = 0.0
    for i in range(365):
        d = datetime.date(2026, 1, 1) + datetime.timedelta(days=i)
        if chance(d):
            free = 1.0
            for k in range(hi):
                free *= 1 - chance(d - datetime.timedelta(days=k + 1)) * lasts[k]
            total += chance(d) * free
    return total


def calendar_table(mapping="pheno", calendar=None):
    """(season, month, day) for each season that is on: CALENDAR when the config has one,
    else Polesia's dates, or the meteorological ones with --mapping met."""
    calendar = CALENDAR if calendar is None else calendar
    if calendar:
        return [(s, int(md[0]), int(md[1])) for s, md in calendar.items()]
    return list(PHENO if mapping == "pheno" else MET)


def seasons_on(mapping="pheno"):
    """The seasons that are on, in the order MCM lists them."""
    on = {s for s, _, _ in calendar_table(mapping)}
    return [s for s in SEASONS if s in on]


def is_default(table):
    return sorted(table) == sorted(PHENO)


def is_plain(table, names=None):
    """Polesia's dates under their usual names: the shipped dial fits, nothing to hand on."""
    return is_default(table) and not custom_names(names)


def calendar_text(mapping="pheno"):
    """One line: whose dates these are, and what is off."""
    comma = pgettext("between words in a list", ", ")
    table = calendar_table(mapping)
    if is_default(table):
        named = custom_names()
        if not named:
            return _("Polesia (the Zone's own dates)")
        # translators: a season's usual name, then the player's own name for it
        pair = pgettext("a season and its name", "%(season)s \"%(name)s\"")
        return _("Polesia (the Zone's own dates); named: %s") % comma.join(
            pair % {"season": usual_name(s), "name": n}
            for s, n in sorted(named.items(), key=lambda kv: SEASONS.index(kv[0])))
    if not CALENDAR:
        return _("meteorological (month starts)")
    days = season_lengths({s: (m, d) for s, m, d in table})
    # translators: a season and the day it starts: "summer May 20"
    start = pgettext("a season and its first day", "%(season)s %(day)s")
    parts = comma.join(start % {"season": season_label(s), "day": _md(m, d)}
                       for s, m, d in sorted(table, key=lambda t: (t[1], t[2])))
    off = [season_label(s) for s in SEASONS if s not in days]
    if off:
        return _("your own: %(seasons)s; off: %(off)s") % {"seasons": parts,
                                                            "off": comma.join(off)}
    return _("your own: %s") % parts


def _signature(table, names=None):
    """What a redrawn dial depends on: the dates and names, and the arc colors and drawing
    code, so a mod update that changes either redraws it too."""
    h = hashlib.md5(",".join("%s=%d-%d" % t for t in sorted(table)).encode("utf-8"))
    h.update(repr(sorted(custom_names(names).items())).encode("utf-8"))
    for p in (os.path.join(MODS, SOTZ, "gamedata", "configs", "seasons_of_the_zone.ltx"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "build_season_dial.py")):
        try:
            h.update(io.open(p, "rb").read())
        except OSError:
            pass
    return h.hexdigest()[:8]


def _calendar_path():
    return os.path.join(MODS, SOTZ, "gamedata", *CALENDAR_REL)


def dial_text(state):
    """What the game shows for the dial, in words, by dial_state()."""
    return {"default": _("the shipped one, for Polesia's dates"),
            "custom": _("drawn for your dates and names"),
            "stale": _("to be drawn for your dates and names at the next play.bat"),
            "none": _("hidden - the game has no dial for your dates and names")}.get(
                state, _("not written"))


def pillow_note():
    """Why there is no dial: Pillow is missing, and the command that adds it."""
    return _("drawing one needs Pillow: %s") % ("%s -m pip install pillow" % _python())


def dial_state(mapping="pheno", calendar=None, names=None):
    """What the game will show for the dial, without writing anything: 'default',
    'custom' when the redrawn one matches the calendar, 'stale' when it needs redrawing
    and can be, or 'none' when it cannot be (no Pillow)."""
    table = calendar_table(mapping, calendar)
    if is_plain(table, names):
        return "default"
    tex = os.path.join(MODS, SOTZ, "gamedata", "textures")
    # a set drawn for other dates is stale even when every file is there
    have = all(os.path.isfile(os.path.join(tex, "%s%02d.dds" % (DIAL_PREFIX, i)))
               for i in range(DIALS))
    try:
        old = io.open(_calendar_path(), encoding="cp1251").read()
    except OSError:
        old = ""
    if have and ("dial_sig = %s" % _signature(table, names)) in old:
        return "custom"
    try:
        import PIL                              # noqa: F401 - only asking whether it is here
        return "stale"
    except ImportError:
        return "none"


def write_calendar(mapping="pheno", calendar=None, redraw=True, names=None, staged=False):
    """Write configs/season_calendar.ltx for the game, and draw the dial a custom calendar
    needs. Returns (dial state, a sentence to show or None). The spell in the file is the
    one play.bat last staged, so the game keeps to what is staged: it stays as it is unless
    `staged` says this run has just staged today's season, spell or not."""
    table = calendar_table(mapping, calendar)
    named = custom_names(names)
    path = _calendar_path()
    if not os.path.isdir(os.path.dirname(path)):
        return None, _("the mod's configs folder is missing")
    lines = ["; generated by _tools/season.py from seasons_config.py - do not edit by hand",
             "[calendar]"]
    note = None
    tex = os.path.join(MODS, SOTZ, "gamedata", "textures")
    if is_plain(table, names):
        state = "default"
        lines += ["custom = false", "dial = default"]
        # a redrawn set is 18 MB and the shipped one is back in use
        for i in range(DIALS):
            p = os.path.join(tex, "%s%02d.dds" % (DIAL_PREFIX, i))
            if os.path.isfile(p):
                try:
                    os.remove(p)
                except OSError:
                    pass
    else:
        state = dial_state(mapping, calendar, names)
        if state == "stale" and redraw:
            try:
                import build_season_dial
                build_season_dial.write_set(
                    [(m, d, s) for s, m, d in table], tex, DIAL_PREFIX,
                    os.path.join(MODS, SOTZ, "gamedata", "configs",
                                 "seasons_of_the_zone.ltx"), quiet=True,
                    names=named)
                state = "custom"
            except Exception as e:                  # the dial is a nicety; staging goes on
                state, note = "none", _("the dial could not be drawn (%s)") % e
        elif state in ("stale", "none"):
            state, note = "none", pillow_note()
        lines += ["custom = true", "dial = %s" % state]
        if state == "custom":
            lines.append("dial_sig = %s" % _signature(table, names))
        for s, m, d in sorted(table, key=lambda t: SEASONS.index(t[0])):
            lines.append("%s = %d, %d" % (s, m, d))
        # the game's reader keeps a value's spaces; the letters are cp1251, which the
        # rules have checked
        for s in SEASONS:
            if s in named:
                lines.append("name_%s = %s" % (s, named[s]))
    if staged:
        # the spell that brings a season today, for the game to follow while its dates
        # last; an MCM pin still wins over it in game, as it does here
        brings, spell = spell_season(datetime.date.today())
        if spell:
            lines += ["", "[spell]", "season = %s" % brings, "name = %s" % spell[0],
                      "first = %s" % spell[1].isoformat(),
                      "last = %s" % spell[2].isoformat()]
    else:
        lines += _staged_spell(path)
    body = "\r\n".join(lines) + "\r\n"
    try:
        old = io.open(path, encoding="cp1251", errors="replace", newline="").read()
    except OSError:
        old = None
    if old != body:
        try:
            io.open(path, "w", encoding="cp1251", newline="").write(body)
        except OSError as e:
            return None, _("%(file)s could not be written (%(error)s)") % {
                "file": os.path.basename(path), "error": e}
    return state, note


def _staged_spell(path):
    """The [spell] section of the calendar file as it stands, as lines, or []."""
    try:
        old = io.open(path, encoding="cp1251", errors="replace").read().splitlines()
    except OSError:
        return []
    out, keep = [], False
    for line in old:
        if line.strip().startswith("["):
            keep = line.strip().lower() == "[spell]"
        if keep and line.strip():
            out.append(line.rstrip())
    return [""] + out if out else []


def base_table(mapping="pheno"):
    """The base periods: the seasons that are on plus anything in PERIODS. These
    partition the year - exactly one is active on any date."""
    table = calendar_table(mapping)
    for name, when in PERIODS.items():
        table.append((name, int(when[0]), int(when[1])))
    return table


def period_names(mapping="pheno"):
    """Every name a mod may be scoped to: base periods first, then the player's own
    seasons, then events."""
    return [n for n, _, _ in base_table(mapping)] + list(OWN_SEASONS) + list(EVENTS)


def _in_window(d, start, end):
    """Is d inside the inclusive (month, day) window? A window whose start is
    after its end wraps the year end, so (12, 26)-(1, 6) is Christmas to Epiphany."""
    a = (int(start[0]), int(start[1]))
    b = (int(end[0]), int(end[1]))
    x = (d.month, d.day)
    return a <= x <= b if a <= b else (x >= a or x <= b)


# --- events ------------------------------------------------------------------------------
#
# An event is a window of dates, ((12, 24), (12, 26)), or a rule: a dict of any of
#   "weekdays": ("sat", "sun")      those days of the week
#   "days":     (1, 15, -1)         those days of the month; -1 is its last, -2 the one before
#   "weeks":    (1, -1)             with weekdays: the first, or the last, of them in the month
#   "months":   (12, 1, 2)          only in those months
#   "within":   ((12, 1), (2, 28))  only in that window
# A day is in the event when it is everything the rule names at once: {"weekdays":
# ("fri",), "days": (13,)} is each Friday the 13th. Events are decided when play.bat stages
# the launch, so a weekend event switches its mods at the first launch on a Saturday.

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
EVENT_KEYS = ("weekdays", "days", "weeks", "months", "within")


def _month_len(year, month):
    return MONTH_DAYS[month - 1] + (1 if month == 2 and (
        year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 0)


def _ints(v, lo, hi, negative=False):
    """Is v a tuple or list of whole numbers from lo to hi, or -hi to -lo with negative?"""
    return (isinstance(v, (tuple, list)) and len(v) > 0
            and all(isinstance(x, int) and not isinstance(x, bool)
                    and (lo <= x <= hi or (negative and -hi <= x <= -lo)) for x in v))


def event_on(d, spec):
    """Is the event `spec` on date d?"""
    if isinstance(spec, (tuple, list)):
        return _in_window(d, spec[0], spec[1])
    if "within" in spec and not _in_window(d, spec["within"][0], spec["within"][1]):
        return False
    if "months" in spec and d.month not in spec["months"]:
        return False
    if "weekdays" in spec and WEEKDAYS[d.weekday()] not in spec["weekdays"]:
        return False
    last = _month_len(d.year, d.month)
    if "days" in spec and not any(d.day == (x if x > 0 else last + 1 + x)
                                  for x in spec["days"]):
        return False
    if "weeks" in spec:
        nth, from_end = (d.day - 1) // 7 + 1, -((last - d.day) // 7 + 1)
        if nth not in spec["weeks"] and from_end not in spec["weeks"]:
            return False
    return True


def event_problems(name, spec):
    """What is wrong with one EVENTS entry, one sentence each."""
    where = "EVENTS[%r]" % (name,)
    shape = where + ": " + _("give its first and last day, like ((12, 24), (12, 26)), or a "
                             "rule, like {\"weekdays\": (\"sat\", \"sun\")}.")
    if isinstance(spec, (tuple, list)):
        if len(spec) == 2 and all(_is_day(x, leap=True) for x in spec):
            return []
        return [shape]
    if not isinstance(spec, dict) or not spec:
        return [shape]
    out = []
    odd = [k for k in spec if k not in EVENT_KEYS]
    if odd:
        out.append(where + ": " + ngettext(
            "%(keys)s is not a part of a rule. The parts are %(parts)s.",
            "%(keys)s are not parts of a rule. The parts are %(parts)s.", len(odd))
            % {"keys": _and(_q(k) for k in odd), "parts": _and(EVENT_KEYS)})
    wd = spec.get("weekdays")
    if "weekdays" in spec and not (isinstance(wd, (tuple, list)) and wd
                                   and all(x in WEEKDAYS for x in wd)):
        out.append(where + ": " + _("\"weekdays\" must list days of the week as %s, like "
                                    "(\"sat\", \"sun\").") % _and(WEEKDAYS))
    if "days" in spec and not _ints(spec["days"], 1, 31, negative=True):
        out.append(where + ": " + _("\"days\" must list days of the month, 1 to 31, or -1 for "
                                    "the last, like (1, 15, -1)."))
    if "weeks" in spec:
        if not _ints(spec["weeks"], 1, 5, negative=True):
            out.append(where + ": " + _("\"weeks\" must say which of those weekdays in the "
                                        "month count, 1 to 5 or -1 for the last, like (1,)."))
        elif "weekdays" not in spec:
            out.append(where + ": " + _("\"weeks\" needs \"weekdays\" too (--weekdays on the "
                                        "command line), to say which day of the week it "
                                        "counts."))
    if "months" in spec and not _ints(spec["months"], 1, 12):
        out.append(where + ": " + _("\"months\" must list months, 1 to 12, like (12, 1, 2)."))
    win = spec.get("within")
    if "within" in spec and not (isinstance(win, (tuple, list)) and len(win) == 2
                                 and all(_is_day(x, leap=True) for x in win)):
        out.append(where + ": " + _("\"within\" must be a first and last day, like "
                                    "((12, 1), (2, 28))."))
    if not out:
        # a rule nothing can meet, like the 31st in February: 28 years is every weekday
        # on every date, leap years included
        day, end = datetime.date(2024, 1, 1), datetime.date(2052, 1, 1)
        while day < end and not event_on(day, spec):
            day += datetime.timedelta(days=1)
        if day >= end:
            out.append(where + ": " + _("never happens - no date matches every part of the "
                                        "rule."))
    return out


def _ordinal(n):
    """A day of the month in words: "1st", "22nd", "30th"."""
    if n in (1, 21, 31):
        # translators: a day of the month: 1st, 21st, 31st
        return pgettext("a day of the month", "%dst") % n
    if n in (2, 22):
        # translators: a day of the month: 2nd, 22nd
        return pgettext("a day of the month", "%dnd") % n
    if n in (3, 23):
        # translators: a day of the month: 3rd, 23rd
        return pgettext("a day of the month", "%drd") % n
    # translators: a day of the month: 4th to 20th, 24th to 30th
    return pgettext("a day of the month", "%dth") % n


def _and(words):
    """Words in a list the way a sentence runs them, in the player's language: "a, b and
    c"."""
    return lang.and_list(words)


def _and_each(words):
    """Words each joined to the next by "and", in the player's language: "a and b and c",
    as a few of the lines have always read."""
    words = list(words)
    out = words[0] if words else ""
    for w in words[1:]:
        out = pgettext("the last two in a list", "%(rest)s and %(last)s") % {"rest": out,
                                                                             "last": w}
    return out


def _weekday(w):
    """A day of the week, short, in the player's language: "Mon"."""
    return {"mon": pgettext("a day of the week, short", "Mon"),
            "tue": pgettext("a day of the week, short", "Tue"),
            "wed": pgettext("a day of the week, short", "Wed"),
            "thu": pgettext("a day of the week, short", "Thu"),
            "fri": pgettext("a day of the week, short", "Fri"),
            "sat": pgettext("a day of the week, short", "Sat"),
            "sun": pgettext("a day of the week, short", "Sun")}[w]


def _which_week(n):
    """Which of a weekday in the month, by EVENTS' "weeks": 1 "first", -1 "last"."""
    return {1: pgettext("which of those weekdays in the month", "first"),
            2: pgettext("which of those weekdays in the month", "second"),
            3: pgettext("which of those weekdays in the month", "third"),
            4: pgettext("which of those weekdays in the month", "fourth"),
            5: pgettext("which of those weekdays in the month", "fifth"),
            -1: pgettext("which of those weekdays in the month", "last"),
            -2: pgettext("which of those weekdays in the month", "second-last"),
            -3: pgettext("which of those weekdays in the month", "third-last"),
            -4: pgettext("which of those weekdays in the month", "fourth-last"),
            -5: pgettext("which of those weekdays in the month", "fifth-last")}[n]


def event_text(spec):
    """An event in words: "Dec 24 - Dec 26", "weekends", "the first Mon of the month"."""

    def window(w):
        if tuple(w[0]) == tuple(w[1]):
            return _md(*w[0])
        # translators: the first and last day of a stretch of the year: "Dec 24 - Dec 26"
        return pgettext("a stretch of days", "%(first)s - %(last)s") % {
            "first": _md(*w[0]), "last": _md(*w[1])}

    if isinstance(spec, (tuple, list)):
        return window(spec)
    parts = []
    wd = [w for w in WEEKDAYS if w in spec.get("weekdays", ())]
    names = [_weekday(w) for w in wd]
    if "weeks" in spec:
        # translators: "the first and last Mon and Fri of the month"
        parts.append(_("the %(which)s %(days)s of the month")
                     % {"which": _and(_which_week(w) for w in spec["weeks"]),
                        "days": _and(names)})
    elif wd == ["sat", "sun"]:
        parts.append(_("weekends"))
    elif wd == ["mon", "tue", "wed", "thu", "fri"]:
        parts.append(_("workdays"))
    elif wd:
        parts.append(_and(names))
    if "days" in spec:
        days = [_ordinal(x) if x > 0 else _("last day") if x == -1 else
                # translators: "2nd-last day", the day before the last of the month
                _("%s-last day") % _ordinal(-x) for x in spec["days"]]
        if "weeks" not in spec:
            # translators: "the 1st, 15th and last day of the month"
            parts.append(_("the %s of the month") % _and(days))
        else:
            # translators: days of the month after the weekdays: "the 8th and 9th"
            parts.append(pgettext("days of the month, after the weekdays", "the %s")
                         % _and(days))
    if "months" in spec:
        # translators: the months a rule is in: "in Dec, Jan and Feb"
        parts.append(pgettext("the months of a rule", "in %s")
                     % _and(lang.month(m) for m in spec["months"]))
    if "within" in spec:
        parts.append(window(spec["within"]))
    return pgettext("between words in a list", ", ").join(parts)


def wins_over(name):
    """The seasonal mods `name` is set to win over: its `above`, that one's `above`, and so
    on down the chain."""
    out, cur = [], name
    while isinstance(TOGGLE_MODS.get(cur), dict):
        cur = TOGGLE_MODS[cur].get("above")
        if not isinstance(cur, str) or cur == name or cur in out:
            break
        out.append(cur)
    return out


def weather_flags():
    """Period names the real Zone's weather is asserting today.

    Reads season_weather.ltx, which _tools/fetch_weather.py leaves behind. Absent, stale
    or unreadable, this is empty and nothing changes - the file is an enhancement, never
    a dependency, and a launch must not care whether the network was up.

    "freezing" is a day whose observed low dips to or below zero, "thaw" one that also
    climbs above zero by afternoon, and "heat" one that reaches 28 C. Each behaves exactly
    like an event: it overlays whatever season is running rather than replacing it, so a
    freezing day in autumn is still autumn.
    """
    path = os.path.join(MODS, SOTZ, "gamedata", "configs", "season_weather.ltx")
    if not os.path.exists(path):
        return []
    try:
        section, low, high, when, there = None, None, None, None, {}
        # cp1251, the game's own: a place's name can be Cyrillic
        for line in io.open(path, encoding="cp1251", errors="replace"):
            line = line.split(";")[0].strip()
            if line.startswith("[") and line.endswith("]"):
                section = line[1:-1].strip()
                continue
            if "=" not in line:
                continue
            k, v = (x.strip() for x in line.split("=", 1))
            if section == "place" and k in ("lat", "lon"):
                there[k] = float(v)
            if section != "weather":
                continue
            if k == "low":
                low = float(v)
            elif k == "high":
                high = float(v)
            elif k == "date":
                when = v
    except Exception:
        return []

    if low is None:
        return []
    # A reading for another place - the config's changed since the last fetch - says
    # nothing about this one. A file from before places has no [place], and is Chornobyl's.
    here = weather_place()
    if (abs(there.get("lat", DEFAULT_PLACE["lat"]) - here["lat"]) > 1e-3
            or abs(there.get("lon", DEFAULT_PLACE["lon"]) - here["lon"]) > 1e-3):
        return []
    # A reading for another day is worse than none: it reads as authoritative and
    # describes weather that has been and gone.
    if when:
        try:
            got = datetime.date(*(int(x) for x in when.split("-")))
            if abs((datetime.date.today() - got).days) > 1:
                return []
        except Exception:
            return []
    # Day-scale names a mod can scope to, exactly as it scopes to a season. Only the
    # ones a day can be said to HAVE - "freezing" is a property of the day, whereas "it
    # is below zero at this moment" is a question for sotz_api, not for staging.
    out = []
    if low <= 0.0:
        out.append("freezing")
        if high is not None and high > 0.0:
            # froze overnight, above zero by afternoon: what a melt effect wants
            out.append("thaw")
    if high is not None and high >= 28.0:
        out.append("heat")
    return out


def active_for(d, mapping="pheno", base=None):
    """Every period active on d: the base period, then every season of the player's own
    and every event covering it.

    Those OVERLAY rather than replace. That is the whole point - a Christmas event
    does not displace winter, so December 25th keeps its snow and adds to it. Pass
    `base` to honor an MCM pin or --season while events still resolve by date."""
    out = [base or season_for(d, mapping)]
    for name, win in OWN_SEASONS.items():
        if _in_window(d, win[0], win[1]) and name not in out:
            out.append(name)
    for name, _, _ in spells_on(d):
        if name not in out:
            out.append(name)
    for name, spec in EVENTS.items():
        if event_on(d, spec) and name not in out:
            out.append(name)
    for name in weather_flags():
        if name not in out:
            out.append(name)
    return out


def _when(cfg):
    """The periods a mod is scoped to. 'when' is the current key; 'seasons' is the
    original and still works, so existing configs need no edit."""
    v = cfg.get("when")
    if v is None:
        v = cfg.get("seasons")
    return tuple(v) if isinstance(v, (list, tuple)) else ()


def _order(name, mapping="pheno"):
    """Calendar sort key. Events sort after every base period."""
    names = [n for n, _, _ in base_table(mapping)]
    return names.index(name) if name in names else len(names)


def season_for(d, mapping="pheno"):
    """The base period containing date d."""
    table = base_table(mapping)
    starts = sorted(((datetime.date(d.year, m, dd), name) for name, m, dd in table))
    cur = sorted(table, key=lambda t: (t[1], t[2]))[-1][0]     # the season the year starts in
    for start, name in starts:
        if d >= start:
            cur = name
    return cur


def running():
    """Anomaly or MO2 processes belonging to this install, by executable path. A process
    whose path cannot be read is counted as ours."""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "Get-Process -Name anomaly*,ModOrganizer -ErrorAction SilentlyContinue | "
           "ForEach-Object { if ($_.Path) { $_.Path } else { $_.ProcessName + '.exe|?' } }"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60).stdout
    except Exception as e:
        print("  ! " + _("Could not list the running programs (%s), so MO2 and the game are "
                         "taken to be closed.") % e.__class__.__name__)
        return []
    roots = [os.path.normcase(os.path.abspath(p)) + os.sep for p in (ROOT, game_dir())]
    mine = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith("|?"):
            # translators: a program's file name, like anomalydx11avx.exe
            mine.add(_("%s (path unreadable, assumed this install)") % line[:-2].lower())
            continue
        p = os.path.normcase(os.path.abspath(line))
        if any(p.startswith(r) for r in roots):
            mine.add(os.path.basename(line).lower())
    return sorted(mine)


def close_first(busy):
    """The refusal when running() finds MO2 or the game open and season.py has to write."""
    return "  ** " + _("Close %s first. Nothing was changed.") % _and(busy) + " **"


def lp(p):
    """Long-path prefix; some option trees exceed MAX_PATH."""
    p = os.path.abspath(p)
    return p if p.startswith("\\\\?\\") else "\\\\?\\" + p


def md5(p):
    h = hashlib.md5()
    with io.open(lp(p), "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def hashes(base):
    out = {}
    if not os.path.isdir(base):
        return out
    for r, _, fs in os.walk(base):
        for f in fs:
            p = os.path.join(r, f)
            out[os.path.relpath(p, base).replace(os.sep, "/")] = md5(p)
    return out


def archive_missing(archive):
    """What to say about a LAYOUT archive that is not in downloads/."""
    return _("%s is not in downloads. Put it back, or take the mod that uses it out of "
             "LAYOUT in seasons_config.py.") % archive


def no_gamedata(folder):
    """The refusal for an option folder in an archive with no gamedata in it."""
    return "  " + _("The folder \"%s\" in the archive has no gamedata folder. Check the "
                    "option names in LAYOUT.") % folder


def extract(archive, wanted, dest):
    """Extract the named option folders and merge their gamedata trees, in order.
    Returns the merged gamedata directory."""
    dest = _extract_options(archive, wanted, dest)
    merged = os.path.join(dest, "__merged", "gamedata")
    os.makedirs(merged, exist_ok=True)
    for w in wanted:
        gd = os.path.join(dest, w, "gamedata")
        if not os.path.isdir(gd):
            raise SystemExit(no_gamedata(w))
        for r, _, fs in os.walk(gd):
            for f in fs:
                s = os.path.join(r, f)
                t = os.path.join(merged, os.path.relpath(s, gd))
                os.makedirs(os.path.dirname(t), exist_ok=True)
                shutil.copy2(lp(s), lp(t))
    return merged


def _extract_options(archive, wanted, dest):
    """Extract the named top-level option folders into dest/<option>/. Returns the
    directory used; a previous tree Windows will not delete (an indexer holding a
    handle) is left alone and a sibling used instead."""
    src = os.path.join(DOWNLOADS, archive)
    if not os.path.isfile(src):
        raise SystemExit("  " + archive_missing(archive))
    if os.path.isdir(dest):
        for attempt in range(5):
            try:
                shutil.rmtree(dest)
                break
            except OSError:
                time.sleep(0.4)
        else:
            shutil.rmtree(dest, ignore_errors=True)
            if os.path.isdir(dest):
                dest = dest + "_" + datetime.datetime.now().strftime("%H%M%S")
    os.makedirs(dest, exist_ok=True)
    if archive.lower().endswith(".7z"):
        try:
            import py7zr
        except ImportError:
            raise SystemExit("  " + _("Texture sets in a .7z archive need the py7zr package. "
                                      "Install it with:")
                             + "\n    %s -m pip install py7zr\n  " % _python()
                             + _("No texture has been changed."))
        try:
            with py7zr.SevenZipFile(src) as z:
                names = [n for n in z.getnames()
                         if any(n.replace("\\", "/").split("/")[0] == w for w in wanted)]
                z.reset()
                z.extract(path=dest, targets=names)
        except Exception as e:
            raise SystemExit("  " + _("%(archive)s could not be read as a .7z: %(error)s")
                             % {"archive": archive, "error": e}
                             + "\n  " + _("No texture has been changed."))
    else:
        try:
            import rarfile
        except ImportError:
            raise SystemExit("  " + _("Texture sets in a .rar archive need the rarfile "
                                      "package, and WinRAR or 7-Zip installed. Install rarfile "
                                      "with:")
                             + "\n    %s -m pip install rarfile\n  " % _python()
                             + _("No texture has been changed."))
        rarfile.UNRAR_TOOL = _find_unrar()
        try:
            with rarfile.RarFile(src) as z:
                names = [i.filename for i in z.infolist()
                         if any(i.filename.replace("\\", "/").split("/")[0] == w
                                for w in wanted)]
                z.extractall(dest, members=names)
        except Exception as e:
            raise SystemExit("  " + _("%(archive)s could not be read as a .rar: %(error)s")
                             % {"archive": archive, "error": e}
                             + "\n  " + _("No texture has been changed."))
    return dest


HASH_CACHE = os.path.join(ROOT, "_baseline", "season-archive-hashes.json")


def _archive_key(archive):
    """name|size|mtime - a replaced archive invalidates its cached hashes."""
    src = os.path.join(DOWNLOADS, archive)
    if not os.path.isfile(src):
        raise SystemExit("  " + archive_missing(archive))
    st = os.stat(src)
    return "%s|%d|%d" % (archive, st.st_size, int(st.st_mtime))


def _option_hashes(archive, options, tmp, mod):
    """{relpath: md5} of the merged gamedata for these options. Per-option hashes are
    cached on disk; only options not yet cached are extracted."""
    key = _archive_key(archive)
    cache = {}
    if os.path.isfile(HASH_CACHE):
        try:
            cache = json.loads(io.open(HASH_CACHE, encoding="utf-8").read())
        except (OSError, ValueError):
            cache = {}
    per = cache.get(key, {})
    missing = [o for o in options if o not in per]
    if missing:
        dest = _extract_options(archive, missing,
                                os.path.join(tmp, mod[:18].replace(" ", "_"), "_hash"))
        for o in missing:
            gd = os.path.join(dest, o, "gamedata")
            if not os.path.isdir(gd):
                raise SystemExit(no_gamedata(o))
            per[o] = hashes(gd)
        cache = {k: v for k, v in cache.items() if k.split("|")[0] != archive}
        cache[key] = per
        os.makedirs(os.path.dirname(HASH_CACHE), exist_ok=True)
        io.open(HASH_CACHE, "w", encoding="utf-8").write(json.dumps(cache))
    merged = {}
    for o in options:
        merged.update(per[o])
    return merged


def identify(mod, cfg, tmp, prefer=None):
    """The season on disk, by hash: (season or None, detail). Two seasons can be the same
    bytes (Aydin ships four sets for six seasons), so the requested season is preferred
    when it is among the matches."""
    live = hashes(os.path.join(MODS, mod, "gamedata"))
    if not live:
        return None, (_("its gamedata/ is empty") if os.path.isdir(os.path.join(MODS, mod))
                      else _("not in mods/"))
    matches, detail = [], []
    for season in cfg["options"]:
        cand = _option_hashes(cfg["archive"], cfg["options"][season], tmp, mod)
        same = sum(1 for k in set(cand) & set(live) if cand[k] == live[k])
        detail.append((season, len(cand), len(set(cand) & set(live)), same))
        if same == len(live) and same > 0 and len(cand) == len(live):
            matches.append(season)
    if not matches:
        return None, detail
    return (prefer if prefer in matches else matches[0]), detail


def state_word(state):
    """A mod's state in MO2's list, in words: "+" enabled, "-" disabled, None not listed."""
    return {"+": pgettext("a mod in MO2's list", "enabled"),
            "-": pgettext("a mod in MO2's list", "disabled"),
            None: pgettext("a mod in MO2's list", "not listed")}[state]


def _print_lines(lead, text):
    """Print a message that runs over more than one line: the first after `lead`, like
    "  ! ", the rest lined up under it. A translation breaks its lines where it likes."""
    lines = text.split("\n")
    print(lead + lines[0])
    for line in lines[1:]:
        print(" " * len(lead) + line)


def who_wins(rel, mine=None):
    """Print every mod shipping `rel`, enabled or disabled, in priority order, and the mod
    a seasonal mod has to win over to win it.

    `mine` is the mod being placed, and it is left out of the answer. Set to win over
    itself, a mod stays where it is, and the next mod to ship the file above it wins
    without a word. Without `mine` the top enabled mod may be the one being placed - MO2
    enables a new install at the top - so the next one down is named too."""
    rel = rel.replace(chr(92), "/").strip("/")
    for lead in ("gamedata/", "mods/"):
        if rel.startswith(lead):
            rel = rel[len(lead):]

    lines = _modlist_lines()
    if lines is None:
        print("  " + _("Can't read MO2's mod list (%s).")
              % ("profiles\\%s\\modlist.txt" % profile_name()))
        return 1
    body = [l for l in lines if l[:1] in ("+", "-")]
    if mine is not None and not any(l[1:] == mine for l in body):
        print("  " + _("No mod named \"%s\" in MO2's mod list. Use the name exactly as MO2 "
                       "shows it.") % mine)
        return 1

    print("  " + _("file: %s") % ("gamedata/" + rel))
    print()
    hits, ships, enabled = 0, False, []
    for i, line in enumerate(body):
        name = line[1:]
        p = os.path.join(MODS, name, "gamedata", *rel.split("/"))
        if not os.path.isfile(p):
            continue
        hits += 1
        mark = ""
        if name == mine:
            ships = True
            # translators: marks the mod being placed, in the list of mods that ship a file
            mark = "   <-- " + _("yours")
        elif line[:1] == "+":
            enabled.append(name)
            if len(enabled) == 1 and mine is None:
                # translators: marks the mod whose copy of a file the game uses
                mark = "   <-- " + _("WINS")
            elif len(enabled) == 1:
                mark = "   <-- " + _("yours has to win over this one")
        # translators: a line of MO2's mod list, by its number
        where = _("line %5d") % (i + 2)
        # translators: a file's size in bytes
        size = _("%d B") % os.path.getsize(p)
        print("    %s  %-8s  %-46s %11s%s" % (where, state_word(line[:1]), name[:46], size,
                                              mark))

    def config(other):
        # the line to put in the config, as the config spells it
        print("  " + _("In the config:") + "  \"above\": \"%s\"" % other + "   "
              + _("(in configure.bat: its Wins over box)"))

    print()
    if mine is not None:
        if not ships:
            print("  " + _("%s does not ship this file. Pick a file it does ship.") % mine)
            return 1
        if not enabled:
            print("  " + _("No other enabled mod ships it, so %s wins it wherever it sits.")
                  % mine)
        else:
            print("  " + _("Make %(mod)s win over:  %(other)s") % {"mod": mine,
                                                                   "other": enabled[0]})
            config(enabled[0])
    elif not hits:
        _print_lines("  ", _("No mod ships this file. Either the base game has it in its .db "
                             "archives, or\nthe path is misspelled. A mod that ships it wins "
                             "it wherever it sits."))
    elif not enabled:
        print("  " + _("Only disabled mods ship it, so the base game's copy, if it has one, is "
                       "in use."))
    else:
        print("  " + _("Make your seasonal mod win over:  %s") % enabled[0])
        config(enabled[0])
        print()
        if len(enabled) > 1:
            print("  " + _("If that is the mod you are placing, make it win over the next one "
                           "down:"))
            config(enabled[1])
        else:
            print("  " + _("If that is the mod you are placing, it wins this file wherever it "
                           "sits."))
        print("  " + _("(%s leaves your mod out and gives one answer.)")
              % "--for \"<your mod>\"")
    return 0


def _check_mod_state():
    """Warn when the mod itself is missing or disabled, or Season Flora is enabled beside
    it. season.py never enables the main mod."""
    gd = os.path.join(MODS, SOTZ, "gamedata")
    if not os.path.isdir(gd):
        _print_lines("  ! ", _("Seasons of the Zone is not in mods/. Install the zip with "
                               "MO2's\n\"Install a new mod from archive\", then enable it."))
        return
    copies = sotz_copies()
    if len(copies) > 1:
        print("  ! " + ngettext("Seasons of the Zone is installed %(n)d time: %(folders)s.",
                                "Seasons of the Zone is installed %(n)d times: %(folders)s.",
                                len(copies))
              % {"n": len(copies), "folders": ", ".join("'%s'" % c for c in copies)})
        print("    " + _("Using '%s'. Remove the others in MO2.") % SOTZ)
    lines = _modlist_lines()
    if lines is None:
        return
    state = next((l[:1] for l in lines if l[:1] in ("+", "-") and l[1:] == SOTZ), None)
    if state is None:
        _print_lines("  ! ", _("\"%(mod)s\" is not in MO2's mod list for profile "
                               "\"%(profile)s\". MO2 adds it disabled\nat its next start. "
                               "Enable it in MO2, or nothing happens in the game.")
                     % {"mod": SOTZ, "profile": profile_name()})
    elif state == "-":
        print("  ! " + _("\"%(mod)s\" is disabled in profile \"%(profile)s\". Enable it in "
                         "MO2.") % {"mod": SOTZ, "profile": profile_name()})
    if state == "+" and _mod_enabled(FLORA_MOD):
        _print_lines("  ! ", _("%(mod)s is enabled. It is this mod's old prototype and sets "
                               "the same foliage\nand fog values, so the two fight. Disable "
                               "%(mod)s in MO2.") % {"mod": FLORA_MOD})


SHADOW_CACHE = os.path.join(ROOT, "_baseline", "season-shadow-check.json")


def shadow_check(force=False):
    """Lines about the files of each seasonal mod that a mod above it wins, judged on the
    order apply leaves MO2's mod list in, not the order it is in now.

    "!": an enabled mod above ships the file. "-": disabled mods above do, and would win
    it if enabled; or two seasonal mods overlap in a season they share (judged on seasons,
    not on today's flags, so it shows out of season too), unless the one on top is set to
    win over the other.

    Costs a stat per (file, higher mod) pair, so `apply` runs it only when the mod list or
    the config has changed; `status` always does. No lines when it did not run."""
    lines = _modlist_lines()
    if lines is None:
        return []
    body = [l for l in lines if l[:1] in ("+", "-")]
    key = hashlib.md5(("|".join(body) + "|" + repr(sorted(
        (n, _when(c), c.get("above")) for n, c in TOGGLE_MODS.items())))
                      .encode("utf-8", "replace")).hexdigest()
    if not force and os.path.isfile(SHADOW_CACHE):
        try:
            if json.loads(io.open(SHADOW_CACHE, encoding="utf-8").read()).get("key") == key:
                return []
        except (OSError, ValueError):
            pass

    # the moves apply makes: a mod it is about to put above another is not losing to it
    folders = _mod_folders()
    for name, cfg in TOGGLE_MODS.items():
        if name in folders:
            i = _find(body, name)
            _place(body, name, cfg["above"], body[i][:1] if i is not None else "-")

    ours = set(TOGGLE_MODS) | {SOUND_MOD, SOTZ}
    index = {l[1:]: i for i, l in enumerate(body)}
    shadowed, dormant, notes = [], {}, []
    for name, cfg in TOGGLE_MODS.items():
        base = os.path.join(MODS, name, "gamedata")
        if name not in index or not os.path.isdir(base):
            continue
        rels = []
        for r, __, fs in os.walk(base):
            for f in fs:
                rels.append(os.path.relpath(os.path.join(r, f), base))
        for line in body[:index[name]]:
            other, on = line[1:], line[:1] == "+"
            og = os.path.join(MODS, other, "gamedata")
            if not os.path.isdir(og):
                continue
            hits = [rel for rel in rels if os.path.isfile(os.path.join(og, rel))]
            if not hits:
                continue
            eg = hits[0].replace(os.sep, "/")
            if other in TOGGLE_MODS:
                shared = set(_when(cfg)) & set(_when(TOGGLE_MODS[other]))
                # set to win over this one, itself or through the mods it wins over:
                # the overlap is the intent
                if shared and name not in wins_over(other):
                    notes.append((name, other, len(hits), eg, seasons_text(sorted(
                        shared, key=lambda p: (p not in SEASONS, SEASONS.index(p)
                                               if p in SEASONS else 0, p)))))
            elif other in ours:
                continue
            elif on:
                shadowed.append((name, other, len(hits), eg))
            else:
                dormant.setdefault(name, []).append((other, len(hits), eg))

    os.makedirs(os.path.dirname(SHADOW_CACHE), exist_ok=True)
    io.open(SHADOW_CACHE, "w", encoding="utf-8").write(json.dumps({"key": key}))
    out = []
    for name, other, n, eg in shadowed:
        out.append("  ! " + ngettext(
            "%(mod)s loses %(n)d file to \"%(other)s\", which is enabled and wins over it in "
            "MO2's mod list (like %(file)s).",
            "%(mod)s loses %(n)d files to \"%(other)s\", which is enabled and wins over it in "
            "MO2's mod list (like %(file)s).", n)
            % {"mod": name[:36], "n": n, "other": other[:44], "file": eg})
        out.append("    " + _("In configure.bat, make it win over that mod, or disable that "
                              "mod."))
    for name, lst in dormant.items():
        other, n, eg = lst[0]
        out.append("  - " + ngettext(
            "%(n)d disabled mod in MO2 would win some of %(mod)s's files if enabled (like "
            "\"%(other)s\": %(files)s, %(file)s).",
            "%(n)d disabled mods in MO2 would win some of %(mod)s's files if enabled (like "
            "\"%(other)s\": %(files)s, %(file)s).", len(lst))
            % {"n": len(lst), "mod": name[:36], "other": other[:40],
               "files": ngettext("%d file", "%d files", n) % n, "file": eg})
    if dormant:
        out.append("    " + _("After enabling one, check with %s.")
                   % command("season.py", "status"))
    for name, other, n, eg, seasons in notes:
        # translators: English says "files" for 1 too: "wins 1 of X's files"
        out.append("  - " + ngettext(
            "\"%(other)s\" wins %(n)d of %(mod)s's files in %(seasons)s (like %(file)s).",
            "\"%(other)s\" wins %(n)d of %(mod)s's files in %(seasons)s (like %(file)s).", n)
            % {"other": other[:40], "n": n, "mod": name[:36], "seasons": seasons,
               "file": eg})
        out.append("    " + _("Fine if that is the intent; if not, make %(mod)s win over "
                              "\"%(other)s\" in configure.bat.")
                   % {"mod": name[:36], "other": other[:40]})
    return out


def _check_install():
    """Stop with a plain message when not run from a Mod Organizer install."""
    ini = os.path.join(ROOT, "ModOrganizer.ini")
    modlist = _modlist_path()
    if os.path.isfile(ini) and os.path.isfile(modlist):
        return

    print("  " + _("This does not look like a Mod Organizer install."))
    print()
    looked, expected = _("looked in"), _("expected")
    width = max(10, len(looked) + 1, len(expected) + 1)
    found, missing = pgettext("a file", "found"), pgettext("a file", "MISSING")
    print("    %-*s: %s" % (width, looked, ROOT))
    print("    %-*s: ModOrganizer.ini        %s"
          % (width, expected, found if os.path.isfile(ini) else missing))
    print("    %s  profiles\\%s\\modlist.txt %s"
          % (" " * width, profile_name(), found if os.path.isfile(modlist) else missing))
    print()
    _print_lines("  ", _("The tools run from your GAMMA folder, the one with ModOrganizer.exe. "
                         "To put\nthem there, open configure.bat in the mod's folder: in MO2, "
                         "right-click the\nmod and choose Open in Explorer. Nothing has been "
                         "changed."))
    raise SystemExit(2)


def play_words(key):
    """What play.bat says around a launch, by key, or None for one it doesn't say. A batch
    file can't read a translation, so play.bat asks for these with `season.py say <key>`
    and falls back on its own English."""
    return {"checking": _("Checking the season..."),
            # translators: play.bat's console window shows it; keep its lines about this long
            "stopped": _("season.py stopped with an error - read the lines above. Seasonal "
                         "mods and\ntextures stay as they were after the last launch; light "
                         "and weather still\nfollow the season. Press a key to start the "
                         "game anyway, or close this\nwindow to fix it first."),
            "starting": _("Starting Anomaly...")}.get(key)


def _row(label, value):
    """A line of the report: its label in a column of its own, then the value."""
    print("  %-15s %s" % (label, value))


def main():
    ap = argparse.ArgumentParser(
        description=_("Stage today's season for Seasons of the Zone (play.bat runs apply)."))
    ap.add_argument("cmd", choices=["status", "apply", "whowins", "dial", "say"],
                    # translators: status, apply, whowins, dial and say are typed; keep them
                    help=_("status: what the next launch would do; apply: do it; whowins: "
                           "which mod wins a file; dial: send the calendar and names to the "
                           "game; say: a line play.bat shows"))
    ap.add_argument("path", nargs="?",
                    # translators: the path, and checking, stopped and starting, are typed
                    help=_("for whowins: a file path inside gamedata, like "
                           "textures/terrain/terrain_escape.dds; for say: checking, stopped "
                           "or starting"))
    ap.add_argument("--for", dest="mine", metavar="MOD",
                    help=_("for whowins: the mod you are placing, left out of the answer"))
    ap.add_argument("--season", metavar="SEASON",
                    help=_("stage this season or event instead of today's"))
    ap.add_argument("--mapping", choices=["pheno", "met"], default="pheno",
                    # translators: pheno and met are typed; keep them
                    help=_("pheno: Polesia's dates (the default); met: meteorological. "
                           "Ignored when seasons_config.py sets CALENDAR"))
    ap.add_argument("--dry-run", action="store_true",
                    help=_("show what apply would change, and change nothing"))
    ap.add_argument("--no-textures", action="store_true",
                    help=_("turn texture swapping off for this run only: seasonal mods "
                           "disabled, texture sets kept. MCM has the lasting switch"))
    a = ap.parse_args()

    # play.bat's lines come before any check: it shows them whatever state the install is in
    if a.cmd == "say":
        words = play_words(a.path)
        if words is None:
            raise SystemExit(2)                     # play.bat says its own English instead
        _print_lines(" ", words)                    # one space in, as its echo lines are
        return

    _check_install()

    # before the config check: whowins is how the config gets its `above`, so a
    # half-written seasons_config.py must not lock it out
    if a.cmd == "whowins":
        if not a.path:
            raise SystemExit("  " + _("whowins needs a file path inside gamedata, like:")
                             + "\n    " + command("season.py", "whowins "
                                                  "textures/terrain/terrain_escape.dds"))
        raise SystemExit(who_wins(a.path, a.mine))

    _validate_config()
    if a.season and a.season not in period_names(a.mapping):
        # typed, so the keys: the seasons that are on in their usual order, then the rest
        can = seasons_on(a.mapping) + [n for n in period_names(a.mapping)
                                       if n not in SEASONS]
        said = (_("--season %(season)s: your calendar has %(label)s off. These are: "
                  "%(names)s") if a.season in SEASONS else
                _("--season %(season)s: your calendar has no such season or event. These "
                  "are: %(names)s"))
        raise SystemExit("  " + said % {"season": a.season, "label": season_label(a.season),
                                        "names": ", ".join(can)})
    if a.cmd == "dial":
        # What configure.bat runs after saving a calendar. The game reads the calendar
        # when it starts, whether or not that start goes through play.bat.
        state, note = write_calendar(a.mapping)
        _row(pgettext("report", "calendar"), calendar_text(a.mapping))
        _row(pgettext("report", "dial"), dial_text(state))
        if note:
            print("  - " + note)
        raise SystemExit(0 if state else 1)
    _check_mod_state()

    today = datetime.date.today()
    prefs = read_prefs()

    # MCM offers "automatic, or pin one" and the in-engine layers honor it, so the
    # staged layers follow it too - otherwise pinning a season gives you its light
    # over another season's ground. An explicit --season still wins over the pin. A pin
    # left on a season the calendar has turned off counts as automatic, as in game.
    on = seasons_on(a.mapping)
    pinned = prefs["mode"] if prefs["mode"] in on else None
    pin_off = prefs["mode"] in SEASONS and prefs["mode"] not in on
    # a spell brings its season unless the season is fixed: by --season or an MCM pin
    brings, spell = spell_season(today) if not (a.season or pinned) else (None, None)
    want = a.season or pinned or brings or season_for(today, a.mapping)
    # A pin or --season fixes the BASE period; events still resolve by real date,
    # so pinning summer in December does not cancel a Christmas event.
    active = active_for(today, a.mapping, base=want)
    tmp = os.path.join(ROOT, "_staging", "season-%d" % os.getpid())    # per process
    if a.no_textures:
        prefs["stage_textures"] = False
    stage_tex = prefs["stage_textures"]
    writing = (a.cmd == "apply") and not a.dry_run
    title = cap_first(season_label(want))

    _row(pgettext("report", "date"), today.isoformat())
    _row(pgettext("report", "calendar"), calendar_text(a.mapping))
    why = ("   " + _("(forced with --season)") if a.season else
           "   " + _("(pinned in MCM)") if pinned else
           "   " + _("(a spell: %(name)s, %(first)s to %(last)s)")
           % {"name": spell[0], "first": _md(spell[1].month, spell[1].day),
              "last": _md(spell[2].month, spell[2].day)} if spell else "")
    _row(pgettext("report", "season"), season_label(want) + why)
    if (pinned and not a.season) or spell:
        _row(pgettext("report", "calendar says"), season_label(season_for(today, a.mapping)))
    # the player's own seasons, spells and events on today; the weather has a line of its own
    also = [n for n in active[1:] if n not in WEATHER_NAMES and not (spell and n == spell[0])]
    if also:
        _row(pgettext("report", "also today"), ", ".join(also))
    if pin_off and not a.season:
        print("  - " + _("MCM pins %s, which your calendar has off, so the date decides.")
              % season_label(prefs["mode"]))
    if writing:
        # the dates and names go to the game now, as configure.bat sends them; today's spell
        # only once what it brings is staged (send_spell), so a run that stops - MO2 open,
        # a failed copy - leaves the game on what is staged
        dial, note = write_calendar(a.mapping)
    else:
        dial = dial_state(a.mapping)
        note = pillow_note() if dial == "none" else None
    if dial != "default":
        _row(pgettext("report", "dial"), dial_text(dial))
    if note:
        print("  - " + note)
    flags = weather_flags()
    _row(pgettext("report", "weather from"), place_words(weather_place()) + (
        "   " + _("(today: %s)") % ", ".join(flags) if flags else ""))
    _row(pgettext("report", "texture layer"), pgettext("the texture layer", "on") if stage_tex
         else _("OFF for this run (--no-textures) - seasonal mods disabled, texture sets kept; "
                "the seasonal atmosphere still runs") if a.no_textures
         else _("OFF in MCM - seasonal mods disabled, texture sets kept; the seasonal "
                "atmosphere still runs"))
    print()

    try:
        # `installed` holds the LAYOUT mods this launch can stage for `want`. One missing
        # from mods/ is left alone, and so is one with no option for `want`: that keeps
        # whatever it has, as CONFIGURING.md says. So is one whose archive is gone: nothing
        # can tell its sets apart or restage it, and the rest of the launch goes on.
        installed, sets_skipped = {}, []
        for mod, cfg in LAYOUT.items():
            print("  %s" % mod[:70])
            if not os.path.isdir(os.path.join(MODS, mod)):
                near = near_folder(mod)
                print("     " + (_("not in mods/ - left alone (MO2 has \"%s\")") % near if near
                                 else _("not in mods/ - left alone. Check the name in LAYOUT, "
                                        "as MO2 shows it.")))
                continue
            if not os.path.isfile(os.path.join(DOWNLOADS, cfg["archive"])):
                print("     ! " + archive_missing(cfg["archive"]))
                if want not in cfg["options"]:
                    print("     " + _("no option for %s in LAYOUT - what it has stays")
                          % season_label(want))
                elif stage_tex:
                    print("       " + _("Its textures are left as they are."))
                    sets_skipped.append(mod)
                continue
            got, detail = identify(mod, cfg, tmp, want)
            print("     " + _("installed: %s") % (
                season_label(got) if got else
                _("unrecognized - not a clean copy of any season")))
            if got is None and isinstance(detail, list):
                for s, n, shared, same in detail:
                    # translators: files in the archive's set, in both, and the same in both
                    counts = _("archive %(archive)3d | shared %(shared)3d | identical "
                               "%(same)3d") % {"archive": n, "shared": shared, "same": same}
                    print("        %-12s %s" % (season_label(s), counts))
            elif got is None:
                print("        (%s)" % detail)
            if want in cfg["options"]:
                installed[mod] = got
            else:
                print("     " + _("no option for %s in LAYOUT - what it has stays")
                      % season_label(want))
        print()

        folders = _mod_folders()
        for name, inst, state, should, held in toggle_status(active, prefs):
            if not inst:
                near = near_folder(name, folders)
                print("  %-30s %s   %s" % (
                    name[:30], _("not installed"),
                    _("(MO2 has \"%s\"; use that name exactly)") % near if near
                    else _("(no folder with that name in mods)")))
            else:
                due = (_("(today: off)") if not should else _("(today: on)") if not held else
                       _("(today: off - texture swapping is off for this run "
                         "(--no-textures))") if held == "off" and a.no_textures else
                       _("(today: off - texture swapping is off in MCM)") if held == "off"
                       else _("(today: off - unchecked for this season in MCM)"))
                print("  %-30s %-10s %s" % (name[:30], state_word(state), due))
        # A mod on only in seasons that are off never comes on: worth saying, since
        # nothing else would
        for name, cfg in TOGGLE_MODS.items():
            w = set(_when(cfg))
            if w and w <= (set(SEASONS) - set(on)):
                print("  - " + _("%(mod)s is on only in %(seasons)s, which your calendar has "
                                 "off, so it never switches on.")
                      % {"mod": name[:40], "seasons": seasons_text(sorted(w,
                                                                          key=SEASONS.index))})
        # MCM keys a mod's per-season checkbox by its name with the punctuation dropped, so
        # "Winter Pack" and "Winter-Pack" would share one
        keys = {}
        for name in TOGGLE_MODS:
            keys.setdefault(_slug(name), []).append(name)
        for key, same in keys.items():
            if len(same) > 1:
                print("  - " + _("%s share one checkbox in MCM, so unchecking it keeps all of "
                                 "them disabled in that season.") % _and_each(same))
        for line in shadow_check(force=(a.cmd == "status")):
            print(line)
        sound_now = soundscape_installed()
        if not SOUND_SRC:
            _row(pgettext("report", "soundscape"), _("none set up"))
        else:
            listed = any(l[1:] == SOUND_SRC for l in (_modlist_lines() or [])
                         if l[:1] in ("+", "-"))
            _row(pgettext("report", "soundscape"),
                 (_("staged for %s") % season_label(sound_now) if sound_now
                  else _("none staged"))
                 + ("   " + _("(SOUND_SRC \"%s\" is not in MO2's mod list; check the name)")
                    % SOUND_SRC if not listed else
                    "   " + _("(\"%s\" is disabled in MO2, so the soundscape is off)")
                    % SOUND_SRC if not _mod_enabled(SOUND_SRC) else
                    "" if prefs["stage_sound"] else "   " + _("(gating is off in MCM)")))
        shipped, present, copied = install_presets(writing)
        if shipped:
            _row(pgettext("report", "grade presets"),
                 _("%(shipped)d shipped, %(there)d in appdata")
                 % {"shipped": len(shipped), "there": len(present) + len(copied)}
                 + ("   " + _("(copied: %s)") % ", ".join(copied) if copied else ""))
        print()

        def send_spell():
            """Hand the game today's spell, now that its season is staged."""
            state, why = write_calendar(a.mapping, redraw=False, staged=True)
            if state is None and dial is not None:
                print("  - " + why)

        def say_skipped():
            mods, sets = len(SKIPPED), len(sets_skipped)
            if mods and sets:
                said = _("%(season)s: %(mods)s and %(sets)s skipped; the ! lines above say "
                         "why.") % {
                    "season": title,
                    "mods": ngettext("%d seasonal mod", "%d seasonal mods", mods) % mods,
                    "sets": ngettext("%d texture set", "%d texture sets", sets) % sets}
            elif mods:
                said = ngettext("%(season)s: %(n)d seasonal mod skipped; the ! lines above say "
                                "why.",
                                "%(season)s: %(n)d seasonal mods skipped; the ! lines above "
                                "say why.", mods) % {"season": title, "n": mods}
            elif sets:
                said = ngettext("%(season)s: %(n)d texture set skipped; the ! lines above say "
                                "why.",
                                "%(season)s: %(n)d texture sets skipped; the ! lines above say "
                                "why.", sets) % {"season": title, "n": sets}
            else:
                return
            print("  => " + said)

        # With the texture layer off, whatever is staged stays.
        tex_ok = True if not stage_tex else all(v == want for v in installed.values())
        _ssrc = _sound_src_dir()
        src_live = bool(_ssrc) and os.path.isdir(_ssrc)
        if not src_live:
            # no source, or the source mod is disabled: stale overrides come out
            sound_ok = (sound_now is None) if SOUND_SRC else True
        elif prefs["stage_sound"]:
            sound_ok = (sound_now == want
                        and soundscape_signature() == _sound_signature(want))
        else:
            sound_ok = sound_now is None
        if tex_ok and sound_ok:
            # Toggles are checked even when nothing else moved: a newly installed
            # seasonal mod is absent from the mod list until something inserts it.
            tg = apply_toggles(active, not writing, prefs)
            for name, was, now in tg:
                print("  %-58s %s" % (name[:58], change_text(was, now)))
            if tg and writing:
                print("  => " + _("%s: seasonal mods switched. The game picks this up when it "
                                  "starts.") % title)
            elif tg:
                print("  => " + _("%(season)s: seasonal mods need switching. Start the game "
                                  "with play.bat, or run %(command)s")
                      % {"season": title, "command": command("season.py", "apply")})
            elif SKIPPED or sets_skipped:
                pass                                        # said just below
            elif not stage_tex:
                print("  => " + (_("%s: texture swapping is off for this run (--no-textures), "
                                   "nothing staged; the seasonal atmosphere still runs")
                                 if a.no_textures else
                                 _("%s: texture swapping is off in MCM, nothing staged; the "
                                   "seasonal atmosphere still runs")) % title)
            else:
                print("  => " + _("already on %s, nothing to do") % season_label(want))
            say_skipped()
            if writing:
                write_staged(staged_texture_season(installed) if not stage_tex else want,
                             stage_tex)
                write_mod_panel(active, prefs)
                send_spell()
            return
        if not tex_ok:
            # translators: a texture set, restaged: "Tex Mod (summer) -> autumn"
            change = _("%(mod)s (%(now)s) -> %(want)s")
            print("  => %-8s: %s" % (pgettext("restaged", "textures"), _and_each(
                change % {"mod": m, "want": season_label(want),
                          "now": season_label(installed[m]) if installed[m]
                          else pgettext("a texture set", "unrecognized")}
                for m in installed if installed[m] != want)))
        if not sound_ok:
            # where the source is live, only MCM's switch keeps the soundscape off
            print("  => %-8s: %s -> %s" % (
                pgettext("restaged", "sound"),
                season_label(sound_now) if sound_now else pgettext("the soundscape", "none"),
                season_label(want) if src_live and prefs["stage_sound"] else
                _("off (gating is off in MCM)") if src_live else
                _("off (\"%s\" is not enabled in MO2)") % SOUND_SRC
                if not _mod_enabled(SOUND_SRC) else
                _("off (\"%s\" has no ambient sound files)") % SOUND_SRC))

        if a.cmd == "status" or a.dry_run:
            say_skipped()
            if a.dry_run:
                print("  " + _("(dry run, so nothing was changed)"))
            return
        busy = running()
        if busy:
            raise SystemExit(close_first(busy))

        print()
        done = []
        # Only when the textures are wrong: a sound-only correction must not copy gigabytes.
        for mod, cfg in ([(m, LAYOUT[m]) for m in installed] if not tex_ok else []):
            merged = extract(cfg["archive"], cfg["options"][want],
                             os.path.join(tmp, "apply", mod[:18].replace(" ", "_")))
            target = os.path.join(MODS, mod, "gamedata")
            env = dict(os.environ, MSYS_NO_PATHCONV="1")
            r = subprocess.run(["robocopy", merged, target, "/MIR", "/R:3", "/W:2",
                                "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
                               capture_output=True, text=True, env=env)
            if r.returncode > 7:
                raise SystemExit("  ** " + _("Copying the textures into %(mod)s failed "
                                             "(robocopy code %(code)d). Run play.bat again.")
                                 % {"mod": mod, "code": r.returncode} + " **")
            src, dst = hashes(merged), hashes(target)
            bad = sorted(k for k in set(src) | set(dst) if src.get(k) != dst.get(k))
            # translators: English says MISMATCH for any number
            wrong = ngettext("%d MISMATCH", "%d MISMATCH", len(bad)) % len(bad)
            print("  %-64s %3d %-5s  %s" % (mod[:64], len(dst),
                                            ngettext("file", "files", len(dst)),
                                            _("VERIFIED") if not bad else "** %s **" % wrong))
            if bad:
                raise SystemExit("  " + ngettext(
                    "Stopped: %(n)d file in %(mod)s did not match the archive after copying "
                    "(like %(file)s). Run play.bat again.",
                    "Stopped: %(n)d files in %(mod)s did not match the archive after copying "
                    "(like %(file)s). Run play.bat again.", len(bad))
                    % {"n": len(bad), "mod": mod, "file": bad[0]})
            done.append("textures")

        if not sound_ok:
            if not src_live:
                if os.path.isdir(_sound_dst_dir()):
                    shutil.rmtree(_sound_dst_dir(), ignore_errors=True)
                n, cuts = 0, 0
            else:
                n, cuts = write_soundscape(want, prefs["stage_sound"])
            if n is None:
                print("  %-64s %s" % (pgettext("report", "soundscape"),
                                      _("skipped: \"%s\" is not installed") % SOUND_SRC))
            else:
                got = soundscape_installed()
                # not `active`: that is the list of periods the toggles below still need
                sound_on = prefs["stage_sound"] and src_live
                exp = want if sound_on else None
                label = (ngettext("soundscape -> %(season)s (%(n)d channel cut)",
                                  "soundscape -> %(season)s (%(n)d channel cuts)", cuts)
                         % {"season": season_label(want), "n": cuts}
                         if sound_on else _("soundscape off, its files removed"))
                print("  %-64s %3d %-5s  %s" % (
                    label, n, ngettext("file", "files", n),
                    _("VERIFIED") if got == exp else "** %s **" % (
                        _("reads as %s") % (season_label(got) if got
                                            else pgettext("the soundscape", "none")))))
                if got != exp:
                    raise SystemExit("  " + _("Stopped: the soundscape files did not come out "
                                              "right. Run play.bat again."))
                done.append("soundscape")

        print()
        tg = apply_toggles(active, False, prefs)
        for name, was, now in tg:
            print("  %-58s %s" % (name[:58], change_text(was, now)))
        if tg:
            done.append("seasonal mods")
        # after the toggles, so the panel reports the mod list as it now stands
        write_staged(staged_texture_season(installed) if not stage_tex else want, stage_tex)
        write_mod_panel(active, prefs)
        send_spell()
        # each restaged texture set adds "textures"; say it once
        words = {"textures": pgettext("staged", "textures"),
                 "soundscape": pgettext("staged", "soundscape"),
                 "seasonal mods": pgettext("staged", "seasonal mods")}
        print("  => " + _("%(season)s staged (%(what)s). The game picks this up when it "
                          "starts.")
              % {"season": title,
                 "what": pgettext("between words in a list", ", ").join(
                     words[w] for w in dict.fromkeys(done)) or _("nothing to do")})
        say_skipped()
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
