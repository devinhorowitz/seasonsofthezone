#!/usr/bin/env python3
"""Tie the installed ground/foliage textures to the real-world season in the Zone.

  python _tools/season.py status              # what season is it, what is installed
  python _tools/season.py apply               # stage the season for today's date
  python _tools/season.py apply --season winter
  python _tools/season.py apply --dry-run
  python _tools/season.py apply --mapping met

WHY THIS WORKS AT BOOT AND NOT IN GAME
--------------------------------------
X-Ray binds terrain and grass textures at level load, out of MO2's virtual file
system, and that VFS is frozen the moment the game launches. There is no runtime
texture-swap API - the only `reload_textures()` in the whole install is
`ui_debug_launcher.script`, and it works by calling ChangeLevel(). So a season
cannot rotate mid-session. Deciding it BEFORE MO2 starts is just file staging,
which is completely safe.

Textures are not stored in saves, so an existing playthrough simply looks
different the next time it loads. Reverting is `apply --season summer`.

THE MAPPING
-----------
The Zone sits at roughly 51.4N 30.1E - Polesia, northern Kyiv Oblast, humid
continental (Koppen Dfb).

  phenological (default) - when the Zone actually LOOKS like each season
      spring       Mar 05 - May 19   (76 d)   thaw and meltwater, then green-up
      summer       May 20 - Sep 14  (118 d)   full foliage
      autumn       Sep 15 - Oct 31   (47 d)   the turn; October is peak golden autumn
      winter       Nov 01 - Nov 30   (30 d)   first snowfall, ground not yet covered
      winter_snow  Dec 01 - Mar 04   (94 d)   snow lies on the ground

  meteorological (--mapping met) - Ukraine's hydrometeorological convention
      winter Nov 1 / winter_snow Dec 1 / spring Mar 1 / summer Jun 1 / autumn Sep 1

WINTER IS TWO SEASONS, and that is the point. In Polesia snow arrives from late
October, but cover only holds from about December through March, and the thaw is
what makes spring wet. One 110-day "winter" forced a choice between snow two
months too early and bare ground through February.

The split is deliberately lopsided - winter_snow is nearly twice spring. That is
correct for the latitude, and the calendar version would flatten it out.

Both winters currently stage the SAME textures (Aydin ships four sets, not five);
they differ in grade, flora, fog, wind and snowfall.

IDENTIFYING WHAT IS INSTALLED
-----------------------------
Always by hashing the mod folder against every option in the source archive,
never by a stored note. `.Grok's Modpack Installer/mods.txt` field 2 claimed the
terrain LOD patch was installed as `Winter` when the bytes were `Summer` - that
field records what the installer was ASKED for, not what landed.
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
STATE = os.path.join(ROOT, "_baseline", "season-state.json")
SOTZ = "Seasons of the Zone"


def _find_unrar():
    """Locate UnRAR/7z for the .rar sources. Returns a path, or "UnRAR" to let rarfile
    search PATH itself - which is also what makes this work on a machine where WinRAR was
    installed somewhere other than the default."""
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
    """Read a value out of the portable ModOrganizer.ini beside this install.

    MO2 stores paths as `key=@ByteArray(D:\\ANOMALY)` with doubled backslashes.
    Reading them is what makes this tool portable: nothing below needs to know the drive
    letter, the game folder name, or which profile is selected.
    """
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
    """The Anomaly install MO2 is pointed at."""
    return _mo2_ini("gamePath", os.path.join(os.path.dirname(ROOT), "ANOMALY"))


def profile_name():
    return _mo2_ini("selected_profile", "G.A.M.M.A")


SEASONS = ("spring", "summer", "autumn", "winter", "winter_snow")

# ---------------------------------------------------------------------------------
# INSTALL-SPECIFIC CONFIGURATION lives in seasons_config.py, not here. The engine does
# not know your folder names; that file describes one person's mod set. Missing or empty
# is a supported state - the whole in-engine seasonal layer runs with no texture staging
# at all, which is how this is meant to be tried for the first time.
# ---------------------------------------------------------------------------------
try:
    import seasons_config as _cfg
    LAYOUT = getattr(_cfg, "LAYOUT", {})
    TOGGLE_MODS = getattr(_cfg, "TOGGLE_MODS", {})
    SOUND_SRC = getattr(_cfg, "SOUND_SRC", None)
except ImportError:
    LAYOUT, TOGGLE_MODS, SOUND_SRC = {}, {}, None



def _detect_nl(raw):
    """CRLF if the file uses it. Written with chr() on purpose: every attempt to embed
    the escapes through a shell heredoc turned them into real control characters."""
    crlf = chr(13) + chr(10)
    return crlf if crlf in raw else chr(10)


def _modlist_path():
    return os.path.join(ROOT, "profiles", profile_name(), "modlist.txt")


def _mod_enabled(name):
    """Is this mod actually mounted? A layer staged into a DISABLED mod is dead work, and
    worse, a status line claiming it is installed is a lie the next reader has to unpick."""
    try:
        raw = io.open(_modlist_path(), encoding="utf-8", errors="replace", newline="").read()
    except OSError:
        return False
    nl = _detect_nl(raw)
    return any(l == "+" + name for l in raw.split(nl))


def write_staged(season, staging=True):
    """Record which season the TEXTURES were staged for, where the mod can read it.

    The runtime layer follows the calendar on its own, but textures are frozen into the
    VFS at launch. If the two disagree - because someone pinned a season in MCM, or
    launched MO2 directly without staging - nothing used to say so, and you got winter
    light on autumn ground with no explanation. The mod compares this against the season
    it is actually running and reports the mismatch.

    `staging` records whether the launch-time texture layer is switched on at all. With
    it off the two are EXPECTED to disagree, and the mod stays quiet: a disagreement the
    player asked for is not a fault worth reporting every load.
    """
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


# --- the launch-time texture layer, and the player's control over it ----------------
#
# season.py runs before the game exists, so it cannot ask MCM anything. It reads MCM's
# OWN store instead: ui_mcm's get/set go through axr_main.config:w_value + :save()
# (ui_mcm.script:742-760), which lands in axr_options.ltx under an [mcm] section, one
# key per line as "<tree>/<option> = <value>". That file is plain text on disk, so the
# settings are readable without the game running - and, because MCM writes it on Apply
# from the main menu too, changes made without loading a save are picked up as well.
#
# Two generated files go the other way:
#   season_mods.ltx            what is installed, which seasons each mod belongs to, its
#                              size, its current state. The MCM page builds itself from
#                              this, so the list is whatever is actually present.
#   ui_mcm_seasons_mods.xml    the captions. MCM builds an option's label from the string
#                              id ui_mcm_<hint> (ui_mcm.script:1122) and
#                              translate_string returns its input unchanged when nothing
#                              matches - so a generated option without a generated string
#                              puts the raw key on screen.
#
# Preferences only ever SUBTRACT. They can hold a mod back; they cannot force a winter
# texture set on in July, and they cannot stage a season the calendar did not pick.
def _axr_options():
    """Locate MCM's store. MO2 redirects a VFS write to whichever ENABLED mod owns the
    path - here "G.A.M.M.A. MCM values" - or to overwrite/ when none does. Both are
    checked and the newest wins, so renaming or replacing the owning mod (which that
    mod's own name invites) cannot strand us on a stale copy."""
    cands = glob.glob(os.path.join(MODS, "*", "gamedata", "configs", "axr_options.ltx"))
    cands.append(os.path.join(ROOT, "overwrite", "gamedata", "configs", "axr_options.ltx"))
    try:
        raw = io.open(_modlist_path(), encoding="utf-8", errors="replace", newline="").read()
        enabled = set(l[1:] for l in raw.split(_detect_nl(raw)) if l[:1] == "+")
    except OSError:
        enabled = None
    live = []
    for p in cands:
        if not os.path.isfile(p):
            continue
        if p.startswith(MODS) and enabled is not None:
            mod = os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(p))))
            if mod not in enabled:
                continue                  # a disabled mod's copy is not what the game reads
        live.append(p)
    return max(live, key=os.path.getmtime) if live else None


