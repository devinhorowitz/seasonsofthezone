#!/usr/bin/env python3
"""Stage the launch-time seasonal layers for today's date.

  python _tools/season.py status                 today's season, what is staged
  python _tools/season.py apply                  stage it (what play.bat runs)
  python _tools/season.py apply --season winter
  python _tools/season.py apply --dry-run
  python _tools/season.py whowins <gamedata path>

The in-engine layers (light, fog, wind, wetness) follow the calendar on their own.
Textures cannot: X-Ray loads them from MO2's virtual file system at level load and keeps
them for the session. So texture mods are enabled, disabled or restaged here, before the
game starts. Configuration is in seasons_config.py; with none, nothing is staged.

Seasons (phenological, for Polesia):
  spring       Mar 05 - May 19    76 d
  summer       May 20 - Sep 14   118 d
  autumn       Sep 15 - Oct 31    47 d
  winter       Nov 01 - Nov 30    30 d   first snowfall, bare ground
  winter_snow  Dec 01 - Mar 04    94 d   snow on the ground
--mapping met uses Ukraine's meteorological convention instead.

What is installed is identified by hashing the mod folder against the archive's options,
never by a stored note. The archive side is cached (_baseline/season-archive-hashes.json,
keyed on the archive's size and mtime); the live folder is hashed on every run.
"""
import argparse
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

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS = os.path.join(ROOT, "mods")
DOWNLOADS = os.path.join(ROOT, "downloads")
SOTZ = "Seasons of the Zone"
SEASONS = ("spring", "summer", "autumn", "winter", "winter_snow")


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
PRESET_DIR = os.path.join(MODS, SOTZ, "gamedata", "configs", "seasons_presets")

# Install-specific configuration lives in seasons_config.py. Missing or empty is fine:
# the in-engine layer runs with nothing staged.
try:
    import seasons_config as _cfg
    LAYOUT = getattr(_cfg, "LAYOUT", {})
    TOGGLE_MODS = getattr(_cfg, "TOGGLE_MODS", {})
    SOUND_SRC = getattr(_cfg, "SOUND_SRC", None)
    # The calendar itself is configurable. PERIODS adds base periods (they
    # partition the year alongside the seasons); EVENTS adds windows that OVERLAY
    # whatever period they fall in, which is what lets a one-day event keep the
    # season around it.
    PERIODS = getattr(_cfg, "PERIODS", {})
    EVENTS = getattr(_cfg, "EVENTS", {})
except ImportError:
    LAYOUT, TOGGLE_MODS, SOUND_SRC = {}, {}, None
    PERIODS, EVENTS = {}, {}


def _validate_config():
    """Refuse a malformed seasons_config.py with a message naming the entry.

    `"seasons": ("winter")` is a string, not a tuple, and `"winter" in "winter_snow"` is
    true, so without this check that mod would be enabled in deep winter."""
    problems = []
    known = period_names()
    valid = ", ".join(known)

    if not isinstance(TOGGLE_MODS, dict):
        problems.append("TOGGLE_MODS must be a dict of {mod folder: {...}}")
    else:
        for name, cfg in TOGGLE_MODS.items():
            where = "TOGGLE_MODS[%r]" % name
            if not isinstance(cfg, dict):
                problems.append(where + " must be a dict with 'seasons' and 'above'")
                continue
            raw_when = cfg.get("when", cfg.get("seasons"))
            if isinstance(raw_when, str) or not isinstance(raw_when, (list, tuple)) or not raw_when:
                problems.append(where + ": 'when' must be a tuple of period names - "
                                "note the trailing comma in a one-element tuple, "
                                "(\"winter\",) not (\"winter\")")
            else:
                bad = [str(x) for x in raw_when if x not in known]
                if bad:
                    problems.append(where + ": unknown period(s) %s - valid: %s"
                                    % (", ".join(bad), valid))
            above = cfg.get("above")
            if not isinstance(above, str) or not above.strip():
                problems.append(where + ": 'above' must name the mod this one has to "
                                "outrank (find it with: season.py whowins <file>)")

    if not isinstance(LAYOUT, dict):
        problems.append("LAYOUT must be a dict of {mod folder: {...}}")
    else:
        for name, cfg in LAYOUT.items():
            where = "LAYOUT[%r]" % name
            if not isinstance(cfg, dict):
                problems.append(where + " must be a dict with 'archive' and 'options'")
                continue
            if not isinstance(cfg.get("archive"), str) or not cfg.get("archive"):
                problems.append(where + ": 'archive' must be a filename in downloads/")
            opts = cfg.get("options")
            if not isinstance(opts, dict) or not opts:
                problems.append(where + ": 'options' must map each season to a list of "
                                "folder names inside the archive")
            else:
                for season, folders in opts.items():
                    if season not in known:
                        problems.append(where + ": unknown season %r in 'options' - valid: %s"
                                        % (season, valid))
                    if (isinstance(folders, str) or not isinstance(folders, (list, tuple))
                            or not folders or not all(isinstance(f, str) for f in folders)):
                        problems.append(where + ": options[%r] must be a list of folder "
                                        "names, e.g. [\"Spring\"]" % season)

    if SOUND_SRC is not None and (not isinstance(SOUND_SRC, str) or not SOUND_SRC):
        problems.append("SOUND_SRC must be None or a mod folder name")

    if problems:
        raise SystemExit("  seasons_config.py needs fixing before anything runs:\n"
                         + "\n".join("    - " + p for p in problems)
                         + "\n  Nothing has been changed.")


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
        tail = " - " + season_label(s)
        if low.endswith(tail):
            return name[:-len(tail)]
    return name


