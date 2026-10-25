"""Modded Exes and the shader cache: the game keeps the shaders it builds, and exes older than
2026.6.21 don't notice when a shader's #include files change, so the shaders built with the
last season's headers stay. play.bat names the exes the game last ran on, from its log, and
with older ones sets the cache aside when the seasonal mods' shader files change; newer exes
rebuild the shaders themselves, so the cache is left alone.

  python _tools/test_exes_floor.py
"""
import io
import os
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402

CASES = []
CRLF = "\r\n"
HEADER = "shaders/r3/settings_screenspace_TERRAIN.h"
MODS = [
    ("Winter Pack", False, ["textures/terrain/t.dds", HEADER]),
    ("Base Terrain", True, ["textures/terrain/t.dds"]),
    ("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"]),
]
CONFIG = 'TOGGLE_MODS = {\n    "Winter Pack": {"when": ("winter",), "above": "Base Terrain"},\n}\n'


def case(fn):
    CASES.append(fn)
    return fn


def scratch(d, exes):
    """An install whose game folder last ran on `exes` ("2026.06.13"; None: never ran), with
    a shader cache that holds one file."""
    tc.install(d, config=CONFIG, mods=MODS)
    tc.with_mod(d)
    g = os.path.join(d, "ANOMALY")
    io.open(os.path.join(d, "ModOrganizer.ini"), "a", encoding="utf-8").write(
        "gamePath=@ByteArray(%s)\r\n" % g.replace("\\", "\\\\"))
    os.makedirs(os.path.join(g, "appdata", "logs"))
    if exes:
        log(d, "xray_player.log", exes)
    cache = os.path.join(g, "appdata", "shaders_cache", "r4")
    os.makedirs(cache)
    io.open(os.path.join(cache, "shader.bin"), "w").write("built")
    return cache


def log(d, name, exes):
    """A game log as the engine starts it, naming the exes."""
    io.open(os.path.join(d, "ANOMALY", "appdata", "logs", name), "w", newline="").write(CRLF.join([
        "'xrCore' build 10087, Sep 20 2026", "", "Modded Exes version %s" % exes, "",
        "Game started: 25.10.2026 12:47:01.041", ""]))


def row(out):
    return [l for l in out.splitlines() if l.startswith("  Modded Exes")]


@case
def t_the_version_is_read_from_the_newest_log_that_names_it():
    """The newest xray log with the line wins; a log without one is passed over; no logs, no
    version."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, None)
        logs = os.path.join(d, "ANOMALY", "appdata", "logs")
        old = season.APPDATA
        season.APPDATA = os.path.join(d, "ANOMALY", "appdata")
        try:
            none = season.exes_version()
            log(d, "xray_a.log", "2026.06.13")
            io.open(os.path.join(logs, "xray_b.log"), "w").write("no version here\n")
            os.utime(os.path.join(logs, "xray_a.log"), (time.time() - 100, time.time() - 100))
            got = season.exes_version()
            log(d, "xray_c.log", "2026.09.20")
            newest = season.exes_version()
        finally:
            season.APPDATA = old
    assert none is None and got == (2026, 6, 13) and newest == (2026, 9, 20), (none, got, newest)
    assert season.exes_words(got) == "2026.6.13" and got < season.EXES_FLOOR < newest
    return "none, 2026.6.13 past a log without the line, then 2026.9.20"


@case
def t_older_exes_get_the_cache_set_aside_when_the_seasonal_shaders_change():
    """Winter turns on a mod with a terrain header: the launch sets the cache aside; the next
    launch, with nothing changed, leaves the cache the game built again; spring turns the mod
    off, a change again."""
    with tempfile.TemporaryDirectory() as d:
        cache = scratch(d, "2026.06.13")
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        assert rc == 0 and not os.path.isdir(cache) and os.path.isfile(
            os.path.join(cache + ".stale", "shader.bin")), out
        assert row(out) == ["  Modded Exes     2026.6.13"], row(out)
        assert "2026.6.21 and later rebuild them" in out, out
        assert "the game's shader cache is set aside" in out, out
        os.makedirs(cache)                              # the game builds it again
        io.open(os.path.join(cache, "shader.bin"), "w").write("rebuilt")
        rc, out2 = tc.run(d, "apply", "--season", "winter", tool="season.py")
        assert rc == 0 and os.path.isdir(cache) and "set aside" not in out2, out2
        rc, out3 = tc.run(d, "apply", "--season", "spring", tool="season.py")
        assert rc == 0 and not os.path.isdir(cache) and io.open(
            os.path.join(cache + ".stale", "shader.bin")).read() == "rebuilt", out3
    return "set aside in winter, kept on the second launch, set aside again in spring"


@case
def t_newer_exes_rebuild_the_shaders_themselves():
    """2026.9.20: the same switch leaves the cache alone, and the report says only the
    version."""
    with tempfile.TemporaryDirectory() as d:
        cache = scratch(d, "2026.09.20")
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        assert rc == 0 and os.path.isfile(os.path.join(cache, "shader.bin")), out
        assert not os.path.exists(cache + ".stale"), out
        assert row(out) == ["  Modded Exes     2026.9.20"], row(out)
        assert "rebuild them" not in out and "set aside" not in out, out
    return "cache kept, one line: 2026.9.20"


@case
def t_a_dry_run_and_an_unknown_version_change_nothing():
    """status on older exes warns and moves nothing; before the game's first run there is no
    log, so no row and nothing moved."""
    with tempfile.TemporaryDirectory() as d:
        cache = scratch(d, "2026.06.13")
        rc, out = tc.run(d, "status", "--season", "winter", tool="season.py")
        assert rc == 0 and os.path.isdir(cache) and "2026.6.21 and later rebuild them" in out, out
    with tempfile.TemporaryDirectory() as d:
        cache = scratch(d, None)
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        assert rc == 0 and os.path.isdir(cache) and row(out) == [], out
    return "status warns only; no log, no row"


if __name__ == "__main__":
    failed = 0
    for fn in CASES:
        name = fn.__name__[2:]
        try:
            print("  PASS  %-58s %s" % (name, fn()))
        except AssertionError as e:
            failed += 1
            print("  FAIL  %-58s %s" % (name, str(e)[:1500]))
    print("%d/%d passed" % (len(CASES) - failed, len(CASES)))
    sys.exit(1 if failed else 0)