def _slug(name):
    """Stable, filename-safe key for a mod folder. This becomes the MCM option id, so it
    must not drift between runs or the player's choice detaches from the mod it was made
    about and silently reverts to the default."""
    s = "".join(c if c.isalnum() else "_" for c in name.lower())
    while "__" in s:
        s = s.replace("__", "_")
    return s.strip("_")[:48]


def _display(name):
    """The folder name carries a parenthetical for MO2's benefit - "(seasonal)",
    "(winter only)". The panel states the seasons on its own line, so on screen the
    suffix is just noise."""
    i = name.rfind(" (")
    return name[:i] if i > 0 and name.endswith(")") else name


def season_label(s):
    return "deep winter" if s == "winter_snow" else s


def read_prefs():
    """What the player set on the MCM page, read out of MCM's own store.

    Returns {"stage_textures": bool, "off": set(slug)}. No file, or no keys yet, means a
    game that has not been launched since the panel appeared - defaults, not an error.
    Anything unreadable falls back to defaults too: a texture layer that refuses to stage
    because a config could not be parsed would be a far worse failure than staging it.
    """
    out = {"stage_textures": True, "stage_sound": True, "off": set()}
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
        k = k[len("seasons_zone/"):]
        off = v.lower() in ("false", "off", "0", "no")
        if k == "stage_textures":
            out["stage_textures"] = not off
        elif k == "stage_sound":
            out["stage_sound"] = not off
        elif k.startswith("mod_") and off:
            out["off"].add(k[4:])
    return out


def apply_toggles(season, dry_run=False, prefs=None):
    """Enable/disable season-scoped mods. Returns [(name, from, to)] for what changed.

    With the texture layer switched off every one of them is disabled, whatever the
    season: "hold these back" has to mean the world does not change under you.
    """
    prefs = prefs if prefs is not None else read_prefs()
    p = _modlist_path()
    raw = io.open(p, encoding="utf-8", errors="replace", newline="").read()
    nl = _detect_nl(raw)
    lines = raw.split(nl)
    if not lines or not lines[0].startswith("#"):
        raise SystemExit("  modlist.txt line 1 is not the MO2 header - refusing to touch it")

    head, body = lines[0], lines[1:]
    changed = []
    for name, cfg in TOGGLE_MODS.items():
        folder = os.path.join(MODS, name)
        if not os.path.isdir(folder):
            continue                      # not installed yet; nothing to toggle
        on = (season in cfg["seasons"]
              and prefs["stage_textures"]
              and _slug(name) not in prefs["off"])
        want = "+" if on else "-"
        def find(n):
            return next((i for i, l in enumerate(body)
                         if l[:1] in ("+", "-") and l[1:] == n), None)

        idx, ref = find(name), find(cfg["above"])
        if ref is None:
            raise SystemExit("  cannot place %s: %s not in modlist" % (name, cfg["above"]))
        if idx is None:
            body.insert(ref, want + name)
            changed.append((name, "absent", want))
            continue
        # PLACEMENT IS CHECKED EVERY RUN, not only on insert. Lower line = higher
        # priority, so the mod must sit ABOVE its anchor. This used to be enforced only
        # when inserting, which meant correcting an `above` here silently did nothing to
        # a mod already in the list - the flag kept flipping while a higher-priority mod
        # quietly won the same files.
        if idx > ref:
            body.pop(idx)
            body.insert(find(cfg["above"]), want + name)
            changed.append((name, "misplaced", want))
            continue
        if body[idx][:1] != want:
            changed.append((name, body[idx][:1], want))
            body[idx] = want + name

    if changed and not dry_run:
        # MO2 holds modlist.txt in memory and rewrites it on exit, so an edit made while
        # it is open is silently reverted - the toggle appears to work and then does not.
        # The long staging path already refuses to run against a live MO2; this path can
        # now change the modlist on its own, so it needs the same guard.
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


