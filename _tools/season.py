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
import ast
import datetime
import hashlib
import io
import re
import glob
import json
import math
import os
import random
import shutil
import struct
import subprocess
import sys
import time
import tokenize
import traceback
import types
import zlib

import lang
import winter_rain
from lang import _, N_, ngettext, pgettext        # noqa: F401 - used as the strings are marked

# Python 3.8 or later: the config's checks read its syntax tree as 3.8 lays it out, and an
# older Python stopped at the first launch with a traceback. Every tool comes through here,
# play.bat's and, by config_edit, configure.bat's, so this says it in words before anything.
if sys.version_info < (3, 8):
    raise SystemExit("  " + _("Seasons of the Zone's tools need Python 3.8 or later, and this "
                              "is Python %s. Install the latest from python.org, with \"Add "
                              "python.exe to PATH\" checked, then try again.")
                     % ".".join(str(n) for n in sys.version_info[:3]))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# a refusal goes out on stderr, and in another language it has letters cp1252 lacks
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = os.path.join(ROOT, "mods")
DOWNLOADS = os.path.join(ROOT, "downloads")
SOTZ = "Seasons of the Zone"
VERSION = "2.12.0"          # of the tools; build_release.py checks it against CHANGELOG.md
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


def point_rarfile(rarfile):
    """Point rarfile at the tool there is, 7-Zip as its 7-Zip and UnRAR or WinRAR's Rar as
    its UnRAR, and check that it runs: False when neither is installed. Handed 7z.exe as
    UnRAR, rarfile ran 7-Zip with UnRAR's switches, and a .rar failed with only 7-Zip in."""
    tool = _find_unrar()
    if os.path.splitext(os.path.basename(tool))[0].lower() == "7z":
        rarfile.SEVENZIP_TOOL = tool
    else:
        rarfile.UNRAR_TOOL = tool
    try:
        try:
            rarfile.tool_setup(force=True)
        except TypeError:                       # a rarfile from before force=
            rarfile.tool_setup()
    except rarfile.RarCannotExec:
        return False
    return True


def _mo2_ini(key, default=None):
    """A value from the portable ModOrganizer.ini, as MO2 meant it: MO2 writes paths as
    key=@ByteArray(D:\\\\ANOMALY), and a name outside ASCII in escapes (lang.qt_value)."""
    return lang.mo2_setting(ROOT, key, None, default)


def game_dir():
    return _mo2_ini("gamePath", os.path.join(os.path.dirname(ROOT), "ANOMALY"))


def profile_name():
    return _mo2_ini("selected_profile", "G.A.M.M.A")


APPDATA = os.path.join(game_dir(), "appdata")

# With MCM's calendar on the game's clock, the game writes the Zone's date here as it saves
# and loads; play.bat switches by it. CLOCK is the clock this run goes by: "real", "game",
# or "none" for the game's clock with no date written yet, which goes by the real date.
CLOCK_FILE = "seasons_clock.txt"
CLOCK = "real"

# MCM's dice. With "Roll the season at launch" on, each apply draws 1 to 100, and a draw at
# or under the chance runs another season the calendar has on, picked at random, until the
# next launch; the game reads what was rolled from season_calendar.ltx's [roll]. A seed in
# SOTZ_DICE_SEED makes the draws repeatable, for the tests.
DICE_CHANCE = 25            # MCM's default chance, in percent
DICE_SEED = os.environ.get("SOTZ_DICE_SEED")


def clock_files():
    """Where the game's clock file is, the one written last first: appdata, and MO2's
    overwrite/appdata, where MO2 can put a file the game makes in a folder that a mod ships
    files to (Atmospherics ships appdata/). _user_ltx() looks in both too."""
    found = []
    for p in (os.path.join(APPDATA, CLOCK_FILE),
              os.path.join(ROOT, "overwrite", "appdata", CLOCK_FILE)):
        try:
            found.append((os.path.getmtime(p), p))
        except OSError:
            pass
    return [p for t, p in sorted(found, reverse=True)]


def clock_today(prefs=None):
    """The day the seasons run on, and its clock: (the real date, "real"); with MCM's
    calendar on the game's clock, (the Zone's date the game last wrote, "game"), or, with
    none written yet, (the real date, "none")."""
    prefs = read_prefs() if prefs is None else prefs
    if prefs.get("clock") != "game":
        return datetime.date.today(), "real"
    for p in clock_files():
        try:
            text = io.open(p, encoding="utf-8", errors="replace").read()
            m = re.search(r"(?m)^\s*zone\s*=\s*(\d{4})-(\d\d)-(\d\d)\s*$", text)
            if m:
                return (datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))),
                        "game")
        except (OSError, ValueError):
            pass
    return datetime.date.today(), "none"

CONFIG_NAMES = ("LAYOUT", "TOGGLE_MODS", "SOUND_SRC", "PERIODS", "EVENTS", "CALENDAR",
                "NAMES", "WEATHER_PLACE", "OWN_SEASONS", "SPELLS", "MCM_SETTINGS",
                "SEASON_LUTS", "SEASON_ACCENTS", "SEASON_ACCENTS_ON_PACKS")


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
# Other mods' MCM options that follow the season, {"mod/option": {name: value, ...,
# "else": value}}: play.bat sets each in MCM's saved options before the game starts, to
# its value for what is on that day, or its "else".
MCM_SETTINGS = getattr(_cfg, "MCM_SETTINGS", None)
MCM_SETTINGS = {} if MCM_SETTINGS is None else MCM_SETTINGS
# Seasonal LUTs, {season: (source, option, percent)}: the season's color grade moved from
# the game's LUT toward one the player downloaded, by `percent`. See "seasonal LUTs" below.
SEASON_LUTS = getattr(_cfg, "SEASON_LUTS", None)
SEASON_LUTS = {} if SEASON_LUTS is None else SEASON_LUTS
# Seasonal accents, True for Seasons' own or {season: {accent: value}}: color changes built
# into each season's LUT. See "seasonal accents" below.
SEASON_ACCENTS = getattr(_cfg, "SEASON_ACCENTS", None)
# Whether a season with a LUT pack gets the accents too. Not True, its pack's grade stays as
# its author made it, mixed by the percent, and the accents color the seasons without one.
SEASON_ACCENTS_ON_PACKS = getattr(_cfg, "SEASON_ACCENTS_ON_PACKS", None)


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
                                              SPELLS, MCM_SETTINGS, luts=SEASON_LUTS,
                                              accents=SEASON_ACCENTS,
                                              accents_on_packs=SEASON_ACCENTS_ON_PACKS)
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
    """This mod's folders, and the soundscape and LUT it generates: never on the calendar."""
    return set(sotz_copies() or [SOTZ]) | {SOTZ, SOUND_MOD, LUT_MOD}


def config_problems(toggle_mods, layout, sound_src, periods, events, calendar=None,
                    names=None, place=None, own=None, spells=None, mcm=None, luts=None,
                    accents=None, accents_on_packs=None):
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
            if SAVE_CONTENT in cfg and not isinstance(cfg[SAVE_CONTENT], bool):
                problems.append(where + ": " + _("\"%s\" is True or False, without quotes. "
                                                 "True lets play.bat switch a mod that puts "
                                                 "things into saves.") % SAVE_CONTENT)
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
    if mcm is not None:
        problems += mcm_problems(mcm, known)
    if luts is not None:
        problems += lut_problems(luts)
    if accents is not None:
        problems += accent_problems(accents)
    if accents_on_packs is not None and not isinstance(accents_on_packs, bool):
        # translators: follows a setting's name, which stays English
        problems.append("SEASON_ACCENTS_ON_PACKS " + _("must be True or False."))
    return problems


