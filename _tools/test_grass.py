"""Grass by the season: play.bat sets the game's grass density in user.ltx before the game
starts, to the share of the player's own grass the season's MCM page asks for. The share
comes out in the engine's steps, never denser than the player's; a change made in the
game's options becomes the player's value; MCM's switch gives it back; the rest of user.ltx
is left byte for byte.

  python _tools/test_grass.py
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402

CASES = []
CRLF = "\r\n"
MCM_SCRIPT = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone", "gamedata",
                          "scripts", "zzz_seasons_of_the_zone_mcm.script")
# user.ltx as the engine writes it: a preset line, settings, the binds at the end
USER = CRLF.join([
    "_preset Default",
    "ai_aim_fire_angle 0.3927",
    "r__detail_density 0.25",
    "r__detail_height 0.5",
    "r__detail_radius 160",
    "r__dtex_range 50.",
    "bind left kLEFT",
    ""])


def case(fn):
    CASES.append(fn)
    return fn


def game(d):
    """A game folder inside the scratch install, named in ModOrganizer.ini, with user.ltx
    in its appdata; the file's path."""
    g = os.path.join(d, "ANOMALY")
    io.open(os.path.join(d, "ModOrganizer.ini"), "a", encoding="utf-8").write(
        "gamePath=@ByteArray(%s)\r\n" % g.replace("\\", "\\\\"))
    p = os.path.join(g, "appdata", "user.ltx")
    os.makedirs(os.path.dirname(p))
    open(p, "wb").write(USER.encode("latin-1"))
    return p


def mcm(d, *lines):
    """MCM's file in the scratch install's overwrite/, holding these [mcm] lines."""
    p = os.path.join(d, "overwrite", "gamedata", "configs", "axr_options.ltx")
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").write(CRLF.join(["[mcm]"] + ["        " + l for l in lines] + [""])
                        .encode("cp1251"))


def scratch(d):
    tc.install(d, config="")
    tc.with_mod(d)
    return game(d)


def row(out):
    return [l for l in out.splitlines() if l.startswith("  grass")]


@case
def t_the_grid_is_counted_as_the_engine_counts_it():
    """Each 2 m slot holds (ceil(2 / density) + 1) squared places: 2 / 0.4 is five rows
    exactly, and 0.6 needs a fourth row where 0.67 fits in three."""
    got = [season.grass_points(v) for v in (0.25, 0.5, 0.34, 0.4, 1.0, 0.6, 0.67)]
    assert got == [81, 25, 49, 36, 9, 25, 16], got
    return "81, 25, 49, 36, 9, 25 and 16 places"


@case
def t_a_share_picks_the_nearest_step_and_never_more_grass():
    """Of the 0.01 steps from the player's value up, the one whose grid comes nearest the
    share; the lowest of a tie; never a value under the player's."""
    got = [season.grass_density(0.25, s) for s in (100, 80, 60, 40, 20)]
    assert got == [(0.25, 100), (0.29, 79), (0.34, 60), (0.4, 44), (0.67, 20)], got
    assert season.grass_density(0.5, 40) == (1.0, 36), season.grass_density(0.5, 40)
    # the first step above the player's can be the one
    assert season.grass_density(0.33, 80) == (0.34, 77), season.grass_density(0.33, 80)
    for own in (0.04, 0.1, 0.25, 0.33, 0.6, 1.0):
        for share in range(20, 101, 10):
            v, got_share = season.grass_density(own, share)
            assert own - 1e-9 <= v <= 1.0 and got_share <= 100, (own, share, v)
    return "79, 60, 44 and 20 percent for GAMMA's 0.25; never denser"