def toggle_status(season, prefs=None):
    """What each season-scoped mod is doing right now.

    Yields (name, installed, state, wanted, held_back) where `wanted` is what the season
    alone asks for and `held_back` is why it will not get it - "off" for the master
    switch, "mod" for this one being unticked, or None.
    """
    prefs = prefs if prefs is not None else read_prefs()
    p = _modlist_path()
    raw = io.open(p, encoding="utf-8", errors="replace", newline="").read()
    nl = _detect_nl(raw)
    body = raw.split(nl)[1:]
    out = []
    for name, cfg in TOGGLE_MODS.items():
        installed = os.path.isdir(os.path.join(MODS, name))
        state = next((l[:1] for l in body if l[:1] in ("+", "-") and l[1:] == name), None)
        held = None
        if not prefs["stage_textures"]:
            held = "off"
        elif _slug(name) in prefs["off"]:
            held = "mod"
        out.append((name, installed, state, season in cfg["seasons"], held))
    return out


# --- seasonal soundscape ---------------------------------------------------------
#
# The ambient system names its sound channels per time-of-day in plain-text presets:
#     sound_channels_dynamic = wind_normal, birds, Insects, birds_night, wind_heavy, ...
# so gating insects out of a snow-covered Zone is a text edit, not a new sound pack. The
# generated files are a full override of the winner's, regenerated per season exactly the
# way write_flora() regenerates the flora config.
#
# SOURCE IS THE MOD THAT ACTUALLY WINS THE FILE, not the obvious one. Three mods ship
# these presets - "457- RETUNE" (disabled), "304- Dark Signal Weather and Ambiance Audio"
# (~line 570) and "3- Soundscape Overhaul - Solarint" (~861) - and the HIGHEST enabled one
# wins. Generating from Solarint would have produced overrides built on a base the game
# never loads, quietly changing the soundscape while appearing to preserve it.
SOUND_MOD = "Seasonal Soundscape"
SOUND_REL = ("configs", "environment", "ambients", "presets")

# Channels removed per season. Everything not listed here is left alone - wind, storms,
# drones, spooks, urban and underground beds play year-round.
#
#   Insects/insects/Insects_night   the case really does vary in the source files
#   birds                           daytime songbirds
#   birds_night                     owls and crows; KEPT in every season, because a winter
#                                   night without crows is emptier than the Zone should be
#   birds_swamp                     marsh life, which freezes out first
SOUND_CUT = {
    "spring":      (),
    "summer":      (),
    "autumn":      ("birds_swamp",),
    "winter":      ("Insects", "insects", "Insects_night", "birds_swamp"),
    "winter_snow": ("Insects", "insects", "Insects_night", "birds_swamp", "birds"),
}

SOUND_TAG = ";; seasonal-soundscape season="


def _sound_src_dir():
    """Where the ambient presets are generated FROM, or None when no source is configured.

    None is the default and a supported state: with no SOUND_SRC there is nothing to gate,
    and the rest of the seasonal system runs exactly as it otherwise would. Every caller
    checks for None rather than assuming a path."""
    if not SOUND_SRC:
        return None
    return os.path.join(MODS, SOUND_SRC, "gamedata", *SOUND_REL)


def _sound_dst_dir():
    return os.path.join(MODS, SOUND_MOD, "gamedata", *SOUND_REL)


def _strip_channels(line, cut):
    """Remove named channels from one sound_channels_dynamic assignment, preserving the
    key, the spacing around '=', and any trailing ';' the source used."""
    m = re.match(r"^(\s*sound_channels_dynamic\s*=\s*)(.*?)(;?\s*)$", line)
    if not m:
        return line
    head, body, tail = m.group(1), m.group(2), m.group(3)
    kept = [c for c in (x.strip() for x in body.split(",")) if c and c not in cut]
    return head + ", ".join(kept) + tail


def write_soundscape(season, enabled=True):
    """Regenerate the ambient presets for `season`. Returns (files, channels removed)."""
    src = _sound_src_dir()
    if not src or not os.path.isdir(src):
        return None, 0
    dst = _sound_dst_dir()
    if not enabled:
        # Switched off: delete the overrides rather than writing uncut copies, so the
        # source mod wins the files again and this layer leaves no trace at all.
        if os.path.isdir(dst):
            shutil.rmtree(dst, ignore_errors=True)
        return 0, 0
    cut = set(SOUND_CUT.get(season, ()))
    if os.path.isdir(dst):
        shutil.rmtree(dst, ignore_errors=True)
    os.makedirs(dst)

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
        body = nl.join([SOUND_TAG + season] + out)
        io.open(os.path.join(dst, f), "w", encoding="cp1251", newline="").write(body)
        n += 1
    return n, removed


def soundscape_installed():
    """Which season the generated presets are for, by reading the marker they carry."""
    d = _sound_dst_dir()
    if not os.path.isdir(d):
        return None
    for f in sorted(os.listdir(d)):
        if f.lower().endswith(".ltx"):
            first = io.open(os.path.join(d, f), encoding="cp1251",
                            errors="replace").readline().strip()
            if first.startswith(SOUND_TAG):
                return first[len(SOUND_TAG):].strip()
            return None
    return None


def _mod_weight(folder):
    """Only what MO2 actually mounts. meta.ini and readmes sit in the folder but are
    not content, and counting them puts a number on screen that no other tool agrees
    with."""
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