def lut_problems(luts):
    """What is wrong with a SEASON_LUTS table, one sentence each."""
    if not isinstance(luts, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["SEASON_LUTS " + _("must be a table, {season: (source, option, percent)}, or "
                                   "{} for none.")]
    out = []
    for season, spec in luts.items():
        where = "SEASON_LUTS[%r]" % (season,)
        if season not in SEASONS:
            out.append(where + ": " + _("a LUT is for one of the six seasons: %s.")
                       % ", ".join(_q(s) for s in SEASONS))
            continue
        if not isinstance(spec, (tuple, list)) or len(spec) != 3:
            # translators: follows an entry, like PERIODS['x'], which stays English
            out.append(where + " " + _("must be (source, option, percent): an archive in "
                                       "MO2's downloads folder or a mod's folder in MO2, the "
                                       "folder in it that holds gamedata or None, and a "
                                       "whole number from 1 to 100."))
            continue
        source, option, percent = spec
        if not isinstance(source, str) or not source.strip() or _folder_problem(source):
            out.append(where + ": " + _("the source is an archive's file name or a mod's folder "
                                        "name, in quotes."))
        elif source in _own_folders():
            out.append(where + ": " + _("%s is written by season.py itself; name a LUT pack.")
                       % _q(source))
        if option is not None and (not isinstance(option, str) or not option.strip()):
            out.append(where + ": " + _("the option is the folder that holds gamedata, in "
                                        "quotes, or None."))
        if isinstance(percent, bool) or not isinstance(percent, int) or not 1 <= percent <= 100:
            out.append(where + ": " + _("the percent is a whole number from 1 to 100: how far "
                                        "the season's grade moves toward the LUT."))
    return out


def _number(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def accent_problems(accents):
    """What is wrong with SEASON_ACCENTS, one sentence each."""
    if accents is True or accents is False:
        return []
    if not isinstance(accents, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["SEASON_ACCENTS " + _("must be True for Seasons' own accents, False for none, or "
                                      "a table, {season: {accent: value}}.")]
    out = []
    for season, spec in accents.items():
        where = "SEASON_ACCENTS[%r]" % (season,)
        if season not in SEASONS:
            out.append(where + ": " + _("accents are for one of the six seasons: %s.")
                       % ", ".join(_q(s) for s in SEASONS))
            continue
        if not isinstance(spec, dict):
            # translators: follows an entry, like PERIODS['x'], which stays English
            out.append(where + " " + _("must be a table of accents, like {\"vibrance\": 0.2, "
                                       "\"contrast\": 0.1}."))
            continue
        for key, value in spec.items():
            at = "%s[%r]" % (where, key)
            if key not in ACCENT_RANGES:
                out.append(at + ": " + _("not an accent. These are: %s.")
                           % ", ".join(_q(k) for k in ACCENT_RANGES))
                continue
            lo, hi, three = ACCENT_RANGES[key]
            if three:
                ok = (isinstance(value, (tuple, list)) and len(value) == 3
                      and all(_number(x) and lo <= x <= hi for x in value))
                if not ok:
                    out.append(at + ": " + _("three numbers, for red, green and blue, each from "
                                             "%(lo)s to %(hi)s.") % {"lo": lo, "hi": hi})
            elif not (_number(value) and lo <= value <= hi):
                out.append(at + ": " + _("a number from %(lo)s to %(hi)s.") % {"lo": lo, "hi": hi})
    return out


# --- MCM settings -----------------------------------------------------------------------
#
# Another mod's MCM option can follow the season without that mod knowing about this one:
# MCM keeps every option in axr_options.ltx, and reads it as the game starts. play.bat
# sets each option in MCM_SETTINGS there first, to its value for the most specific name on
# that day - a kind of weather, then a spell, an event, a season of one's own, and last the
# season or period - or to its "else" when none is on. A change made in MCM lasts until
# the next launch.

MCM_ELSE = "else"
MCM_KEY = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_.-]+)+$")


def _mcm_value_problem(name, v):
    """Why `v` can't be the value MCM saves for an option, as a sentence, or None."""
    if isinstance(v, (bool, int)):
        return None
    if isinstance(v, float):
        return None if v == v and abs(v) != float("inf") else (
            _("the value for %s isn't a number MCM can hold.") % _q(name))
    if isinstance(v, str):
        if (not v.strip() or v != v.strip() or any(ord(c) < 32 for c in v)
                or any(c in v for c in ";[]") or not _cp1251(v)):
            return (_("the value for %s can't be empty, start or end with a space, or hold "
                      "; [ ], a line break or a letter the game can't show.") % _q(name))
        return None
    return _("the value for %s must be True, False, a number or text in quotes.") % _q(name)


def mcm_problems(settings, known):
    """What is wrong with an MCM_SETTINGS table, one sentence each. `known` is the names an
    option can follow: seasons, periods, events, seasons of one's own, spells, weather."""
    if not isinstance(settings, dict):
        # translators: follows a table's name, like PERIODS, which stays English
        return ["MCM_SETTINGS " + _("must be a table, {\"mod/option\": {\"winter\": True, "
                                    "\"else\": False}}, or {} for none.")]
    out = []
    for key, spec in settings.items():
        where = "MCM_SETTINGS[%r]" % (key,)
        if not isinstance(key, str) or not MCM_KEY.match(key):
            out.append(where + ": " + _("an option is named as MCM saves it: its page and the "
                                        "option, with / between, like \"cold_system/winter\"."))
            continue
        if key.lower().startswith("seasons_zone/"):
            out.append(where + ": " + _("that is one of this mod's own options, which follow "
                                        "the season already. Take the entry out."))
            continue
        if not isinstance(spec, dict):
            # translators: follows an entry, like PERIODS['x'], which stays English
            out.append(where + " " + _("must be {\"winter\": True, \"else\": False}: a "
                                       "value for each season, event, spell or weather it "
                                       "names, and one for the rest of the year."))
            continue
        if MCM_ELSE not in spec:
            out.append(where + ": " + _("it needs \"else\", its value the rest of the year."))
        names = [n for n in spec if n != MCM_ELSE]
        if not names:
            out.append(where + ": " + _("it names no season, event, spell or weather, so it "
                                        "would never change."))
        bad = [str(n) for n in names if n not in known]
        if bad:
            out.append(where + ": " + ngettext(
                "%(names)s is not a season, an event, a spell or weather. Valid: %(valid)s.",
                "%(names)s are not seasons, events, spells or weather. Valid: %(valid)s.",
                len(bad)) % {"names": _and(_q(x) for x in bad), "valid": ", ".join(known)})
        kinds = {"check" if isinstance(v, bool) else "text" if isinstance(v, str)
                 else "number" for v in spec.values()
                 if isinstance(v, (bool, int, float, str))}
        if len(kinds) > 1:
            out.append(where + ": " + _("its values are of more than one kind; MCM keeps an "
                                        "option as a checkbox, a number or text. Give each "
                                        "the same kind."))
        for n, v in spec.items():
            p = _mcm_value_problem(n, v)
            if p:
                out.append(where + ": " + p)
    return out


def mcm_rank(name, spells=None, events=None, own=None):
    """How specific a name is, for an option with more than one of its names on: lowest
    wins. A kind of weather, then a spell, an event, a season of one's own, a season."""
    spells = SPELLS if spells is None else spells
    events = EVENTS if events is None else events
    own = OWN_SEASONS if own is None else own
    return (0 if name in WEATHER_NAMES else 1 if name in spells else 2 if name in events
            else 3 if name in own else 4)


def mcm_values(active, settings=None, rank=None):
    """{"mod/option": (value, the name it follows, or None for its "else")} for a day, given
    the names on then, `active`. Of an option's names on, the most specific wins, and of
    those alike, the first listed."""
    settings = MCM_SETTINGS if settings is None else settings
    rank = mcm_rank if rank is None else rank
    on = set(active)
    out = {}
    for key, spec in settings.items():
        hits = [n for n in spec if n != MCM_ELSE and n in on]
        if hits:
            n = min(hits, key=rank)
            out[key] = (spec[n], n)
        else:
            out[key] = (spec.get(MCM_ELSE), None)
    return out


def mcm_text(v):
    """A value as MCM saves it: true or false, a number without trailing zeros, or text."""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return "%d" % v
    if isinstance(v, float):
        s = ("%.6f" % v).rstrip("0").rstrip(".")
        return "0" if s in ("", "-0") else s
    return str(v)


def mcm_saved(path=None):
    """{option: value, as text} from the [mcm] part of MCM's store; {} when there is none."""
    path = _axr_options() if path is None else path
    if not path:
        return {}
    try:
        raw = io.open(path, encoding="cp1251", errors="replace", newline="").read()
    except OSError:
        return {}
    out, here = {}, None
    for line in raw.splitlines():
        s = line.split(";")[0].strip()
        if s.startswith("[") and s.endswith("]"):
            here = s[1:-1].strip()
        elif here == "mcm" and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def mcm_changes(values, path=None):
    """[(option, as saved or None, as it would be)] for each of `values` MCM's store
    doesn't hold yet."""
    saved = mcm_saved(path)
    return [(k, saved.get(k), mcm_text(v)) for k, v in values.items()
            if saved.get(k) != mcm_text(v)]


def write_mcm(values, path=None):
    """Set options in MCM's store: an option's line in [mcm] gets its new value, keeping the
    file's own layout, and one it doesn't have yet is added to [mcm]. Everything else stays
    byte for byte. The file is kept as it was in _baseline/modfile-backups first, the
    newest ten of them. With no store at all, one is made in overwrite/, where the game
    would make its own; the base game's is empty, so it hides nothing. Returns the
    changes, as mcm_changes() gives them."""
    changes = mcm_changes(values, path)
    if not changes:
        return []
    path = _axr_options() if path is None else path
    if not path:
        path = os.path.join(ROOT, "overwrite", "gamedata", "configs", "axr_options.ltx")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        data = b""
    else:
        data = open(path, "rb").read()
        bk = os.path.join(ROOT, "_baseline", "modfile-backups")
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(path, os.path.join(bk, "axr_options-%s-pre-mcm.ltx"
                                        % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
        old = sorted(glob.glob(os.path.join(glob.escape(bk), "axr_options-*-pre-mcm.ltx")))
        for p in old[:-10]:
            try:
                os.remove(p)
            except OSError:
                pass
    # latin-1 reads every byte as itself, so what isn't changed is written back unchanged
    text = data.decode("latin-1")
    nl = "\r\n" if "\r\n" in text or not text else "\n"
    lines = text.split(nl)
    want = {k: new.encode("cp1251").decode("latin-1") for k, _was, new in changes}
    here, end = None, None
    for i, line in enumerate(lines):
        s = line.split(";")[0].strip()
        if s.startswith("[") and s.endswith("]"):
            here = s[1:-1].strip()
            if here == "mcm":
                end = i
            continue
        if here == "mcm":
            if "=" in s:
                end = i
                k = s.split("=", 1)[0].strip()
                if k in want:
                    lines[i] = line[:line.index("=") + 1] + " " + want.pop(k)
    if want:
        new = ["        %-32s = %s" % (k, v) for k, v in sorted(want.items())]
        if end is None:
            while lines and not lines[-1].strip():
                lines.pop()
            lines += ([""] if lines else []) + ["[mcm]"] + new + [""]
        else:
            lines[end + 1:end + 1] = new
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(nl.join(lines).encode("latin-1"))
    os.replace(tmp, path)
    return changes


def mcm_why(name):
    """What an option follows today, in words: the season or name, or the rest of the year."""
    if name is None:
        return _("the rest of the year")
    return season_label(name) if name in SEASONS else name


# --- grass by the season ----------------------------------------------------------------
#
# The game spaces its grass by r__detail_density, a console setting in appdata's user.ltx,
# and a level reads it as it loads, so it can't follow the season during play. play.bat sets
# it before the game starts: the share of the player's grass the season's MCM page asks for
# (seasons_zone/<season>/grass, in percent), with MCM's switch on the Main page
# (seasons_zone/main/stage_grass). The player's own value is what user.ltx held before
# play.bat first set it, or any value it holds that play.bat didn't write, so a change made
# in the game's options becomes theirs. _baseline/season-grass.json keeps the two.
GRASS_CMD = "r__detail_density"
# each season page's default, in percent; zzz_seasons_of_the_zone_mcm.script has the same
GRASS_SHARE = {"spring": 80, "summer": 100, "autumn": 100, "winter": 60,
               "winter_snow": 40, "late_winter": 60}
GRASS_LOWEST = 20                           # the pages' lowest share
GRASS_RANGE = (0.04, 1.0)                   # what the console takes for r__detail_density
GRASS_STATE = os.path.join(ROOT, "_baseline", "season-grass.json")
DETAIL_SLOT = 2.0                           # a detail slot's side, in meters


def grass_share(v, default=100):
    """A season page's grass share as MCM saved it, a whole percent from GRASS_LOWEST to
    100; `default` for anything else."""
    try:
        n = float(v)
    except (TypeError, ValueError):
        return default
    if n != n:
        return default
    return int(min(100, max(GRASS_LOWEST, round(n))))


def grass_points(density):
    """The places a detail slot can put grass at this r__detail_density: the engine lays a
    grid of ceil(2 / density) + 1 points along each side of a 2 m slot
    (CDetailManager::cache_Decompress), so the count is that squared. It works in floats;
    for a value of up to three decimals, doubles give the same."""
    return (int(math.ceil(DETAIL_SLOT / density)) + 1) ** 2


def grass_density(own, share):
    """(r__detail_density, the share of `own`'s grass it gives, in percent) for about
    `share` percent of the grass `own` gives. The grid comes in steps, so this is the value
    on the 0.01 grid of the game's options, from `own` up, whose grid comes nearest; the
    lowest of a tie. Never denser than `own`."""
    lo, hi = GRASS_RANGE
    own = min(max(own, lo), hi)
    full = grass_points(own)
    if share >= 100:
        return own, 100
    want = full * share / 100.0
    best, gap = own, full - want
    for c in range(int(math.floor(own * 100 + 1e-6)) + 1, int(round(hi * 100)) + 1):
        v = c / 100.0
        g = abs(grass_points(v) - want)
        if g < gap - 1e-9:
            best, gap = v, g
    return best, int(round(100.0 * grass_points(best) / full))


def _user_ltx():
    """appdata's user.ltx as the game reads it, by MO2's rules: overwrite/ if it has one, else
    the highest-priority enabled mod that ships one, else the game's own. None when there
    is none yet: the game makes it the first time it closes."""
    ow = os.path.join(ROOT, "overwrite", "appdata", "user.ltx")
    if os.path.isfile(ow):
        return ow
    for line in _modlist_lines() or []:                 # the top of modlist.txt wins
        if line[:1] == "+":
            p = os.path.join(MODS, line[1:], "appdata", "user.ltx")
            if os.path.isfile(p):
                return p
    p = os.path.join(APPDATA, "user.ltx")
    return p if os.path.isfile(p) else None


def console_value(path, cmd):
    """A console setting's number in user.ltx, the last line of it as the console runs them;
    None when there is no such line, or no number on it."""
    try:
        raw = io.open(path, encoding="latin-1", newline="").read()
    except OSError:
        return None
    value = None
    for line in raw.splitlines():
        parts = line.split(None, 1)
        if parts and parts[0] == cmd:
            try:
                value = float(parts[1]) if len(parts) == 2 else None
            except ValueError:
                value = None
    return value


def grass_state():
    """{"own": the player's value, "wrote": what play.bat last set}, or None."""
    try:
        s = json.loads(io.open(GRASS_STATE, encoding="utf-8").read())
        return {"own": float(s["own"]), "wrote": float(s["wrote"])}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _same(a, b):
    return abs(a - b) < 0.0005


def grass_plan(prefs, season, path=None):
    """What the launch does with the grass: {"path", "now", "own", "want", "share", "got",
    "on", "kept"}, or None with no user.ltx or no grass line in it. "now" is what user.ltx
    holds; "own" the player's value; "want" what it should hold; "share" the percent the
    season's page asks for (100 for anything else, and with the switch off); "got" what
    "want" gives; "kept" whether play.bat keeps the grass: on, or set by it before."""
    path = _user_ltx() if path is None else path
    if not path:
        return None
    now = console_value(path, GRASS_CMD)
    if now is None:
        return None
    st = grass_state()
    own = st["own"] if st and _same(now, st["wrote"]) else now
    on = prefs.get("grass", True)
    # only the six seasons have pages; a period or event staged in their place keeps it all
    share = prefs.get("grass_share", GRASS_SHARE).get(season, 100) if on else 100
    want, got = grass_density(own, share)
    return {"path": path, "now": now, "own": own, "want": want, "share": share, "got": got,
            "on": on, "kept": on or st is not None}


def grass_words(plan):
    """The report's grass line."""
    if plan is None:
        return _("as you set it: there is no user.ltx with %s in it yet") % GRASS_CMD
    shown = {"cmd": GRASS_CMD, "want": mcm_text(plan["want"]), "own": mcm_text(plan["own"])}
    if not plan["on"]:
        said = _("as you set it, %(cmd)s %(own)s (off in MCM)") % shown
    elif plan["got"] >= 100:
        said = _("all of yours, %(cmd)s %(own)s") % shown
    else:
        said = (_("about %(got)d%% of yours, %(cmd)s %(want)s (yours: %(own)s)")
                % dict(shown, got=plan["got"]))
    if not _same(plan["now"], plan["want"]):
        said += "   " + _("(now %s)") % mcm_text(plan["now"])
    return said


def write_console(path, cmd, value):
    """Set one console setting's line in user.ltx, the rest byte for byte, the file kept as
    it was in _baseline/modfile-backups first, the newest ten. A file without the line gets
    it after its last. Returns the text written for the value."""
    data = open(path, "rb").read()
    bk = os.path.join(ROOT, "_baseline", "modfile-backups")
    os.makedirs(bk, exist_ok=True)
    shutil.copy2(path, os.path.join(bk, "user-%s-pre-grass.ltx"
                                    % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
    old = sorted(glob.glob(os.path.join(glob.escape(bk), "user-*-pre-grass.ltx")))
    for p in old[:-10]:
        try:
            os.remove(p)
        except OSError:
            pass
    # latin-1 reads every byte as itself, so what isn't changed is written back unchanged
    text = data.decode("latin-1")
    nl = _detect_nl(text)
    lines = text.split(nl)
    said = mcm_text(value)
    hits = [i for i, l in enumerate(lines) if l.split(None, 1)[:1] == [cmd]]
    for i in hits:
        lines[i] = cmd + " " + said
    if not hits:
        end = len(lines)
        while end and not lines[end - 1].strip():
            end -= 1
        lines.insert(end, cmd + " " + said)
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(nl.join(lines).encode("latin-1"))
    os.replace(tmp, path)
    return said


def send_grass(plan):
    """Set the grass for this launch, and remember it; the change as (was, now), or None.
    Not while the game runs: it saves its own over user.ltx as it closes."""
    if plan is None or not plan["kept"]:
        return None
    change = None
    if not _same(plan["now"], plan["want"]):
        game = [p for p in running() if p.startswith("anomaly")]
        if game:
            print("  - " + _("The grass waits for the next launch: %s is running, and would "
                             "save its own over it.") % _and(game))
            return None
        change = (mcm_text(plan["now"]), write_console(plan["path"], GRASS_CMD, plan["want"]))
    os.makedirs(os.path.dirname(GRASS_STATE), exist_ok=True)
    io.open(GRASS_STATE, "w", encoding="utf-8").write(json.dumps(
        {"own": plan["own"], "wrote": plan["want"]}))
    return change


def _detect_nl(raw):
    crlf = chr(13) + chr(10)
    return crlf if crlf in raw else chr(10)


def replace_file(path, data):
    """Write `data`, bytes, over the file at `path` whole or not at all: into a temp file
    beside it, then renamed over it. A write that fails, a full disk say, leaves the file
    as it was; opened for writing, it was empty before a byte went in."""
    tmp = path + ".tmp"
    try:
        with open(tmp, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise


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
    enabled mod that ships it, else a copy loose in the game's own gamedata/, which a start
    without MO2 leaves. None when there is none; the base game's own is empty."""
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
    if best:
        return best
    loose = os.path.join(game_dir(), "gamedata", "configs", "axr_options.ltx")
    return loose if os.path.isfile(loose) else None


def _slug(name):
    """A mod's name as a key: lower case, letters and digits kept and the rest "_", 48
    characters at most. A letter the game's files can't hold (cp1251) counts as the rest.
    mod_keys() makes each mod's its own."""
    s = "".join(c if c.isalnum() and _cp1251(c) else "_" for c in name.lower())
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:48]


def mod_keys(names=None):
    """{mod: key} for the mods on the calendar, a key each: the MCM checkbox goes by it, and
    season_mods.ltx has a section for it, which the game can't load twice. A mod keeps its
    _slug unless that lost letters the game's files can't hold, or a mod before it by name
    has it already - names that differ only in punctuation, or long ones that start alike;
    then a checksum of its whole name makes it its own."""
    names = TOGGLE_MODS if names is None else names
    out, taken = {}, set()
    for name in sorted(names, key=lambda n: (n.casefold(), n)):
        k = _slug(name)
        if not k or k in taken or any(c.isalnum() and not _cp1251(c) for c in name.lower()):
            k = "%s_%08x" % (k[:39].rstrip("_") or "mod",
                             zlib.crc32(name.encode("utf-8")) & 0xffffffff)
        while k in taken:
            k += "_"
        taken.add(k)
        out[name] = k
    return out


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


def place_name(place=None):
    """A place's name as the tools show it: Chornobyl's in their language. The name the
    weather file and the PDA get is the config's."""
    p = place or DEFAULT_PLACE
    # translators: where the real weather comes from unless the player picks another place
    return _("Chornobyl") if p == DEFAULT_PLACE else p["name"]


def place_words(place=None):
    """Where the weather comes from, in words: "Kyiv (50.45 N, 30.52 E)"."""
    p = place or DEFAULT_PLACE
    north, east = p["lat"] >= 0, p["lon"] >= 0
    # translators: a place and where it is: N north, S south, E east, W west
    text = (_("%(name)s (%(lat).2f N, %(lon).2f E)") if north and east else
            _("%(name)s (%(lat).2f N, %(lon).2f W)") if north else
            _("%(name)s (%(lat).2f S, %(lon).2f E)") if east else
            _("%(name)s (%(lat).2f S, %(lon).2f W)"))
    return text % {"name": place_name(p), "lat": abs(p["lat"]), "lon": abs(p["lon"])}


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
    per-season mod hold is seasons_zone/<season>/mod_<slug>, and a season's grass
    seasons_zone/<season>/grass. Returns {"stage_textures", "stage_sound", "mode", "clock",
    "dice", "dice_chance", "grass", "grass_share": {season: percent}, "off": {season:
    set(slug)}}. No file yet means defaults."""
    out = {"stage_textures": True, "stage_sound": True, "mode": "auto", "clock": "real",
           "dice": False, "dice_chance": DICE_CHANCE, "grass": True,
           "grass_share": dict(GRASS_SHARE), "off": {s: set() for s in SEASONS}}
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
        elif page == "main" and o == "clock":
            out["clock"] = "game" if v.strip().lower() == "game" else "real"
        elif page == "main" and o == "stage_textures":
            out["stage_textures"] = not off
        elif page == "main" and o == "stage_sound":
            out["stage_sound"] = not off
        elif page == "main" and o == "dice":
            out["dice"] = not off
        elif page == "main" and o == "dice_chance":
            out["dice_chance"] = dice_chance(v)
        elif page == "main" and o == "stage_grass":
            out["grass"] = not off
        elif o == "grass" and page in out["grass_share"]:
            out["grass_share"][page] = grass_share(v, GRASS_SHARE[page])
        elif o.startswith("mod_") and off and page in out["off"]:
            out["off"][page].add(o[4:])       # a mod held for that one season
    return out


def dice_chance(v):
    """MCM's chance as saved, "25" or "25.0", as a whole percent from 1 to 100; the default
    when it isn't a number."""
    try:
        n = int(round(float(str(v).strip())))
    except ValueError:
        return DICE_CHANCE
    return min(100, max(1, n))


def roll_season(prefs, on, otherwise, rng=None):
    """MCM's dice for this launch: (season, draw, chance). With the dice off, (None, None,
    None). Otherwise a draw of 1 to 100: at or under the chance, a season picked evenly from
    `on`, the seasons the calendar has on, leaving out `otherwise`, the one that would run
    without the dice, so a hit always changes the season. A miss, or no other season on,
    gives (None, draw, chance)."""
    if not prefs.get("dice"):
        return None, None, None
    chance = prefs.get("dice_chance", DICE_CHANCE)
    if rng is None:
        rng = random.Random(DICE_SEED) if DICE_SEED else random.SystemRandom()
    draw = rng.randint(1, 100)
    pool = [s for s in on if s != otherwise]
    if draw > chance or not pool:
        return None, draw, chance
    return rng.choice(pool), draw, chance


def dice_setting(on, chance):
    """MCM's dice as a setting, in a few words: off, every launch, or a chance."""
    if not on:
        return _("off")
    if chance >= 100:
        return _("every launch rolls another season")
    return _("a %d%% chance at each launch of another season") % chance


def dice_words(prefs, fixed=False, draw=None):
    """The report's dice line when no roll changed the season: the setting, or why it
    didn't roll, or what it drew."""
    chance = prefs.get("dice_chance", DICE_CHANCE)
    if fixed:
        return _("on, but a pinned or forced season is never rolled over")
    if draw is None:
        return dice_setting(True, chance)
    if draw <= chance:
        return _("drew %d, but the calendar has no other season on") % draw
    return _("drew %(draw)d, over %(chance)d, so the calendar's season") % {
        "draw": draw, "chance": chance}


# the seasonal mods apply_toggles() could not place, for the summary line
SKIPPED = []
# (seasonal mod, the "above" it names, the renamed mod placed against instead), as _place
# found them
RENAMED = []


def _find(body, name):
    """The index of `name`'s line in modlist.txt's lines, or None."""
    return next((i for i, l in enumerate(body) if l[:1] in ("+", "-") and l[1:] == name),
                None)


def name_key(name):
    """The part of a mod's folder name that an update leaves alone: the words before the
    first one with a digit in it, without GAMMA's "123- " number, punctuation or case.
    "Atmospherics 2.69 RC7.2 SSS24" and "Atmospherics 2.69 RC7.3 hotfix SSS24" are both
    "atmospherics"."""
    words = []
    for w in re.sub(r"^\d+[a-z]?-\s*", "", name.strip()).split():
        if re.search(r"\d", w):
            break
        w = re.sub(r"[^\w]", "", w.lower())
        if w:
            words.append(w)
    return " ".join(words)


def renamed(name, listed, skip=()):
    """The mod in `listed`, [(name, enabled)], that `name` became when an update renamed its
    folder: the one with the same name_key(). Mods carry their version in the folder name,
    so a seasonal mod set to win over the old name would otherwise be skipped. An enabled
    mod beats a disabled one; None when nothing fits, or more than one mod does."""
    key = name_key(name)
    if len(key) < 3:
        return None
    fits = [(on, n) for n, on in listed if n != name and n not in skip and name_key(n) == key]
    pick = [n for on, n in fits if on] or [n for on, n in fits]
    return pick[0] if len(pick) == 1 else None


def _place(body, name, above, want):
    """Put `name` just above `above` in modlist.txt's lines (a lower line has the higher
    priority) and set it to `want`, "+" or "-", as apply does. Returns (was, now) for a
    change, None for none, or False when `above` is not in the list and no mod in it is
    `above` renamed (see renamed(); a rename it does find goes into RENAMED)."""
    idx, ref = _find(body, name), _find(body, above)
    if ref is None:
        now = renamed(above, [(l[1:], l[:1] == "+") for l in body if l[:1] in ("+", "-")],
                      skip=(name,))
        if now is None:
            return False
        RENAMED.append((name, above, now))
        above, ref = now, _find(body, now)
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


def _place_all(body, wanted):
    """_place for each of `wanted`, [(name, above, "+" or "-")], pass after pass until none
    moves. A mod set to win over another seasonal mod has to follow it when a later entry
    lifts that one past its own anchor: in one pass it landed below both for a launch.
    Returns {name: _place's answer} for those that changed or were skipped, a mod's change
    over the passes as one; loops of "above" are refused by config_problems, so it settles."""
    out, anchor = {}, {}
    for name, above, want in wanted:
        seen = len(RENAMED)
        got = _place(body, name, above, want)
        anchor[name] = RENAMED[-1][2] if len(RENAMED) > seen else above
        if got is not None:
            out[name] = got
    for _pass in range(len(wanted)):
        moved = False
        for name, above, want in wanted:
            if out.get(name) is False:
                continue
            got = _place(body, name, anchor[name], want)
            if got:
                moved = True
                # a later pass only moves a mod: whether it was added, or switched, stays
                if name not in out or out[name][0] in ("+", "-"):
                    out[name] = got
        if not moved:
            break
    return out


def change_text(was, now):
    """A change apply_toggles() makes, in words: "disabled -> enabled", "added, enabled"."""
    return {("absent", "+"): _("added, enabled"), ("absent", "-"): _("added, disabled"),
            ("misplaced", "+"): _("moved, enabled"), ("misplaced", "-"): _("moved, disabled"),
            ("-", "+"): _("disabled -> enabled"), ("+", "-"): _("enabled -> disabled")}[
                (was, now)]


# --- what a seasonal mod leaves in saves ------------------------------------------------
#
# A save keeps each object in it by its section's name. A mod that adds items, puts them in
# traders' stock or a loadout, adds spawns, or creates objects from its scripts leaves
# those in the saves made while it is on. Once it is off, the sections are gone: current
# Modded Exes delete such objects as a save loads, older exes crash on them, and a save
# with one on a quick-use slot won't load ("Can't open section"): each save keeps its own
# slots. So each seasonal mod's files are looked through before it is switched, and a mod
# with any of that is left as it is in MO2, unless its entry says "save_content": True.
# The look costs a walk of the folder and a read of its configs, scripts and .db file
# lists: 0.06 s for thirteen mods and 3,200 files, so it is not cached between runs.

SAVE_CONTENT = "save_content"

# X-Ray's LZHUF, which packs a .db's file list (xrCore's LzHuf.cpp): Okumura's, with N 4096,
# F 60 and THRESHOLD 2, the unpacked size first as a u32, and the tree rebuilt at 0x4000
_LZ_N, _LZ_F, _LZ_THRESHOLD = 4096, 60, 2
_LZ_CHARS = 256 - _LZ_THRESHOLD + _LZ_F
_LZ_T = _LZ_CHARS * 2 - 1
_LZ_R = _LZ_T - 1
_LZ_MAX_FREQ = 0x4000


def _lz_positions():
    """The upper 6 bits of a match's position, and its code's length, by the 8 bits its code
    starts with."""
    code, length = [], []
    for v in range(64):
        n = (3 if v == 0 else 4 if v < 4 else 5 if v < 12 else 6 if v < 24 else 7 if v < 48
             else 8)
        code += [v] * (1 << (8 - n))
        length += [n] * (1 << (8 - n))
    return code, length


_LZ_D_CODE, _LZ_D_LEN = _lz_positions()


def lzhuf_unpack(src):
    """Bytes X-Ray's LZHUF packed, unpacked. ValueError for bytes that don't unpack."""
    T, R, CHARS = _LZ_T, _LZ_R, _LZ_CHARS
    if len(src) < 4:
        raise ValueError("too short to be packed")
    size = struct.unpack_from("<I", src)[0]
    if size > 64 << 20:
        raise ValueError("unpacks to %d bytes" % size)
    data, end = src[4:], len(src) - 4
    freq = [1] * CHARS + [0] * (T + 1 - CHARS)
    prnt = [0] * (T + CHARS)
    son = [0] * T
    for i in range(CHARS):
        son[i] = i + T
        prnt[i + T] = i
    i, j = 0, CHARS
    while j <= R:
        freq[j] = freq[i] + freq[i + 1]
        son[j] = i
        prnt[i] = prnt[i + 1] = j
        i += 2
        j += 1
    freq[T] = 0xFFFF
    prnt[R] = 0
    pos, buf, have = 0, 0, 0            # bytes read; the bit buffer, 16 bits; bits in it

    def bits(n):
        """The next n bits, n at most 8, as a number."""
        nonlocal pos, buf, have
        while have <= 8:
            buf |= (data[pos] if pos < end else 0) << (8 - have)
            pos += 1
            have += 8
        v = buf >> (16 - n)
        buf = (buf << n) & 0xFFFF
        have -= n
        return v

    def rebuild():
        k = 0
        for i in range(T):
            if son[i] >= T:
                freq[k] = (freq[i] + 1) // 2
                son[k] = son[i]
                k += 1
        i, j = 0, CHARS
        while j < T:
            f = freq[i] + freq[i + 1]
            freq[j] = f
            k = j - 1
            while f < freq[k]:
                k -= 1
            k += 1
            freq[k + 1:j + 1] = freq[k:j]
            freq[k] = f
            son[k + 1:j + 1] = son[k:j]
            son[k] = i
            i += 2
            j += 1
        for i in range(T):
            k = son[i]
            if k >= T:
                prnt[k] = i
            else:
                prnt[k] = prnt[k + 1] = i

    def update(c):
        if freq[R] == _LZ_MAX_FREQ:
            rebuild()
        c = prnt[c + T]
        while True:
            freq[c] += 1
            k = freq[c]
            n = c + 1
            if k > freq[n]:
                n += 1
                while k > freq[n]:
                    n += 1
                n -= 1
                freq[c] = freq[n]
                freq[n] = k
                i = son[c]
                prnt[i] = n
                if i < T:
                    prnt[i + 1] = n
                j = son[n]
                son[n] = i
                prnt[j] = c
                if j < T:
                    prnt[j + 1] = c
                son[c] = j
                c = n
            c = prnt[c]
            if c == 0:
                break

    out = bytearray()
    text = bytearray(b" " * _LZ_N)
    r = _LZ_N - _LZ_F
    while len(out) < size:
        if pos > end + 2:
            raise ValueError("the packed bytes end early")
        c = son[R]
        while c < T:
            c = son[c + bits(1)]
        c -= T
        update(c)
        if c < 256:
            out.append(c)
            text[r] = c
            r = (r + 1) & (_LZ_N - 1)
            continue
        i = bits(8)
        hi, n = _LZ_D_CODE[i] << 6, _LZ_D_LEN[i] - 2
        i = (i << n) | bits(n) if n else i
        start = (r - (hi | (i & 0x3F)) - 1) & (_LZ_N - 1)
        for k in range(c - 255 + _LZ_THRESHOLD):
            b = text[(start + k) & (_LZ_N - 1)]
            out.append(b)
            text[r] = b
            r = (r + 1) & (_LZ_N - 1)
    return bytes(out[:size])


def db_files(path):
    """The files an X-Ray .db holds, by the path each is mounted at, with forward slashes:
    read from its file list alone, nothing unpacked. A .db is chunks, [u32 id][u32 size]
    [data]; chunk 1 is the file list, LZHUF-packed when the id's top bit is set, and each
    entry is u16 length, u32 size, u32 packed size, u32 crc, the name, u32 offset.
    ValueError for a file that doesn't read as one."""
    table = None
    with open(path, "rb") as f:
        f.seek(0, 2)
        total = f.tell()
        f.seek(0)
        while True:
            head = f.read(8)
            if not head:
                break
            if len(head) < 8:
                raise ValueError("a chunk is cut short")
            cid, size = struct.unpack("<II", head)
            if f.tell() + size > total:
                raise ValueError("a chunk runs past the end")
            if cid & 0x7FFFFFFF == 1:
                table = f.read(size)
                if cid & 0x80000000:
                    table = lzhuf_unpack(table)
                break
            f.seek(size, 1)
    if table is None:
        raise ValueError("no file list")
    names, p = [], 0
    while p + 2 <= len(table):
        n = struct.unpack_from("<H", table, p)[0]
        if n < 16 or p + 2 + n > len(table):
            raise ValueError("a file list that doesn't read")
        names.append(table[p + 14:p + n - 2].decode("cp1251", "replace").replace("\\", "/"))
        p += 2 + n
    if p != len(table):
        raise ValueError("a file list that doesn't read")
    return [n for n in names if n and not n.endswith("/")]


def _ltx_line(line):
    """An .ltx line as the game reads it: trimmed, and a comment (; or //) taken off unless
    it starts inside quotes."""
    s = line.strip()
    cut = min([x for x in (s.find(";"), s.find("//")) if x >= 0] or [len(s)])
    if cut < len(s):
        q = s.find('"')
        if not (0 <= q < cut < s.find('"', q + 1)):
            s = s[:cut]
    return s.strip()


_LTX_HEAD = re.compile(r"^(!!|!|@)?\[([^\]]*)\]\s*(?::(.*))?$")


def ltx_objects(text):
    """The sections in an .ltx's text that make an object a save can hold: one with
    $spawn, or one with an inventory key (inv_...) and a class, its own or a parent's.
    DLTX's ![...] and !![...] change or delete a section defined elsewhere, so they don't
    count; its @[...] can make one, so it does."""
    out, name, keys, parents = [], None, set(), False

    def close():
        if name and ("$spawn" in keys or ((parents or "class" in keys)
                                          and any(k.startswith("inv_") for k in keys))):
            out.append(name)
    for line in text.splitlines():
        s = _ltx_line(line)
        m = _LTX_HEAD.match(s)
        if m:
            close()
            name = m.group(2).strip() if m.group(1) in (None, "@") else None
            parents, keys = bool((m.group(3) or "").strip()), set()
        elif name is not None and s and s[0] not in "!#":
            keys.add(s.split("=", 1)[0].strip().lower())
    close()
    return out


# Lua that creates an object: alife():create() and the rest of the family, on alife() or
# on a name it is kept in (`local sim = alife()`), and the helpers that call them
_CREATES = re.compile(r"\balife\s*\(\s*\)\s*:\s*create\w*\s*\("
                      r"|\b\w+\s*:\s*create(?:_ammo)?\s*\("
                      r"|\b(?:alife_create\w*|alife_clone\w*|create_ammo|create_squad|"
                      r"spawn_item|buy_supplies)\s*\(")
_LUA_SKIP = re.compile(r"--|[\"']|\[=*\[")
_LUA_LONG = re.compile(r"\[(=*)\[")


def lua_code(text):
    """Lua source with its comments and strings blanked and its line breaks kept: what is
    left is the code, on the lines it was on."""
    out, i, n = [], 0, len(text)
    while i < n:
        m = _LUA_SKIP.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i:m.start()])
        i, tok = m.start(), m.group()
        if tok == "--":
            long = _LUA_LONG.match(text, i + 2)
            if long:
                close = text.find("]" + long.group(1) + "]", long.end())
                end = n if close < 0 else close + len(long.group(1)) + 2
            else:
                end = text.find("\n", i)
                end = n if end < 0 else end
        elif tok in "\"'":
            j = i + 1
            while j < n and text[j] != tok and text[j] != "\n":
                j += 2 if text[j] == "\\" else 1
            end = min(j + 1, n)
        else:
            close = text.find("]" + tok[1:-1] + "]", i + len(tok))
            end = n if close < 0 else close + len(tok)
        out.append(re.sub(r"[^\n]", " ", text[i:end]))
        i = end
    return "".join(out)


def lua_creates(text):
    """(line, call) for the first call in Lua source that creates an object, like (189,
    "sim:create"), or None. A function of that name being defined is not a call."""
    code = lua_code(text)
    for m in _CREATES.finditer(code):
        start = code.rfind("\n", 0, m.start()) + 1
        if re.search(r"\bfunction\s+[\w.:]*$", code[start:m.start()]):
            continue
        return code.count("\n", 0, m.start()) + 1, re.sub(r"\s+", "", m.group())[:-1]
    return None


def save_content(folder):
    """What in the mod folder `folder` ties a save to the mod: [(file, kind, detail)], each
    file by its path in the mod with forward slashes. The kinds:
      "items"    an .ltx in configs/ with sections that make objects; detail, their names
      "trade"    traders' stock: configs/items/trade/, or "trade" a word in the name
      "loadout"  a loadout, a new game's or NPCs': "loadout(s)" a word in the name
      "spawns"   spawns/, or a .spawn
      "script"   a script that creates objects; detail, (line, call)
      "db"       a .db holding a script, a config or spawns, which can't be read from
                 outside; detail, (the first, how many)
      "db?"      a .db whose file list can't be read; detail, why
    Only what the game loads from a mod counts: gamedata/, and the archives in db/. The
    sections are not checked against the game's own, so a mod that only ships a full copy
    of a game file counts too."""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(root, f)
            rel = os.path.relpath(p, folder).replace(os.sep, "/")
            low = rel.lower()
            if low.startswith("db/") and re.search(r"\.x?db\w*$", low) and \
                    f.lower() != "thumbs.db":
                try:
                    inside = db_files(p)
                except (OSError, ValueError) as e:
                    found.append((rel, "db?", str(e)))
                    continue
                held = [n for n in inside if re.match(
                    r"(?:gamedata/)?(?:.*\.(?:script|spawn)$|spawns/|configs/.*\.ltx$)",
                    n.lower())]
                if held:
                    found.append((rel, "db", (held[0], len(held))))
                continue
            if not low.startswith("gamedata/"):
                continue
            g = low[len("gamedata/"):]
            words = re.split(r"[^a-z0-9]+", g.rsplit("/", 1)[-1])
            if g.startswith("spawns/") or g.endswith(".spawn"):
                found.append((rel, "spawns", None))
            elif g.startswith("configs/") and g.endswith(".ltx"):
                if g.startswith("configs/items/trade/") or "trade" in words:
                    found.append((rel, "trade", None))
                elif "loadout" in words or "loadouts" in words:
                    found.append((rel, "loadout", None))
                else:
                    try:
                        names = ltx_objects(io.open(p, encoding="cp1251",
                                                    errors="replace").read())
                    except OSError:
                        continue
                    if names:
                        found.append((rel, "items", names))
            elif g.startswith("scripts/") and g.endswith(".script"):
                try:
                    hit = lua_creates(io.open(p, encoding="cp1251", errors="replace").read())
                except OSError:
                    continue
                if hit:
                    found.append((rel, "script", hit))
    return sorted(found, key=lambda x: x[0].lower())


_SAVE_SCANS = {}                        # a mod folder's save_content(), once a run


def mod_save_content(name):
    """save_content() for the mod `name` in mods/, looked through once a run; [] for one
    that isn't there."""
    folder = os.path.join(MODS, name)
    if folder not in _SAVE_SCANS:
        if not os.path.isdir(folder):
            return []
        _SAVE_SCANS[folder] = save_content(folder)
    return _SAVE_SCANS[folder]


def saves_allowed(cfg):
    """Does a TOGGLE_MODS entry let play.bat switch a mod that puts things into saves?"""
    return isinstance(cfg, dict) and cfg.get(SAVE_CONTENT) is True


def held_for_saves(name, cfg):
    """What in the seasonal mod `name` puts things into saves when its entry `cfg` doesn't
    allow switching it, so play.bat leaves it as it is; [] when it can be switched."""
    return [] if saves_allowed(cfg) else mod_save_content(name)


def _names_text(names, most=3):
    """Names in a list, cut short past `most`."""
    head = pgettext("between words in a list", ", ").join(names[:most])
    more = len(names) - most
    if more <= 0:
        return head
    # translators: a list cut short, as in "a, b, c, d and 2 more"
    return ngettext("%(names)s and %(more)d more", "%(names)s and %(more)d more",
                    more) % {"names": head, "more": more}


def save_content_text(kind, detail):
    """What a file found by save_content() puts into saves, in words."""
    if kind == "items":
        return _("defines items or other objects: %s") % _names_text(detail)
    if kind == "trade":
        return _("puts items in traders' stock")
    if kind == "loadout":
        return _("puts items in loadouts")
    if kind == "spawns":
        return _("adds spawns to the world")
    if kind == "script":
        return _("creates objects (line %(line)d: %(call)s)") % {"line": detail[0],
                                                                 "call": detail[1]}
    if kind == "db":
        return ngettext("holds %(file)s, which can't be checked inside a .db",
                        "holds %(file)s and others like it, %(n)d in all, which can't be "
                        "checked inside a .db", detail[1]) % {"file": detail[0],
                                                               "n": detail[1]}
    return _("a .db whose list of files can't be read (%s), so what it holds is unknown") \
        % detail


def save_content_lines(found, most=5):
    """save_content()'s findings as lines, "file: what it does", cut short past `most`."""
    out = ["%s: %s" % (rel, save_content_text(kind, detail))
           for rel, kind, detail in found[:most]]
    if len(found) > most:
        out.append(ngettext("and %d more file", "and %d more files", len(found) - most)
                   % (len(found) - most))
    return out


def apply_toggles(active, dry_run=False, prefs=None):
    """Enable or disable the seasonal mods and put each just above the mod it wins over.
    Returns [(name, from, to)] for what changed. With the texture layer off, every
    seasonal mod is disabled. A mod that puts things into saves is left as it is, unless
    its entry allows switching it (held_for_saves)."""
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
    keys = mod_keys()
    del SKIPPED[:]
    del RENAMED[:]
    wanted = []
    for name, cfg in TOGGLE_MODS.items():
        if name not in folders:
            continue
        if held_for_saves(name, cfg):
            SKIPPED.append(name)            # the status lines above say why
            continue
        # A mod is on if ANY period it is scoped to is active today - that is what
        # makes an event additive on top of its season. MCM holds are per base
        # period, because that is what has a page.
        on = (bool(set(_when(cfg)) & active_set)
              and prefs["stage_textures"]
              and keys[name] not in prefs["off"].get(base, set()))
        wanted.append((name, cfg["above"], "+" if on else "-"))
    placed = _place_all(body, wanted)
    renames = {mod: now for mod, _was, now in RENAMED}
    for name, above, want in wanted:
        if name in renames:
            print("  ~ " + _("%(mod)s now wins over \"%(now)s\": the mod it is set to win over, "
                             "\"%(was)s\", is not in MO2's mod list, and this looks like the "
                             "same mod renamed by an update.")
                  % {"mod": name[:40], "now": renames[name], "was": above})
            print("    " + _("Pick it in its \"Wins over\" box in configure.bat to keep it."))
        got = placed.get(name)
        if got is False:
            print("  ! " + _("%(mod)s skipped: the mod it wins over, \"%(above)s\", is not in "
                             "MO2's mod list.") % {"mod": name[:40], "above": above})
            print("    " + _("Pick another in its \"Wins over\" box in configure.bat."))
            SKIPPED.append(name)
        elif got:
            changed.append((name,) + got)

    # No Rain in Winter, made by configure.py rain --build, goes off once the calendar no
    # longer has it, as Seasonal LUT does below: taken off with MO2 open, it stayed on and
    # took the rain out of every season
    if winter_rain.MOD not in TOGGLE_MODS and winter_rain.made(MODS):
        i = _find(body, winter_rain.MOD)
        if i is not None and body[i][:1] == "+":
            body[i] = "-" + winter_rain.MOD
            changed.append((winter_rain.MOD, "+", "-"))

    # The generated soundscape is placed too: a folder MO2 finds on its own is added
    # disabled, and it has to sit above its source.
    if SOUND_SRC and _find(body, SOUND_SRC) is not None:
        have = os.path.isdir(os.path.join(MODS, SOUND_MOD))
        if have or _find(body, SOUND_MOD) is not None:
            on = have and prefs["stage_sound"] and _mod_enabled(SOUND_SRC)
            got = _place(body, SOUND_MOD, SOUND_SRC, "+" if on else "-")
            if got:
                changed.append((SOUND_MOD,) + got)
    else:
        # no source set (configure.py sound --off), or one MO2 doesn't list: the soundscape
        # goes off as its files come out (main), or the last season's set plays all year
        i = _find(body, SOUND_MOD)
        if i is not None and body[i][:1] == "+":
            body[i] = "-" + SOUND_MOD
            changed.append((SOUND_MOD, "+", "-"))

    # So is Seasonal LUT: just above the mod whose LUT is today's, on while SEASON_LUTS asks
    # for a LUT and the build is whole. Off, the game's own LUT comes back. A dry run
    # (status) builds nothing, so a build that is due counts as made: apply makes it first.
    if os.path.isdir(os.path.join(MODS, LUT_MOD)) or _find(body, LUT_MOD) is not None:
        base = lut_base(body)
        state = lut_plan_now()["state"]
        on = base is not None and (state == "built" or (dry_run and state == "stale"))
        if base is not None:
            got = _place(body, LUT_MOD, base[0], "+" if on else "-")
            if got:
                changed.append((LUT_MOD,) + got)
        else:
            i = _find(body, LUT_MOD)
            if i is not None and body[i][:1] == "+":
                body[i] = "-" + LUT_MOD
                changed.append((LUT_MOD, "+", "-"))

    if changed and not dry_run:
        # MO2 rewrites modlist.txt from memory on exit, so an edit made while it is open
        # is lost.
        busy = running()
        if busy:
            raise SystemExit(close_first(busy))
        _keep_modlist(p)
        replace_file(p, nl.join([head] + body).encode("utf-8"))
    return changed


def _keep_modlist(p):
    """A copy of MO2's list as it was, before season.py writes it."""
    bk = os.path.join(ROOT, "_baseline", "modfile-backups")
    os.makedirs(bk, exist_ok=True)
    shutil.copy2(p, os.path.join(bk, "modlist-%s-pre-toggle.txt"
                                 % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))


def disable_mod(name):
    """Disable `name` in MO2's list, which has to be closed. True when it was enabled."""
    p = _modlist_path()
    raw = io.open(p, encoding="utf-8", errors="replace", newline="").read()
    nl = _detect_nl(raw)
    lines = raw.split(nl)
    i = _find(lines, name)
    if i is None or lines[i][:1] != "+":
        return False
    lines[i] = "-" + name
    _keep_modlist(p)
    replace_file(p, nl.join(lines).encode("utf-8"))
    return True


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
    wanted mod stays off: "off" (texture layer off), "mod" (unchecked in MCM), None; or
    "saves" for a mod play.bat leaves as it is, on or off, since it puts things into saves
    (held_for_saves)."""
    prefs = prefs if prefs is not None else read_prefs()
    active = [active] if isinstance(active, str) else list(active)
    base, active_set = active[0], set(active)
    body = (_modlist_lines() or [])[1:]
    folders = _mod_folders()
    keys = mod_keys()
    out = []
    for name, cfg in TOGGLE_MODS.items():
        installed = name in folders
        state = next((l[:1] for l in body if l[:1] in ("+", "-") and l[1:] == name), None)
        held = None
        if installed and held_for_saves(name, cfg):
            held = "saves"
        elif not prefs["stage_textures"]:
            held = "off"
        elif keys[name] in prefs["off"].get(base, set()):
            held = "mod"
        out.append((name, installed, state, bool(set(_when(cfg)) & active_set), held))
    return out


# --- no rain in the winters ---------------------------------------------------------------
#
# winter_rain.py makes a mod of the installed weathers that rain, with their rain taken out,
# and configure.py rain --build puts it on the calendar. Each copy names the copy it was
# made from, so a weather mod's update is caught here and the mod made again before the
# toggles switch it.

def rain_refresh(writing):
    """Make No Rain in Winter again when a weather it was made from has changed, and keep
    it above every mod it copies. The lines to print; none when it is current or not set
    up."""
    cfg = TOGGLE_MODS.get(winter_rain.MOD)
    if cfg is None:
        return []
    order = [(l[1:], l[:1] == "+") for l in (_modlist_lines() or [])[1:] if l[:1] in ("+", "-")]
    n = sum(len(x) for x in winter_rain.stale(MODS, order))
    out = []
    if n and writing:
        busy = running()
        if busy:
            # MO2 maps a mod's files when it starts: a copy added now would not reach the game
            out.append("  - " + ngettext(
                "No Rain in Winter is out of date (%(n)d weather changed since it was made), "
                "and is made again at a launch with %(what)s closed.",
                "No Rain in Winter is out of date (%(n)d weathers changed since it was made), "
                "and is made again at a launch with %(what)s closed.", n)
                % {"n": n, "what": _and(busy)})
        else:
            winter_rain.build(MODS, order)
            out.append("  " + ngettext(
                "No Rain in Winter made again: %d weather changed since it was made.",
                "No Rain in Winter made again: %d weathers changed since it was made.", n) % n)
    elif n:
        out.append("  - " + ngettext(
            "No Rain in Winter is out of date: %d weather changed since it was made. play.bat "
            "makes it again.",
            "No Rain in Winter is out of date: %d weathers changed since it was made. play.bat "
            "makes it again.", n) % n)
    above = winter_rain.anchor(MODS, order, list(winter_rain.wanted(MODS, order)))
    if above and above != cfg["above"]:
        # it has to win over the highest mod with a weather it copies, or that mod's rain wins
        out.append("  ~ " + _("No Rain in Winter wins over \"%(now)s\" for this launch: that is "
                              "now the highest mod with a weather it copies, not \"%(was)s\".")
                   % {"now": above, "was": cfg["above"]})
        out.append("    " + _("To keep it that way, run %s") % command("configure.py",
                                                                       "rain --build"))
        cfg["above"] = above
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
# birds_night (owls) and the crows stay all year. Names are matched exactly, and the
# packs spell some two ways, so both spellings are listed.
#
# Two sources are covered. Dark Signal Weather and Ambiance Audio names its insects
# Insects (day) and Insects_night. Dark Signal Amplified renames them bugs_day, bugs_night
# and bugs_swamp, and adds leaf rustle: Foliage/foliage, foliage_lite, tree_lush and
# tree_small (gusts through leaves; tree_sway, tree_tall and the branch snaps are wood and
# wind, and stay). A name a source does not use cuts nothing there.
#
#   spring       crickets are a summer and autumn night sound, so spring nights are owls
#                and the dawn chorus carries the season on its own
#   summer       nothing cut - the full soundscape, and the baseline the rest are read against
#   autumn       day insects are gone by October, but crickets call at night until the
#                first frost, so the night insects stay; the waders have left the marshes
#   winter       nothing stridulates below freezing, and bare trees do not rustle
#   winter_snow  corvids and owls only
#   late_winter  the thaw brings the waterfowl back to the marshes before any insect
#                stirs or any leaf opens
#
# Each season must leave a different set of channels standing, or two of them sound
# alike; _tools/test_soundscape.py checks that against the installed source.
_LEAVES = ("Foliage", "foliage", "foliage_lite", "tree_lush", "tree_small")
_DAY_INSECTS = ("Insects", "insects", "bugs_day", "bugs_swamp")
_NIGHT_INSECTS = ("Insects_night", "bugs_night")
SOUND_CUT = {
    "spring":      _NIGHT_INSECTS,
    "summer":      (),
    "autumn":      _DAY_INSECTS + ("birds_swamp",),
    "winter":      _DAY_INSECTS + _NIGHT_INSECTS + ("birds_swamp",) + _LEAVES,
    "winter_snow": _DAY_INSECTS + _NIGHT_INSECTS + ("birds_swamp", "birds") + _LEAVES,
    "late_winter": _DAY_INSECTS + _NIGHT_INSECTS + _LEAVES,
}

SOUND_TAG = ";; seasonal-soundscape season="
SOUND_SIG = " cuts="


def _sound_signature(season):
    """Short hash of the source mod and the channels cut for `season`. It goes in the
    marker so that editing SOUND_CUT or changing SOUND_SRC makes the generated files stale
    even when the season has not moved - otherwise the change silently does nothing until
    the season turns, and the old source's presets stay on top of the new source."""
    raw = (SOUND_SRC or "") + "|" + ",".join(sorted(SOUND_CUT.get(season, ())))
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:8]


def _sound_src_dir():
    """The source presets folder, or None when no source is configured or the source mod
    is disabled."""
    if not SOUND_SRC or not _mod_enabled(SOUND_SRC):
        return None
    return os.path.join(MODS, SOUND_SRC, "gamedata", *SOUND_REL)


def _sound_dst_dir():
    return os.path.join(MODS, SOUND_MOD, "gamedata", *SOUND_REL)


def sound_sources():
    """The enabled mods that ship ambient sound files (configs/environment/ambients/
    presets/*.ltx), highest in MO2's list first, each with the files' names in lower case:
    the mods SOUND_SRC can name. The generated soundscape itself is left out."""
    out = []
    for line in _modlist_lines() or []:
        if line[:1] != "+" or line[1:] == SOUND_MOD:
            continue
        try:
            files = {f.lower() for f in os.listdir(os.path.join(MODS, line[1:], "gamedata",
                                                                *SOUND_REL))
                     if f.lower().endswith(".ltx")}
        except OSError:
            continue
        if files:
            out.append((line[1:], files))
    return out


def sound_shadow(src=None):
    """The enabled mods above the source that ship some of its ambient sound files, as
    [(mod, files it wins, files the source has)], highest first. The generated files sit
    directly above the source, so these win them back and the season never reaches those
    places: a soundscape pack installed over the one SOUND_SRC names, like Dark Signal
    Amplified over GAMMA's Dark Signal. Empty when no source is set or nothing is above it."""
    src = SOUND_SRC if src is None else src
    if not src:
        return []
    found = sound_sources()
    mine = dict(found).get(src)
    if not mine:
        return []
    out, taken = [], set()
    for name, files in found:
        if name == src:
            break
        won = (files & mine) - taken
        if won:
            out.append((name, len(won), len(mine)))
            taken |= won
    return out


def sound_shadow_text(mod, src, won, total):
    """A pack above the source that wins `won` of its `total` ambient sound files, in words:
    what status and configure.bat's setup both say."""
    return ngettext(
        "\"%(mod)s\" is above \"%(src)s\" and wins %(won)d of its %(total)d ambient sound "
        "file, so the seasons don't reach those places.",
        "\"%(mod)s\" is above \"%(src)s\" and wins %(won)d of its %(total)d ambient sound "
        "files, so the seasons don't reach those places.", total) % {
        "mod": mod, "src": src, "won": won, "total": total}


def sound_shadow_lines(src=None):
    """What sound_shadow found, as lines to print after "  ! ": what wins, and the two ways
    to make it the source: configure.bat's setup, or the command."""
    src = SOUND_SRC if src is None else src
    out = []
    for name, won, total in sound_shadow(src):
        out.append(sound_shadow_text(name, src, won, total))
        out.append(_("To take the soundscape from it instead, pick it in configure.bat under "
                     "\"Texture sets and ambient sound\", or run %s")
                   % command("configure.py", "sound \"%s\"" % name))
    return out


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
    removes the generated folder so the source mod wins again.

    latin-1 reads every byte as itself, and only the channel names change, all ASCII, so
    the rest of each file goes back as it was, whatever its encoding: read as cp1251, a
    byte it lacks (a comment saved as UTF-8) became a letter it can't write, which stopped
    the run with the file being written left empty. The set is made beside the folder and
    swapped in whole, so a run that stops keeps the last season's set as it was."""
    src = _sound_src_dir()
    if not src or not os.path.isdir(src):
        return None, 0
    dst = _sound_dst_dir()
    if not enabled:
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        return 0, 0
    work, old = dst + ".building", dst + ".previous"
    for p in (work, old):
        if os.path.isdir(p):
            shutil.rmtree(p)                    # left by a run that stopped part way
    os.makedirs(work, exist_ok=True)
    cut = set(SOUND_CUT.get(season, ()))
    n = removed = 0
    for f in sorted(os.listdir(src)):
        if not f.lower().endswith(".ltx"):
            continue
        raw = open(os.path.join(src, f), "rb").read().decode("latin-1")
        nl = _detect_nl(raw)
        out = []
        for line in raw.split(nl):
            new = _strip_channels(line, cut) if "sound_channels_dynamic" in line else line
            if new != line:
                removed += 1
            out.append(new)
        body = nl.join([SOUND_TAG + season + SOUND_SIG + _sound_signature(season)]
                       + out)
        with open(os.path.join(work, f), "wb") as fh:
            fh.write(body.encode("latin-1"))
        n += 1
    had = os.path.isdir(dst)
    if had:
        os.replace(dst, old)
    try:
        os.replace(work, dst)
    except OSError:
        if had:
            os.replace(old, dst)                # the last season's set back in its place
        raise
    shutil.rmtree(old, ignore_errors=True)
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


# --- seasonal LUTs -------------------------------------------------------------------------
#
# Screen Space Shaders grades the frame last with a LUT atlas, textures/shaders/
# lut_atlas.dds: 64-cubed LUTs, each laid out as 64 slices of 64 x 64, stacked as groups
# 4096 texels wide. Its command ssfx_lut (intensity, group1, group2, blend) picks the
# groups, and mixes two of them when the shader header (shaders/r3/
# settings_screenspace_LUT.h) defines G_ADVANCE_TRANSITION. Atmospherics ships that define
# off, and its ssfx_lut.script sets each level's group as the level loads: Atmospherics 2.69
# has one group, for every level; G.A.M.M.A.'s Atmospherics has 17, saved as a PNG under
# the .dds name, of which its levels use five.
#
# SEASON_LUTS moves a season's grade from the LUT the game has today toward a LUT the
# player downloaded, by a share: {season: (source, option, percent)}. The source is an
# archive in MO2's downloads folder or a mod's folder in MO2; the option is the folder in
# it that holds gamedata, None when gamedata is at the top. season.py builds the mod
# "Seasonal LUT" from them: an atlas with today's groups first, as they are, then for each
# season with a LUT its mix with each group the levels use; the header that lets two groups
# mix; and configs/seasons_lut.ltx, which tells sotz_lut.script which group is which. The
# mod sits just above the mod whose LUT is today's; the script swaps the level's group for
# the seasons' mixes of it, crossfading as the seasons turn. The packs are other people's
# work, so they stay where the player put them; only the atlas built from them goes into
# the player's mods folder.
LUT_MOD = "Seasonal LUT"
LUT_ATLAS = ("textures", "shaders", "lut_atlas.dds")
LUT_HEADER = ("shaders", "r3", "settings_screenspace_LUT.h")
LUT_INFO = ("configs", "seasons_lut.ltx")
LUT_RECORD = "seasons_lut.json"         # beside gamedata: what the atlas was built from
LUT_GROUP = 4096 * 64 * 4               # one LUT: 64 rows of 4096 32-bit texels
LUT_ARCHIVES = (".zip", ".7z", ".rar")
LUT_LIST_CACHE = os.path.join(ROOT, "_baseline", "season-lut-sources.json")
LUT_SCRIPT = ("scripts", "ssfx_lut.script")     # Atmospherics': the group each level loads
LUT_MOST = 256                          # groups an atlas can hold: D3D11's 16384 rows
_LUT_TAIL = "gamedata/textures/shaders/lut_atlas.dds"
_TEXEL = (2, 1, 0, 3)                   # red, green, blue, alpha in a texel we write: B G R A
_LUT_HEADER_TEXT = (
    "// [ SETTINGS ] [ LUT ]  Seasonal LUT, written by Seasons of the Zone's season.py\r\n"
    "\r\n"
    "#define G_LUT_SIZE_W\t4096.0\t// Width of your LUT texture\r\n"
    "\r\n"
    "#define G_CELLS_SIZE\t64\t\t// Width/Height of your cell\r\n"
    "#define G_CELLS_GROUPS\t%d\t\t// Quantity of tables in your texture\r\n"
    "\r\n"
    "#define G_ADVANCE_TRANSITION\t// blend group1 and group2 by ssfx_lut.w (the seasons' "
    "crossfade)\r\n")


class LutError(Exception):
    """A LUT that can't be used, with the words to say why."""


def _dds_shape(data):
    """(width, height, bytes a texel, offsets) of a DDS uncompressed at 24 or 32 bits a texel,
    8 bits a color; None for anything else. The offsets are where red, green, blue and alpha
    sit in a texel, alpha None when there is none: most packs keep B, G, R, A, as Atmospherics
    does, and a few of Kumo's R, G, B, A."""
    if len(data) < 128 or data[:4] != b"DDS ":
        return None
    h, w = struct.unpack_from("<II", data, 12)
    fourcc, bits = struct.unpack_from("<4sI", data, 84)
    if fourcc != b"\0\0\0\0" or bits not in (24, 32):
        return None
    size = bits // 8
    spots = {0xff: 0, 0xff00: 1, 0xff0000: 2, 0xff000000: 3}
    at = [spots.get(m) for m in struct.unpack_from("<IIII", data, 92)]
    if None in at[:3] or len(set(at[:3])) != 3 or max(at[:3]) >= size:
        return None
    if size == 3 or at[3] in at[:3]:
        at[3] = None
    return w, h, size, at


def _png_shape(data):
    """(width, height, bytes a pixel) of a PNG at 8 bits a color, RGB or RGBA, not
    interlaced; None for anything else."""
    if len(data) < 29 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    w, h, depth, kind, packed, filtered, laced = struct.unpack_from(">IIBBBBB", data, 16)
    if depth != 8 or kind not in (2, 6) or packed or filtered or laced:
        return None
    return w, h, 3 if kind == 2 else 4


def lut_groups(data):
    """How many LUTs an atlas holds, its rows over 64, by its header: a DDS uncompressed at 24
    or 32 bits a texel, or a PNG (G.A.M.M.A.'s Atmospherics saves its atlas as one, under the
    .dds name), 8 bits a color and 4096 texels wide. None for anything else, or a DDS cut
    short."""
    shape = _dds_shape(data)
    if shape:
        if len(data) < 128 + shape[0] * shape[1] * shape[2]:
            return None
    else:
        shape = _png_shape(data)
    if not shape or shape[0] != 4096 or not shape[1] or shape[1] % 64:
        return None
    return shape[1] // 64


def _png_rows(data):
    """The pixels of a PNG _png_shape takes, its rows unfiltered, top to bottom. Sub and Up,
    the filters G.A.M.M.A.'s atlas uses, run on whole rows at once as big numbers; Average
    and Paeth byte by byte."""
    w, h, px = _png_shape(data)
    pos, parts = 8, []
    while pos + 8 <= len(data):
        n, kind = struct.unpack_from(">I4s", data, pos)
        if kind == b"IDAT":
            parts.append(data[pos + 8:pos + 8 + n])
        elif kind == b"IEND":
            break
        pos += 12 + n
    try:
        raw = zlib.decompress(b"".join(parts))
    except zlib.error:
        raise LutError(_("its PNG data is damaged"))
    stride = w * px
    if len(raw) < (stride + 1) * h:
        raise LutError(_("its PNG data is cut short"))
    lo = int.from_bytes(b"\x7f" * stride, "little")
    hi = int.from_bytes(b"\x80" * stride, "little")
    whole = (1 << (8 * stride)) - 1

    def add(a, b):                  # byte by byte, no carry from one byte into the next
        return ((a & lo) + (b & lo)) ^ ((a ^ b) & hi)

    out = bytearray(stride * h)
    up, up_row = 0, bytes(stride)
    for y in range(h):
        at = y * (stride + 1)
        kind, row = raw[at], raw[at + 1:at + 1 + stride]
        if kind in (0, 1, 2):
            x = int.from_bytes(row, "little")
            if kind == 1:           # each byte adds the one a pixel left: a running sum
                step = px
                while step < stride:
                    x = add(x, (x << (8 * step)) & whole)
                    step *= 2
            elif kind == 2:
                x = add(x, up)
            line = x.to_bytes(stride, "little")
        elif kind in (3, 4):
            line = bytearray(row)
            for i in range(stride):
                left = line[i - px] if i >= px else 0
                above = up_row[i]
                if kind == 3:
                    line[i] = (line[i] + ((left + above) >> 1)) & 255
                    continue
                corner = up_row[i - px] if i >= px else 0
                p = left + above - corner
                pa, pb, pc = abs(p - left), abs(p - above), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc
                                      else above if pb <= pc else corner)) & 255
            line = bytes(line)
            x = int.from_bytes(line, "little")
        else:
            raise LutError(_("its PNG data is damaged"))
        out[y * stride:(y + 1) * stride] = line
        up, up_row = x, line
    return bytes(out)


