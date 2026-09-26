"""Assemble the distributable package from this install.

This is the maintainer's build script. It is tracked in the repository so the checks
below are reviewable, but it is not part of the package: it expects a GAMMA install
around it (`mods/`, `_tools/`, `_release/`), so running it from a clone will not work.
Copy it to `<your GAMMA>/_tools/` to build.

Ships: the mod, the tools and their presets, play.bat, configure.bat, the patcher, README,
CHANGELOG, LICENSE and docs. The presets are the ones marked as shipped, never one saved on
this install, and a "GAMMA example" preset made from this install's config.
Does not ship: any third-party asset, the generated Seasonal Soundscape mod, this
install's seasons_config.py (it ships as the example), MO2's meta.ini, or the fetched
weather.

The zip installs through MO2 like any other mod: gamedata/ sits at the top of its one
folder, and the tools and docs come along in the mod folder. Before the zip is kept, it
is walked the way MO2's installer walks it, installed into a simulated fresh GAMMA under
MO2's default name, and the packaged installer puts the tools in place there, where they
are run. A failure refuses the package, and so does a season.py VERSION that is not the
newest entry in CHANGELOG.md.
"""
import ast
import io
import os
import re
import shutil
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "_tools")
OUT = os.path.join(ROOT, "_release")
STAGE = os.path.join(OUT, "Seasons of the Zone")

MOD = "Seasons of the Zone"
ZIP_NAME = "SeasonsOfTheZone.zip"
MARKER = "gamedata/scripts/zzz_seasons_of_the_zone.script"

# where season.py writes the gated ambient presets; must match SOUND_REL there
SOUND_REL = ("configs", "environment", "ambients", "presets")

# Images for the GitHub page only: the README's season animation would add 4 MB to a
# 6 MB download. The packaged README links to the copy on GitHub instead.
WEB_ONLY = ["docs/images/seasons.webp"]
WEB_BASE = "https://github.com/devinhorowitz/seasonsofthezone/raw/main/"

# What MO2's Anomaly plugin accepts at the top of an archive
# (plugins/basic_games/games/game_stalkeranomaly.py, dataLooksValid).
MO2_DATA_DIRS = ("appdata", "bin", "db", "gamedata")

# The engine plus the generators for the mod's own content (season table, dial, header
# bars). luacheck.py and check_mcm_strings.py are general X-Ray tools and stay out.
TOOL_FILES = [
    "season.py",
    "configure.py",
    "config_edit.py",
    "fetch_weather.py",
    "guide.py",
    "installer.py",
    "mod_install.py",
    "lang.py",
    "build_messages.py",
    "build_season_dial.py",
    "build_season_headers.py",
    "build_seasons_ltx.py",
]
# the translations and what they are made from; the language picked in the window stays
LANG_FILES = (".po", ".pot")