def write_mod_panel(season, prefs=None):
    """Describe the season-scoped mods for the MCM page, and generate their labels.

    Rewritten every launch, so the panel can never be stale, and it reports what is TRUE
    on disk rather than what TOGGLE_MODS hopes for: a mod that was deleted reads as not
    installed instead of quietly vanishing from the list.
    """
    prefs = prefs if prefs is not None else read_prefs()
    d = os.path.join(MODS, SOTZ, "gamedata", "configs")
    if not os.path.isdir(d):
        return None
    status = {n: (inst, st, want, held) for n, inst, st, want, held in
              toggle_status(season, prefs)}
    crlf = chr(13) + chr(10)

    rows = []
    for name, cfg in TOGGLE_MODS.items():
        inst, state, want, held = status[name]
        if not inst:
            continue                      # nothing to offer a switch for
        n, b = _mod_weight(os.path.join(MODS, name))
        rows.append({
            "key": _slug(name), "name": _display(name), "folder": name,
            "seasons": cfg["seasons"], "files": n, "mb": b / 1048576.0,
            "enabled": state == "+", "wanted": want, "held": held,
        })

    # GROUPED BY SEASON, because a flat list hides the thing worth seeing: winter carries
    # four mods and several gigabytes while summer carries one. A mod can span seasons and
    # an MCM option id can only exist once, so each is filed under the FIRST season it
    # serves and its full span stays in the label and hover text. Sorted into calendar
    # order, so the panel reads the way the year does.
    rows.sort(key=lambda r: (SEASONS.index(r["seasons"][0]), r["name"].lower()))
    for r in rows:
        r["group"] = r["seasons"][0]

    # Sound layer state, as NUMBERS not prose: r_string_ex strips internal whitespace out
    # of an ltx value, so a sentence would arrive mangled (this is what turned "Deep winter"
    # into "DEEPWINTER"). The mod composes the wording from these.
    _ssrc = _sound_src_dir()
    sound_have = bool(_ssrc) and os.path.isdir(_ssrc)
    sound_cuts = 0
    if sound_have and prefs["stage_sound"]:
        cut = set(SOUND_CUT.get(season, ()))
        srcd = _ssrc
        for f in sorted(os.listdir(srcd)):
            if not f.lower().endswith(".ltx"):
                continue
            raw = io.open(os.path.join(srcd, f), encoding="cp1251",
                          errors="replace", newline="").read()
            for line in raw.split(_detect_nl(raw)):
                if "sound_channels_dynamic" in line and _strip_channels(line, cut) != line:
                    sound_cuts += 1

    lines = ["; generated by _tools/season.py on every launch - do not edit by hand",
             "[mods]",
             "staged_for = " + (season or "unknown"),
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
                  # UNDERSCORE, not a space: X-Ray's r_string_ex strips internal
                  # whitespace out of an ltx value, which rendered "Deep winter" on the
                  # panel as "DEEPWINTER". The mod turns it back into a space.
                  "group_label = " + cap_first(season_label(r["group"])).replace(" ", "_"),
                  "span = " + " and ".join(season_label(s) for s in r["seasons"]),
                  "files = %d" % r["files"],
                  # same decimal rule as the captions: a 0.49 MB mod printed as "0"
                  # reads like a broken install
                  "mb = " + ("%.1f" % r["mb"] if r["mb"] < 10 else "%.0f" % r["mb"]),
                  "enabled = " + ("true" if r["enabled"] else "false"),
                  "wanted = " + ("true" if r["wanted"] else "false")]
    manifest = os.path.join(d, "season_mods.ltx")
    io.open(manifest, "w", encoding="cp1251", newline="").write(crlf.join(lines) + crlf)

    # The captions. Anomaly loads every .xml under configs/text/<lang>/ by filename -
    # there is no manifest to register with - so writing the file is the whole job.
    x = ['<?xml version="1.0" encoding="windows-1251"?>', "",
         "<!-- generated by _tools/season.py - one entry per installed season-scoped",
         "     mod, so the MCM page lists whatever is actually present. -->",
         "<string_table>"]
    for r in rows:
        seas = " and ".join(season_label(s) for s in r["seasons"])
        # Say what is true and what the switch does from HERE. A mod already held back
        # does not also need telling what unticking it would have done.
        if r["enabled"]:
            state = "Mounted now. Untick to leave it out from the next launch on."
        elif r["held"] == "off":
            state = "Held back - the texture layer above is switched off."
        elif r["held"] == "mod":
            state = "Switched off. Tick to bring it back at the next launch."
        elif r["wanted"]:
            state = "Due this season - mounts at the next launch."
        else:
            state = "Out of season. It will mount when the season comes round."
        # A 0.49 MB mod printed as "0 MB" reads like a broken install. Give small mods a
        # decimal; whole numbers are fine once there are gigabytes in play.
        mb = ("{:,.1f}".format(r["mb"]) if r["mb"] < 10 else "{:,.0f}".format(r["mb"]))
        desc = ("%s. %s files, %s MB. %s"
                % (cap_first(seas), "{:,}".format(r["files"]), mb, state))
        # The mod sits under its FIRST season's heading, so name the others inline - under
        # a WINTER heading you would otherwise have to hover to learn a mod also runs in
        # deep winter, which is exactly the question the grouping exists to answer.
        extra = [season_label(s) for s in r["seasons"][1:]]
        caption = r["name"] + ("   + %s" % " and ".join(extra) if extra else "")
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
    """The season the on-disk textures actually are, or None if they disagree."""
    vals = set(v for v in installed.values() if v)
    return vals.pop() if len(vals) == 1 else None

# (month, day) start of each season
# Winter is split: snow arrives in Polesia from late October, but the ground only holds
# cover from about December through March, and the thaw is what makes spring wet.
#   winter       25 Oct - 30 Nov   37d   first snows, bare ground
#   winter_snow   1 Dec - 14 Mar  104d   snow cover
PHENO = [("winter_snow", 12, 1), ("spring", 3, 5), ("summer", 5, 20),
         ("autumn", 9, 15), ("winter", 11, 1)]
MET = [("winter_snow", 12, 1), ("spring", 3, 1), ("summer", 6, 1),
       ("autumn", 9, 1), ("winter", 11, 1)]

# --- colour grade -----------------------------------------------------------
# The Atmos_*.ltx files in appdata/ are cfg_load presets. Their values are plain
# console variables, and console variables persist in appdata/user.ltx - so the
# season can write them at boot instead of you typing cfg_load every session.
# (cfg_load applies in-session but does NOT write back to user.ltx, which is how
# a whole session once silently ran on Neutral while we thought it was Autumn.)
APPDATA = os.path.join(game_dir(), "appdata")
GRADE_FILE = {"spring": "Atmos_Spring.ltx", "summer": "Atmos_Summer.ltx",
              "autumn": "Atmos_Autumn.ltx", "winter": "Atmos_Winter.ltx",
              # INVERNO's own grade, authored for its snow textures
              "winter_snow": "Atmos_WinterSnow.ltx"}