def lut_atlas(data):
    """The LUTs of an atlas lut_groups takes, each 4096 x 64 texels as B, G, R, A (alpha 255
    when it has none). LutError for anything else."""
    n = lut_groups(data)
    if not n:
        raise LutError(_("it is not a LUT atlas these tools read: 4096 texels wide, 64 rows a "
                         "LUT, 8 bits a color, uncompressed"))
    shape = _dds_shape(data)
    if shape:
        size, at = shape[2], shape[3]
        px = data[128:128 + 4096 * 64 * n * size]
    else:
        size = _png_shape(data)[2]
        at = [0, 1, 2, 3 if size == 4 else None]
        px = _png_rows(data)
    count = 4096 * 64 * n
    out = bytearray(count * 4)
    for c in range(3):
        out[_TEXEL[c]::4] = px[at[c]::size]
    out[_TEXEL[3]::4] = px[at[3]::size] if at[3] is not None else b"\xff" * count
    return [bytes(out[i * LUT_GROUP:(i + 1) * LUT_GROUP]) for i in range(n)]


def lut_mix(base, src, share):
    """A LUT moved from `base` toward `src` by `share`, 0 to 1: each color is
    (base x (256 - w) + src x w + 128) / 256, rounded down, w being the share in 256ths.
    Both are LUTs as lut_atlas gives them; the alpha is base's. Each color of all 262,144
    texels is one big number with a 16-bit lane a texel, so one multiplication mixes it."""
    w = int(round(share * 256))
    n = len(base) // 4
    lanes = bytearray(2 * n)
    half = int.from_bytes(b"\x80\x00" * n, "little")
    out = bytearray(base)
    for c in range(3):
        lanes[0::2] = base[c::4]
        a = int.from_bytes(lanes, "little")
        lanes[0::2] = src[c::4]
        b = int.from_bytes(lanes, "little")
        out[c::4] = (a * (256 - w) + b * w + half).to_bytes(2 * n, "little")[1::2]
    return bytes(out)