def check_messages():
    """The strings for translators up to date with the tools, and every translation one the
    tools can fill in: build_messages.py --check."""
    r = subprocess.run([sys.executable, os.path.join(TOOLS, "build_messages.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise SystemExit("  refusing to package: the translations are out of step:\n"
                         + r.stdout + r.stderr)
    print("  translations           %s" % r.stdout.strip().splitlines()[-1])


def check_version(season_py, changelog):
    """season.py's VERSION names the release, and the installer tells an update from a
    downgrade by it: it has to be the newest entry in CHANGELOG.md."""
    m = re.search(r"""(?m)^VERSION\s*=\s*["']([^"']*)["']""",
                  io.open(season_py, encoding="utf-8").read())
    heads = (re.findall(r"(?m)^## (\d+\.\d+\.\d+)\b",
                        io.open(changelog, encoding="utf-8").read())
             if os.path.isfile(changelog) else [])
    version = m.group(1) if m else None
    if not heads or version != heads[0]:
        raise SystemExit("  refusing to package: season.py's VERSION is %s and CHANGELOG.md's "
                         "newest entry is %s" % (version or "missing",
                                                 heads[0] if heads else "missing"))
    print("  version                %s, CHANGELOG.md's newest" % version)


def refuse_test_rigs():
    """Stop a build that would ship a test rig.

    build_release copies the mod straight out of mods/, so anything armed there for a
    live test ships. On 2026-09-21 a remapped remembrance date and 20-second PDA
    intervals went into several builds before anyone looked.
    """
    import glob
    bad = []
    for p in glob.glob(os.path.join(ROOT, 'mods', MOD, 'gamedata', 'scripts',
                                    '*.script')):
        txt = io.open(p, encoding='utf-8', errors='replace').read()
        for marker in ('LIVETEST', 'TESTDAY', 'TEST open:'):
            if marker in txt:
                bad.append('%s contains %s' % (os.path.basename(p), marker))
    if bad:
        raise SystemExit('  ** refusing to build - test rig still armed:' + chr(10)
                         + chr(10).join('      ' + b for b in bad))
    print('  no test rig armed     OK')


def verify_engine_only():
    """Run season.py status with the configuration hidden."""
    hidden = os.path.join(TOOLS, "seasons_config.py")
    tmp = hidden + ".packing"
    moved = False
    if os.path.isfile(hidden):
        os.rename(hidden, tmp)
        moved = True
    try:
        r = subprocess.run([sys.executable, os.path.join(TOOLS, "season.py"), "status"],
                           capture_output=True, text=True, cwd=ROOT)
        ok = r.returncode == 0 and "Traceback" not in (r.stdout + r.stderr)
        print("  engine-only run        %s" % ("OK" if ok else "** FAILED **"))
        if not ok:
            print((r.stdout + r.stderr)[-900:])
            raise SystemExit("  refusing to package an engine that fails its first run")
    finally:
        if moved:
            os.rename(tmp, hidden)


# The four files season.py rewrites at every launch ship as empty stubs. The mod reads
# all four, and the empty form is what renders the right first-run text.
CRLF = chr(13) + chr(10)

STUB_MODS = CRLF.join([
    "; generated by _tools/season.py on every launch - do not edit by hand",
    "[mods]",
    "staged_for = none",
    "stage_textures = on",
    "stage_sound = on",
    "sound_available = false",
    "sound_cuts = 0",
    "list =",
    "",
])

# season = unknown is the value the mod's mismatch warning ignores.
STUB_STAGED = CRLF.join([
    "[staged]",
    "season = unknown",
    "staging = on",
    "stamped = never",
    "",
])

# Polesia's calendar and the shipped dial, byte for byte what season.py writes for them
STUB_CALENDAR = CRLF.join([
    "; generated by _tools/season.py from seasons_config.py - do not edit by hand",
    "[calendar]",
    "custom = false",
    "dial = default",
    "",
])

# A dial season.py drew for one install's own calendar; each install draws its own
CUSTOM_DIAL = "ui_seasons_dial_c"

STUB_XML = CRLF.join([
    '<?xml version="1.0" encoding="windows-1251"?>',
    "",
    "<!-- generated by _tools/season.py - one entry per installed season-scoped",
    "     mod, so the MCM page lists whatever is actually present. Ships empty. -->",
    "<string_table>",
    "</string_table>",
    "",
])


def neutralise_generated(moddir):
    cfg = os.path.join(moddir, "gamedata", "configs")
    for rel, body in (
        (os.path.join(cfg, "season_mods.ltx"), STUB_MODS),
        (os.path.join(cfg, "season_staged.ltx"), STUB_STAGED),
        (os.path.join(cfg, "text", "eng", "ui_mcm_seasons_mods.xml"), STUB_XML),
        (os.path.join(cfg, "season_calendar.ltx"), STUB_CALENDAR),
    ):
        if not os.path.isfile(rel):
            raise SystemExit("  expected generated file missing: %s" % rel)
        io.open(rel, "w", encoding="cp1251", newline="").write(body)
    tex = os.path.join(moddir, "gamedata", "textures")
    drawn = [f for f in os.listdir(tex) if f.startswith(CUSTOM_DIAL)]
    for f in drawn:
        os.remove(os.path.join(tex, f))
    print("  generated state          4 files reset to first-run stubs%s"
          % ("; %d custom dials left out" % len(drawn) if drawn else ""))


def mo2_base(names):
    """The folder MO2 installs the mod from, or None where MO2 calls the archive invalid.

    MO2's quick installer steps into a lone top-level folder until a level holds one of
    MO2_DATA_DIRS (installer_quick's getSimpleArchiveBase with the Anomaly plugin's
    dataLooksValid). 1.6.0 and earlier put the mod at mods/Seasons of the Zone/ inside
    the zip, and MO2 refused it."""
    base = ""
    while True:
        below = [n[len(base):] for n in names if n.startswith(base)]
        top = {n.split("/", 1)[0] for n in below if n}
        dirs = {n.split("/", 1)[0] for n in below if "/" in n}
        if any(d.lower() in MO2_DATA_DIRS for d in dirs):
            return base
        if len(top) == 1 and top == dirs:
            base += dirs.pop() + "/"
            continue
        return None


def selftest_mo2_base():
    old = ["Seasons of the Zone/mods/Seasons of the Zone/" + MARKER,
           "Seasons of the Zone/play.bat"]
    new = ["Seasons of the Zone/" + MARKER, "Seasons of the Zone/play.bat"]
    assert mo2_base(old) is None, "old layout accepted"
    assert mo2_base(new) == "Seasons of the Zone/", "wrapped layout refused"
    assert mo2_base([MARKER]) == "", "flat layout refused"
    assert mo2_base(["a/" + MARKER, "b/readme.txt"]) is None, "two top folders accepted"


def check_contents(names, base):
    """What the zip must carry, and what it must never carry."""
    must = [MARKER, "play.bat", "configure.bat", "_tools/season.py",
            "_tools/fetch_weather.py", "_tools/configure.py", "_tools/config_edit.py",
            "_tools/installer.py", "_tools/presets/Polesia.json",
            "_tools/presets/GAMMA example.json"]
    never = ["meta.ini",                            # MO2 writes its own
             "_tools/seasons_config.py",            # would overwrite the user's on update
             "gamedata/configs/season_weather.ltx"  # one machine's fetched day
             ] + WEB_ONLY                           # the GitHub page's, not the download's
    missing = [p for p in must if base + p not in names]
    present = [p for p in never if base + p in names] + [
        n[len(base):] for n in names if CUSTOM_DIAL in n]
    if missing or present:
        raise SystemExit("  refusing to package:%s%s"
                         % ("".join("\n    missing  " + p for p in missing),
                            "".join("\n    shipped  " + p for p in present)))
    print("  contents               required present, excluded absent")


def check_doc_images(stage):
    """Every image a packaged doc shows by relative path must be in the package; one left
    out on purpose has to be linked absolutely."""
    missing = []
    for d, _, files in os.walk(stage):
        for f in files:
            if not f.lower().endswith(".md"):
                continue
            p = os.path.join(d, f)
            for link in re.findall(r"!\[[^\]]*\]\(([^)\s]+)\)", io.open(p, encoding="utf-8").read()):
                if re.match(r"^[a-z]+://", link):
                    continue
                if not os.path.isfile(os.path.normpath(os.path.join(d, link))):
                    missing.append("%s -> %s" % (os.path.relpath(p, stage), link))
    if missing:
        raise SystemExit("  refusing to package: docs show images the zip does not have:%s"
                         % "".join("\n    " + m for m in missing))
    print("  doc images             every shown image is packaged or linked")


def check_play_bat(stage):
    """Every script the batch files run must be in the package. 1.5.0 and 1.6.0 shipped
    without fetch_weather.py, and play.bat carried on without it."""
    for bat_name in ("play.bat", "configure.bat"):
        bat = io.open(os.path.join(stage, bat_name), encoding="latin-1").read()
        wanted = sorted(set(re.findall(r"_tools\\(\w+\.py)", bat)))
        missing = [f for f in wanted if not os.path.isfile(os.path.join(stage, "_tools", f))]
        if not wanted or missing:
            raise SystemExit("  refusing to package: %s runs %s, which is not in _tools/"
                             % (bat_name, ", ".join(missing) or "nothing from _tools"))
        print("  %-22s %3d tools it runs, all packaged" % (bat_name, len(wanted)))


def write_crlf(src, dst):
    """cmd.exe misreads parts of a batch file with bare LF endings; ship CRLF."""
    data = open(src, "rb").read().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    open(dst, "wb").write(data)


# fetch_weather.py without the network: write() is handed a made-up day.
FETCH_PROBE = (
    "import fetch_weather as f\n"
    "f.write([{'date': '2026-01-15', 'high': -3.0, 'low': -9.5, 'cycle': 'clear'}])\n")

# The sandbox's MO2 executable entries; play.bat starts the first until told otherwise
ENTRIES = ("Anomaly (DX11-AVX)", "Anomaly (DX11)")
SHORTCUT = re.compile(r'(?m)^(set "SHORTCUT=)([^"]*)')


def report(what, good, text=""):
    print("  fresh install: %-36s %s" % (what, "OK" if good else "** FAILED **"))
    if not good and text:
        print(text[-1200:])
    return good


def verify_installer(root, mod):
    """The packaged installer, run as configure.bat runs it from the mod's folder: the
    tools arrive in the GAMMA folder byte for byte, a second run finds nothing to do, and
    an update puts a changed tool back and keeps the entry play.bat starts. `root` is the
    GAMMA folder, `mod` the mod's folder in it."""
    def install():
        r = subprocess.run([sys.executable, os.path.join(mod, "_tools", "configure.py"),
                            "install", "--yes"], capture_output=True, text=True, cwd=mod)
        return r.returncode, r.stdout + r.stderr

    def arrived(rel):
        there = os.path.join(root, rel)
        return (os.path.isfile(there)
                and open(os.path.join(mod, rel), "rb").read() == open(there, "rb").read())

    tools = os.path.join(mod, "_tools")
    shipped = (["play.bat", "configure.bat"]
               + [os.path.join("_tools", f) for f in os.listdir(tools) if f.endswith(".py")]
               + [os.path.join("_tools", "presets", f)
                  for f in os.listdir(os.path.join(tools, "presets"))]
               + [os.path.join("_tools", "lang", f)
                  for f in os.listdir(os.path.join(tools, "lang"))])
    code, text = install()
    if not report("the installer puts %d files there" % len(shipped),
                  code == 0 and "Traceback" not in text and all(arrived(f) for f in shipped),
                  text):
        return False
    code, text = install()
    ok = report("a second run finds them up to date",
                code == 0 and "Traceback" not in text and "up to date" in text, text)
    # a tool changed there, and play.bat set to start another of MO2's entries
    tool = os.path.join("_tools", "season.py")
    io.open(os.path.join(root, tool), "a", encoding="utf-8").write("# changed" + chr(10))
    bat = io.open(os.path.join(mod, "play.bat"), encoding="latin-1", newline="").read()
    was = SHORTCUT.search(bat)
    mine = [e for e in ENTRIES if not was or e != was.group(2)][0]
    want = SHORTCUT.sub(lambda m: m.group(1) + mine, bat, count=1)
    io.open(os.path.join(root, "play.bat"), "w", encoding="latin-1", newline="").write(want)
    code, text = install()
    got = io.open(os.path.join(root, "play.bat"), encoding="latin-1", newline="").read()
    ok &= report("an update puts a changed tool back",
                 code == 0 and "Traceback" not in text and arrived(tool), text)
    ok &= report("and keeps the entry play.bat starts",
                 code == 0 and was is not None and got == want, text)
    return ok


def verify_fresh_install(zp, base, name):
    """Install the zip as MO2 does and run the packaged tools against it.

    The mod goes in under MO2's default name, the archive's, so nothing may depend on the
    folder being called "Seasons of the Zone". Then the packaged installer puts _tools,
    play.bat and configure.bat in the GAMMA folder, as configure.bat does for players."""
    import tempfile
    sb = os.path.join(tempfile.gettempdir(), "sotz_fresh_install")
    shutil.rmtree(sb, ignore_errors=True)
    game = os.path.join(sb, "ANOMALY")
    root = os.path.join(sb, "GAMMA")
    mod = os.path.join(root, "mods", name)
    os.makedirs(os.path.join(game, "appdata"))
    os.makedirs(os.path.join(root, "profiles", "Default"))
    os.makedirs(os.path.join(root, "downloads"))
    os.makedirs(os.path.join(root, "mods", "Some Other Mod"))
    io.open(os.path.join(root, "ModOrganizer.ini"), "w", encoding="utf-8").write(
        "[General]" + chr(10)
        + "gamePath=@ByteArray(" + game.replace(chr(92), chr(92) * 2) + ")" + chr(10)
        + "selected_profile=@ByteArray(Default)" + chr(10)
        + "[customExecutables]" + chr(10) + "size=%d" % len(ENTRIES) + chr(10)
        + "".join("%d%stitle=%s%s" % (i, chr(92), t, chr(10))
                  for i, t in enumerate(ENTRIES, 1)))
    modlist = os.path.join(root, "profiles", "Default", "modlist.txt")
    header = "# This file was automatically generated by Mod Organizer." + CRLF
    io.open(modlist, "w", encoding="utf-8", newline="").write(
        header + "+" + name + CRLF + "+Some Other Mod" + CRLF)

    with zipfile.ZipFile(zp) as z:
        for n in z.namelist():
            if n.startswith(base) and not n.endswith("/"):
                t = os.path.join(mod, *n[len(base):].split("/"))
                os.makedirs(os.path.dirname(t), exist_ok=True)
                with z.open(n) as src, open(t, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    if not verify_installer(root, mod):
        shutil.rmtree(sb, ignore_errors=True)
        return False

    def run(args, offline=False):
        # offline: nothing a check starts goes out to open-meteo
        r = subprocess.run([sys.executable] + args, capture_output=True, text=True,
                           cwd=os.path.join(root, "_tools") if args[0] == "-c" else root,
                           env=dict(os.environ, SEASONS_OFFLINE="1") if offline else None)
        return r.returncode, r.stdout + r.stderr

    season = os.path.join(root, "_tools", "season.py")
    ok = True
    for args in (["status"], ["apply", "--dry-run"], ["apply"]):
        code, text = run([season] + args)
        ok &= report("season.py " + " ".join(args),
                     code == 0 and "Traceback" not in text and "not in mods/" not in text,
                     text)
    staged = io.open(os.path.join(mod, "gamedata", "configs", "season_staged.ltx"),
                     encoding="cp1251").read()
    ok &= report("apply wrote season_staged.ltx",
                 "season = unknown" not in staged and "stamped = never" not in staged)
    ml = io.open(modlist, encoding="utf-8", newline="").read()
    ok &= report("modlist.txt intact",
                 ml.startswith(header) and ("+" + name + CRLF) in ml)

    code, text = run(["-c", FETCH_PROBE])
    wx = os.path.join(mod, "gamedata", "configs", "season_weather.ltx")
    other = os.path.join(root, "mods", "Some Other Mod", "gamedata")
    ok &= report("fetch_weather writes into the mod",
                 code == 0 and os.path.isfile(wx) and not os.path.exists(other)
                 and "freezing     = true" in io.open(wx, encoding="utf-8").read(), text)

    # A season change with a soundscape configured. apply restages the presets and then
    # switches the seasonal mods; from 1.4.0 until 1.7.0 it raised a TypeError between
    # the two, which an install with no SOUND_SRC never reaches.
    amb = os.path.join(root, "mods", "Some Ambience Mod", "gamedata", *SOUND_REL)
    os.makedirs(amb)
    io.open(os.path.join(amb, "test.ltx"), "w", encoding="cp1251", newline="").write(
        "[test]" + CRLF + "sound_channels_dynamic = birds, Insects_night, wind" + CRLF)
    io.open(modlist, "a", encoding="utf-8", newline="").write("+Some Ambience Mod" + CRLF)
    cfg = os.path.join(root, "_tools", "seasons_config.py")
    io.open(cfg, "w", encoding="utf-8").write('SOUND_SRC = "Some Ambience Mod"\n')
    preset = os.path.join(root, "mods", "Seasonal Soundscape", "gamedata", *SOUND_REL,
                          "test.ltx")
    for s in ("spring", "winter", "late_winter"):
        code, text = run([season, "apply", "--season", s])
        body = io.open(preset, encoding="cp1251").read() if os.path.isfile(preset) else ""
        head, _, rest = body.partition("\n")
        ok &= report("season change to %s, with a soundscape" % s,
                     code == 0 and "Traceback" not in text and ("season=" + s) in head
                     and "wind" in rest and "Insects_night" not in rest, text)
    os.remove(cfg)

    # The configure tool, as the window uses it: a mod put on the calendar has to give
    # a file season.py accepts. Nothing shares the ambience mod's files, so this also
    # takes the stay-where-it-is anchor.
    configure = os.path.join(root, "_tools", "configure.py")
    code, text = run([configure, "add", "some ambience mod", "--when", "winter"])
    wrote = os.path.isfile(cfg) and "Some Ambience Mod" in io.open(
        cfg, encoding="utf-8").read()
    ok &= report("configure.py add", code == 0 and wrote and "Traceback" not in text, text)
    code, text = run([season, "status"])
    ok &= report("season.py accepts what it wrote",
                 code == 0 and "needs fixing" not in text, text)
    code, text = run([configure, "list"])
    ok &= report("configure.py list", code == 0 and "Some Ambience Mod" in text, text)

    # A calendar of the player's own: two seasons, one moved. apply hands it to the game
    # and draws a dial for it when Pillow is here; back on Polesia's, the stub returns.
    calendar = os.path.join(mod, "gamedata", "configs", "season_calendar.ltx")
    code, text = run([configure, "calendar", "summer=5-1", "winter_snow=11-15",
                      "--only"])
    code2, text2 = run([season, "apply"])
    body = io.open(calendar, encoding="cp1251").read()
    try:
        import PIL                                      # noqa: F401
        drawn = "dial = custom" in body and len([
            f for f in os.listdir(os.path.join(mod, "gamedata", "textures"))
            if f.startswith(CUSTOM_DIAL)]) == 32
    except ImportError:
        drawn = "dial = none" in body
    ok &= report("a calendar of your own reaches the game",
                 code == 0 and code2 == 0 and "custom = true" in body
                 and "summer = 5, 1" in body and "winter_snow = 11, 15" in body
                 and "spring =" not in body and drawn, text + text2 + body)
    code, text = run([configure, "calendar", "--reset"])
    code2, text2 = run([season, "apply"])
    body = io.open(calendar, encoding="cp1251", newline="").read()
    ok &= report("and Polesia's comes back",
                 code == 0 and code2 == 0 and body == STUB_CALENDAR and not [
                     f for f in os.listdir(os.path.join(mod, "gamedata", "textures"))
                     if f.startswith(CUSTOM_DIAL)], text + text2 + body)
    # The presets that come with the tool, a name of the player's own, and an event that
    # repeats: each through the command the window's buttons stand for, then season.py.
    code, text = run([configure, "preset"])
    ok &= report("presets listed", code == 0 and "Two seasons" in text
                 and "GAMMA example" in text, text)
    code, text = run([configure, "preset", "load", "Two seasons"])
    code2, text2 = run([season, "status"])
    ok &= report("a shipped preset loads", code == 0 and code2 == 0
                 and "your own: summer May 1, deep winter Nov 15" in text2, text + text2)
    code, text = run([configure, "name", "deep winter", "The Long Cold"])
    body = io.open(calendar, encoding="cp1251").read()
    ok &= report("a season named", code == 0 and "name_winter_snow = The Long Cold" in body,
                 text + body)
    code, text = run([configure, "event", "weekend", "--weekdays", "weekends"])
    code2, text2 = run([season, "status"])
    ok &= report("an event that repeats", code == 0 and code2 == 0
                 and "needs fixing" not in text2, text + text2)
    code, text = run([configure, "preset", "save", "Mine"])
    ok &= report("a preset saved", code == 0 and os.path.isfile(
        os.path.join(root, "_tools", "presets", "Mine.json")), text)
    # where the real weather comes from, as the setup's Weather step sets it
    code, text = run([configure, "place", "--at", "50.45", "30.52", "--name", "Kyiv"],
                     offline=True)
    code2, text2 = run([season, "status"])
    ok &= report("a weather place set", code == 0 and code2 == 0
                 and "weather from    Kyiv (50.45 N, 30.52 E)" in text2, text + text2)
    code, text = run([configure, "place", "--reset"], offline=True)
    ok &= report("and Chornobyl again", code == 0, text)
    for f in (cfg, cfg + ".bak"):
        if os.path.isfile(f):
            os.remove(f)

    # A second copy under the old name, lower in the list: season.py says so and keeps
    # using the copy MO2 loads.
    copytree(os.path.join(mod, "gamedata"), os.path.join(root, "mods", MOD, "gamedata"))
    io.open(modlist, "a", encoding="utf-8", newline="").write("+" + MOD + CRLF)
    code, text = run([season, "status"])
    ok &= report("two copies reported",
                 code == 0 and "installed 2 times" in text and ("Using '%s'" % name) in text,
                 text)

    shutil.rmtree(sb, ignore_errors=True)
    return ok


def write_presets(td):
    """The presets marked as shipped, and one made from this install's config. A preset
    saved on this install stays here: it names this install's mods and dates."""
    sys.path.insert(0, TOOLS)
    import config_edit as ce
    out = os.path.join(td, "presets")
    os.makedirs(out)
    n = 0
    for name, path in ce.preset_files().items():
        p, problems = ce.read_preset(path)
        if p and p["shipped"]:
            if problems:
                raise SystemExit("  refusing to package: preset %s can't be used: %s"
                                 % (name, problems))
            shutil.copy2(path, os.path.join(out, name + ".json"))
            n += 1
    cal = ce.Calendar(os.path.join(TOOLS, "seasons_config.py"))
    if cal.error or cal.problems:
        raise SystemExit("  refusing to package: this install's config can't make the GAMMA "
                         "example: %s" % (cal.error or cal.problems))
    # the parts with something in them: an empty one would empty that part of the setup
    # of whoever loads it
    data = ce.preset_from(cal, [p for p in ce.parts_with_content(cal) if p != "calendar"])
    data["shipped"] = True
    data["about"] = ("The setup these tools were made on: GAMMA's seasonal texture sets, "
                     "each on the calendar, and the ambience mod the soundscape comes from. "
                     "Mods you don't have are left out when it loads.")
    io.open(os.path.join(out, "GAMMA example.json"), "w", encoding="utf-8",
            newline="\n").write(ce.preset_json(data) + "\n")
    p, problems = ce.read_preset(os.path.join(out, "GAMMA example.json"))
    if problems:
        raise SystemExit("  refusing to package: the GAMMA example can't be used: %s"
                         % problems)
    return n


EXAMPLE_DOC = '''"""A worked example: the setup these tools were made on, each table filled in.

Your own settings go in seasons_config.py, next to this file. configure.bat makes that
file and edits it for you - its window, its commands and its presets - and you can edit
it by hand as well: the tool keeps what you write and rewrites only the entries it
changes. This file is only here to read. The same setup loads into configure.bat as the
"GAMMA example" preset.

With every table empty, the seasonal atmosphere still runs; the tables add what play.bat
changes at launch, using mods you install yourself. The full reference is
docs/CONFIGURING.md.

  TOGGLE_MODS    seasonal mods: each is enabled in the seasons it lists and disabled the
                 rest of the year. Nothing is copied. `above` is the mod it wins over,
                 which configure.bat finds from the files the two share; to check one,
                 `season.py whowins <file> --for "<your mod>"`.
  LAYOUT         texture sets: mods restaged from their archive each season, for mods
                 that ship one folder per season. Gigabytes move; prefer TOGGLE_MODS.
  SOUND_SRC      the ambience mod whose sound channels are cut back by season. It has to
                 be the mod that wins those files.
  PERIODS        base periods of your own, alongside the seasons: name: (month, day) it
                 starts. Each runs until the next one begins.
  EVENTS         windows laid over whatever period they land in, so an event keeps the
                 season under it: name: ((m, d) start, (m, d) end), both inclusive, and a
                 start after its end wraps the year. Or a rule, like
                 {"weekdays": ("sat", "sun")}. See docs/SCHEDULING.md.
  CALENDAR       the day each season starts, and which are on; None is Polesia's six.
  NAMES          names of your own for the seasons; None keeps the usual ones.
"""
'''


def write_example(src, dst):
    """This install's config as the worked example. Its tables are shipped as they are;
    its docstring is replaced, since the one in the file may be older than the tools."""
    sys.path.insert(0, TOOLS)
    import season
    text = season.read_config_text(src)
    tree = ast.parse(text)
    lines = text.split("\n")
    first = tree.body[0] if tree.body else None
    if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)):
        lines = lines[first.end_lineno:]
    body = "\n".join(lines).lstrip("\n")
    io.open(dst, "w", encoding="utf-8", newline="\n").write(EXAMPLE_DOC + "\n" + body)
    theirs, ours = {}, {}
    exec(compile(text, src, "exec"), theirs)
    exec(compile(io.open(dst, encoding="utf-8").read(), dst, "exec"), ours)
    for var in season.CONFIG_NAMES:
        if theirs.get(var) != ours.get(var):
            raise SystemExit("  refusing to package: the worked example's %s differs from "
                             "this install's" % var)


def copytree(src, dst):
    n = 0
    for root, _, files in os.walk(src):
        for f in files:
            p = os.path.join(root, f)
            rel = os.path.relpath(p, src)
            t = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(t), exist_ok=True)
            shutil.copy2(p, t)
            n += 1
    return n


