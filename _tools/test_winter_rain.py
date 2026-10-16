"""No Rain in Winter (winter_rain.py): copies of the weathers that rain, with no rain, made from
whichever copy wins in MO2, and told apart from their sources once those change.

Each case builds a small GAMMA folder in a scratch directory: mods/, MO2's overwrite/, and
weather files with rain_density lines the way Atmospherics writes them.

  python _tools/test_winter_rain.py
"""
import hashlib
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import winter_rain as wr  # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def weather(rain, nl="\r\n", extra=()):
    """A small weather file: two hours, the given rain_density at each, a commented line and
    an inline comment, the way Atmospherics lays them out."""
    lines = ["[00:00:00]",
             "        ambient                          = ambient_rain",
             "        rain_density                     = %s" % rain[0],
             ";       rain_density                     = 0.9",
             "        rain_color                       = 0.3, 0.3, 0.3",
             "",
             "[12:00:00]",
             "        rain_density                     = %s ; heaviest at noon" % rain[1],
             "        fog_density                      = 0.4"] + list(extra)
    return nl.join(lines) + nl


def tree(d, layout, overwrite=None):
    """mods/<mod>/gamedata/configs/environment/weathers/<file> = text, and overwrite's."""
    mods = os.path.join(d, "mods")
    for mod, files in layout.items():
        w = os.path.join(mods, mod, *wr.WEATHERS)
        os.makedirs(w, exist_ok=True)
        for f, text in files.items():
            with open(os.path.join(w, f), "wb") as fh:
                fh.write(text.encode("latin-1"))
    if overwrite:
        w = os.path.join(d, wr.OVERWRITE, *wr.WEATHERS)
        os.makedirs(w, exist_ok=True)
        for f, text in overwrite.items():
            with open(os.path.join(w, f), "wb") as fh:
                fh.write(text.encode("latin-1"))
    return mods


def copy_of(mods, f):
    return open(os.path.join(mods, wr.MOD, *wr.WEATHERS, f), "rb").read()


def sha(text):
    return hashlib.sha256(text.encode("latin-1")).hexdigest()


LAYOUT = {
    "Weather Expansion": {"w_rain5.ltx": weather(("0.66", "1")),
                          "w_clear4.ltx": weather(("0", "0.0"))},
    "Atmospherics": {"w_rain1.ltx": weather(("0.8", "0.5"), nl="\n"),
                     "w_storm1.ltx": weather(("1", "0.9"))},
    "GAMMA Weathers": {"w_rain1.ltx": weather(("0.2", "0.2"))},
    "Disabled pack": {"w_rain2.ltx": weather(("0.7", "0.7"))},
}
ORDER = [("Disabled pack", False), ("Weather Expansion", True), ("Atmospherics", True),
         ("GAMMA Weathers", True)]


@case
def t_the_winning_rainy_weathers_are_copied_dry():
    with tempfile.TemporaryDirectory() as d:
        mods = tree(d, LAYOUT)
        sources, lines = wr.build(mods, ORDER)
        assert sources == {"Atmospherics": ["w_rain1.ltx", "w_storm1.ltx"],
                           "Weather Expansion": ["w_rain5.ltx"]}, sources
        assert lines == 6, "turned off %d rain lines, not 6" % lines
        for f, mod in (("w_rain1.ltx", "Atmospherics"), ("w_rain5.ltx", "Weather Expansion"),
                       ("w_storm1.ltx", "Atmospherics")):
            src = LAYOUT[mod][f]
            nl = "\r\n" if "\r\n" in src else "\n"
            got = copy_of(mods, f).decode("latin-1")
            first, body = got.split(nl, 1)
            assert first == wr.head_line(mod, sha(src)), "%s: first line %r" % (f, first)
            want = (src.replace("= 0.8\n", "= 0\n").replace("= 0.66\r\n", "= 0\r\n")
                    .replace("= 1\r\n", "= 0\r\n").replace("= 0.5 ;", "= 0 ;")
                    .replace("= 1 ;", "= 0 ;").replace("= 0.9 ;", "= 0 ;"))
            assert body == want, "%s: the copy differs beyond its rain\n%r\n%r" % (f, body, want)
            assert ";       rain_density                     = 0.9" in body, "a comment changed"
            assert body.count("\r\n") == src.count("\r\n"), "%s: line endings changed" % f
        names = sorted(os.listdir(os.path.join(mods, wr.MOD, *wr.WEATHERS)))
        assert names == ["w_rain1.ltx", "w_rain5.ltx", "w_storm1.ltx"], (
            "a dry weather, a losing copy or a disabled mod's was copied: %s" % names)
        assert os.path.isfile(os.path.join(mods, wr.MOD, "meta.ini")), "no meta.ini"
    return "3 rainy winners copied, 6 rain lines to 0, every other byte and line end kept"