# Seasonal accents: SEASON_ACCENTS adds color changes to each season's LUT as it is built,
# on top of its pack's LUT or of the game's: saturation (SweetFX Tonemap's), contrast on
# brightness (SweetFX Curves' default curve), a midtone tint and a gain (LiftGammaGain's gamma
# and gain), and vibrance (SweetFX Vibrance: more color where there is little). In that order,
# each clamped to 0-1 as a screen pass would be. Each is a change of color alone, so a LUT
# carries it exactly; the game applies the LUT to the finished image, before the HUD, and
# crossfades the seasons' LUTs as the seasons turn. Seasons' own accents were tuned as ReShade
# presets in the game and moved here, where they need no ReShade. Building them needs numpy.
ACCENT_RANGES = {"saturation": (-1, 1, False), "contrast": (-1, 1, False),
                 "tint": (0.5, 2, True), "gain": (0.5, 2, True),
                 "vibrance": (-1, 1, False), "vibrance_rgb": (0, 10, True)}
# 25/9 of the ReShade values, raised twice by 5/3 at the player's word: those carried a vignette
# the LUT can't, and without it the accents read too faint in the game (2026-10-18, autumn, a
# doorway at noon against the same shots without accents). Then all six were seen in the game
# the same night: summer's contrast went back to 0.25, as 0.42 made the canopy too dark, and late
# winter's tint lifts the midtones by 1.10 (same earthy ratio), as the thaw read too dark.
ACCENTS = {
    "spring": {"vibrance": 0.83, "vibrance_rgb": (0.8, 1.5, 0.9)},           # young greens
    "summer": {"contrast": 0.25, "vibrance": 0.42},                          # high sun
    "autumn": {"vibrance": 0.50, "vibrance_rgb": (1.3, 1.0, 0.6)},           # reds and golds
    "winter": {"saturation": -0.42, "tint": (0.972, 1.0, 1.055)},            # gray, cold
    "winter_snow": {"contrast": 0.28, "tint": (0.958, 0.987, 1.07),          # crisp snow
                    "gain": (0.972, 1.0, 1.055), "vibrance": -0.42},
    "late_winter": {"saturation": -0.33, "tint": (1.146, 1.1, 1.04)},        # mud and thaw
}


def accents_wanted(accents=None):
    """{season: {accent: value}} as SEASON_ACCENTS asks: True gives Seasons' own, False or
    None none; a season left out of a table has none."""
    accents = SEASON_ACCENTS if accents is None else accents
    if accents is True:
        return {s: dict(ACCENTS[s]) for s in SEASONS if s in ACCENTS}
    if not isinstance(accents, dict):
        return {}
    return {s: dict(accents[s]) for s in SEASONS if accents.get(s)}


def accents_built(accents=None, luts=None, on_packs=None):
    """The accents a build puts into the seasons' LUTs: accents_wanted's, less each season
    with a LUT pack unless SEASON_ACCENTS_ON_PACKS is True. A pack's grade stays as its
    author made it, mixed by the percent: accents on top of an authored grade, say spring's
    greens on a pack that already pushes green, can spoil it."""
    wanted = accents_wanted(accents)
    luts = SEASON_LUTS if luts is None else luts
    on_packs = SEASON_ACCENTS_ON_PACKS if on_packs is None else on_packs
    if on_packs is True:
        return wanted
    return {s: a for s, a in wanted.items() if s not in luts}


def _numpy():
    """numpy, or None where it isn't installed."""
    try:
        import numpy
    except ImportError:
        return None
    return numpy


def accent_rgb(np, rgb, accent):
    """The accents applied to colors: `rgb` an (n, 3) array of red, green, blue from 0 to 1."""
    c = np.clip(rgb.astype(np.float64), 0.0, 1.0)
    if accent.get("saturation"):
        diff = c - c.mean(axis=1, keepdims=True)
        s = float(accent["saturation"])
        c = np.clip((c + diff * s) / (1.0 + diff * s), 0.0, 1.0)
    if accent.get("contrast"):
        luma = (c @ np.array([0.2126, 0.7152, 0.0722]))[:, None]
        curve = luma * (luma * (1.5 - luma) + 0.5)
        c = np.clip(luma + (curve - luma) * float(accent["contrast"]) * 2.0 + (c - luma),
                    0.0, 1.0)
    if "tint" in accent or "gain" in accent:
        gain = np.array(accent.get("gain", (1.0, 1.0, 1.0)), np.float64)
        gamma = np.array(accent.get("tint", (1.0, 1.0, 1.0)), np.float64)
        c = np.clip(np.power(np.abs(c * gain), 1.0 / gamma), 0.0, 1.0)
    if accent.get("vibrance"):
        luma = (c @ np.array([0.212656, 0.715158, 0.072186]))[:, None]
        sat = (c.max(axis=1) - c.min(axis=1))[:, None]
        coeff = np.array(accent.get("vibrance_rgb", (1.0, 1.0, 1.0)), np.float64) \
            * float(accent["vibrance"])
        c = np.clip(luma + (c - luma) * (1.0 + coeff * (1.0 - np.sign(coeff) * sat)), 0.0, 1.0)
    return c


def lut_accent(group, accent, np=None):
    """A LUT with the accents applied to each of its colors: a LUT as lut_atlas gives it,
    B, G, R, A; the alpha is kept."""
    np = np or _numpy()
    texels = np.frombuffer(group, dtype=np.uint8).reshape(-1, 4)
    rgb = texels[:, [_TEXEL[0], _TEXEL[1], _TEXEL[2]]] / 255.0
    out = texels.copy()
    done = np.floor(accent_rgb(np, rgb, accent) * 255.0 + 0.5).astype(np.uint8)
    for i in range(3):
        out[:, _TEXEL[i]] = done[:, i]
    return out.tobytes()


def lut_apply(np, group, rgb):
    """Colors through a LUT as SSS's shader reads it (screenspace_lut.h): `rgb` an (n, 3)
    array from 0 to 1, `group` a LUT as lut_atlas gives it. A LUT is 64 slices of 64 x 64
    side by side, blue choosing the slice, red across and green down; the shader reads red
    and green bilinearly and mixes the two slices around blue by its fraction."""
    t = np.frombuffer(group, dtype=np.uint8).reshape(64, 64, 64, 4)     # green, blue, red
    tab = t[..., [_TEXEL[0], _TEXEL[1], _TEXEL[2]]].astype(np.float64) / 255.0
    c = np.clip(np.asarray(rgb, dtype=np.float64), 0.0, 1.0) * 63.0
    lo = np.floor(c).astype(np.intp)
    hi = np.minimum(lo + 1, 63)
    f = c - lo
    r0, g0, b0, r1, g1, b1 = lo[:, 0], lo[:, 1], lo[:, 2], hi[:, 0], hi[:, 1], hi[:, 2]
    fr, fg, fb = f[:, 0:1], f[:, 1:2], f[:, 2:3]

    def plane(b):
        top = tab[g0, b, r0] * (1.0 - fr) + tab[g0, b, r1] * fr
        low = tab[g1, b, r0] * (1.0 - fr) + tab[g1, b, r1] * fr
        return top * (1.0 - fg) + low * fg
    return plane(b0) * (1.0 - fb) + plane(b1) * fb


def lut_preview(luts, accents, on_packs, np=None):
    """What configure.bat's preview shows for a setup it holds, saved or not: {"base": the
    mod whose LUT the game uses, "group": the group most levels use, "game": that LUT,
    "seasons": {season: {"pack": the pack's LUT as its author made it, or None, "label":
    its name and percent, "made": the season's LUT as build_luts makes it from that group,
    "accents": whether they are in it}}, "problems": sentences}."""
    np = np or _numpy()
    out = {"base": None, "group": 0, "game": None, "seasons": {}, "problems": []}
    base = lut_base()
    if base is None:
        out["problems"].append(_("No enabled mod ships a LUT (textures\\shaders\\lut_atlas.dds). "
                                 "Seasonal LUTs grade on top of Screen Space Shaders' LUT, "
                                 "which Atmospherics ships."))
        return out
    try:
        groups = lut_atlas(io.open(base[1], "rb").read())
    except (OSError, LutError) as e:
        out["problems"].append(_("%(mod)s's LUT: %(why)s") % {"mod": "\"%s\"" % base[0],
                                                             "why": e})
        return out
    script = lut_script()
    g = lut_main_group(script and script[1], len(groups))
    out.update(base=base[0], group=g, game=groups[g])
    built = accents_built(accents, luts, on_packs)
    for season in SEASONS:
        pack, label, why = None, None, None
        if season in luts:
            source, option, percent = luts[season]
            label = "%s %d%%" % (lut_name(source, option), percent)
            try:
                path, member, __, ___ = _lut_source(source, option)
                try:
                    data = _lut_read(path, member)
                except Exception:               # a damaged archive, or no py7zr or rarfile
                    raise LutError(_("%s could not be read") % source)
                src = lut_atlas(data)
                if len(src) != 1:
                    why = _("%(season)s's LUT, %(name)s, is not one LUT (a 4096 x 64 atlas).") % {
                        "season": season_label(season), "name": lut_name(source, option)}
                else:
                    pack = src[0]
            except LutError as e:
                why = _("%(season)s's LUT: %(why)s.") % {"season": season_label(season),
                                                         "why": e}
        if why:
            out["problems"].append(why)
        made = groups[g] if pack is None else lut_mix(groups[g], pack, luts[season][2] / 100.0)
        accented = season in built and np is not None
        if accented:
            made = lut_accent(made, built[season], np)
        out["seasons"][season] = {"pack": pack, "label": label, "made": made,
                                  "accents": accented}
    return out