def check_savedgames_repair(moddir):
    """Listing $app_data_root$ costs the engine its registry for the savedgames folder
    underneath it, and CALifeUpdateManager::load then fatals with "Cannot find the
    specified saved game" on a save that is plainly on disk. MCM calls on_mcm_load at
    startup, so it happens on every load, not only when the menu is opened. Every appdata
    listing must be followed by a $game_saves$ listing that puts the registry back.

    This shipped unguarded once and every save load crashed."""
    listed = 0
    for root, _, files in os.walk(moddir):
        for f in sorted(files):
            if not f.lower().endswith(".script"):
                continue
            p = os.path.join(root, f)
            lines = io.open(p, encoding="latin-1", newline="").read().splitlines()
            for i, line in enumerate(lines):
                if 'file_list_open_ex("$app_data_root$"' not in line:
                    continue
                listed += 1
                if 'file_list_open_ex("$game_saves$"' not in "\n".join(lines[i:i + 40]):
                    raise SystemExit(
                        "  refusing to package: %s lists $app_data_root$ at line %d and\n"
                        "  never re-lists $game_saves$. Saves would stop loading."
                        % (os.path.basename(p), i + 1))
    print("  savedgames guard       %3d appdata listing(s), each repaired" % listed)


def main():
    selftest_mo2_base()
    refuse_test_rigs()
    check_version(os.path.join(TOOLS, "season.py"), os.path.join(OUT, "CHANGELOG.md"))
    verify_engine_only()

    shutil.rmtree(STAGE, ignore_errors=True)
    os.makedirs(STAGE)

    # gamedata/ at the top of the zip's one folder, so MO2 installs it like any mod.
    # Only gamedata/ is taken: the mod folder's meta.ini is MO2's.
    n = copytree(os.path.join(ROOT, "mods", MOD, "gamedata"), os.path.join(STAGE, "gamedata"))
    print("  mod                    %3d files" % n)
    wx = os.path.join(STAGE, "gamedata", "configs", "season_weather.ltx")
    if os.path.isfile(wx):
        os.remove(wx)       # this machine's fetched day; without it the game models one
    neutralise_generated(STAGE)
    check_savedgames_repair(os.path.join(STAGE, "gamedata"))

    td = os.path.join(STAGE, "_tools")
    os.makedirs(td)
    for f in TOOL_FILES:
        shutil.copy2(os.path.join(TOOLS, f), os.path.join(td, f))
    check_messages()
    os.makedirs(os.path.join(td, "lang"))
    words = [f for f in sorted(os.listdir(os.path.join(TOOLS, "lang")))
             if f.endswith(LANG_FILES)]
    for f in words:
        shutil.copy2(os.path.join(TOOLS, "lang", f), os.path.join(td, "lang", f))
    print("  translations           %3d files" % len(words))
    # No seasons_config.py: the installer never copies one, but a _tools/ copied by hand
    # over a player's own, as before the installer, would wipe their tables. season.py
    # runs without it.
    live = os.path.join(TOOLS, "seasons_config.py")
    if os.path.isfile(live):
        write_example(live, os.path.join(td, "seasons_config.example.py"))
    print("  tools                  %3d files  (+ worked example)" % len(TOOL_FILES))
    print("  presets                %3d shipped (+ GAMMA example)" % write_presets(td))

    write_crlf(os.path.join(ROOT, "play.bat"), os.path.join(STAGE, "play.bat"))
    write_crlf(os.path.join(ROOT, "configure.bat"), os.path.join(STAGE, "configure.bat"))
    check_play_bat(STAGE)
    shutil.copy2(os.path.join(OUT, "README.md"), os.path.join(STAGE, "README.md"))
    for extra in ("CHANGELOG.md", "LICENSE"):
        p = os.path.join(OUT, extra)
        if os.path.isfile(p):
            shutil.copy2(p, os.path.join(STAGE, extra))

    nd = copytree(os.path.join(OUT, "docs"), os.path.join(STAGE, "docs"))
    readme = os.path.join(STAGE, "README.md")
    text = io.open(readme, encoding="utf-8", newline="").read()
    for rel in WEB_ONLY:
        p = os.path.join(STAGE, *rel.split("/"))
        if os.path.isfile(p):
            os.remove(p)
            nd -= 1
        text = text.replace("(%s)" % rel, "(%s%s)" % (WEB_BASE, rel))
    io.open(readme, "w", encoding="utf-8", newline="").write(text)
    print("  docs                   %3d files  (%d linked from GitHub instead)"
          % (nd, len(WEB_ONLY)))
    check_doc_images(STAGE)

    np = copytree(os.path.join(OUT, "patches"), os.path.join(STAGE, "patches"))
    print("  patches                %3d files" % np)

    # INVERNO's script must never ship, in any form.
    for root, _, files in os.walk(STAGE):
        for f in files:
            if f.lower() == "yawm_snowfall.script":
                raise SystemExit("  refusing to package %s"
                                 % os.path.join(root, f))

    # Built beside the real name and kept only when every check passes.
    zp = os.path.join(OUT, ZIP_NAME)
    tmp = zp + ".building"
    if os.path.isfile(tmp):
        os.remove(tmp)
    total = 0
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for root, _, files in os.walk(STAGE):
            for f in files:
                p = os.path.join(root, f)
                z.write(p, os.path.join(MOD, os.path.relpath(p, STAGE)))
                total += 1

    names = zipfile.ZipFile(tmp).namelist()
    base = mo2_base(names)
    if base is None:
        os.remove(tmp)
        raise SystemExit("  refusing to package: MO2 would call this archive invalid")
    print("  MO2 install            from '%s'" % (base or "/"))
    check_contents(names, base)
    if not verify_fresh_install(tmp, base, os.path.splitext(ZIP_NAME)[0]):
        os.remove(tmp)
        raise SystemExit("  refusing to package: the tooling fails on a fresh install")
    os.replace(tmp, zp)

    print()
    print("  %-38s %4d files  %6.1f MB" % (os.path.basename(zp), total,
                                           os.path.getsize(zp) / 1048576.0))


if __name__ == "__main__":
    main()