@case
def t_a_changed_source_is_seen_and_made_again():
    with tempfile.TemporaryDirectory() as d:
        mods = tree(d, LAYOUT)
        wr.build(mods, ORDER)
        assert wr.stale(mods, ORDER) == ([], [], []), "a fresh build reads as stale"
        newer = weather(("0.3", "0.3"), nl="\n")
        tree(d, {"Atmospherics": {"w_rain1.ltx": newer}})
        assert wr.stale(mods, ORDER) == ([], ["w_rain1.ltx"], []), wr.stale(mods, ORDER)
        wr.build(mods, ORDER)
        assert wr.stale(mods, ORDER) == ([], [], []), "a rebuild left it stale"
        assert sha(newer) in copy_of(mods, "w_rain1.ltx").decode("latin-1"), "old copy kept"

        order = [(n, on and n != "Weather Expansion") for n, on in ORDER]
        assert wr.stale(mods, order) == ([], [], ["w_rain5.ltx"]), wr.stale(mods, order)
        wr.build(mods, order)
        left = sorted(os.listdir(os.path.join(mods, wr.MOD, *wr.WEATHERS)))
        assert left == ["w_rain1.ltx", "w_storm1.ltx"], "a copy whose mod is off stayed: %s" % left

        tree(d, {"Atmospherics": {"w_rain3.ltx": weather(("0.5", "0.5"))}})
        assert wr.stale(mods, order) == (["w_rain3.ltx"], [], []), wr.stale(mods, order)
    return "a changed source, a mod switched off and a new weather each read as stale; rebuilt"


@case
def t_a_second_build_writes_nothing():
    with tempfile.TemporaryDirectory() as d:
        mods = tree(d, LAYOUT)
        wr.build(mods, ORDER)
        folder = os.path.join(mods, wr.MOD)
        stamps = {}
        for r, _, fs in os.walk(folder):
            for f in fs:
                p = os.path.join(r, f)
                stamps[p] = os.stat(p).st_mtime_ns
        meta = os.path.join(folder, "meta.ini")
        os.utime(meta, ns=(10 ** 9, 10 ** 9))       # an old stamp a rewrite would replace
        stamps[meta] = os.stat(meta).st_mtime_ns
        wr.build(mods, ORDER)
        moved = [p for p, t in stamps.items() if os.stat(p).st_mtime_ns != t]
        assert not moved, "rewritten though unchanged: %s" % moved
    return "%d files left alone" % len(stamps)


@case
def t_files_that_are_not_ours_stay():
    with tempfile.TemporaryDirectory() as d:
        mods = tree(d, LAYOUT)
        wr.build(mods, ORDER)
        mine = os.path.join(mods, wr.MOD, *wr.WEATHERS, "w_custom.ltx")
        with open(mine, "wb") as fh:
            fh.write(weather(("0.4", "0.4")).encode("latin-1"))
        wr.build(mods, [(n, on and n != "Weather Expansion") for n, on in ORDER])
        assert os.path.isfile(mine), "a file without our first line was removed"
        assert "w_custom.ltx" not in wr.made(mods), "a file without our first line counts as ours"
    return "a hand-made file in the folder is never touched"