@case
def t_the_pages_and_the_switch_are_read_from_mcm():
    """seasons_zone/main/stage_grass and seasons_zone/<season>/grass; a share out of range
    is held to 20-100, and one that isn't a number keeps the page's default."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d)
        mcm(d, "seasons_zone/main/stage_grass        = false",
            "seasons_zone/winter/grass              = 30",
            "seasons_zone/winter_snow/grass         = 5",
            "seasons_zone/spring/grass              = 150",
            "seasons_zone/late_winter/grass         = lots")
        # imported from the scratch install's _tools, so its ROOT is the scratch install
        r = subprocess.run([sys.executable, "-c",
                            "import sys; sys.path.insert(0, r'%s'); import season; "
                            "p = season.read_prefs(); print('PREFS', p['grass'], "
                            "sorted(p['grass_share'].items()))" % os.path.join(d, "_tools")],
                           capture_output=True, text=True, cwd=d)
        out = r.stdout + r.stderr
    want = ("PREFS False [('autumn', 100), ('late_winter', 60), ('spring', 100), "
            "('summer', 100), ('winter', 30), ('winter_snow', 20)]")
    assert want in out, out
    return "switch off, 30 kept, 5 held to 20, 150 to 100, a word ignored"


@case
def t_play_bat_sets_the_grass_and_leaves_the_rest_of_user_ltx_be():
    """status says what the grass will be and changes nothing; apply sets the one line,
    keeps the file first, and remembers what it wrote; the next apply has nothing to do."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        rc, out = tc.run(d, "status", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and row(out) == [
            "  grass           about 44% of yours, r__detail_density 0.4 (yours: 0.25)   "
            "(now 0.25)"], out
        assert "the grass needs setting" in out and open(p, "rb").read() == USER.encode(), out
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "0.25 -> 0.4" in out and "grass set" in out, out
        assert open(p, "rb").read() == USER.replace("density 0.25", "density 0.4").encode(), \
            open(p, "rb").read()
        kept = os.listdir(os.path.join(d, "_baseline", "modfile-backups"))
        assert [k for k in kept if k.startswith("user-") and k.endswith("-pre-grass.ltx")], kept
        st = json.load(open(os.path.join(d, "_baseline", "season-grass.json")))
        assert st == {"own": 0.25, "wrote": 0.4}, st
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "already on" in out and "->" not in out, out
        rc, out = tc.run(d, "apply", "--season", "summer", tool="season.py")
        assert rc == 0 and "0.4 -> 0.25" in out, out
        assert open(p, "rb").read() == USER.encode()
    return "said, one line set, kept first, remembered, idle next time, all back in summer"


@case
def t_a_share_set_on_a_season_page_is_the_one_used():
    """The page's own share, saved by MCM, wins over its default."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        mcm(d, "seasons_zone/winter_snow/grass         = 20")
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "0.25 -> 0.67" in out and row(out) == [
            "  grass           about 20% of yours, r__detail_density 0.67 (yours: 0.25)   "
            "(now 0.25)"], out
        assert open(p, "rb").read() == USER.replace("density 0.25", "density 0.67").encode()
    return "deep winter at 20: 0.67"


@case
def t_a_launch_that_restages_textures_sets_the_grass_too():
    """The launch that copies a texture set takes the other road through apply; the grass
    goes with it and is named in what was staged."""
    import test_hardening as th
    layout = ('{"Base Grass": {"archive": "grass.7z", "options": {"summer": ["Summer"], '
              '"winter": ["Winter"]}}}')
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=th.cfg(LAYOUT=layout))
        tc.with_mod(d)
        th.with_archive(d)
        p = game(d)
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        assert rc == 0 and "0.25 -> 0.34" in out and "Winter staged (textures, grass)" in out, \
            out
        assert open(p, "rb").read() == USER.replace("density 0.25", "density 0.34").encode()
    return "textures and grass staged together"


@case
def t_a_change_made_in_the_game_becomes_the_players_own():
    """A value play.bat didn't write is the player's: the next launch thins from it."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        assert rc == 0 and "0.25 -> 0.34" in out, out
        # the player moves the options slider to 0.2, which the game saves as it closes
        open(p, "wb").write(USER.replace("density 0.25", "density 0.2").encode())
        rc, out = tc.run(d, "status", "--season", "winter", tool="season.py")
        assert row(out) == ["  grass           about 67% of yours, r__detail_density 0.25 "
                            "(yours: 0.2)   (now 0.2)"], out
        rc, out = tc.run(d, "apply", "--season", "summer", tool="season.py")
        assert rc == 0 and row(out) == ["  grass           all of yours, r__detail_density "
                                        "0.2"] and "->" not in out, out
    return "the slider's 0.2 is theirs; winter thins from it, summer keeps it"