# only these are touched in user.ltx; every other line is left alone
GRADE_VARS = ["r__color_grading", "r__saturation", "r__gamma", "r__exposure",
              "r2_sun_lumscale", "r2_sun_lumscale_hemi", "r2_sun_lumscale_amb",
              "r2_tonemap_adaptation", "r2_tonemap_lowlum", "r2_tonemap_middlegray",
              "ssfx_hud_hemi", "r2_sunshafts_value"]


# --- flora layer ------------------------------------------------------------
# SSS foliage shader uniforms, driven per season by zzz_season_flora.script.
# ssfx_floravariation is declared in deffer_grass.ps/.vs but set by NO script in
# the install (it sits at 0, so the colour-variation layer is inert) - driving it
# overrides nothing. florafixes_1/_2 are re-applied after ssfx_florafixes.script
# rather than by editing the player's MCM values.
#
# AUTHORED, not derived - same status as the colour grade. Tune freely.
#   variation: autumn is deliberately the highest. Patchy, uneven colour IS what
#   turning foliage looks like; summer is the most uniform.
#   sss (sun through a leaf): high on thin new spring growth, near-zero on bare winter.
FLORA_MOD = "Season Flora"
# ssfx_floravariation IS LEFT AT ZERO ON PURPOSE. It is not a seasonal tint - the
# shader does:
#     float3 color_variation(float t)
#         { return sin(t + float3(0.0, 0.33, 0.66) * 6.28) * 0.5; }
#     S.base.rgb = saturate(S.base.rgb + color_variation(...) * ssfx_floravariation.x);
# Three sine waves offset by a third of a cycle each = a HUE ROTATION, +/-0.5 per
# channel, applied out of phase. Driving it at 0.30 turned foliage red and dark
# blue. It is a per-instance decorrelation knob for breaking up uniformity between
# grass clumps, not a way to express a season - it rotates hue in all directions
# rather than shifting toward amber. Wrong tool; left at the shipped default of 0.
# (If subtle natural break-up is ever wanted, explore around 0.02-0.03, not here.)
FLORA = {
    #            var: all zero - see above  | spec: g   g_wet  t   t_wet | sss: int  color
    "spring": dict(var=(0.0, 0.0, 0.0, 0.0), spec=(0.40, 0.55, 0.45, 0.60), sss=(2.80, 0.85),
                   fog=(15.0, 2.2, 0.060, 1.0)),
    "summer": dict(var=(0.0, 0.0, 0.0, 0.0), spec=(0.30, 0.45, 0.35, 0.50), sss=(2.50, 0.75),
                   fog=(10.0, 1.4, 0.020, 0.9)),
    "autumn": dict(var=(0.0, 0.0, 0.0, 0.0), spec=(0.38, 0.55, 0.42, 0.58), sss=(1.80, 0.60),
                   fog=(20.0, 3.0, 0.080, 1.0)),
    "winter_snow": dict(var=(0.0, 0.0, 0.0, 0.0), spec=(0.58, 0.66, 0.54, 0.66), sss=(0.55, 0.30),
                        fog=(14.0, 2.9, 0.010, 1.0)),
    "winter": dict(var=(0.0, 0.0, 0.0, 0.0), spec=(0.50, 0.60, 0.50, 0.62), sss=(0.80, 0.40),
                   fog=(17.0, 2.4, 0.015, 1.0)),
}
# fog = (height, density, suncolor, scattering) -> ssfx_fog (h,d,s,0) + ssfx_fog_scattering
#
# HEIGHT IS CAPPED AT 20.0 BY THE ENGINE. See RANGES below - this table used to run
# autumn at 28.0 and spring at 22.0, and the engine threw BOTH away silently.
#
# Anchored on GAMMA's OWN MCM tuning (20, 2, 0.015, 1), not the SSS defaults
# (8, 1.3, 0.1, 0.7) - GAMMA deliberately runs taller, denser and far more neutral
# fog, and that is the baseline a season should move around. Because height is pinned
# to a 1..20 band, most of the seasonal spread is carried by DENSITY, which has real
# headroom (max 5.0).
#
#   autumn  20 / 3.0 / 0.080  the foggy season in Polesia: cool nights over damp warm
#                             ground make radiation fog, and a low sun tints it.
#                             Height at the engine ceiling, density well above baseline.
#   winter  17 / 2.4 / 0.015  dense but low and grey - ice fog takes no sun colour
#   spring  15 / 2.2 / 0.060  thaw damp, morning mist, mildly warm light
#   summer  10 / 1.4 / 0.020  least fog - hot dry air holds it down
#
# suncolor is documented 0.0-1.0 ("0% .. 100% sun color in the fog"), so 0.08 is a
# restrained 8%. Kept deliberately low after the floravariation lesson: that one had
# no documented range and turned out to be a hue rotation.


# Engine-enforced ranges for every uniform we drive, read from the mod's own MCM
# sliders (ssfx_fog_mcm.script, ssfx_florafixes_mcm.script).
#
# WHY THIS EXISTS: X-Ray REJECTS THE WHOLE COMMAND when any single component is out
# of range. It does NOT clamp. The only evidence is one line in the log -
#     ~ Invalid syntax in call to 'ssfx_fog'
# - and the previous value silently retained, so the readback reports a plausible
# number and nothing looks broken. Autumn fog height 28.0 against a max of 20.0
# discarded all four fog components while the other uniforms applied normally.
RANGES = {
    "spec_grass":     (0.0,  1.0),
    "spec_grass_wet": (0.0,  1.0),
    "spec_trees":     (0.0,  1.0),
    "spec_trees_wet": (0.0,  1.0),
    "sss_int":        (0.0, 10.0),
    "sss_color":      (0.0,  1.0),
    "fog_height":     (1.0, 20.0),
    "fog_density":    (0.0,  5.0),
    "fog_suncolor":   (0.0,  1.0),
    "fog_scattering": (0.0,  1.0),
}


def check_ranges():
    """Refuse to ship a value the engine will throw away. Called on every write."""
    bad = []
    for season in sorted(FLORA):
        for key, names in FLORA_KEYS:
            for name, val in zip(names, FLORA[season][key]):
                lo_hi = RANGES.get(name)
                if lo_hi and not (lo_hi[0] <= val <= lo_hi[1]):
                    bad.append("%s.%s = %s (engine allows %s..%s)"
                               % (season, name, val, lo_hi[0], lo_hi[1]))
    if bad:
        raise SystemExit("season.py: the engine would REJECT these outright: "
                         + "; ".join(bad))