@case
def t_overwrite_wins_and_the_mod_is_never_its_own_source():
    with tempfile.TemporaryDirectory() as d:
        ow = weather(("0.25", "0.25"))
        mods = tree(d, LAYOUT, overwrite={"w_rain1.ltx": ow})
        order = [(wr.MOD, True)] + ORDER
        first = wr.build(mods, order)
        assert wr.made(mods)["w_rain1.ltx"][:2] == (wr.OVERWRITE, sha(ow)), wr.made(mods)
        # built again with the mod enabled at the top of MO2's list: its own dry copies would
        # win, rain nowhere, and the weathers they were made from would drop out
        again = wr.build(mods, order)
        assert again == first, "the second build read the mod's own copies: %s" % (again,)
        assert sorted(wr.made(mods)) == ["w_rain1.ltx", "w_rain5.ltx", "w_storm1.ltx"], (
            "the mod's own copies counted as sources: %s" % sorted(wr.made(mods)))
        assert wr.anchor(mods, order, ["w_rain1.ltx", "w_rain5.ltx"]) == "Weather Expansion"
        assert wr.anchor(mods, order, ["w_storm1.ltx"]) == "Atmospherics"
        assert wr.anchor(mods, order, ["w_rain2.ltx"]) is None, "a disabled mod was picked"
        assert wr.anchor(mods, order, ["w_nothing.ltx"]) is None
    return "MO2's overwrite folder first, the mod itself never; it wins over the top source"


@case
def t_rain_lines_are_read_as_numbers():
    for text, want in (("rain_density = 0", False), ("rain_density = 0.0", False),
                       ("  rain_density=0.001", True), ("\train_density = 1 ; storm", True),
                       ("; rain_density = 0.9", False), ("rain_density_x = 0.9", False),
                       ("rain_density = ", False)):
        assert wr.rains(text) is want, "%r read as %s" % (text, not want)
    body, n = wr.dry("a = 1\nrain_density = 0.7 ; wet\nrain_density = 0\n")
    assert (body, n) == ("a = 1\nrain_density = 0 ; wet\nrain_density = 0\n", 1), (body, n)
    return "zero, blank, commented and longer keys don't rain; one line changed"


# --- configure.py rain and play.bat, run as shipped against a scratch install -------------

RAIN_MODS = [("Weather Expansion", True, {"w_rain5.ltx": weather(("0.66", "1")),
                                          "w_clear4.ltx": weather(("0", "0"))}),
             ("Atmospherics", True, {"w_rain1.ltx": weather(("0.8", "0.5")),
                                     "w_storm1.ltx": weather(("1", "0.9"))})]


def sandbox(d, mods=RAIN_MODS):
    """A scratch GAMMA folder: the weather mods [(name, enabled, {file: text})], highest
    priority first, then Seasons of the Zone. Returns test_configure, which runs the tools."""
    import test_configure as tc
    tc.install(d, mods=[(n, on, []) for n, on, _ in mods]
               + [("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"])])
    tc.with_mod(d)
    tree(d, {n: files for n, _, files in mods})
    return tc


def modlist(d):
    return io.open(os.path.join(d, "profiles", "Default", "modlist.txt"),
                   encoding="utf-8").read().splitlines()


def above_of(d):
    """The mod the rain mod sits just above in MO2's list, and whether it is enabled."""
    lines = modlist(d)
    i = [l[1:] for l in lines].index(wr.MOD)
    return lines[i + 1][1:], lines[i][:1] == "+"


@case
def t_configure_builds_it_and_play_bat_switches_it():
    with tempfile.TemporaryDirectory() as d:
        tc = sandbox(d)
        rc, out = tc.run(d, "rain")
        assert rc == 0 and "rain --build" in out, out
        assert "Atmospherics" in out and "2 weathers" in out, "no count by mod:\n" + out
        rc, out = tc.run(d, "rain", "--build")
        assert rc == 0 and "3 weathers" in out, out
        cfg = tc.table(d)[0].get(wr.MOD)
        assert cfg == {"when": ("winter", "winter_snow"), "above": "Weather Expansion"}, cfg
        mods = os.path.join(d, "mods")
        assert sorted(wr.made(mods)) == ["w_rain1.ltx", "w_rain5.ltx", "w_storm1.ltx"]
        rc, out = tc.run(d, "rain", "--build")
        assert rc == 0 and "Nothing changed" not in out, "a second build said nothing:\n" + out
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0, out
        assert above_of(d) == ("Weather Expansion", True), (above_of(d), modlist(d))
        rc, out = tc.run(d, "apply", "--season", "summer", tool="season.py")
        assert rc == 0 and above_of(d) == ("Weather Expansion", False), out
    return "built, on the calendar, on above its anchor in deep winter and off in summer"