@case
def t_the_switch_gives_the_grass_back_and_then_leaves_it():
    """With MCM's switch off, a launch sets the player's own value back once; after that
    the line is theirs, and play.bat writes nothing."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "0.25 -> 0.4" in out, out
        mcm(d, "seasons_zone/main/stage_grass        = false")
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "0.4 -> 0.25" in out and row(out) == [
            "  grass           as you set it, r__detail_density 0.25 (off in MCM)   "
            "(now 0.4)"], out
        assert open(p, "rb").read() == USER.encode()
        open(p, "wb").write(USER.replace("density 0.25", "density 0.3").encode())
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "->" not in out, out
        assert open(p, "rb").read() == USER.replace("density 0.25", "density 0.3").encode()
    return "set back once, then left as the player sets it"


@case
def t_the_game_running_holds_the_grass_for_the_next_launch():
    """With the game open, it would save its own user.ltx over the change as it closes:
    apply leaves the file be, says so, and remembers nothing."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        drive = os.path.join(d, "busy.py")
        io.open(drive, "w", encoding="utf-8").write(
            "import sys\nsys.path.insert(0, sys.argv[1])\nimport season\n"
            "season.running = lambda: ['anomalydx11avx.exe']\n"
            "sys.argv = ['season.py', 'apply', '--season', 'winter_snow']\nseason.main()\n")
        r = subprocess.run([sys.executable, "-B", drive, os.path.join(d, "_tools")], cwd=d,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        assert r.returncode == 0 and "The grass waits for the next launch: anomalydx11avx.exe " \
            "is running" in out and open(p, "rb").read() == USER.encode(), out
        assert not os.path.exists(os.path.join(d, "_baseline", "season-grass.json"))
    return "the file left as it was, and why"


@case
def t_switched_off_from_the_start_it_never_writes():
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        mcm(d, "seasons_zone/main/stage_grass        = false")
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "->" not in out and open(p, "rb").read() == USER.encode(), out
        assert not os.path.exists(os.path.join(d, "_baseline", "season-grass.json"))
    return "no write, nothing remembered"


@case
def t_no_user_ltx_is_said_and_none_is_made():
    """The game makes user.ltx the first time it closes; until then there is nothing to
    set, and play.bat makes no file of its own."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        os.remove(p)
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and row(out) == [
            "  grass           as you set it: there is no user.ltx with r__detail_density "
            "in it yet"], out
        assert not os.path.exists(p)
    return "said, and no file made"


@case
def t_the_copy_the_game_reads_is_the_one_set():
    """By MO2's rules: one in overwrite/ hides the game's own."""
    with tempfile.TemporaryDirectory() as d:
        p = scratch(d)
        ow = os.path.join(d, "overwrite", "appdata", "user.ltx")
        os.makedirs(os.path.dirname(ow))
        open(ow, "wb").write(USER.replace("\r\n", "\n").encode())
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and open(p, "rb").read() == USER.encode(), out
        assert open(ow, "rb").read() == USER.replace("\r\n", "\n").replace(
            "density 0.25", "density 0.4").encode(), open(ow, "rb").read()
    return "overwrite/'s copy set, with its own line endings"


@case
def t_a_period_with_no_page_keeps_all_of_it():
    """Only the six seasons have pages; anything else staged keeps all the grass."""
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "user.ltx")
        open(p, "wb").write(USER.encode())
        prefs = {"grass": True, "grass_share": dict(season.GRASS_SHARE)}
        old = season.GRASS_STATE
        season.GRASS_STATE = os.path.join(d, "season-grass.json")
        try:
            plan = season.grass_plan(prefs, "mud_week", path=p)
            deep = season.grass_plan(prefs, "winter_snow", path=p)
        finally:
            season.GRASS_STATE = old
    assert (plan["share"], plan["want"], deep["share"], deep["want"]) == (100, 0.25, 40, 0.4), \
        (plan, deep)
    return "a period of one's own: 100; deep winter: 40"


@case
def t_the_pages_defaults_are_the_tools():
    """MCM's season pages and season.py hold the same defaults, and the slider's floor is
    the tool's: a page MCM hasn't saved yet reads as its default in both."""
    src = io.open(MCM_SCRIPT, encoding="utf-8").read()
    m = re.search(r"local GRASS_SHARE = \{(.*?)\}", src, re.S)
    page = {k: int(v) for k, v in re.findall(r"(\w+) = (\d+)", m.group(1))}
    assert page == season.GRASS_SHARE, page
    slider = re.search(r'add\(\{id = "grass", type = "track", val = 2, min = (\d+), '
                       r'max = (\d+)', src)
    assert slider and (int(slider.group(1)), int(slider.group(2))) == (season.GRASS_LOWEST,
                                                                       100), slider
    assert re.search(r'add\(\{id = "stage_grass", type = "check", val = 1, def = true\}\)', src)
    return "six defaults, 20 to 100, the switch on by default"


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