def _dds_header(groups):
    """The header of an atlas of `groups` LUTs, 32 bits a texel as B, G, R, A and no mipmaps:
    Atmospherics 2.69's, its height aside."""
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<7I", head, 4, 124, 0x100f, 64 * groups, 4096, 4096 * 4, 0, 1)
    struct.pack_into("<2I4s5I", head, 76, 32, 0x41, b"\0\0\0\0", 32, 0xff0000, 0xff00, 0xff,
                     0xff000000)
    struct.pack_into("<I", head, 108, 0x1000)
    return bytes(head)


def _lut_option(path):
    """The option an archive member that is a LUT atlas sits in: "" for gamedata at the
    top, None when the member is not a LUT atlas."""
    p = path.replace("\\", "/")
    if not p.lower().endswith(_LUT_TAIL):
        return None
    head = p[:len(p) - len(_LUT_TAIL)]
    if head and not head.endswith("/"):
        return None
    return head.rstrip("/")


def _archive_listing(path):
    """[(name, size)] of an archive's files; None when it can't be read (a .7z without
    py7zr, a .rar without rarfile and a tool for it, or a damaged file)."""
    low = path.lower()
    try:
        if low.endswith(".zip"):
            import zipfile
            with zipfile.ZipFile(path) as z:
                return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
        if low.endswith(".7z"):
            import py7zr
            with py7zr.SevenZipFile(path) as z:
                return [(f.filename, f.uncompressed) for f in z.list() if not f.is_directory]
        if low.endswith(".rar"):
            import rarfile
            if not point_rarfile(rarfile):
                return None
            with rarfile.RarFile(path) as z:
                return [(i.filename, i.file_size) for i in z.infolist() if not i.is_dir()]
    except Exception:
        return None
    return None


def _groups_by_size(size):
    """How many LUTs a DDS of `size` bytes holds, at 32 bits a texel or else 24; 0 when
    neither comes out whole. For an archive's files, which are listed without reading them."""
    for texel in (4, 3):
        n, rest = divmod(size - 128, 4096 * 64 * texel)
        if size > 128 and not rest:
            return n
    return 0


def _file_groups(path):
    """lut_groups of a file; 0 when it can't be read or holds no LUT these tools read."""
    try:
        return lut_groups(io.open(path, "rb").read()) or 0
    except OSError:
        return 0


def lut_choices():
    """The LUTs SEASON_LUTS can name, [(source, option, LUTs in it)]: archives in MO2's
    downloads folder, then mod folders, each in name order. An option is None when gamedata
    is at the top. An archive's listing is cached by its name, size and time; one that can't
    be read is not, so it is read once py7zr or rarfile is in (lut_needs says which)."""
    try:
        cache = json.loads(io.open(LUT_LIST_CACHE, encoding="utf-8").read())
    except (OSError, ValueError):
        cache = {}
    keep, out = {}, []
    names = sorted(os.listdir(DOWNLOADS), key=str.lower) if os.path.isdir(DOWNLOADS) else []
    for f in names:
        p = os.path.join(DOWNLOADS, f)
        if not f.lower().endswith(LUT_ARCHIVES) or not os.path.isfile(p):
            continue
        st = os.stat(p)
        key = "%s|%d|%d" % (f, st.st_size, int(st.st_mtime))
        found = cache.get(key)
        if not isinstance(found, list):
            listing = _archive_listing(p)
            if listing is None:
                continue
            found = []
            for name, size in listing:
                opt = _lut_option(name)
                if opt is not None:
                    found.append([opt, _groups_by_size(size)])
        keep[key] = found
        for opt, n in sorted(found, key=lambda e: e[0].lower()):
            out.append((f, opt or None, n))
    for mod in sorted(os.listdir(MODS), key=str.lower) if os.path.isdir(MODS) else []:
        p = os.path.join(MODS, mod, "gamedata", *LUT_ATLAS)
        if mod != LUT_MOD and os.path.isfile(p):
            out.append((mod, None, _file_groups(p)))
    if keep != cache:
        try:
            os.makedirs(os.path.dirname(LUT_LIST_CACHE), exist_ok=True)
            io.open(LUT_LIST_CACHE, "w", encoding="utf-8").write(json.dumps(keep, indent=1))
        except OSError:
            pass
    return out


def lut_needs():
    """What looking for LUT packs in MO2's downloads folder lacks here, [(package, archives)]:
    py7zr for its .7z archives and rarfile for its .rar, Python packages pip installs, or
    None for the .rar when rarfile is in but neither WinRAR nor 7-Zip is."""
    names = os.listdir(DOWNLOADS) if os.path.isdir(DOWNLOADS) else []
    out = []
    for ext, package in ((".7z", "py7zr"), (".rar", "rarfile")):
        n = len([f for f in names if f.lower().endswith(ext)])
        if not n:
            continue
        try:
            mod = __import__(package)
        except ImportError:
            out.append((package, n))
            continue
        try:
            ok = ext != ".rar" or point_rarfile(mod)
        except Exception:
            ok = False
        if not ok:
            out.append((None, n))
    return out


def lut_name(source, option):
    """A LUT as the player knows it: its option folder's last part, or the source with no
    archive extension, without a leading "LUT - "."""
    name = (option or "").replace("\\", "/").rstrip("/").split("/")[-1] or source
    if name.lower().endswith(LUT_ARCHIVES):
        name = name.rsplit(".", 1)[0]
    if name[:6].lower() == "lut - ":
        name = name[6:]
    return name.strip() or source


def _lut_source(source, option):
    """(path, member, size, mtime) of the atlas an entry names; LutError when it isn't
    there. `member` is None for a mod folder's file."""
    if source.lower().endswith(LUT_ARCHIVES):
        path = os.path.join(DOWNLOADS, source)
        if not os.path.isfile(path):
            raise LutError(_("%s is not in MO2's downloads folder") % source)
        listing = _archive_listing(path)
        if listing is None:
            raise LutError(_("%s could not be read") % source
                           + (" " + _("(a .7z needs py7zr; a .rar needs rarfile and WinRAR or "
                                      "7-Zip)") if not source.lower().endswith(".zip") else ""))
        want = (option or "").replace("\\", "/").strip("/").lower()
        for name, size in listing:
            opt = _lut_option(name)
            if opt is not None and opt.lower() == want:
                st = os.stat(path)
                return path, name, size, int(st.st_mtime)
        raise LutError(_("%(archive)s has no LUT in %(option)s")
                       % {"archive": source, "option": "\"%s\"" % option if option
                          else _("its top folder")})
    path = os.path.join(MODS, source, *([option] if option else []) + ["gamedata"]
                        + list(LUT_ATLAS))
    if not os.path.isfile(path):
        raise LutError(_("%s has no LUT (textures\\shaders\\lut_atlas.dds)")
                       % ("\"%s\"" % source))
    st = os.stat(path)
    return path, None, st.st_size, int(st.st_mtime)


def _lut_read(path, member):
    """The bytes of an atlas: a file, or a member of the archive at `path`."""
    if member is None:
        return io.open(path, "rb").read()
    low = path.lower()
    if low.endswith(".zip"):
        import zipfile
        with zipfile.ZipFile(path) as z:
            return z.read(member)
    if low.endswith(".rar"):
        import rarfile
        point_rarfile(rarfile)
        with rarfile.RarFile(path) as z:
            return z.read(member)
    import py7zr
    import tempfile
    tmp = tempfile.mkdtemp(prefix="sotz_lut_")
    try:
        with py7zr.SevenZipFile(path) as z:
            z.extract(path=tmp, targets=[member])
        return io.open(os.path.join(tmp, *member.replace("\\", "/").split("/")), "rb").read()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def lut_base(body=None):
    """(mod, path) of the LUT the game uses without Seasonal LUT: the enabled mod highest
    in MO2's list that ships a lut_atlas.dds; None when no enabled mod does."""
    return _top_file(LUT_ATLAS, body)


def lut_script(body=None):
    """(mod, path) of the ssfx_lut.script the game runs: the enabled mod highest in MO2's
    list that ships one; None when no enabled mod does."""
    return _top_file(LUT_SCRIPT, body)


def _top_file(rel, body=None):
    lines = body if body is not None else (_modlist_lines() or [])[1:]
    for line in lines:
        name = line[1:]
        if line[:1] == "+" and name != LUT_MOD:
            p = os.path.join(MODS, name, "gamedata", *rel)
            if os.path.isfile(p):
                return name, p
    return None


def _lut_named(path, groups):
    """Each group under `groups` the ssfx_lut.script at `path` gives a level, once a level,
    comments left out."""
    try:
        text = io.open(path, "rb").read().decode("latin-1") if path else ""
    except OSError:
        text = ""
    text = re.sub(r"--\[(=*)\[.*?\]\1\]", "", text, flags=re.S)
    text = re.sub(r"--[^\n]*", "", text)
    return [int(g) for g in re.findall(r"\bgroup\s*=\s*(\d+)", text) if int(g) < groups]


def lut_used(path, groups):
    """The groups of a `groups`-LUT atlas the levels use, by the ssfx_lut.script at `path`:
    each group it names under `groups`, in order (Atmospherics gives each level one, and the
    others a default); [0] when it names none, or there is no script."""
    return sorted(set(_lut_named(path, groups))) or [0]


def lut_main_group(path, groups):
    """The group most levels use, by the ssfx_lut.script at `path`, the lower of two that
    tie; 0 when it names none, or there is no script."""
    named = _lut_named(path, groups)
    return min(set(named), key=lambda g: (-named.count(g), g)) if named else 0


_LUT_PLAN = []


def lut_plan_now(refresh=False):
    """lut_plan(), worked out once a run: it lists archives."""
    if refresh or not _LUT_PLAN:
        _LUT_PLAN[:] = [lut_plan()]
    return _LUT_PLAN[0]


def lut_plan():
    """What SEASON_LUTS asks for, against what is built: a dict with "state" - "none" (no
    LUT asked for), "blocked" (see "problems"), "built" or "stale" (to be built) -, "base",
    "seasons" ({season: (source, option, percent)}), "record" (what a build is made from:
    the game's LUT, the script that gives the levels its groups and the groups they use,
    each season's LUT and the accents built in), "accents" (as accents_built gives them:
    SEASON_ACCENTS's, on a season with a pack only if SEASON_ACCENTS_ON_PACKS), "problems"
    (sentences) and "notes" (sentences about a build that goes ahead)."""
    accents = accents_built()
    plan = {"seasons": dict(SEASON_LUTS), "accents": accents, "problems": [], "notes": [],
            "base": None, "record": None}
    if not SEASON_LUTS and not accents:
        plan["state"] = "none"
        return plan
    base = lut_base()
    if base is None:
        plan["problems"].append(_("No enabled mod ships a LUT (textures\\shaders\\lut_atlas.dds). "
                                  "Seasonal LUTs grade on top of Screen Space Shaders' LUT, "
                                  "which Atmospherics ships."))
        plan["state"] = "blocked"
        return plan
    plan["base"] = base
    groups = _file_groups(base[1])
    if not groups:
        plan["problems"].append(_("%s's LUT is not one Seasonal LUTs can build on: an atlas 4096 "
                                  "texels wide, 64 rows a LUT, 8 bits a color, uncompressed, as "
                                  "Atmospherics' are.") % ("\"%s\"" % base[0]))
        plan["state"] = "blocked"
        return plan
    script = lut_script()
    used = lut_used(script and script[1], groups)
    st = os.stat(base[1])
    # version 4: the ltx's labels have "_" for spaces, so a build made before is made again
    record = {"version": 4, "base": [base[0], st.st_size, int(st.st_mtime)],
              "script": [script[0], os.path.getsize(script[1]), int(os.path.getmtime(script[1]))]
              if script else None, "used": used, "seasons": {}, "accents": {}}
    for season in SEASONS:
        if season not in SEASON_LUTS:
            continue
        source, option, percent = SEASON_LUTS[season]
        try:
            path, member, size, mtime = _lut_source(source, option)
        except LutError as e:
            plan["problems"].append(_("%(season)s's LUT: %(why)s.")
                                    % {"season": season_label(season), "why": e})
            continue
        if (_groups_by_size(size) if member is not None else _file_groups(path)) != 1:
            plan["problems"].append(_("%(season)s's LUT, %(name)s, is not one LUT (a "
                                      "4096 x 64 atlas).")
                                    % {"season": season_label(season),
                                       "name": lut_name(source, option)})
            continue
        record["seasons"][season] = [source, option, percent, size, mtime]
    if accents and _numpy() is None:
        install = "%s -m pip install numpy" % _python()
        if record["seasons"]:
            plan["notes"].append(_("The seasons' accents need numpy, which isn't installed, so "
                                   "the LUTs are built without them. To add them, run: %s")
                                 % install)
        elif not plan["problems"]:
            plan["problems"].append(_("The seasons' accents need numpy, which isn't installed. "
                                      "Install it with: %s") % install)
    elif accents:
        # as the record's JSON gives them back, so a built record compares equal
        record["accents"] = {s: {k: list(v) if isinstance(v, (tuple, list)) else v
                                 for k, v in a.items()} for s, a in accents.items()}
    plan["record"] = record
    total = groups + len(set(record["seasons"]) | set(record["accents"])) * len(used)
    if total > LUT_MOST:
        plan["problems"].append(_("Seasonal LUT would hold %(n)d LUTs, and an atlas holds at "
                                  "most %(most)d.") % {"n": total, "most": LUT_MOST})
    if plan["problems"]:
        plan["state"] = "blocked"
        return plan
    try:
        built = json.loads(io.open(os.path.join(MODS, LUT_MOD, LUT_RECORD),
                                   encoding="utf-8").read())
    except (OSError, ValueError):
        built = None
    have = all(os.path.isfile(os.path.join(MODS, LUT_MOD, "gamedata", *rel))
               for rel in (LUT_ATLAS, LUT_HEADER, LUT_INFO))
    plan["state"] = "built" if have and built == record else "stale"
    return plan


def build_luts(plan):
    """Build Seasonal LUT from a plan that is "stale": the atlas - the game's groups as they
    are, then for each season with a LUT or accents, each group the levels use mixed with the
    season's LUT and given its accents -, the header and the ltx, then the record. Returns
    how many seasons have a LUT. LutError when a source turns out unusable."""
    base_mod, base_path = plan["base"]
    try:
        base = lut_atlas(io.open(base_path, "rb").read())
    except LutError as e:
        raise LutError(_("%(mod)s's LUT: %(why)s") % {"mod": "\"%s\"" % base_mod, "why": e})
    used = plan["record"]["used"]
    accents = plan["record"].get("accents") or {}
    np = _numpy() if accents else None
    groups, index, labels = list(base), {}, {}
    for season in SEASONS:
        got = plan["record"]["seasons"].get(season)
        accent = accents.get(season)
        if not got and not accent:
            continue
        src, share = None, 0.0
        if got:
            source, option, percent = got[0], got[1], got[2]
            name = lut_name(source, option)
            path, member, __, ___ = _lut_source(source, option)
            try:
                data = _lut_read(path, member)
            except Exception:                   # a damaged archive: py7zr's and rarfile's own
                raise LutError(_("%s could not be read") % source)
            try:
                src = lut_atlas(data)
            except LutError as e:
                raise LutError(_("%(season)s's LUT, %(name)s: %(why)s")
                               % {"season": season_label(season), "name": name, "why": e})
            if len(src) != 1:
                raise LutError(_("%(season)s's LUT, %(name)s, is not one LUT (a 4096 x 64 "
                                 "atlas)") % {"season": season_label(season), "name": name})
            share = percent / 100.0
            labels[season] = "%s %d%%" % (name, percent)
        index[season] = []
        for g in used:
            group = base[g] if src is None else lut_mix(base[g], src[0], share)
            if accent:
                group = lut_accent(group, accent, np)
            groups.append(group)
            index[season].append((g, len(groups) - 1))
    atlas = _dds_header(len(groups)) + b"".join(groups)
    header = (_LUT_HEADER_TEXT % len(groups)).encode("ascii")
    info = ["; written by Seasons of the Zone's season.py from SEASON_LUTS and SEASON_ACCENTS, "
            "for sotz_lut.script: for each season with a LUT or accents, each group of the "
            "game's that levels use and the group of its mix with the season's LUT and accents",
            "[seasons_lut]",
            "atlas_bytes = %d" % len(atlas),
            "header_bytes = %d" % len(header),
            "base = %s" % base_mod,
            "base_groups = %d" % len(base)]
    info += ["%s = %s" % (s, ", ".join("%d:%d" % pair for pair in index[s]))
             for s in SEASONS if s in index]
    # "_" for each space: the game's reader drops the spaces in a value, which showed
    # "FoveaMemory50%"; sotz_lut.script turns them back, as group_label's are
    info += ["", "[labels]"] + ["%s = %s" % (s, labels[s].replace(" ", "_")) for s in SEASONS
                                if s in labels]
    # the seasons whose groups carry accents; the script says so in the player's language
    info += ["", "[accents]"] + ["%s = true" % s for s in SEASONS if s in accents]
    dest = os.path.join(MODS, LUT_MOD)
    for rel, data in ((LUT_ATLAS, atlas), (LUT_HEADER, header),
                      (LUT_INFO, ("\r\n".join(info) + "\r\n").encode("cp1251", "replace"))):
        p = os.path.join(dest, "gamedata", *rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p + ".tmp", "wb") as f:
            f.write(data)
        os.replace(p + ".tmp", p)
    meta = os.path.join(dest, "meta.ini")
    if not os.path.isfile(meta):
        io.open(meta, "w", encoding="utf-8", newline="\r\n").write(
            "[General]\ngameName=stalkeranomaly\nmodid=0\nversion=\nnewestVersion=\n"
            "category=\"0\"\ninstallationFile=\nnotes=\"Built by Seasons of the Zone's "
            "play.bat from SEASON_LUTS and SEASON_ACCENTS; play.bat places it and rebuilds it. "
            "Not to be edited by hand.\"\n")
    io.open(os.path.join(dest, LUT_RECORD), "w", encoding="utf-8").write(
        json.dumps(plan["record"], indent=1))
    return len(index)


LUT_CMD = "ssfx_lut"


def lut_reset(path=None):
    """A user.ltx ssfx_lut naming a group the atlas the game will load lacks - a season's,
    left from a Seasonal LUT now off or holding fewer - samples outside it until a level
    loads and Atmospherics sets the level's: put its groups back to 0, the intensity kept.
    Returns the change as (was, now), or None. Not while the game runs."""
    path = _user_ltx() if path is None else path
    if not path:
        return None
    if _mod_enabled(LUT_MOD):
        atlas = os.path.join(MODS, LUT_MOD, "gamedata", *LUT_ATLAS)
    else:
        base = lut_base()
        atlas = base[1] if base else None
    groups = _file_groups(atlas) if atlas else 0
    if not groups:
        return None
    try:
        text = io.open(path, "rb").read().decode("latin-1")
    except OSError:
        return None
    nl = _detect_nl(text)
    lines = text.split(nl)
    hits = [i for i, l in enumerate(lines) if l.split(None, 1)[:1] == [LUT_CMD]]
    if not hits:
        return None
    nums = re.findall(r"-?\d+(?:\.\d+)?", lines[hits[-1]].split(None, 1)[1]
                      if len(lines[hits[-1]].split(None, 1)) == 2 else "")
    if len(nums) < 4 or all(float(n) < groups - 0.5 for n in nums[1:3]):
        return None
    if [p for p in running() if p.startswith("anomaly")]:
        return None
    now = "(%s, 0.000000, 0.000000, 0.000000)" % ("%.6f" % float(nums[0]))
    was = lines[hits[-1]].split(None, 1)[1].strip()
    for i in hits:
        lines[i] = LUT_CMD + " " + now
    replace_file(path, nl.join(lines).encode("latin-1"))
    return was, now