@case
def t_play_bat_makes_it_again_and_follows_a_new_weather_mod():
    with tempfile.TemporaryDirectory() as d:
        tc = sandbox(d)
        tc.run(d, "rain", "--build")
        tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        mods = os.path.join(d, "mods")
        newer = weather(("0.4", "0.4"))
        tree(d, {"Atmospherics": {"w_rain1.ltx": newer}})
        rc, out = tc.run(d, "status", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "out of date: 1 weather changed" in out, out
        assert wr.made(mods)["w_rain1.ltx"][1] != sha(newer), "status wrote the mod"
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "made again: 1 weather changed" in out, out
        assert wr.made(mods)["w_rain1.ltx"][1] == sha(newer), "apply left the old copy"

        # a new pack on top of the list, with a rainy weather of its own: the mod takes it
        # in and moves above it, or the pack's rain wins
        p = os.path.join(d, "profiles", "Default", "modlist.txt")
        lines = modlist(d)
        lines.insert(1, "+Rain Pack")
        io.open(p, "w", encoding="utf-8", newline="").write("\r\n".join(lines) + "\r\n")
        tree(d, {"Rain Pack": {"w_rain9.ltx": weather(("0.5", "0.5"))}})
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and 'wins over "Rain Pack" for this launch' in out, out
        assert "rain --build" in out, "no word on keeping it:\n" + out
        assert above_of(d) == ("Rain Pack", True), modlist(d)
        assert "w_rain9.ltx" in wr.made(mods), sorted(wr.made(mods))
        rc, out = tc.run(d, "rain", "--build")
        assert rc == 0 and tc.table(d)[0][wr.MOD]["above"] == "Rain Pack", out
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and "for this launch" not in out and "made again" not in out, out
    return "a changed weather: status says so, apply makes it again; a new pack on top: " \
        "taken in and won over"


@case
def t_rain_off_takes_it_off_and_disables_it():
    with tempfile.TemporaryDirectory() as d:
        tc = sandbox(d)
        rc, out = tc.run(d, "rain", "--off")
        assert rc == 1 and "not set up" in out, out
        tc.run(d, "rain", "--build")
        tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert above_of(d)[1], "not on in deep winter"
        rc, out = tc.run(d, "rain", "--off")
        assert rc == 0 and "disabled in MO2" in out, out
        assert wr.MOD not in tc.table(d)[0], tc.table(d)[0]
        assert not above_of(d)[1], "still enabled: %s" % modlist(d)
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        assert rc == 0 and not above_of(d)[1], "apply switched it back on:\n" + out
    return "off the calendar and disabled, and play.bat leaves it off"


@case
def t_nothing_to_build_from_is_refused():
    with tempfile.TemporaryDirectory() as d:
        tc = sandbox(d, [("Dry Pack", True, {"w_clear1.ltx": weather(("0", "0"))})])
        rc, out = tc.run(d, "rain", "--build")
        assert rc == 1 and "no rain to take out" in out, out
        assert not os.path.isdir(os.path.join(d, "mods", wr.MOD)), "built an empty mod"
        assert tc.config(d) is None or wr.MOD not in tc.table(d)[0], "put on the calendar"
        tree(d, {}, overwrite={"w_rain1.ltx": weather(("0.5", "0.5"))})
        rc, out = tc.run(d, "rain", "--build")
        assert rc == 1 and "overwrite folder" in out, out
        rc, out = tc.run(d, "rain")
        assert rc == 0 and "overwrite folder wins over every mod" in out, out
    return "no rainy weather, or only MO2's overwrite folder's: refused, nothing written"


if __name__ == "__main__":
    print("  No Rain in Winter, in a scratch GAMMA folder")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-48s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-48s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-48s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