def season_label(s):
    return "deep winter" if s == "winter_snow" else s


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


def apply_toggles(active, dry_run=False, prefs=None):
    """Enable or disable the season-scoped mods and place each above its anchor.
    Returns [(name, from, to)] for what changed. With the texture layer off, every
    season-scoped mod is disabled."""
    prefs = prefs if prefs is not None else read_prefs()
    active = [active] if isinstance(active, str) else list(active)
    base, active_set = active[0], set(active)
    p = _modlist_path()
    raw = io.open(p, encoding="utf-8", errors="replace", newline="").read()
    nl = _detect_nl(raw)
    lines = raw.split(nl)
    if not lines or not lines[0].startswith("#"):
        raise SystemExit("  modlist.txt line 1 is not the MO2 header - refusing to touch it")

    head, body = lines[0], lines[1:]
    changed = []

    def find(n):
        return next((i for i, l in enumerate(body)
                     if l[:1] in ("+", "-") and l[1:] == n), None)

    def place(name, above, want):
        idx, ref = find(name), find(above)
        if ref is None:
            print("  ! %s: anchor %r is not in the modlist - SKIPPED. Fix 'above' in"
                  " seasons_config.py (season.py whowins <file> names the right mod)."
                  % (name[:40], above))
            return
        if idx is None:
            body.insert(ref, want + name)
            changed.append((name, "absent", want))
            return
        # lower line = higher priority; the mod must sit above its anchor
        if idx > ref:
            body.pop(idx)
            body.insert(find(above), want + name)
            changed.append((name, "misplaced", want))
            return
        if body[idx][:1] != want:
            changed.append((name, body[idx][:1], want))
            body[idx] = want + name

    for name, cfg in TOGGLE_MODS.items():
        if not os.path.isdir(os.path.join(MODS, name)):
            continue
        # A mod is on if ANY period it is scoped to is active today - that is what
        # makes an event additive on top of its season. MCM holds are per base
        # period, because that is what has a page.
        on = (bool(set(_when(cfg)) & active_set)
              and prefs["stage_textures"]
              and _slug(name) not in prefs["off"].get(base, set()))
        place(name, cfg["above"], "+" if on else "-")

    # The generated soundscape is placed too: a folder MO2 finds on its own is added
    # disabled, and it has to sit above its source.
    if SOUND_SRC and find(SOUND_SRC) is not None:
        have = os.path.isdir(os.path.join(MODS, SOUND_MOD))
        if have or find(SOUND_MOD) is not None:
            on = have and prefs["stage_sound"] and _mod_enabled(SOUND_SRC)
            place(SOUND_MOD, SOUND_SRC, "+" if on else "-")

    if changed and not dry_run:
        # MO2 rewrites modlist.txt from memory on exit, so an edit made while it is open
        # is lost.
        busy = running()
        if busy:
            raise SystemExit("  ** %s running - close it first, modlist not touched **"
                             % ", ".join(busy))
        bk = os.path.join(ROOT, "_baseline", "modfile-backups")
        os.makedirs(bk, exist_ok=True)
        shutil.copy2(p, os.path.join(bk, "modlist-%s-pre-toggle.txt"
                                     % datetime.datetime.now().strftime("%Y%m%d-%H%M%S")))
        io.open(p, "w", encoding="utf-8", newline="").write(nl.join([head] + body))
    return changed