def lut_words(plan):
    """The report's LUT line for a plan."""
    if plan["state"] == "none":
        return _("none (configure.bat sets them)")
    if plan["state"] == "blocked":
        return _("not built: the ! lines below say why")
    accented = (plan["record"] or {}).get("accents") or {}
    shown = []
    for s in SEASONS:
        lut = ("%s %d%%" % (lut_name(plan["seasons"][s][0], plan["seasons"][s][1]),
                            plan["seasons"][s][2]) if s in plan["seasons"] else None)
        if s in accented:
            # translators: a season's LUT and the accents built into it, or the accents alone
            lut = (_("%s + accents") % lut) if lut else _("accents")
        if lut:
            shown.append(_("%(season)s %(lut)s") % {"season": season_label(s), "lut": lut})
    used = (plan["record"] or {}).get("used") or [0]
    words = (_("%(luts)s; built on %(base)s's LUT") if len(used) == 1 else
             _("%(luts)s; built on the %(n)d LUTs of %(base)s that levels use")) % {
        "luts": ", ".join(shown), "base": plan["base"][0], "n": len(used)}
    return words if plan["state"] == "built" else words + "   " + _("(to be built)")


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

    rows, keys = [], mod_keys()
    for name, cfg in TOGGLE_MODS.items():
        inst, state, want, held = status[name]
        # a mod play.bat leaves as it is gets no checkbox, which could not switch it
        if not inst or held == "saves":
            continue
        n, b = _mod_weight(os.path.join(MODS, name))
        rows.append({
            "key": keys[name], "name": _display(name), "folder": name,
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
        desc = ("%s. %s %s, %s MB. Uncheck to leave it out of this season, from the next "
                "start with play.bat."
                % (cap_first(seas), "{:,}".format(r["files"]),
                   "file" if r["files"] == 1 else "files", mb))
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
        elif (any(ord(c) < 32 or ord(c) == 127 for c in name)
              or any(c in name for c in ",;[]=")):
            # season_mods.ltx lists a mod's seasons with commas, in an ini file
            out.append(where + ": " + _("the name can't contain , ; [ ] = or a line break."))
        elif not _cp1251(name):
            out.append(where + ": " + _("the name has letters the game can't show. Use "
                                        "English or Cyrillic letters."))
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
        elif (any(ord(c) < 32 or ord(c) == 127 for c in name)
              or any(c in name for c in ",;[]=")):
            out.append(where + ": " + _("the name can't contain , ; [ ] = or a line break."))
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
            bad = [str(x) for x in start
                   if not isinstance(x, str) or (x not in SEASONS and x not in own)]
            off = [x for x in start if isinstance(x, str) and x in SEASONS and x not in on]
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


def days_on(name, base, own=None, events=None, spells=None):
    """The days of 2026, a year without February 29, that `name` is on: a base period on
    the days `base(day)` names it, a season of the player's own or an event on the days it
    covers, and a spell on every day it can run - from each day it can start on, for as
    long as it can last. None for a kind of weather, which can come any day."""
    own = OWN_SEASONS if own is None else own
    events = EVENTS if events is None else events
    spells = SPELLS if spells is None else spells
    if name in WEATHER_NAMES:
        return None
    year = [datetime.date(2026, 1, 1) + datetime.timedelta(days=i) for i in range(365)]
    if name in own:
        return {d for d in year if _in_window(d, *own[name])}
    if name in events:
        return {d for d in year if event_on(d, events[name])}
    if name in spells:
        spec = spells[name]
        start = spec["in"]
        start = {start} if isinstance(start, str) else set(start)
        most = spell_days(spec)[1]
        out = set()
        for d in year:
            if base(d) in start or any(o in start and _in_window(d, *w)
                                       for o, w in own.items()):
                out.update((d + datetime.timedelta(days=k)).replace(year=2026)
                           for k in range(most))
        return out
    return {d for d in year if base(d) == name}


def meet(when, other, days, bases, spells=None):
    """The names in `when` or `other` that mark the times a mod on in `when` and one on in
    `other` are both on: for each pair that meets, the shorter of the two. The same kind of
    weather meets itself only. A spell that brings a season meets that season's mods, and
    not those of the base periods it takes the place of. `days(name)` is as days_on, and
    `bases` the base periods: the seasons and PERIODS."""
    spells = SPELLS if spells is None else spells
    cache = {}

    def on(p):
        if p not in cache:
            cache[p] = days(p)
        return cache[p]

    out = set()
    for p in when:
        for q in other:
            if p == q:
                out.add(p)
                continue
            brought = None
            for s, b in ((p, q), (q, p)):
                spec = spells.get(s)
                if isinstance(spec, dict) and spec.get("as") and b in bases:
                    brought = s if b == spec["as"] else False
                    break
            if brought is not None:
                if brought:
                    out.add(brought)
                continue
            a, b = on(p), on(q)
            if a is None or b is None or not (a & b):
                continue
            out.add(p if len(a) <= len(b) else q)
    return out


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


def dial_language():
    """The language the dial is drawn in: the game's, which the game shows it in whatever
    the window's is; English when the tools have no translation for it."""
    code = lang.game_language()
    if code and code != lang.ENGLISH and lang.load(code) is not None:
        return code
    return lang.ENGLISH


def _signature(table, names=None):
    """What a redrawn dial depends on: the dates and names, the arc colors and drawing
    code, so a mod update that changes either redraws it too, and the language its words
    are in, with that language's translation."""
    h = hashlib.md5(",".join("%s=%d-%d" % t for t in sorted(table)).encode("utf-8"))
    h.update(repr(sorted(custom_names(names).items())).encode("utf-8"))
    code = dial_language()
    h.update(code.encode("utf-8"))
    for p in (os.path.join(MODS, SOTZ, "gamedata", "configs", "seasons_of_the_zone.ltx"),
              os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "build_season_dial.py")) + (
            (lang.po_path(code),) if code != lang.ENGLISH else ()):
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


# --- the player's own, for the game --------------------------------------------------------
#
# season_calendar.ltx carries the player's own seasons, events, periods and spells too, so
# the PDA's Year page can show them and MCM can offer a PDA message for each. The game
# works out which are on by the date itself: with the calendar on the game's clock the
# Zone's date moves on mid-session, past anything worked out at launch. Each comes
# numbered, a part to a line, as "1_name = Wormhole season", because a name can have
# spaces and the game's reader keeps one value to a key. [today] holds what only play.bat
# knows about the day it staged: the kinds of weather, and the spells on, which are drawn
# here and never shown before they come.
YOURS_XML = "ui_mcm_seasons_yours.xml"
# The hover text of each one's switch on MCM's page for them, in the game's languages; the
# name goes in as it is.
YOURS_DESC = {
    "eng": "A PDA message when %s is on as the game starts, and when it begins while you "
           "play.",
    "rus": "Сообщение на КПК, когда «%s» идёт при входе в игру и когда начинается по ходу "
           "игры.",
}


def your_keys():
    """{(kind, name): key} for the player's own seasons ("own"), events, periods and spells:
    MCM's switch for each one's PDA message goes by it, and so do its strings. Letters and
    digits as they are, the rest "_"; a name with letters past ASCII, or one that comes out
    like another's, takes a checksum of its whole name, so a key is the same every run."""
    out, taken = {}, set()
    for kind, table in (("own", OWN_SEASONS), ("event", EVENTS), ("period", PERIODS),
                        ("spell", SPELLS)):
        for name in sorted((n for n in table if isinstance(n, str)),
                           key=lambda n: (n.casefold(), n)):
            s = "".join(c if c.isascii() and c.isalnum() else "_" for c in name.lower())
            while "__" in s:
                s = s.replace("__", "_")
            k = ("%s_%s" % (kind, s.strip("_")[:32])).rstrip("_")
            if k == kind or k in taken or not name.isascii():
                k = "%s_%08x" % (k[:40], zlib.crc32(name.encode("utf-8")) & 0xffffffff)
            while k in taken:
                k += "_"
            taken.add(k)
            out[(kind, name)] = k
    return out


def your_name(kind, name):
    """One of the player's own as the game shows it: a season of their own or a spell as it
    was typed, an event or a period, which are letters and underscores, as words."""
    if kind in ("event", "period"):
        return cap_first(name.replace("_", " "))
    return name


def _mmdd(md):
    return "%02d-%02d" % (int(md[0]), int(md[1]))


def your_sections():
    """season_calendar.ltx's [own], [events], [periods] and [spells], as lines, each section
    after a blank one; [] for a player with none of them."""
    keys = your_keys()
    out = []

    def section(title, rows):
        if rows:
            out.extend(["", "[%s]" % title])
            for i, parts in enumerate(rows, 1):
                out.extend("%d_%s = %s" % (i, k, v) for k, v in parts if v not in (None, ""))

    def head(kind, name):
        return [("name", name), ("key", keys[(kind, name)]), ("show", your_name(kind, name))]

    section("own", [head("own", n) + [("from", _mmdd(w[0])), ("to", _mmdd(w[1]))]
                    for n, w in sorted(OWN_SEASONS.items(),
                                       key=lambda nw: (tuple(nw[1][0]), nw[0].casefold()))])
    rows = []
    for name in sorted(EVENTS, key=lambda n: (n.casefold(), n)):
        spec = EVENTS[name]
        if isinstance(spec, (tuple, list)):
            rows.append(head("event", name) + [("from", _mmdd(spec[0])), ("to", _mmdd(spec[1]))])
            continue
        parts = head("event", name)
        for k in ("weekdays", "days", "weeks", "months"):
            if k in spec:
                parts.append((k, ", ".join(str(x) for x in spec[k])))
        if "within" in spec:
            parts.append(("within", "%s, %s" % (_mmdd(spec["within"][0]),
                                                _mmdd(spec["within"][1]))))
        rows.append(parts)
    section("events", rows)
    section("periods", [head("period", n) + [("from", _mmdd(md))]
                        for n, md in sorted(PERIODS.items(), key=lambda nm: tuple(nm[1]))])
    rows = []
    for name in sorted(SPELLS, key=lambda n: (n.casefold(), n)):
        spec = SPELLS[name]
        lo, hi = spell_days(spec)
        start = spec["in"]
        start = [start] if isinstance(start, str) else list(start)
        rows.append(head("spell", name) + [("in", ", ".join(start)),
                                           ("chance", "%g" % float(spec["chance"])),
                                           ("days", "%d, %d" % (lo, hi)),
                                           ("as", spec.get("as") or "")])
    section("spells", rows)
    return out


def today_section(day):
    """[today], as lines after a blank one: the day play.bat staged, the kinds of weather it
    found for it, and each spell on, with its days and the season it brings. [] when there
    is none of these, which leaves Polesia's calendar file as it ships."""
    keys = your_keys()
    out = []
    flags = weather_flags()
    if flags:
        out.append("weather = %s" % ", ".join(flags))
    for i, (name, first, last) in enumerate(spells_on(day), 1):
        out += ["%d_spell = %s" % (i, name), "%d_key = %s" % (i, keys.get(("spell", name), "")),
                "%d_first = %s" % (i, first.isoformat()), "%d_last = %s" % (i, last.isoformat())]
        if SPELLS[name].get("as"):
            out.append("%d_as = %s" % (i, SPELLS[name]["as"]))
    return ["", "[today]", "day = %s" % day.isoformat()] + out if out else []


def write_your_strings():
    """The labels of MCM's switches for the player's own, a switch for each season, event,
    period and spell, in English and Russian: its name, and what the switch does. Rewritten
    with the calendar file, so the two always name the same ones."""
    d = os.path.join(MODS, SOTZ, "gamedata", "configs", "text")
    if not os.path.isdir(d):
        return
    keys = your_keys()
    for code, desc in sorted(YOURS_DESC.items()):
        x = ['<?xml version="1.0" encoding="windows-1251"?>', "",
             "<!-- generated by _tools/season.py - the labels of MCM's switches for the",
             "     player's own seasons, events, periods and spells. -->",
             "<string_table>"]
        for (kind, name), key in sorted(keys.items(), key=lambda kv: kv[1]):
            shown = _xml_escape(your_name(kind, name))
            x += ['\t<string id="ui_mcm_seasons_zone_ann_%s"><text>%s</text></string>'
                  % (key, shown),
                  '\t<string id="ui_mcm_seasons_zone_ann_%s_desc"><text>%s</text></string>'
                  % (key, desc % shown)]
        x += ["</string_table>", ""]
        body = chr(13) + chr(10)
        body = body.join(x)
        path = os.path.join(d, code, YOURS_XML)
        try:
            old = io.open(path, encoding="cp1251", errors="replace", newline="").read()
        except OSError:
            old = None
        if old != body:
            try:
                os.makedirs(os.path.dirname(path), exist_ok=True)
                io.open(path, "w", encoding="cp1251", errors="replace",
                        newline="").write(body)
            except OSError:
                pass


def write_calendar(mapping="pheno", calendar=None, redraw=True, names=None, staged=False,
                   today=None, roll=None):
    """Write configs/season_calendar.ltx for the game, and draw the dial a custom calendar
    needs. Returns (dial state, a sentence to show or None). The spell and the roll in the
    file are the ones play.bat last staged, so the game keeps to what is staged: they stay
    as they are unless `staged` says this run has just staged `today`'s season, spell or
    not, and `roll`, (season, draw, chance), what MCM's dice rolled for it."""
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
                with lang.speaking(dial_language()):
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
    # the player's own seasons, events, periods and spells, which the PDA and MCM show
    lines += your_sections()
    write_your_strings()
    if staged:
        # the spell that brings a season today, for the game to follow while its dates
        # last; an MCM pin still wins over it in game, as it does here. A roll of the dice
        # fixes the season for the launch, as a pin does, so it leaves the spell out.
        brings, spell = spell_season(today or datetime.date.today())
        if spell and not roll:
            lines += ["", "[spell]", "season = %s" % brings, "name = %s" % spell[0],
                      "first = %s" % spell[1].isoformat(),
                      "last = %s" % spell[2].isoformat()]
        if roll:
            # what MCM's dice rolled for this launch; the next apply rolls again or clears it
            lines += ["", "[roll]", "season = %s" % roll[0], "draw = %d" % roll[1],
                      "chance = %d" % roll[2],
                      "day = %s" % (today or datetime.date.today()).isoformat()]
        lines += today_section(today or datetime.date.today())
    else:
        lines += _staged_sections(path)
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


def _staged_sections(path, names=("spell", "roll", "today")):
    """The [spell], [roll] and [today] sections of the calendar file as they stand, as
    lines, each after a blank one; [] when it has none of them."""
    try:
        old = io.open(path, encoding="cp1251", errors="replace").read().splitlines()
    except OSError:
        return []
    out, keep = [], False
    for line in old:
        s = line.strip()
        if s.startswith("["):
            keep = s.lower() in ["[%s]" % n for n in names]
            if keep:
                out.append("")
        if keep and s:
            out.append(line.rstrip())
    return out


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

    None on the game's clock: the real weather is not the Zone's day's.
    """
    if CLOCK == "game":
        return []
    path = os.path.join(MODS, SOTZ, "gamedata", "configs", "season_weather.ltx")
    if not os.path.exists(path):
        return []
    try:
        section, low, high, when, there, ahead = None, None, None, None, {}, {}
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
            if section == "forecast":
                ahead[k] = v
            if section != "weather":
                continue
            if k == "low":
                low = float(v)
            elif k == "high":
                high = float(v)
            elif k == "date":
                when = v
        # the day from the forecast the file keeps, when the last fetch was days ago: a
        # launch without a connection still has it
        row = ahead.get(datetime.date.today().isoformat())
        if row:
            parts = [x.strip() for x in row.split(",")]
            high, low, when = float(parts[0]), float(parts[1]), datetime.date.today().isoformat()
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


# --- Real Time Zone ---------------------------------------------------------------------
# Real Time Zone (RTZ), DamageZedd's add-on for this mod, runs the game's clock on real time
# and takes the sky from the real weather each hour. From 1.0.2 it reads the hours from
# season_weather.ltx's [hourly], which fetch_weather.py writes, and from its own
# rtz_weather.ltx only when ours has none and its own is dated today. From 1.0.3 ours count
# for a day from their `start`; past that it reads its own of today, else models the sky
# from [forecast]. 1.0.0 and 1.0.1 read their own file first, and ship one, a sample day for
# Ottawa, so until its setup_rtz.bat installs the fetcher that rewrites it, they read that
# same day forever. The report says which file RTZ reads, and what to do when it is the
# wrong one.
RTZ_MARKER = ("gamedata", "scripts", "rtz_main.script")
RTZ_WEATHER = ("gamedata", "configs", "rtz_weather.ltx")
RTZ_FETCHER = "fetch_rtz_hourly.py"       # what setup_rtz.bat copies into _tools
RTZ_STALE_DAYS = 1
RTZ_SEASONS_FIRST = (1, 0, 2)             # the first release that reads our hours first
RTZ_FRESH_FIRST = (1, 0, 3)               # the first that reads them for a day from start
RTZ_HOURS_LAST = 86400                    # that day, in seconds, as rtz_weather.script has it


def _ltx_sections(path):
    """{section: {key: value}} of an ltx, comments dropped; {} when it can't be read."""
    out, here = {}, None
    try:
        for line in io.open(path, encoding="cp1251", errors="replace"):
            line = line.split(";")[0].strip()
            if line.startswith("[") and line.endswith("]"):
                here = out.setdefault(line[1:-1].strip(), {})
            elif here is not None and "=" in line:
                k, v = line.split("=", 1)
                here[k.strip()] = v.strip()
    except OSError:
        return {}
    return out


def rtz_folder():
    """The enabled mod that is Real Time Zone, found by its main script: MO2 names a mod
    after its archive. None without it."""
    try:
        names = sorted(n for n in os.listdir(MODS)
                       if os.path.isfile(os.path.join(MODS, n, *RTZ_MARKER)))
    except OSError:
        return None
    on = [n for n in names if _mod_enabled(n)]
    return os.path.join(MODS, on[0]) if on else None


def rtz_version(folder):
    """Real Time Zone's version, from the line its main script logs as it starts, as a tuple
    of ints; None when the script doesn't say."""
    try:
        text = io.open(os.path.join(folder, *RTZ_MARKER), encoding="cp1251",
                       errors="replace").read()
    except OSError:
        return None
    m = re.search(r"Real Time Zone \(RTZ\) v(\d+)\.(\d+)\.(\d+)", text)
    return tuple(int(n) for n in m.groups()) if m else None


def hourly_start(sections):
    """When season_weather.ltx's [hourly] starts, a time.time() on this PC's clock, read as
    rtz_weather.script reads it; None when it has no start that reads."""
    m = re.match(r"^(\d+)-(\d+)-(\d+)T(\d+):(\d+)", sections.get("hourly", {}).get("start", ""))
    if not m:
        return None
    try:
        return time.mktime(tuple(int(n) for n in m.groups()) + (0, 0, 0, -1))
    except (OverflowError, ValueError):
        return None


def rtz_plan(now=None):
    """What Real Time Zone reads for the sky's hours, and what leaves that wrong:
    {"state": "none" | "own" | "seasons" | "model", "place", "refreshed", "problems",
    "notes"}. "own" is its rtz_weather.ltx, "seasons" season_weather.ltx's [hourly],
    "model" the sky modeled from season_weather.ltx's forecast, which 1.0.3 falls back on
    when our hours are a day past their start and its own aren't today's. A release that
    doesn't log its version is taken to be the latest."""
    out = {"state": "none", "place": None, "refreshed": False, "problems": [], "notes": []}
    folder = rtz_folder()
    if not folder:
        return out
    here = weather_place()
    own_path = os.path.join(folder, *RTZ_WEATHER)
    own = _ltx_sections(own_path) if os.path.isfile(own_path) else {}
    out["refreshed"] = os.path.isfile(os.path.join(ROOT, "_tools", RTZ_FETCHER))
    ours = _ltx_sections(os.path.join(MODS, SOTZ, "gamedata", "configs", "season_weather.ltx"))
    has_ours = any(k.isdigit() for k in ours.get("hourly", {}))
    has_own = any(k.isdigit() or (k[:1] == "h" and k[1:].isdigit())
                  for k in own.get("hourly", {}))
    version = rtz_version(folder)
    if version is None or version >= RTZ_SEASONS_FIRST:
        at = time.time() if now is None else now
        today = time.strftime("%Y-%m-%d", time.localtime(at))
        # 1.0.2 reads ours whatever their age; from 1.0.3, for a day from their start
        start = hourly_start(ours)
        fresh = has_ours and ((version is not None and version < RTZ_FRESH_FIRST)
                              or (start is not None and 0 <= at - start < RTZ_HOURS_LAST))
        when = {"start": ours.get("hourly", {}).get("start", "").replace("T", " ") or "?"}
        if not fresh and has_own and own.get("place", {}).get("date") == today:
            out["state"] = "own"
            out["place"] = own["place"].get("name") or "?"
            if has_ours:
                out["notes"].append(_(
                    "The hours of the sky play.bat fetched last (%(start)s) are over a day "
                    "old, so Real Time Zone reads its own, dated today, until play.bat fetches "
                    "them again.") % when)
            return out
        if has_ours and not fresh:
            out["state"] = "model"
            out["place"] = place_name(here)
            out["notes"].append(_(
                "The hours of the sky play.bat fetched last (%(start)s) are over a day old, so "
                "Real Time Zone models the sky from the day's forecast until play.bat fetches "
                "them again.") % when)
            return out
    elif has_own:
        out["state"] = "own"
        there = own.get("place", {})
        out["place"] = there.get("name") or "?"
        if out["refreshed"]:
            return out
        try:
            same = (abs(float(there["lat"]) - here["lat"]) < 1e-3
                    and abs(float(there["lon"]) - here["lon"]) < 1e-3)
        except (KeyError, ValueError):
            same = False
        fix = {"file": os.path.relpath(own_path, ROOT), "setup": "setup_rtz.bat",
               "there": out["place"], "here": place_name(here)}
        age = ((now or time.time()) - os.path.getmtime(own_path)) / 86400.0
        if not same:
            # translators: two places; %(file)s, a path, and %(setup)s, a file, stay as they are
            out["problems"].append(_(
                "Real Time Zone's hours of the sky are for %(there)s, not %(here)s, and "
                "nothing refreshes them. Delete %(file)s and it reads the hours play.bat "
                "fetches, or run its %(setup)s once.") % fix)
        elif age > RTZ_STALE_DAYS:
            fix["days"] = int(age)
            # translators: %(file)s, a path, and %(setup)s, a file, stay as they are
            out["problems"].append(ngettext(
                "Real Time Zone's hours of the sky are %(days)d day old and nothing "
                "refreshes them. Delete %(file)s and it reads the hours play.bat fetches, or "
                "run its %(setup)s once.",
                "Real Time Zone's hours of the sky are %(days)d days old and nothing "
                "refreshes them. Delete %(file)s and it reads the hours play.bat fetches, or "
                "run its %(setup)s once.", fix["days"]) % fix)
        return out
    out["state"] = "seasons"
    out["place"] = place_name(here)
    if not has_ours:
        out["notes"].append(_(
            "season_weather.ltx has no hours yet - play.bat fetches them - so Real Time Zone "
            "models the hours from the day's forecast."))
    return out


def rtz_words(plan):
    """The report's Real Time Zone line."""
    if plan["state"] == "own" and plan["refreshed"]:
        # translators: Real Time Zone's weather; %s is a place
        return _("its own hours of the sky, for %s, refreshed at each launch") % plan["place"]
    if plan["state"] == "own":
        # translators: Real Time Zone's weather; %s is a place
        return _("its own hours of the sky, for %s") % plan["place"]
    if plan["state"] == "model":
        # translators: Real Time Zone's weather; %s is a place
        return _("the sky modeled from the day's forecast, for %s") % plan["place"]
    # translators: Real Time Zone's weather; %s is a place
    return _("the hours of the sky play.bat fetches, for %s") % plan["place"]


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


def _real(p):
    """A path as Windows resolves it, in one case: a junction or a link followed, so two
    spellings of one folder compare equal."""
    return os.path.normcase(os.path.realpath(p))


def running():
    """Anomaly or MO2 processes belonging to this install, by executable path. A process
    whose path cannot be read is counted as ours. PowerShell writes the paths in UTF-8: a
    pipe otherwise gets the console's code page, which Python reads as another, so a path
    with a letter past ASCII matched nothing or didn't decode at all. Both sides are
    resolved, so MO2 started from a junction to the GAMMA folder is this install too."""
    cmd = ["powershell", "-NoProfile", "-NonInteractive", "-Command",
           "[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
           "Get-Process -Name anomaly*,ModOrganizer -ErrorAction SilentlyContinue | "
           "ForEach-Object { if ($_.Path) { $_.Path } else { $_.ProcessName + '.exe|?' } }"]
    try:
        out = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                             timeout=60).stdout or ""
    except Exception as e:
        print("  ! " + _("Could not list the running programs (%s), so MO2 and the game are "
                         "taken to be closed.") % e.__class__.__name__)
        return []
    roots = [os.path.join(_real(p), "") for p in (ROOT, game_dir())]
    mine = set()
    for line in out.splitlines():
        line = line.strip().lstrip("﻿")
        if not line:
            continue
        if line.endswith("|?"):
            # translators: a program's file name, like anomalydx11avx.exe
            mine.add(_("%s (path unreadable, assumed this install)") % line[:-2].lower())
            continue
        p = _real(line)
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