FLORA_KEYS = (("var", ["var_grass_int", "var_grass_freq",
                       "var_foliage_int", "var_foliage_freq"]),
              ("spec", ["spec_grass", "spec_grass_wet",
                        "spec_trees", "spec_trees_wet"]),
              ("sss", ["sss_int", "sss_color"]),
              ("fog", ["fog_height", "fog_density",
                       "fog_suncolor", "fog_scattering"]))


def _flora_body(season):
    """The exact file body a season should produce - single source of truth."""
    check_ranges()
    f = FLORA[season]
    body = ["[flora]", "season = %s" % season, ""]
    for key, names in FLORA_KEYS:
        for name, val in zip(names, f[key]):
            body.append("%-18s = %s" % (name, val))
        body.append("")
    return "\r\n".join(body)


def write_flora(season):
    """Write the season's uniform values where zzz_season_flora.script reads them."""
    p = os.path.join(MODS, FLORA_MOD, "gamedata", "configs", "season_flora.ltx")
    if not os.path.isdir(os.path.dirname(p)):
        return None
    io.open(p, "wb").write(_flora_body(season).encode("cp1251"))
    return p


def flora_installed():
    """Which season's config is on disk - by CONTENT, not by the `season =` line.

    Matching only the season name was a real bug: when the MEANING of a season
    changed (fog values added), the name still read `autumn`, so apply reported
    "already on autumn" and the new keys never landed. Exactly the same failure as
    trusting a stored note over the bytes - so compare the whole body against what
    this season would generate now.
    """
    p = os.path.join(MODS, FLORA_MOD, "gamedata", "configs", "season_flora.ltx")
    if not os.path.isfile(p):
        return None
    on_disk = io.open(p, encoding="cp1251", errors="replace").read().replace("\r\n", "\n").strip()
    for season in SEASONS:
        if _flora_body(season).replace("\r\n", "\n").strip() == on_disk:
            return season
    return None


def _read_vars(path):
    d = {}
    if not os.path.isfile(path):
        return d
    for line in io.open(path, encoding="cp1251", errors="replace"):
        p = line.strip().split(None, 1)
        if len(p) == 2:
            d[p[0]] = p[1].strip()
    return d


def _num(s):
    """Compare 1. / 1.0 / 1.00 as equal, and do it component-wise for tuples.

    r__color_grading is written "(0.8600, 0.7050, 0.4400)" in the preset files but
    echoed back by the engine as "(0.860000, 0.705000, 0.440000)". A plain string
    fallback called those different, so identify_grade() reported a correctly
    applied preset as UNRECOGNISED and apply() rewrote it on every run.
    """
    if s is None:
        return None
    nums = re.findall(r"-?[0-9]+\.?[0-9]*", str(s))
    if nums:
        return tuple(round(float(n), 6) for n in nums)
    return str(s).strip()


def identify_grade():
    """Which Atmos_* preset does user.ltx currently match? None if no clean match."""
    live = _read_vars(os.path.join(APPDATA, "user.ltx"))
    best = None
    for season, fn in GRADE_FILE.items():
        p = _read_vars(os.path.join(APPDATA, fn))
        if not p:
            continue
        keys = [k for k in GRADE_VARS if k in p]
        if keys and all(_num(live.get(k)) == _num(p[k]) for k in keys):
            best = season
    return best


def apply_grade(season):
    """Rewrite only the grade vars in user.ltx. Returns list of (var, old, new)."""
    src = os.path.join(APPDATA, GRADE_FILE[season])
    if not os.path.isfile(src):
        raise SystemExit("  missing grade preset: %s" % src)
    preset = _read_vars(src)
    U = os.path.join(APPDATA, "user.ltx")
    bk = os.path.join(ROOT, "_baseline", "appdata-presets")
    os.makedirs(bk, exist_ok=True)
    shutil.copy2(U, os.path.join(bk, "user-%s-pre-%s.ltx"
                                 % (datetime.datetime.now().strftime("%Y%m%d-%H%M%S"), season)))
    # newline="" is load-bearing: without it io.open() translates CRLF to LF on READ, so
    # the CRLF test below can never be true and every rewrite silently flattens the file.
    # user.ltx hides this (the game rewrites it CRLF on exit) but the Atmos_*.ltx presets
    # do not, and a flattened preset turns a one-value change into a 49-line diff.
    raw = io.open(U, encoding="cp1251", errors="replace", newline="").read()
    nl = "\r\n" if "\r\n" in raw else "\n"
    lines = raw.replace("\r\n", "\n").split("\n")
    changed = []
    for i, l in enumerate(lines):
        s = l.strip()
        if not s:
            continue
        k = s.split(None, 1)[0]
        if k in GRADE_VARS and k in preset:
            old = s.split(None, 1)[1] if len(s.split(None, 1)) > 1 else ""
            if _num(old) != _num(preset[k]):
                indent = l[:len(l) - len(l.lstrip())]
                lines[i] = "%s%s %s" % (indent, k, preset[k])
                changed.append((k, old, preset[k]))
    io.open(U, "w", encoding="cp1251", newline="").write(nl.join(lines))
    return changed


def season_for(d, mapping="pheno"):
    """Which season contains date d. Windows wrap across new year."""
    table = PHENO if mapping == "pheno" else MET
    starts = sorted(((datetime.date(d.year, m, dd), name) for name, m, dd in table))
    cur = starts[0][1]
    # the season running at the start of the year is the last one in the table
    cur = sorted(table, key=lambda t: (t[1], t[2]))[-1][0]
    for start, name in starts:
        if d >= start:
            cur = name
    return cur


def running():
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=60).stdout.lower()
    except Exception:
        return []
    return [p for p in ("anomalydx11avx.exe", "anomalydx11.exe", "modorganizer.exe") if p in out]