def toggle_status(active, prefs=None):
    """[(name, installed, state, wanted, held)] for each season-scoped mod. `held` is why
    a wanted mod stays off: "off" (texture layer off), "mod" (switched off in MCM), None."""
    prefs = prefs if prefs is not None else read_prefs()
    active = [active] if isinstance(active, str) else list(active)
    base, active_set = active[0], set(active)
    body = (_modlist_lines() or [])[1:]
    out = []
    for name, cfg in TOGGLE_MODS.items():
        installed = os.path.isdir(os.path.join(MODS, name))
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
#
# Each season must leave a different set of channels standing, or two of them sound
# alike; scratchpad/test_soundscape.py checks that.
SOUND_CUT = {
    "spring":      ("Insects_night",),
    "summer":      (),
    "autumn":      ("Insects", "insects", "birds_swamp"),
    "winter":      ("Insects", "insects", "Insects_night", "birds_swamp"),
    "winter_snow": ("Insects", "insects", "Insects_night", "birds_swamp", "birds"),
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
    # NB: this loop variable must not be called  - it used to shadow the
    # function parameter, so every later use read the LAST name in SEASONS
    # ("winter_snow") instead of the period actually being staged.
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
                  # value. The mod turns it back into a space.
                  "group_label = " + cap_first(season_label(r["group"])).replace(" ", "_"),
                  "span = " + " and ".join(season_label(s) for s in r["seasons"]),
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
        seas = " and ".join(season_label(s) for s in r["seasons"])
        mb = ("{:,.1f}".format(r["mb"]) if r["mb"] < 10 else "{:,.0f}".format(r["mb"]))
        desc = ("%s. %s files, %s MB. Untick to leave it out of this season."
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
PHENO = [("winter_snow", 12, 1), ("spring", 3, 5), ("summer", 5, 20),
         ("autumn", 9, 15), ("winter", 11, 1)]
MET = [("winter_snow", 12, 1), ("spring", 3, 1), ("summer", 6, 1),
       ("autumn", 9, 1), ("winter", 11, 1)]

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


def base_table(mapping="pheno"):
    """The base periods: the shipped seasons plus anything in PERIODS. These
    partition the year - exactly one is active on any date."""
    table = list(PHENO if mapping == "pheno" else MET)
    for name, when in PERIODS.items():
        table.append((name, int(when[0]), int(when[1])))
    return table


def period_names(mapping="pheno"):
    """Every name a mod may be scoped to: base periods first, then events."""
    return [n for n, _, _ in base_table(mapping)] + list(EVENTS)


def _in_window(d, start, end):
    """Is d inside the inclusive (month, day) window? A window whose start is
    after its end wraps the year end, so (12, 26)-(1, 6) is Christmas to Epiphany."""
    a = (int(start[0]), int(start[1]))
    b = (int(end[0]), int(end[1]))
    x = (d.month, d.day)
    return a <= x <= b if a <= b else (x >= a or x <= b)


def active_for(d, mapping="pheno", base=None):
    """Every period active on d: the base period, then every event covering it.

    Events OVERLAY rather than replace. That is the whole point - a Christmas event
    does not displace winter, so December 25th keeps its snow and adds to it. Pass
    `base` to honour an MCM pin or --season while events still resolve by date."""
    out = [base or season_for(d, mapping)]
    for name, win in EVENTS.items():
        if _in_window(d, win[0], win[1]) and name not in out:
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
        print("  ! could not list running processes (%s) - assuming MO2 and the game are"
              " closed" % e.__class__.__name__)
        return []
    roots = [os.path.normcase(os.path.abspath(p)) + os.sep for p in (ROOT, game_dir())]
    mine = set()
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.endswith("|?"):
            mine.add(line[:-2].lower() + " (path unreadable, assumed this install)")
            continue
        p = os.path.normcase(os.path.abspath(line))
        if any(p.startswith(r) for r in roots):
            mine.add(os.path.basename(line).lower())
    return sorted(mine)


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


def extract(archive, wanted, dest):
    """Extract the named option folders and merge their gamedata trees, in order.
    Returns the merged gamedata directory."""
    dest = _extract_options(archive, wanted, dest)
    merged = os.path.join(dest, "__merged", "gamedata")
    os.makedirs(merged, exist_ok=True)
    for w in wanted:
        gd = os.path.join(dest, w, "gamedata")
        if not os.path.isdir(gd):
            raise SystemExit("  option has no gamedata/: %s" % w)
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
        raise SystemExit("  missing archive: %s" % src)
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
            raise SystemExit("  the LAYOUT layer needs the py7zr package to read .7z archives:\n"
                             "    python -m pip install py7zr\n"
                             "  Nothing has been changed.")
        with py7zr.SevenZipFile(src) as z:
            names = [n for n in z.getnames()
                     if any(n.replace("\\", "/").split("/")[0] == w for w in wanted)]
            z.reset()
            z.extract(path=dest, targets=names)
    else:
        try:
            import rarfile
        except ImportError:
            raise SystemExit("  the LAYOUT layer needs the rarfile package to read .rar archives:\n"
                             "    python -m pip install rarfile\n"
                             "  (and WinRAR or 7-Zip installed, for the unrar tool). "
                             "Nothing has been changed.")
        rarfile.UNRAR_TOOL = _find_unrar()
        with rarfile.RarFile(src) as z:
            names = [i.filename for i in z.infolist()
                     if any(i.filename.replace("\\", "/").split("/")[0] == w for w in wanted)]
            z.extractall(dest, members=names)
    return dest


HASH_CACHE = os.path.join(ROOT, "_baseline", "season-archive-hashes.json")


def _archive_key(archive):
    """name|size|mtime - a replaced archive invalidates its cached hashes."""
    src = os.path.join(DOWNLOADS, archive)
    if not os.path.isfile(src):
        raise SystemExit("  missing archive: %s" % src)
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
                raise SystemExit("  option has no gamedata/: %s" % o)
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
    bytes (Aydin ships four sets for five seasons), so the requested season is preferred
    when it is among the matches."""
    live = hashes(os.path.join(MODS, mod, "gamedata"))
    if not live:
        return None, "no gamedata"
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


def who_wins(rel):
    """Print every mod shipping `rel`, enabled or disabled, in priority order, and the
    winner among the enabled ones."""
    rel = rel.replace(chr(92), "/").strip("/")
    for lead in ("gamedata/", "mods/"):
        if rel.startswith(lead):
            rel = rel[len(lead):]

    lines = _modlist_lines()
    if lines is None:
        print("  cannot read the modlist")
        return 1
    body = [l for l in lines if l[:1] in ("+", "-")]

    print("  file: gamedata/%s" % rel)
    print()
    hits, winner = 0, None
    for i, line in enumerate(body):
        name = line[1:]
        p = os.path.join(MODS, name, "gamedata", *rel.split("/"))
        if not os.path.isfile(p):
            continue
        hits += 1
        mark = ""
        if line[:1] == "+" and winner is None:
            winner = name
            mark = "   <-- WINS"
        print("    line %5d  [%s]  %-46s %9d B%s"
              % (i + 2, line[:1], name[:46], os.path.getsize(p), mark))

    print()
    if not hits:
        print("  No enabled or disabled mod ships it as a loose file - the base game .db")
        print("  provides it (archives under db/ are not inspected). A mod of your own")
        print("  shipping this file would win outright.")
    elif winner is None:
        print("  Only disabled mods ship it; the base game .db is providing it.")
    else:
        print("  Put your seasonal mod ABOVE:  %s" % winner)
        print("  i.e.  \"above\": \"%s\"" % winner)
    return 0


def _check_mod_state():
    """Warn when the mod itself is missing or disabled, or Season Flora is enabled beside
    it. season.py never enables the main mod."""
    gd = os.path.join(MODS, SOTZ, "gamedata")
    if not os.path.isdir(gd):
        print("  ! mods/%s/gamedata is missing - the mod is not installed. The zip's" % SOTZ)
        print("    INNER 'mods/%s' folder goes into mods/; check the path." % SOTZ)
        return
    lines = _modlist_lines()
    if lines is None:
        return
    state = next((l[:1] for l in lines if l[:1] in ("+", "-") and l[1:] == SOTZ), None)
    if state is None:
        print("  ! '%s' is not in profile %r - MO2 will add it DISABLED at its next start."
              % (SOTZ, profile_name()))
        print("    Enable it in MO2, or nothing in-game will happen.")
    elif state == "-":
        print("  ! '%s' is DISABLED in profile %r - enable it in MO2." % (SOTZ, profile_name()))
    if state == "+" and _mod_enabled(FLORA_MOD):
        print("  ! '%s' is enabled beside '%s'. Both drive the same flora and fog uniforms;"
              % (FLORA_MOD, SOTZ))
        print("    that is two writers on one console value. Disable %s." % FLORA_MOD)


SHADOW_CACHE = os.path.join(ROOT, "_baseline", "season-shadow-check.json")


def shadow_check(force=False):
    """Test every file of every season-scoped mod against every mod above it.

    SHADOWED: an enabled mod above ships the file. dormant: a disabled mod above does, and
    would win if enabled. note: two season-scoped mods overlap in a season they share
    (judged on seasons, not on today's flags, so it shows out of season too).

    Costs a stat per (file, higher mod) pair, so `apply` runs it only when the modlist has
    changed; `status` always does."""
    lines = _modlist_lines()
    if lines is None:
        return
    body = [l for l in lines if l[:1] in ("+", "-")]
    key = hashlib.md5(("|".join(body) + "|" + "|".join(sorted(TOGGLE_MODS)))
                      .encode("utf-8", "replace")).hexdigest()
    if not force and os.path.isfile(SHADOW_CACHE):
        try:
            if json.loads(io.open(SHADOW_CACHE, encoding="utf-8").read()).get("key") == key:
                return
        except (OSError, ValueError):
            pass

    ours = set(TOGGLE_MODS) | {SOUND_MOD, SOTZ}
    index = {l[1:]: i for i, l in enumerate(body)}
    shadowed, dormant, notes = [], {}, []
    for name, cfg in TOGGLE_MODS.items():
        base = os.path.join(MODS, name, "gamedata")
        if name not in index or not os.path.isdir(base):
            continue
        rels = []
        for r, _, fs in os.walk(base):
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
                if shared:
                    notes.append((name, other, len(hits), eg, ", ".join(
                        s_ for s_ in SEASONS if s_ in shared)))
            elif other in ours:
                continue
            elif on:
                shadowed.append((name, other, len(hits), eg))
            else:
                dormant.setdefault(name, []).append((other, len(hits), eg))

    os.makedirs(os.path.dirname(SHADOW_CACHE), exist_ok=True)
    io.open(SHADOW_CACHE, "w", encoding="utf-8").write(json.dumps({"key": key}))
    for name, other, n, eg in shadowed:
        print("  ! %s is SHADOWED by '%s' on %d file(s), e.g. %s"
              % (name[:36], other[:44], n, eg))
        print("    It cannot win those files even when enabled. Anchor it above that mod,"
              " or disable that mod.")
    for name, lst in dormant.items():
        other, n, eg = lst[0]
        print("  - %d disabled mod(s) above %s share its files (e.g. '%s', %d file(s), %s)."
              % (len(lst), name[:36], other[:40], n, eg))
        print("    Enabling one of them will shadow it; run `season.py status` afterwards.")
    for name, other, n, eg, seasons in notes:
        print("  - note: '%s' sits above %s and overrides %d of its file(s) in %s (e.g. %s)"
              % (other[:40], name[:36], n, seasons, eg))
        print("    Fine if that is the intent; if not, swap their anchors.")


def _check_install():
    """Stop with a plain message when not run from a Mod Organizer install."""
    ini = os.path.join(ROOT, "ModOrganizer.ini")
    modlist = _modlist_path()
    if os.path.isfile(ini) and os.path.isfile(modlist):
        return

    print("  This does not look like a Mod Organizer install.")
    print()
    print("    looked in : %s" % ROOT)
    print("    expected  : ModOrganizer.ini        %s"
          % ("found" if os.path.isfile(ini) else "MISSING"))
    print("                profiles/%s/modlist.txt %s"
          % (profile_name(), "found" if os.path.isfile(modlist) else "MISSING"))
    print()
    print("  Put _tools/ and play.bat in your GAMMA folder - the one containing")
    print("  ModOrganizer.exe - and run it from there. Nothing has been changed.")
    raise SystemExit(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["status", "apply", "whowins"])
    ap.add_argument("path", nargs="?",
                    help="for `whowins`: a gamedata-relative file path, e.g. "
                         "textures/terrain/terrain_escape.dds")
    ap.add_argument("--season", choices=period_names())
    ap.add_argument("--mapping", choices=["pheno", "met"], default="pheno")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-textures", action="store_true",
                    help="skip the texture layer for this run only; the MCM page has the "
                         "persistent switch")
    a = ap.parse_args()

    _check_install()
    _validate_config()

    if a.cmd == "whowins":
        if not a.path:
            raise SystemExit("  whowins needs a gamedata-relative path, e.g.\n"
                             "    python _tools/season.py whowins "
                             "textures/terrain/terrain_escape.dds")
        raise SystemExit(who_wins(a.path))

    _check_mod_state()
    shadow_check(force=(a.cmd == "status"))

    today = datetime.date.today()
    prefs = read_prefs()

    # MCM offers "automatic, or pin one" and the in-engine layers honour it, so the
    # staged layers follow it too - otherwise pinning a season gives you its light
    # over another season's ground. An explicit --season still wins over the pin.
    pinned = prefs["mode"] if prefs["mode"] in SEASONS else None
    want = a.season or pinned or season_for(today, a.mapping)
    # A pin or --season fixes the BASE period; events still resolve by real date,
    # so pinning summer in December does not cancel a Christmas event.
    active = active_for(today, a.mapping, base=want)
    tmp = os.path.join(ROOT, "_staging", "season-%d" % os.getpid())    # per process
    if a.no_textures:
        prefs["stage_textures"] = False
    stage_tex = prefs["stage_textures"]
    writing = (a.cmd == "apply") and not a.dry_run

    print("  date            %s" % today.isoformat())
    print("  mapping         %s" % ("phenological (Polesia)" if a.mapping == "pheno"
                                    else "meteorological (UA convention)"))
    why = ("   (forced with --season)" if a.season else
           "   (pinned in MCM)" if pinned else "")
    print("  season          %s%s" % (want, why))
    if pinned and not a.season:
        print("  calendar says   %s" % season_for(today, a.mapping))
    print("  texture layer   %s" % ("on" if stage_tex else
                                    "OFF - textures left alone, in-engine seasons still run"))
    print()

    try:
        installed = {}
        for mod, cfg in LAYOUT.items():
            got, detail = identify(mod, cfg, tmp, want)
            installed[mod] = got
            print("  %s" % mod[:70])
            print("     installed: %s" % (got or "UNRECOGNIZED - not a clean copy of any season"))
            if got is None:
                for s, n, shared, same in detail:
                    print("        %-8s archive %3d | shared %3d | identical %3d" % (s, n, shared, same))
        print()

        for name, inst, state, should, held in toggle_status(active, prefs):
            if not inst:
                print("  %-30s NOT INSTALLED" % name[:30])
            else:
                note = {"off": "held back - texture layer off",
                        "mod": "held back - switched off in MCM"}.get(
                            held, "ENABLED" if should else "disabled")
                print("  %-30s %-9s (should be %s)"
                      % (name[:30],
                         {"+": "ENABLED", "-": "disabled", None: "absent"}[state], note))
        sound_now = soundscape_installed()
        print("  soundscape     installed: %s%s"
              % (sound_now or "not present",
                 "   (source mod disabled - overrides removed)"
                 if (SOUND_SRC and not _mod_enabled(SOUND_SRC)) else
                 "" if prefs["stage_sound"] else "   (gating switched off in MCM)"))
        shipped, present, copied = install_presets(writing)
        if shipped:
            print("  presets        %d shipped, %d in appdata%s"
                  % (len(shipped), len(present) + len(copied),
                     "   (copied: %s)" % ", ".join(copied) if copied else ""))
        print()

        # With the texture layer off, whatever is staged stays.
        tex_ok = True if not stage_tex else all(v == want for v in installed.values())
        _ssrc = _sound_src_dir()
        if not _ssrc or not os.path.isdir(_ssrc):
            # no source, or the source mod is disabled: stale overrides come out
            sound_ok = (sound_now is None) if SOUND_SRC else True
        elif prefs["stage_sound"]:
            sound_ok = (sound_now == want
                        and soundscape_signature() == _sound_signature(want))
        else:
            sound_ok = sound_now is None
        if tex_ok and sound_ok:
            # Toggles are checked even when nothing else moved: a newly installed
            # season-scoped mod is absent from the modlist until something inserts it.
            tg = apply_toggles(active, not writing, prefs)
            for name, was, now in tg:
                print("  %-58s %s -> %s" % (name[:58], was, now))
            if tg and writing:
                print("  => %s: season-scoped mods corrected. Takes effect on next launch."
                      % want)
            elif tg:
                print("  => %s: season-scoped mods need correcting - run `season.py apply`"
                      " (or play.bat)." % want)
            elif not stage_tex:
                print("  => %s in-engine; texture layer off, nothing staged" % want)
            else:
                print("  => already on %s, nothing to do" % want)
            if writing:
                write_staged(staged_texture_season(installed) if not stage_tex else want,
                             stage_tex)
                write_mod_panel(active, prefs)
            return
        if not tex_ok:
            print("  => textures: %s" % " and ".join(
                "%s %s -> %s" % (m.split(" ")[0], installed[m] or "?", want) for m in LAYOUT))
        if not sound_ok:
            print("  => sound   : %s -> %s" % (sound_now or "?", want))

        if a.cmd == "status":
            return
        if a.dry_run:
            print("  (dry run - nothing written)")
            return
        busy = running()
        if busy:
            raise SystemExit("  ** %s running - close it first, nothing written **" % ", ".join(busy))

        print()
        done = []
        # Only when the textures are wrong: a sound-only correction must not copy gigabytes.
        for mod, cfg in (LAYOUT.items() if not tex_ok else []):
            merged = extract(cfg["archive"], cfg["options"][want],
                             os.path.join(tmp, "apply", mod[:18].replace(" ", "_")))
            target = os.path.join(MODS, mod, "gamedata")
            env = dict(os.environ, MSYS_NO_PATHCONV="1")
            r = subprocess.run(["robocopy", merged, target, "/MIR", "/R:3", "/W:2",
                                "/NFL", "/NDL", "/NJH", "/NJS", "/NP"],
                               capture_output=True, text=True, env=env)
            if r.returncode > 7:
                raise SystemExit("  ** robocopy failed (%d) for %s **" % (r.returncode, mod))
            src, dst = hashes(merged), hashes(target)
            bad = [k for k in set(src) | set(dst) if src.get(k) != dst.get(k)]
            print("  %-64s %3d files  %s" % (mod[:64], len(dst),
                                             "VERIFIED" if not bad else "** %d MISMATCH **" % len(bad)))
            if bad:
                raise SystemExit("  aborted - %s" % bad[:3])
            done.append("textures")

        if not sound_ok:
            src_live = bool(_ssrc) and os.path.isdir(_ssrc)
            if not src_live:
                if os.path.isdir(_sound_dst_dir()):
                    shutil.rmtree(_sound_dst_dir(), ignore_errors=True)
                n, cuts = 0, 0
            else:
                n, cuts = write_soundscape(want, prefs["stage_sound"])
            if n is None:
                print("  %-64s %s" % ("soundscape", "SKIPPED - '" + SOUND_SRC + "' not installed"))
            else:
                got = soundscape_installed()
                active = prefs["stage_sound"] and src_live
                exp = want if active else None
                label = ("soundscape -> " + want + " (%d channel cuts)" % cuts
                         if active else "soundscape OFF - overrides removed")
                print("  %-64s %3d files  %s" % (label, n,
                      "VERIFIED" if got == exp else "** reads as %s **" % got))
                if got != exp:
                    raise SystemExit("  aborted - soundscape did not take")
                done.append("soundscape")

        print()
        tg = apply_toggles(active, False, prefs)
        for name, was, now in tg:
            print("  %-58s %s -> %s" % (name[:58], was, now))
        if tg:
            done.append("season-scoped mods")
        # after the toggles, so the panel reports the modlist as it now stands
        write_staged(staged_texture_season(installed) if not stage_tex else want, stage_tex)
        write_mod_panel(active, prefs)
        print("  => %s staged (%s). Takes effect on next launch." % (want, ", ".join(done) or "nothing to do"))
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