def _folded(h):
    """hashes() keyed by path in lower case, to compare an archive's files with a folder's:
    Windows finds a file by its name in any case, and robocopy keeps the case a file already
    has, so two option folders that spell a path differently stopped every launch."""
    return {k.lower(): v for k, v in h.items()}


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
                                      "configure.bat can install it: click Install py7zr on "
                                      "its Seasonal mods step. Or type this in Command Prompt, "
                                      "not in Python:")
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
                                      "package, and WinRAR or 7-Zip installed. configure.bat "
                                      "can install rarfile: click Install rarfile on its "
                                      "Seasonal mods step. Or type this in Command Prompt, not "
                                      "in Python:")
                             + "\n    %s -m pip install rarfile\n  " % _python()
                             + _("No texture has been changed."))
        if not point_rarfile(rarfile):
            raise SystemExit("  " + _("Texture sets in a .rar archive need WinRAR or 7-Zip "
                                      "installed.") + "\n  " + _("No texture has been changed."))
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
    live = _folded(hashes(os.path.join(MODS, mod, "gamedata")))
    if not live:
        return None, (_("its gamedata/ is empty") if os.path.isdir(os.path.join(MODS, mod))
                      else _("not in mods/"))
    matches, detail = [], []
    for season in cfg["options"]:
        cand = _folded(_option_hashes(cfg["archive"], cfg["options"][season], tmp, mod))
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


def _same_file(a, b):
    """Whether two files hold the same bytes; a file that cannot be read is not the same."""
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        with open(a, "rb") as fa, open(b, "rb") as fb:
            while True:
                x, y = fa.read(1 << 20), fb.read(1 << 20)
                if x != y:
                    return False
                if not x:
                    return True
    except OSError:
        return False


def shadow_check(force=False):
    """Lines about the files of each seasonal mod that a mod above it wins, judged on the
    order apply leaves MO2's mod list in, not the order it is in now. A file the mod above
    ships byte for byte is not counted: nothing is lost to it.

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
    folders = _mod_folders()
    # the mods apply leaves as they are, since they put things into saves
    held = sorted(n for n, c in TOGGLE_MODS.items() if n in folders and held_for_saves(n, c))
    key = hashlib.md5(("|".join(body) + "|" + repr(sorted(
        (n, _when(c), c.get("above")) for n, c in TOGGLE_MODS.items())) + "|" + repr(held))
                      .encode("utf-8", "replace")).hexdigest()
    if not force and os.path.isfile(SHADOW_CACHE):
        try:
            if json.loads(io.open(SHADOW_CACHE, encoding="utf-8").read()).get("key") == key:
                return []
        except (OSError, ValueError):
            pass

    # the moves apply makes, pass after pass as it makes them: a mod it is about to put
    # above another is not losing to it
    moves = []
    for name, cfg in TOGGLE_MODS.items():
        if name in folders and name not in held:
            i = _find(body, name)
            moves.append((name, cfg["above"], body[i][:1] if i is not None else "-"))
    _place_all(body, moves)

    ours = set(TOGGLE_MODS) | {SOUND_MOD, LUT_MOD, SOTZ}
    index = {l[1:]: i for i, l in enumerate(body)}
    bases = set(SEASONS) | set(PERIODS)
    base_of, days_of = {}, {}

    def base_period(d):
        if d not in base_of:
            base_of[d] = season_for(d)
        return base_of[d]

    def days(name):
        if name not in days_of:
            days_of[name] = days_on(name, base_period)
        return days_of[name]

    shadowed, dormant, notes = [], {}, []
    for name, cfg in TOGGLE_MODS.items():
        base = os.path.join(MODS, name, "gamedata")
        if name not in index or not os.path.isdir(base) or name in held:
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
            # a file the other mod ships byte for byte is not lost to it
            hits = [rel for rel in rels if os.path.isfile(os.path.join(og, rel))
                    and not _same_file(os.path.join(base, rel), os.path.join(og, rel))]
            if not hits:
                continue
            eg = hits[0].replace(os.sep, "/")
            if other in TOGGLE_MODS:
                # by the dates, so a season of one's own meets the season it falls in
                shared = meet(_when(cfg), _when(TOGGLE_MODS[other]), days, bases)
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


# --- particles a script makes as a save loads ---------------------------------------------
#
# The game loads every script in gamedata\scripts as a game starts, so a script that calls
# particles_object() outside its functions does so as a save loads, and a particle the game
# doesn't have is a fatal error no Lua can catch ("Particle effect or group doesn't
# exist"). INVERNO 1.09's snowfall makes its particles that way, from the ones its base
# module carries: with the script in a mod that stays on and the particles only in a
# seasonal one, every launch outside the winters crashed as the save loaded. So each launch
# looks for particles such a script needs that only mods off for it have.
#
# The game's particles are the .pe and .pg files under gamedata\particles, named by their
# paths (graupel\dust is particles\graupel\dust.pg), and the effects and groups of the
# particles.xr that wins (CPSLibrary::Load in the Modded Exes). One inside a .db can't be
# read from outside, so with no loose particles.xr the game's own may have a name, and
# play.bat only warns.

_PARTICLE_EXT = (".pe", ".pg")


def particle_files(folder):
    """The particles the loose gamedata\\particles in `folder` holds, by the names the game
    gives them, in lower case: graupel\\dust for particles/graupel/dust.pg."""
    base = os.path.join(folder, "gamedata", "particles")
    out = set()
    for root, __, files in os.walk(base):
        for f in files:
            stem, ext = os.path.splitext(f)
            if ext.lower() in _PARTICLE_EXT:
                rel = os.path.relpath(os.path.join(root, stem), base)
                out.add(rel.replace(os.sep, "\\").lower())
    return out


def _chunks(data):
    """X-Ray chunks laid end to end, [u32 id][u32 size][data], as [(id, data)]. ValueError
    when they don't fill `data` exactly."""
    out, p = [], 0
    while p < len(data):
        if p + 8 > len(data):
            raise ValueError("a chunk is cut short")
        cid, size = struct.unpack_from("<II", data, p)
        if p + 8 + size > len(data):
            raise ValueError("a chunk runs past the end")
        out.append((cid, data[p + 8:p + 8 + size]))
        p += 8 + size
    return out


def xr_particles(path):
    """The effects and groups a particles.xr defines, by name, in lower case. Its chunk 1
    holds its version, 3 its effects and 4 its groups, each in a chunk of its own whose
    chunk 2 is its name. ValueError for a file that doesn't read as one, or of a version
    the game skips."""
    with open(path, "rb") as f:
        top = _chunks(f.read())
    ver = [d for cid, d in top if cid == 1]
    if len(ver) != 1 or len(ver[0]) != 2 or struct.unpack("<H", ver[0])[0] != 1:
        raise ValueError("not a particles.xr the game reads")
    names = set()
    for cid, d in top:
        if cid & 0x7FFFFFFF in (3, 4):
            if cid & 0x80000000:
                raise ValueError("packed")
            for __, one in _chunks(d):
                names.update(v.split(b"\0")[0].decode("cp1251", "replace").lower()
                             for k, v in _chunks(one) if k == 2)
    return names


_LUA_WORDS = re.compile(r"\b(?:function|if|while|for|do|repeat|until|end|particles_object)\b")
_LUA_NOT_CALL = re.compile(r"(?:[.:]|\bfunction)\s*$")
_LUA_PAREN = re.compile(r"\s*\(")
_LUA_ARG = re.compile(r"\s*(?:\"((?:[^\"\\\n]|\\.)*)\"|'((?:[^'\\\n]|\\.)*)'"
                      r"|\[(=*)\[\n?(.*?)\]\3\])\s*\)", re.S)
_LUA_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v"}


def _lua_unescape(s):
    return re.sub(r"\\(\d{1,3}|.)", lambda m: chr(int(m.group(1)) % 256) if m.group(1).isdigit()
                  else _LUA_ESCAPES.get(m.group(1), m.group(1)), s)


def loaded_particles(text):
    """[(line, name)] for each particles_object() a Lua script calls with a plain string
    outside its functions, which it does as it loads; the names in lower case. None when its
    blocks don't add up, so where a call stands can't be told."""
    code = lua_code(text)
    blocks, out = [], []
    for m in _LUA_WORDS.finditer(code):
        w = m.group()
        if w in ("function", "if", "repeat"):
            blocks.append(w)
        elif w in ("while", "for"):
            blocks.append("loop")                   # its `do` opens the body
        elif w == "do":
            if blocks and blocks[-1] == "loop":
                blocks[-1] = "loop do"
            else:
                blocks.append("do")
        elif w == "until":
            if not blocks or blocks.pop() != "repeat":
                return None
        elif w == "end":
            if not blocks or blocks.pop() in ("loop", "repeat"):
                return None
        elif "function" not in blocks and not _LUA_NOT_CALL.search(
                code, max(0, m.start() - 40), m.start()):
            paren = _LUA_PAREN.match(code, m.end())
            arg = paren and _LUA_ARG.match(text, paren.end())
            if arg:
                name = (arg.group(4) if arg.group(3) is not None else
                        _lua_unescape(arg.group(1) if arg.group(1) is not None
                                      else arg.group(2)))
                out.append((code.count("\n", 0, m.start()) + 1, name.lower()))
    return None if blocks else out


def launch_order(active, prefs=None, switch=True):
    """MO2's mod list as [(name, on)], the top first. With `switch`, each seasonal mod is on
    or off as apply switches it for `active`, where it stands now."""
    flip = {name: bool(should and not held)
            for name, inst, __, should, held in toggle_status(active, prefs)
            if inst and held != "saves"} if switch else {}
    return [(l[1:], flip.get(l[1:], l[:1] == "+")) for l in (_modlist_lines() or [])[1:]
            if l[:1] in ("+", "-")]


def _db_archives(folder):
    """The .db archives under `folder`\\db, which MO2 maps into the game's db folder."""
    for root, __, files in os.walk(os.path.join(folder, "db")):
        for f in files:
            if re.search(r"\.x?db\w*$", f.lower()) and f.lower() != "thumbs.db":
                yield os.path.join(root, f)


def _db_paths(path):
    """The files the .db `path` holds, by their paths under gamedata, in lower case with
    backslashes. OSError or ValueError when it can't be read."""
    out = set()
    for n in db_files(path):
        n = n.lower()
        out.add((n[len("gamedata/"):] if n.startswith("gamedata/") else n).replace("/", "\\"))
    return out


def loaded_particle_calls(layers):
    """[(script, mod, [(line, name)])] for the scripts the game loads from `layers`,
    [(mod, folder)] with the winner first, that make particles as a save loads: each the
    copy the game loads, from `mod`."""
    found, seen = [], set()
    for mod, folder in layers:
        d = os.path.join(folder, "gamedata", "scripts")
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for f in names:
            low = f.lower()
            if not low.endswith(".script") or low in seen:
                continue
            seen.add(low)
            try:
                raw = open(os.path.join(d, f), "rb").read()
            except OSError:
                continue
            hits = (loaded_particles(raw.decode("cp1251", "replace"))
                    if b"particles_object" in raw else None)
            if hits:
                found.append((f, mod, hits))
    return found


def particle_gaps(order):
    """Particles that scripts make as a save loads and only mods that are off have, in the
    mod list `order`, [(name, on)] with the top first: ([(script, mod, [(line, name)],
    holders)], sure). Each script is the copy the game loads, from `mod`, and `holders` are
    the mods off that have its particles. `sure` is False when the particles.xr that wins
    can't be read, or a .db in a mod that is on can't: either may have them."""
    off = {}
    for name, on in order:
        if not on:
            for p in particle_files(os.path.join(MODS, name)):
                off.setdefault(p, []).append(name)
    if not off:
        return [], True
    # where the game takes files from, the winner first: MO2's overwrite, the mods on, and
    # the game's own folder
    layers = ([("overwrite", os.path.join(ROOT, "overwrite"))]
              + [(name, os.path.join(MODS, name)) for name, on in order if on])
    every = layers + [(None, game_dir())]
    want = set(off)
    for __, folder in every:
        want -= particle_files(folder)
        if not want:
            break
    sure = True
    if want:
        xr = next((p for p in (os.path.join(f, "gamedata", "particles.xr") for __, f in every)
                   if os.path.isfile(p)), None)
        try:
            if xr is None:
                raise ValueError("the game's own, in its .db")
            want -= xr_particles(xr)
        except (OSError, ValueError):
            sure = False
    if not want:
        return [], True

    found = [(f, mod, [(line, n) for line, n in hits if n in want])
             for f, mod, hits in loaded_particle_calls(layers)]
    found = [(f, mod, hits) for f, mod, hits in found if hits]
    if found:
        # a .db in a mod on may hold them, packed
        for __, folder in layers[1:]:
            for path in _db_archives(folder):
                try:
                    held = _db_paths(path)
                except (OSError, ValueError):
                    sure = False
                    continue
                for n in held:
                    stem, ext = os.path.splitext(n)
                    if n.startswith("particles\\") and ext in _PARTICLE_EXT:
                        want.discard(stem[len("particles\\"):])
    rank = {name: i for i, (name, __) in enumerate(order)}
    out = []
    for f, mod, hits in found:
        hits = [(line, n) for line, n in hits if n in want]
        if hits:
            holders = sorted({h for __, n in hits for h in off[n]}, key=rank.get)
            out.append((f, mod, hits, holders))
    return out, sure


def particle_lines(found, sure):
    """particle_gaps()'s findings as lines: "!" when the game will crash, "-" when the
    game's own particles.xr may have the names."""
    out = []
    for f, mod, hits, holders in found:
        names = list(dict.fromkeys(n for __, n in hits))
        if sure:
            said = ngettext(
                "%(script)s, in \"%(mod)s\", makes a particle effect as a save loads that only "
                "mods off for this launch have: %(names)s. The game crashes on it (\"Particle "
                "effect or group doesn't exist\").",
                "%(script)s, in \"%(mod)s\", makes %(n)d particle effects as a save loads that "
                "only mods off for this launch have: %(names)s. The game crashes on the first "
                "(\"Particle effect or group doesn't exist\").", len(names))
        else:
            said = ngettext(
                "%(script)s, in \"%(mod)s\", makes a particle effect as a save loads that only "
                "mods off for this launch have: %(names)s. Unless the game's own particles.xr "
                "has it, the game crashes on it.",
                "%(script)s, in \"%(mod)s\", makes %(n)d particle effects as a save loads that "
                "only mods off for this launch have: %(names)s. Unless the game's own "
                "particles.xr has them, the game crashes on the first.", len(names))
        out.append(("  ! " if sure else "  - ") + said % {
            "script": f, "mod": mod, "n": len(names), "names": _names_text(names)})
        out.append("    " + _("Copy gamedata\\particles from %(holders)s into \"%(mod)s\", the "
                              "mod with the script, so the game has them whenever it loads "
                              "the script.")
                   % {"holders": _and(["\"%s\"" % h for h in holders]), "mod": mod})
    return out


# --- the textures those particles draw with -------------------------------------------------
#
# An effect draws with the texture its [sprite] names when its flags have the sprite bit,
# and a group draws its effects (CPEDef::Load2 and CPGDef::Load2 in the Modded Exes). A
# texture the game can't find crashes nothing: the log says "Can't find texture" and the
# effect draws a stand-in, in squares. INVERNO's snowfall fell as squares that way, for a
# player whose mod with its particles had no db\addons\inverno_textures.db. So each launch
# also reads the loose files that define the particles scripts make as a save loads, and
# looks for their textures where the game does: loose under gamedata\textures, or in a
# .db. The effects of a particles.xr aren't read; a pack's textures come with it.

_SPRITE = 1                                         # dfSprite: the effect draws a sprite
_TEXTURE_EXT = (".dds", ".seq", ".ogm", ".avi")     # what CTexture::Load looks for


def _ini_sections(path):
    """A loose .pe or .pg, read as the game reads an .ltx: {section: {key: value}}, the
    names and keys in lower case. {} for a file that can't be read."""
    try:
        with open(path, "rb") as f:
            text = f.read().decode("cp1251", "replace")
    except OSError:
        return {}
    out, keys = {}, None
    for line in text.splitlines():
        s = _ltx_line(line)
        m = _LTX_HEAD.match(s)
        if m:
            keys = out.setdefault(m.group(2).strip().lower(), {})
        elif keys is not None and "=" in s:
            k, v = s.split("=", 1)
            keys[k.strip().lower()] = v.strip()
    return out


def _ini_number(s):
    try:
        return int(s)
    except (TypeError, ValueError):
        return 0


def _particle_file(name, folders, exts=_PARTICLE_EXT):
    """The loose file that defines particle `name`, from the first of `folders` that has
    one: an effect (.pe) before a group (.pg), as the game looks a name up. None when no
    folder has one."""
    for ext in exts:
        for folder in folders:
            p = os.path.join(folder, "gamedata", "particles", *(name + ext).split("\\"))
            if os.path.isfile(p):
                return p
    return None


def particle_textures(name, folders):
    """The textures particle `name` draws with, in lower case, by the loose .pe and .pg
    files in `folders`, the winner first: an effect's own, and a group's effects'. None
    when no loose file defines it."""
    p = _particle_file(name, folders)
    if p is None:
        return None
    effects = [p]
    if p.lower().endswith(".pg"):
        ini, effects = _ini_sections(p), []
        for i in range(_ini_number(ini.get("_group", {}).get("effects_count"))):
            one = ini.get("effect_%04d" % i, {})
            for key in ("effect_name", "on_play_child", "on_birth_child", "on_death_child"):
                pe = one.get(key) and _particle_file(one[key].lower(), folders, (".pe",))
                if pe:
                    effects.append(pe)
    out = []
    for pe in effects:
        ini = _ini_sections(pe)
        sprite = ini.get("sprite", {})
        if not (_ini_number(ini.get("_effect", {}).get("flags")) & _SPRITE
                and sprite.get("shader")):
            continue
        for t in sprite.get("texture", "").split(","):
            t = t.strip().lower().replace("/", "\\")
            stem, ext = os.path.splitext(t)
            t = stem if ext in (".dds", ".tga", ".bmp", ".ogm") else t     # fix_texture_name
            if t and t not in out:
                out.append(t)
    return out


def _loose_textures(folders, textures):
    """{texture: its file} for those of `textures` that one of `folders` has loose under
    gamedata\\textures, the file from the first that has it, under its folder."""
    dirs = {}
    for t in textures:
        d, __, f = t.rpartition("\\")
        dirs.setdefault(d, set()).add(f)
    out = {}
    for d, files in dirs.items():
        rel = os.path.join("gamedata", "textures", *(d.split("\\") if d else []))
        for folder in folders:
            try:
                there = {x.lower(): x for x in os.listdir(os.path.join(folder, rel))}
            except OSError:
                continue
            for f in files:
                t = d + "\\" + f if d else f
                hit = next((there[f + ext] for ext in _TEXTURE_EXT if f + ext in there), None)
                if hit and t not in out:
                    out[t] = os.path.join(rel, hit)
    return out


def _db_textures(path):
    """The textures the .db `path` holds, by the names the game asks for them by."""
    out = set()
    for n in _db_paths(path):
        stem, ext = os.path.splitext(n)
        if n.startswith("textures\\") and ext in _TEXTURE_EXT:
            out.add(stem[len("textures\\"):])
    return out