def lp(p):
    """Windows MAX_PATH escape - some option trees nest deeply."""
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
    """Extract only the named top-level option folders. Returns merged gamedata dir."""
    src = os.path.join(DOWNLOADS, archive)
    if not os.path.isfile(src):
        raise SystemExit("  missing archive: %s" % src)
    # Windows will refuse to delete a staging file that an indexer or AV still holds a
    # handle on, and shutil.rmtree turns that into a hard crash mid-run. Retry briefly,
    # then fall back to a fresh directory rather than taking the whole launch down.
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
        import py7zr
        with py7zr.SevenZipFile(src) as z:
            names = [n for n in z.getnames()
                     if any(n.replace("\\", "/").split("/")[0] == w for w in wanted)]
            z.reset()
            z.extract(path=dest, targets=names)
    else:
        import rarfile
        # Find UnRAR rather than assume it. WinRAR's default location is only the first
        # guess; PATH and the 32-bit Program Files both count, and a missing tool should
        # say so plainly instead of failing inside rarfile with a confusing error.
        rarfile.UNRAR_TOOL = _find_unrar()
        with rarfile.RarFile(src) as z:
            names = [i.filename for i in z.infolist()
                     if any(i.filename.replace("\\", "/").split("/")[0] == w for w in wanted)]
            z.extractall(dest, members=names)
    # merge the option folders' gamedata trees, in order
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


def identify(mod, cfg, tmp, prefer=None):
    """Which season is on disk, by hash. Returns (season|None, detail).

    Several seasons can be the SAME bytes: Aydin ships four sets, so `winter` and
    `winter_snow` stage identical textures and the match is genuinely ambiguous. This used
    to take the LAST match, which is always `winter_snow`, so a folder staged for `winter`
    reported as `winter_snow` - and season.py then believed the textures were wrong and
    re-ran robocopy over both mods to arrive at the bytes already on disk. Every single
    `apply --season winter`. Prefer the season being asked about when it is among the
    matches; only fall back to the first when it is not.
    """
    live = hashes(os.path.join(MODS, mod, "gamedata"))
    if not live:
        return None, "no gamedata"
    matches, detail = [], []
    for season in SEASONS:
        merged = extract(cfg["archive"], cfg["options"][season],
                         os.path.join(tmp, mod[:18].replace(" ", "_"), season))
        cand = hashes(merged)
        same = sum(1 for k in set(cand) & set(live) if cand[k] == live[k])
        detail.append((season, len(cand), len(set(cand) & set(live)), same))
        if same == len(live) and same > 0 and len(cand) == len(live):
            matches.append(season)
    if not matches:
        return None, detail
    return (prefer if prefer in matches else matches[0]), detail


def who_wins(rel):
    """Print every enabled mod shipping `rel`, highest priority first, and name the winner.

    MO2 resolves a shared file to the HIGHEST enabled mod that ships it. That is the whole
    basis of the seasonal toggling, and it is also the one thing that fails silently: a
    mod placed below the real owner flips its flag exactly as asked and changes nothing.
    """
    rel = rel.replace(chr(92), "/").strip("/")
    for lead in ("gamedata/", "mods/"):
        if rel.startswith(lead):
            rel = rel[len(lead):]

    try:
        raw = io.open(_modlist_path(), encoding="utf-8", errors="replace", newline="").read()
    except OSError:
        print("  cannot read the modlist")
        return 1
    body = [l for l in raw.split(_detect_nl(raw)) if l[:1] in ("+", "-")]

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
        print("  No enabled or disabled mod ships it - the base game .db provides it.")
        print("  A mod of your own shipping this file would win outright.")
    elif winner is None:
        print("  Only disabled mods ship it; the base game .db is providing it.")
    else:
        print("  Put your seasonal mod ABOVE:  %s" % winner)
        print("  i.e.  \"above\": \"%s\"" % winner)
    return 0