def texture_gaps(order):
    """Textures that the particles scripts make as a save loads draw with and the game won't
    find, in the mod list `order`, [(name, on)] with the top first: [(script, mod, textures,
    holders, nowhere)]. Each script is the copy the game loads, from `mod`; `holders` are
    the mods off that have its textures, [(mod, [file])], each file loose or a .db, under
    the mod's folder, and `nowhere` the textures no mod has. [] when the game has them all,
    or when a .db it would look in can't be read, since that one may have them."""
    layers = ([("overwrite", os.path.join(ROOT, "overwrite"))]
              + [(name, os.path.join(MODS, name)) for name, on in order if on])
    folders = [f for __, f in layers] + [game_dir()]
    uses, drawn = [], {}
    for f, mod, hits in loaded_particle_calls(layers):
        tex = []
        for __, n in hits:
            if n not in drawn:
                drawn[n] = particle_textures(n, folders) or []
            tex += [t for t in drawn[n] if t not in tex]
        if tex:
            uses.append((f, mod, tex))
    missing = {t for __, __, tex in uses for t in tex}
    missing -= set(_loose_textures(folders, missing))
    # then in the .db files the game mounts: those of the mods on, and its own, each
    # folder's under db\textures first, where the game keeps its own
    for folder in folders[1:]:
        paths = sorted(_db_archives(folder) if missing else (),
                       key=lambda p: "textures" not in os.path.relpath(
                           p, os.path.join(folder, "db")).lower().split(os.sep)[:-1])
        for path in paths:
            try:
                missing -= _db_textures(path)
            except (OSError, ValueError):
                return []
            if not missing:
                break
    if not missing:
        return []
    have = []
    for name, on in order:
        if on:
            continue
        folder = os.path.join(MODS, name)
        loose = _loose_textures([folder], missing)
        got, files = set(loose), sorted(loose.values())
        for path in _db_archives(folder):
            try:
                held = missing & _db_textures(path)
            except (OSError, ValueError):
                continue
            if held:
                got |= held
                files.append(os.path.relpath(path, folder))
        if got:
            have.append((name, got, files))
    out = []
    for f, mod, tex in uses:
        tex = [t for t in tex if t in missing]
        if tex:
            holders = [(h, files) for h, got, files in have if got.intersection(tex)]
            held = set().union(*[got for __, got, __ in have])
            out.append((f, mod, tex, holders, [t for t in tex if t not in held]))
    return out


def texture_lines(found):
    """texture_gaps()'s findings as lines, warnings all: a texture the game can't find
    draws as squares and crashes nothing."""
    out = []
    for f, mod, tex, holders, nowhere in found:
        out.append("  - " + ngettext(
            "%(script)s, in \"%(mod)s\", makes particles as a save loads that draw with a "
            "texture the game won't find in this launch: %(textures)s. Where they play, the "
            "game draws squares.",
            "%(script)s, in \"%(mod)s\", makes particles as a save loads that draw with "
            "%(n)d textures the game won't find in this launch: %(textures)s. Where they "
            "play, the game draws squares.", len(tex))
            % {"script": f, "mod": mod, "n": len(tex), "textures": _names_text(tex)})
        for holder, files in holders:
            out.append("    " + _("Copy %(files)s from \"%(holder)s\", off for this launch, "
                                  "to the same place in \"%(mod)s\", the mod with the "
                                  "script.")
                       % {"files": _and(files), "holder": holder, "mod": mod})
        if nowhere:
            out.append("    " + ngettext(
                "No mod in MO2's list has %(textures)s. It comes with the mod the particles "
                "are from: copy it into \"%(mod)s\", the mod with the script.",
                "No mod in MO2's list has %(textures)s. They come with the mod the particles "
                "are from: copy them into \"%(mod)s\", the mod with the script.", len(nowhere))
                % {"textures": _names_text(nowhere), "mod": mod, "n": len(nowhere)})
    return out


def _check_install():
    """Stop with a plain message when not run from a Mod Organizer install."""
    ini = os.path.join(ROOT, "ModOrganizer.ini")
    modlist = _modlist_path()
    if os.path.isfile(ini) and os.path.isfile(modlist):
        return

    print("  " + _("This does not look like a Mod Organizer install."))
    print()
    looked, expected, here = _("looked in"), _("expected"), _("profiles here")
    width = max(10, len(looked) + 1, len(expected) + 1, len(here) + 1)
    found, missing = pgettext("a file", "found"), pgettext("a file", "MISSING")
    print("    %-*s: %s" % (width, looked, ROOT))
    print("    %-*s: ModOrganizer.ini        %s"
          % (width, expected, found if os.path.isfile(ini) else missing))
    print("    %s  profiles\\%s\\modlist.txt %s"
          % (" " * width, profile_name(), found if os.path.isfile(modlist) else missing))
    if os.path.isfile(ini):
        # the right folder, and MO2's profile isn't in it: name the ones that are
        try:
            have = sorted(p for p in os.listdir(os.path.join(ROOT, "profiles"))
                          if os.path.isfile(os.path.join(ROOT, "profiles", p, "modlist.txt")))
        except OSError:
            have = []
        if have:
            print("    %-*s: %s" % (width, here, ", ".join(have)))
        print()
        _print_lines("  ", _("MO2 says the profile in use is %s, which has no modlist.txt "
                             "here. Start\nMO2, pick the profile you play in, close MO2 and "
                             "try again. Nothing has been\nchanged.") % profile_name())
        raise SystemExit(2)
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
            "stopped": _("season.py stopped with an error - the lines above say why, and "
                         "what it did\nbefore it stopped. Light and weather still follow the "
                         "season. Press a key to\nstart the game anyway, or close this window "
                         "to fix it first."),
            "starting": _("Starting Anomaly...")}.get(key)


def _row(label, value):
    """A line of the report: its label in a column of its own, then the value."""
    print("  %-15s %s" % (label, value))


def main():
    ap = lang.parser(
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

    global CLOCK
    prefs = read_prefs()
    # the real date, or, with MCM's calendar on the game's clock, the Zone's date the game
    # last wrote; everything below goes by it
    today, CLOCK = clock_today(prefs)

    # MCM offers "automatic, or pin one" and the in-engine layers honor it, so the
    # staged layers follow it too - otherwise pinning a season gives you its light
    # over another season's ground. An explicit --season still wins over the pin. A pin
    # left on a season the calendar has turned off counts as automatic, as in game.
    on = seasons_on(a.mapping)
    pinned = prefs["mode"] if prefs["mode"] in on else None
    pin_off = prefs["mode"] in SEASONS and prefs["mode"] not in on
    writing = (a.cmd == "apply") and not a.dry_run
    # MCM's dice roll at a launch, so only an apply that writes draws; status and a dry run
    # say the chance instead. A season fixed by --season or a pin is never rolled over, and
    # a hit fixes the season the way a pin does, spell or not.
    rolled, draw, chance = None, None, None
    if writing and not (a.season or pinned):
        otherwise = spell_season(today)[0] or season_for(today, a.mapping)
        rolled, draw, chance = roll_season(prefs, on, otherwise)
    # a spell brings its season unless the season is fixed: by --season, an MCM pin or the
    # dice
    brings, spell = (spell_season(today) if not (a.season or pinned or rolled)
                     else (None, None))
    want = a.season or pinned or rolled or brings or season_for(today, a.mapping)
    # A pin or --season fixes the BASE period; events still resolve by the date, so
    # pinning summer in December does not cancel a Christmas event.
    active = active_for(today, a.mapping, base=want)
    tmp = os.path.join(ROOT, "_staging", "season-%d" % os.getpid())    # per process
    if a.no_textures:
        prefs["stage_textures"] = False
    stage_tex = prefs["stage_textures"]
    title = cap_first(season_label(want))

    _row(pgettext("report", "date"), today.isoformat() + (
        "   " + _("(the Zone's date, by the game's clock)") if CLOCK == "game" else
        "   " + _("(the game's clock has no date saved yet, so the real date)")
        if CLOCK == "none" else ""))
    _row(pgettext("report", "calendar"), calendar_text(a.mapping))
    why = ("   " + _("(forced with --season)") if a.season else
           "   " + _("(pinned in MCM)") if pinned else
           "   " + _("(rolled by MCM's dice: %(draw)d, at or under %(chance)d)")
           % {"draw": draw, "chance": chance} if rolled else
           "   " + _("(a spell: %(name)s, %(first)s to %(last)s)")
           % {"name": spell[0], "first": _md(spell[1].month, spell[1].day),
              "last": _md(spell[2].month, spell[2].day)} if spell else "")
    _row(pgettext("report", "season"), season_label(want) + why)
    if (pinned and not a.season) or spell or rolled:
        _row(pgettext("report", "calendar says"), season_label(season_for(today, a.mapping)))
    if prefs["dice"] and not rolled:
        _row(pgettext("report", "dice"), dice_words(prefs, fixed=bool(a.season or pinned),
                                                    draw=draw))
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
        said = dial_text(dial)
        if dial == "stale" and a.mapping == "met" and not CALENDAR:
            # play.bat stages by Polesia's dates: this dial is drawn by the run that asks
            said = _("to be drawn for these dates by %s") % command("season.py",
                                                                    "apply --mapping met")
        _row(pgettext("report", "dial"), said)
    if note:
        print("  - " + note)
    flags = weather_flags()
    _row(pgettext("report", "weather from"), place_words(weather_place()) + (
        "   " + _("(today: %s)") % ", ".join(flags) if flags else ""))
    # Real Time Zone's sky, a line only with it installed; its name stays as it is
    rtz = rtz_plan()
    if rtz["state"] != "none":
        _row("Real Time Zone", rtz_words(rtz))
        for p in rtz["problems"]:
            print("  ! " + p)
        for n in rtz["notes"]:
            print("  - " + n)
    _row(pgettext("report", "texture layer"), pgettext("the texture layer", "on") if stage_tex
         else _("OFF for this run (--no-textures) - seasonal mods disabled, texture sets kept; "
                "the seasonal atmosphere still runs") if a.no_textures
         else _("OFF in MCM - seasonal mods disabled, texture sets kept; the seasonal "
                "atmosphere still runs"))
    # the grass for the season staged; a period with no MCM page of its own gets all of it
    grass = grass_plan(prefs, want)
    grass_pending = bool(grass and grass["kept"] and not _same(grass["now"], grass["want"]))
    _row(pgettext("report", "grass"), grass_words(grass))
    # the seasons' LUTs, built from SEASON_LUTS and SEASON_ACCENTS; a report line only once
    # they are asked for
    lut = lut_plan_now()
    lut_pending = lut["state"] == "stale"
    if lut["state"] != "none" or os.path.isdir(os.path.join(MODS, LUT_MOD)):
        _row(pgettext("report", "LUTs"), lut_words(lut))
        for p in lut["problems"]:
            print("  ! " + p)
        for n in lut["notes"]:
            print("  - " + n)
    # other mods' MCM options that follow the season, and what MCM's file has now
    mcm_now = mcm_values(active)
    mcm_want = {k: v for k, (v, _why) in mcm_now.items()}
    mcm_pending = mcm_changes(mcm_want) if mcm_want else []
    saved = mcm_saved() if mcm_pending else {}
    for i, (key, (value, why)) in enumerate(mcm_now.items()):
        said = "%s = %s   (%s)" % (key, mcm_text(value), mcm_why(why))
        if key in [k for k, _was, _new in mcm_pending]:
            said += "   " + (_("(now %s)") % saved[key] if key in saved
                             else _("(not in MCM's file yet)"))
        _row(pgettext("report", "MCM settings") if i == 0 else "", said)
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

        # before the toggles: they switch a seasonal mod only when its folder is there
        for line in rain_refresh(writing):
            print(line)
        folders = _mod_folders()
        for name, inst, state, should, held in toggle_status(active, prefs):
            if not inst:
                near = near_folder(name, folders)
                print("  %-30s %s   %s" % (
                    name[:30], _("not installed"),
                    _("(MO2 has \"%s\"; use that name exactly)") % near if near
                    else _("(no folder with that name in mods)")))
            else:
                due = (_("(left as it is: it puts things into saves)") if held == "saves" else
                       _("(today: off)") if not should else _("(today: on)") if not held else
                       _("(today: off - texture swapping is off for this run "
                         "(--no-textures))") if held == "off" and a.no_textures else
                       _("(today: off - texture swapping is off in MCM)") if held == "off"
                       else _("(today: off - unchecked for this season in MCM)"))
                print("  %-30s %-10s %s" % (name[:30], state_word(state), due))
        # A mod on only in seasons that are off never comes on: worth saying, since
        # nothing else would
        for name, cfg in TOGGLE_MODS.items():
            w = set(_when(cfg))
            if w and w <= (set(SEASONS) - set(on)) and not held_for_saves(name, cfg):
                print("  - " + _("%(mod)s is on only in %(seasons)s, which your calendar has "
                                 "off, so it never switches on.")
                      % {"mod": name[:40], "seasons": seasons_text(sorted(w,
                                                                          key=SEASONS.index))})
        # what a seasonal mod puts into saves: why it is left as it is, or, in status, that
        # its entry lets it be switched all the same
        for name, cfg in TOGGLE_MODS.items():
            found = mod_save_content(name) if name in folders else []
            if found and not saves_allowed(cfg):
                print("  ! " + _("%s is left as it is in MO2: its files put things into "
                                 "saves, and a save made while it is on can lose them, or not "
                                 "load, once it is off.") % name[:40])
                for line in save_content_lines(found):
                    print("      " + line)
                print("    " + _("To switch it anyway, give its entry \"%s\": True in "
                                 "seasons_config.py.") % SAVE_CONTENT)
            elif found and a.cmd == "status":
                print("  - " + ngettext(
                    "%(mod)s puts things into saves (%(n)d file); its entry says \"%(key)s\": "
                    "True, so play.bat switches it all the same.",
                    "%(mod)s puts things into saves (%(n)d files); its entry says \"%(key)s\": "
                    "True, so play.bat switches it all the same.", len(found))
                    % {"mod": name[:40], "n": len(found), "key": SAVE_CONTENT})
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
            if listed and _mod_enabled(SOUND_SRC) and prefs["stage_sound"]:
                for line in sound_shadow_lines():
                    _print_lines("  ! ", line)
        shipped, present, copied = install_presets(writing)
        if shipped:
            _row(pgettext("report", "grade presets"),
                 _("%(shipped)d shipped, %(there)d in appdata")
                 % {"shipped": len(shipped), "there": len(present) + len(copied)}
                 + ("   " + _("(copied: %s)") % ", ".join(copied) if copied else ""))
        print()

        def send_spell():
            """Hand the game today's spell, or what the dice rolled, now that its season is
            staged."""
            state, why = write_calendar(a.mapping, redraw=False, staged=True, today=today,
                                        roll=(rolled, draw, chance) if rolled else None)
            if state is None and dial is not None:
                print("  - " + why)

        def send_mcm():
            """Set the MCM options that follow the season in MCM's file, each said; the
            changes. Not while the game runs: it would save its own over them."""
            if not (writing and mcm_pending):
                return []
            game = [p for p in running() if p.startswith("anomaly")]
            if game:
                print("  - " + _("The MCM settings wait for the next launch: %s is running, "
                                 "and would save its own over them.") % _and(game))
                return []
            changes = write_mcm(mcm_want)
            for key, was, now in changes:
                print("  %-58s %s" % (key[:58], _("%(was)s -> %(now)s") % {
                    "was": was if was is not None else _("not set"), "now": now}))
            return changes

        def set_grass():
            """Set the grass in user.ltx for the season staged, said; the change, or None."""
            if not writing:
                return None
            change = send_grass(grass)
            if change:
                print("  %-58s %s" % ("%s (user.ltx)" % GRASS_CMD, _("%(was)s -> %(now)s")
                                      % {"was": change[0], "now": change[1]}))
            return change

        def set_luts():
            """Build Seasonal LUT when SEASON_LUTS or a LUT it reads changed, said; whether
            it was built. Before the toggles, so they place a mod built for the first time."""
            if not (writing and lut["state"] == "stale"):
                return False
            busy = running()
            if busy:
                raise SystemExit(close_first(busy))
            try:
                n = build_luts(lut)
            except (LutError, OSError, ImportError) as e:
                print("  ! " + _("Seasonal LUT not built: %s.") % e)
                lut["state"] = "blocked"
                return False
            lut["state"] = "built"
            print("  %-58s %s" % (LUT_MOD, ngettext("built: %(n)d season on %(base)s's LUT",
                                                    "built: %(n)d seasons on %(base)s's LUT",
                                                    n) % {"n": n, "base": lut["base"][0]}))
            return True

        def reset_lut():
            """After the toggles: a user.ltx ssfx_lut group the game's own atlas lacks."""
            change = lut_reset() if writing else None
            if change:
                print("  %-58s %s" % ("%s (user.ltx)" % LUT_CMD, _("%(was)s -> %(now)s")
                                      % {"was": change[0], "now": change[1]}))
            return change

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

        def particle_check():
            """Say what in this launch's mods makes particles as a save loads that the game
            won't have, or that draw with textures it won't find; in a launch, stop before
            the crash. Last, so all else is staged."""
            order = launch_order(active, prefs, switch=not writing)
            found, sure = particle_gaps(order)
            lines = particle_lines(found, sure) + texture_lines(texture_gaps(order))
            if not lines:
                return
            print()
            for line in lines:
                print(line)
            if found and writing and sure:
                raise SystemExit("  ** " + _("Stopped before the launch: the game would crash as "
                                             "the save loads. Fix it as the lines above say, "
                                             "then run play.bat again.") + " **")

        # With the texture layer off, whatever is staged stays.
        tex_ok = True if not stage_tex else all(v == want for v in installed.values())
        _ssrc = _sound_src_dir()
        src_live = bool(_ssrc) and os.path.isdir(_ssrc)
        if not src_live:
            # no source, or the source mod is disabled: stale overrides come out. With none
            # set (configure.py sound --off) too: the last season's set stayed on all year
            sound_ok = sound_now is None
        elif prefs["stage_sound"]:
            sound_ok = (sound_now == want
                        and soundscape_signature() == _sound_signature(want))
        else:
            sound_ok = sound_now is None
        if tex_ok and sound_ok:
            # Toggles are checked even when nothing else moved: a newly installed
            # seasonal mod is absent from the mod list until something inserts it.
            luted = set_luts()
            tg = apply_toggles(active, not writing, prefs)
            for name, was, now in tg:
                print("  %-58s %s" % (name[:58], change_text(was, now)))
            reset_lut()
            mcm = send_mcm()
            grassed = set_grass()
            if tg and writing:
                print("  => " + _("%s: seasonal mods switched. The game picks this up when it "
                                  "starts.") % title)
            elif tg:
                print("  => " + _("%(season)s: seasonal mods need switching. Start the game "
                                  "with play.bat, or run %(command)s")
                      % {"season": title, "command": command("season.py", "apply")})
            elif mcm:
                print("  => " + _("%s: MCM settings set. The game picks this up when it "
                                  "starts.") % title)
            elif mcm_pending and not writing:
                print("  => " + _("%(season)s: MCM settings need setting. Start the game with "
                                  "play.bat, or run %(command)s")
                      % {"season": title, "command": command("season.py", "apply")})
            elif grassed:
                print("  => " + _("%s: grass set. The game picks this up when it starts.")
                      % title)
            elif grass_pending and not writing:
                print("  => " + _("%(season)s: the grass needs setting. Start the game with "
                                  "play.bat, or run %(command)s")
                      % {"season": title, "command": command("season.py", "apply")})
            elif luted:
                print("  => " + _("%s: Seasonal LUT built. The game picks this up when it "
                                  "starts.") % title)
            elif lut_pending and not writing:
                print("  => " + _("%(season)s: Seasonal LUT needs building. Start the game "
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
            particle_check()
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
                _("off (no ambient sound mod is set)") if not SOUND_SRC else
                _("off (\"%s\" is not enabled in MO2)") % SOUND_SRC
                if not _mod_enabled(SOUND_SRC) else
                _("off (\"%s\" has no ambient sound files)") % SOUND_SRC))

        if a.cmd == "status" or a.dry_run:
            say_skipped()
            particle_check()
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
            # only the exit code is read; robocopy writes the console's code page, which a
            # path past ASCII could make undecodable as Windows' own
            r = subprocess.run(["robocopy", merged, target, "/MIR", "/R:3", "/W:2",
                                "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
                               capture_output=True, text=True, errors="replace", env=env)
            if r.returncode > 7:
                raise SystemExit("  ** " + _("Copying the textures into %(mod)s failed "
                                             "(robocopy code %(code)d). Run play.bat again.")
                                 % {"mod": mod, "code": r.returncode} + " **")
            src, dst = _folded(hashes(merged)), _folded(hashes(target))
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
        if set_luts():
            done.append("LUTs")
        tg = apply_toggles(active, False, prefs)
        for name, was, now in tg:
            print("  %-58s %s" % (name[:58], change_text(was, now)))
        if tg:
            done.append("seasonal mods")
        reset_lut()
        # after the toggles, so the panel reports the mod list as it now stands
        write_staged(staged_texture_season(installed) if not stage_tex else want, stage_tex)
        write_mod_panel(active, prefs)
        send_spell()
        if send_mcm():
            done.append("MCM settings")
        if set_grass():
            done.append("grass")
        # each restaged texture set adds "textures"; say it once
        words = {"textures": pgettext("staged", "textures"),
                 "soundscape": pgettext("staged", "soundscape"),
                 "seasonal mods": pgettext("staged", "seasonal mods"),
                 "MCM settings": pgettext("staged", "MCM settings"),
                 "grass": pgettext("staged", "grass"),
                 "LUTs": pgettext("staged", "LUTs")}
        print("  => " + _("%(season)s staged (%(what)s). The game picks this up when it "
                          "starts.")
              % {"season": title,
                 "what": pgettext("between words in a list", ", ").join(
                     words[w] for w in dict.fromkeys(done)) or _("nothing to do")})
        say_skipped()
        particle_check()
    except OSError as e:
        # a file locked, read-only or out of room: said as the other stops are
        raise SystemExit("  ** " + _("Stopped: %s. Run play.bat again.") % e + " **")
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