def _check_install():
    """Confirm we are sitting in a Mod Organizer install before touching anything.

    Without this, running from the wrong folder - which is exactly what happens on a first
    try, before the tools have been copied next to ModOrganizer.exe - produces a raw
    FileNotFoundError about modlist.txt. That is a true message and a useless one.
    """
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
    ap.add_argument("--season", choices=SEASONS)
    ap.add_argument("--mapping", choices=["pheno", "met"], default="pheno")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-textures", action="store_true",
                    help="skip the launch-time texture layer for this run only; the "
                         "in-engine seasons are unaffected. The persistent version of "
                         "this lives on the MCM page.")
    a = ap.parse_args()

    _check_install()

    if a.cmd == "whowins":
        if not a.path:
            raise SystemExit("  whowins needs a gamedata-relative path, e.g.\n"
                             "    python _tools/season.py whowins "
                             "textures/terrain/terrain_escape.dds")
        raise SystemExit(who_wins(a.path))

    today = datetime.date.today()
    want = a.season or season_for(today, a.mapping)
    tmp = os.path.join(ROOT, "_staging", "season")

    prefs = read_prefs()
    if a.no_textures:
        prefs["stage_textures"] = False   # one-off, without touching what MCM stored
    stage_tex = prefs["stage_textures"]

    print("  date            %s" % today.isoformat())
    print("  mapping         %s" % ("phenological (Polesia)" if a.mapping == "pheno"
                                    else "meteorological (UA convention)"))
    print("  season for date %s%s" % (want, "   (forced)" if a.season else ""))
    print("  texture layer   %s" % ("on" if stage_tex else
                                    "OFF - textures left alone, in-engine seasons still run"))
    print()

    try:
        installed = {}
        for mod, cfg in LAYOUT.items():
            got, detail = identify(mod, cfg, tmp, want)
            installed[mod] = got
            print("  %s" % mod[:70])
            print("     installed: %s" % (got or "UNRECOGNISED - not a clean copy of any season"))
            if got is None:
                for s, n, shared, same in detail:
                    print("        %-8s archive %3d | shared %3d | identical %3d" % (s, n, shared, same))
        print()

        grade_now = identify_grade()
        flora_now = flora_installed()
        sound_now = soundscape_installed()
        flora_live = _mod_enabled(FLORA_MOD)
        print("  colour grade   installed: %s" % (grade_now or "UNRECOGNISED / hand-tuned"))
        for name, inst, state, should, held in toggle_status(want, prefs):
            if not inst:
                print("  %-30s NOT INSTALLED" % name[:30])
            else:
                note = {"off": "held back - texture layer off",
                        "mod": "held back - switched off in MCM"}.get(
                            held, "ENABLED" if should else "disabled")
                print("  %-30s %-9s (should be %s)"
                      % (name[:30],
                         {"+": "ENABLED", "-": "disabled", None: "absent"}[state], note))
        print("  flora layer    installed: %s%s"
              % (flora_now or "not present",
                 "" if flora_live else "   (mod disabled - superseded by the main mod)"))
        print("  soundscape     installed: %s%s"
              % (sound_now or "not present",
                 "" if prefs["stage_sound"] else "   (gating switched off in MCM)"))
        print()

        # With the texture layer off the on-disk season is not ours to correct. Nothing
        # is copied, and what is already staged simply stays - that is the whole point.
        tex_ok = True if not stage_tex else all(v == want for v in installed.values())
        grade_ok = grade_now == want
        # SUPERSEDED. "Season Flora" drives ssfx_florafixes_1/2, ssfx_floravariation,
        # ssfx_fog and ssfx_fog_scattering - every one of which Seasons of the Zone now
        # drives itself, blended across boundaries and toggleable from MCM. Both enabled
        # would be two writers on six uniforms, which is the precise race the main engine
        # exists to detect. It is disabled, so this layer is inert and staging into it
        # would be dead work.
        flora_ok = (flora_now == want) if flora_live else True
        _ssrc = _sound_src_dir()
        if not _ssrc or not os.path.isdir(_ssrc):
            sound_ok = True                       # no source configured; nothing to gate
        elif prefs["stage_sound"]:
            sound_ok = sound_now == want
        else:
            sound_ok = sound_now is None          # off means the overrides are gone
        if tex_ok and grade_ok and flora_ok and sound_ok:
            # Toggles are checked even when the season has not moved. A newly installed
            # season-scoped mod is "absent" from the modlist until something inserts it,
            # and an early return here meant it never would be.
            # READ-ONLY UNDER `status`. This branch is reached before the status guard
            # below, so without this a status call would flip modlist flags and rewrite
            # the generated panel - a command that reports state quietly changing it.
            writing = (a.cmd == "apply") and not a.dry_run
            tg = apply_toggles(want, not writing, prefs)
            for name, was, now in tg:
                print("  %-58s %s -> %s" % (name[:58], was, now))
            if tg:
                print("  => %s: season-scoped mods corrected. Takes effect on next launch."
                      % want)
            elif not stage_tex:
                print("  => %s in-engine; texture layer off, nothing staged" % want)
            else:
                print("  => already on %s (textures + grade + flora + season-scoped mods),"
                      " nothing to do" % want)
            # the marker must describe reality on EVERY run, not only on runs that
            # changed something, or a fresh install reads as unstaged.
            if writing:
                write_staged(staged_texture_season(installed) if not stage_tex else want,
                             stage_tex)
                write_mod_panel(want, prefs)
            return
        if not tex_ok:
            print("  => textures: %s" % " and ".join(
                "%s %s -> %s" % (m.split(" ")[0], installed[m] or "?", want) for m in LAYOUT))
        if not grade_ok:
            print("  => grade   : %s -> %s" % (grade_now or "?", want))
        if not flora_ok:
            print("  => flora   : %s -> %s" % (flora_now or "?", want))
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
        # Only when the textures are actually wrong. Guarded so that a grade-only or
        # flora-only correction does not re-copy several GB to reach the same bytes, and
        # so that "texture layer off" reaches here without staging anything.
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

        if not grade_ok:
            ch = apply_grade(want)
            got = identify_grade()
            print("  %-64s %3d var(s)  %s" % ("colour grade -> " + want, len(ch),
                                              "VERIFIED" if got == want else "** reads as %s **" % got))
            if got != want:
                raise SystemExit("  aborted - grade did not take")

        if not flora_ok:
            p = write_flora(want)
            if p is None:
                print("  %-64s %s" % ("flora layer", "SKIPPED - '" + FLORA_MOD + "' mod not installed"))
            else:
                got = flora_installed()
                print("  %-64s %s" % ("flora layer -> " + want,
                                      "VERIFIED" if got == want else "** reads as %s **" % got))
                if got != want:
                    raise SystemExit("  aborted - flora config did not take")

        if not sound_ok:
            n, cuts = write_soundscape(want, prefs["stage_sound"])
            if n is None:
                print("  %-64s %s" % ("soundscape", "SKIPPED - '" + SOUND_SRC + "' not installed"))
            else:
                got = soundscape_installed()
                exp = want if prefs["stage_sound"] else None
                label = ("soundscape -> " + want + " (%d channel cuts)" % cuts
                         if prefs["stage_sound"] else "soundscape OFF - overrides removed")
                print("  %-64s %3d files  %s" % (label, n,
                      "VERIFIED" if got == exp else "** reads as %s **" % got))
                if got != exp:
                    raise SystemExit("  aborted - soundscape did not take")

        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        io.open(STATE, "w", encoding="utf-8").write(json.dumps(
            {"season": want, "applied": today.isoformat(), "mapping": a.mapping,
             "note": "informational only - season.py always re-identifies by hash"},
            indent=2))
        print()
        tg = apply_toggles(want, a.dry_run, prefs)
        for name, was, now in tg:
            print("  %-58s %s -> %s" % (name[:58], was, now))
        if not a.dry_run:
            # After the toggles, so the panel reports the modlist as it now stands.
            # `installed` is still accurate here: with the texture layer off nothing was
            # copied, so nothing has moved since it was identified.
            write_staged(staged_texture_season(installed) if not stage_tex else want,
                         stage_tex)
            write_mod_panel(want, prefs)
        print("  => %s staged (%sgrade + flora%s). Takes effect on next launch."
              % (want, "textures + " if not tex_ok else "",
                 " + season-scoped mods" if tg else ""))
    finally:
        if os.path.isdir(tmp):
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
