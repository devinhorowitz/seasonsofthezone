"""KEEP_ORDER: play.bat keeps MO2's load order as the player left it.

A player asked for it on 2026-10-24: play.bat kept moving a mod they had made seasonal to
just below the mod it was set to win over, where it didn't work for them. With KEEP_ORDER
on, play.bat only switches mods on and off. A mod MO2 doesn't list yet still goes in, and
one that is on and loses to the mod it is set to win over is named, with the fix. These
cases run the shipped tools on scratch installs.

  python _tools/test_keep_order.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import test_configure as tc                                     # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# highest priority first, as modlist.txt lists them: Winter Pack loses to X Base
MODS = [
    ("X Base", True, ["textures/t/a.dds"]),
    ("Winter Pack", False, ["textures/t/a.dds"]),
    ("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"]),
]
TOGGLE = 'TOGGLE_MODS = {\n    "Winter Pack": {"when": ("winter",), "above": "X Base"},\n}\n'
KEEP = TOGGLE + "KEEP_ORDER = True\n"
SAID = ('Winter Pack sits above "X Base" in MO2\'s left pane, the mod it is set to win over, '
        'so where both have a file, that one\'s is used. Your load order is kept as it is.')
FIX = 'Move it below "X Base" in MO2, or pick another in its "Wins over" box in configure.bat.'
LOSES = 'Winter Pack loses 1 file to "X Base"'


def body(root):
    return [l.strip() for l in io.open(os.path.join(root, "profiles", "Default",
                                                    "modlist.txt"), encoding="utf-8")][1:]


def run(root, *args, tool="season.py"):
    return tc.run(root, *args, tool=tool)


def flat(out):
    """The output with the wrapped lines joined, as one line of words."""
    return " ".join(out.split())


# --- the cases -----------------------------------------------------------------------------

@case
def t_kept_it_only_switches_and_says_what_loses():
    """Winter Pack sits below X Base's priority, the mod it is set to win over. Kept, apply
    turns it on in winter where it is, names it with the fix, and status and the file check
    say the same; in autumn it goes off where it is, and nothing is said of a mod that's off."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=KEEP, mods=MODS)
        rc, out = run(d, "status", "--season", "winter")
        f = flat(out)
        assert rc == 0 and SAID in f and FIX in f and LOSES in f, out
        assert body(d) == ["+X Base", "-Winter Pack", "+Seasons of the Zone"], "status wrote"

        rc, out = run(d, "apply", "--season", "winter")
        f = flat(out)
        assert rc == 0 and SAID in f and FIX in f and "moved" not in out, out
        assert body(d) == ["+X Base", "+Winter Pack", "+Seasons of the Zone"], (body(d), out)
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and SAID in flat(out) and "moved" not in out, "the next launch: " + out

        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and SAID not in flat(out), "said for a mod that is off: " + out
        assert body(d) == ["+X Base", "-Winter Pack", "+Seasons of the Zone"], (body(d), out)
    return "on and off where it stands, named while on, in apply and status alike"


@case
def t_without_it_the_mod_still_moves():
    """No KEEP_ORDER, or KEEP_ORDER = False: as before, apply puts Winter Pack just above X
    Base in modlist.txt, says so, and names nothing."""
    for config in (TOGGLE, TOGGLE + "KEEP_ORDER = False\n"):
        with tempfile.TemporaryDirectory() as d:
            tc.install(d, config=config, mods=MODS)
            rc, out = run(d, "status", "--season", "winter")
            assert rc == 0 and LOSES not in flat(out), "a mod about to move was said to lose"
            rc, out = run(d, "apply", "--season", "winter")
            f = flat(out)
            assert rc == 0 and "moved, enabled" in out and SAID not in f, (config, out)
            assert body(d) == ["+Winter Pack", "+X Base", "+Seasons of the Zone"], body(d)
    return "moved, enabled, both ways of leaving it off"


@case
def t_a_mod_mo2_does_not_list_yet_still_goes_in():
    """Kept, a seasonal mod whose folder MO2 hasn't listed yet still goes in once, just
    above the mod it wins over, as MO2 has to list it to load it; the next launch leaves it."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=KEEP, mods=[m for m in MODS if m[0] != "Winter Pack"])
        p = os.path.join(d, "mods", "Winter Pack", "gamedata", "textures", "t", "a.dds")
        os.makedirs(os.path.dirname(p))
        io.open(p, "w").write("Winter Pack")
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "added, enabled" in out and SAID not in flat(out), out
        assert body(d) == ["+Winter Pack", "+X Base", "+Seasons of the Zone"], body(d)
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "added" not in out and "moved" not in out, out
    return "added once where it wins, then left"


@case
def t_the_setting_is_checked_and_set_by_command():
    """KEEP_ORDER is True or False, or season.py refuses the config. configure.py order says
    which way it is, `order keep` writes it with its note, and `order move` turns it off."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=TOGGLE + 'KEEP_ORDER = "yes"\n', mods=MODS)
        rc, out = run(d, "status", "--season", "winter")
        assert rc != 0 and "KEEP_ORDER must be True or False." in flat(out), out
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=TOGGLE, mods=MODS)
        rc, out = run(d, "order", tool="configure.py")
        assert rc == 0 and "moves one there when it isn't" in flat(out), out
        rc, out = run(d, "order", "keep", tool="configure.py")
        assert rc == 0 and "keeps MO2's load order as it is from the next launch" in flat(out), out
        text = tc.config(d)
        assert "KEEP_ORDER = True" in text and "# Whether play.bat keeps MO2's load order" in text
        rc, out = run(d, "order", tool="configure.py")
        assert rc == 0 and "only turns mods on and off" in flat(out), out
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and SAID in flat(out), out
        assert body(d) == ["+X Base", "+Winter Pack", "+Seasons of the Zone"], body(d)

        rc, out = run(d, "order", "move", tool="configure.py")
        assert rc == 0 and "KEEP_ORDER = False" in tc.config(d), tc.config(d)
        rc, out = run(d, "order", "move", tool="configure.py")
        assert rc == 0 and "Nothing changed" in out, out
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "moved" in out, out
        assert body(d) == ["+Winter Pack", "+X Base", "+Seasons of the Zone"], body(d)
    return "a string refused; order, order keep, order move, and play.bat follows each"


@case
def t_the_window_sees_the_order_kept():
    """The window says who wins a file by MO2's list as play.bat leaves it: kept, as it is."""
    import config_edit as ce

    class Listed(object):
        lines = [("X Base", True, False), ("Winter Pack", True, False)]
    toggle = {"Winter Pack": {"above": "X Base"}}
    assert ce.placed(Listed, toggle) == {"Winter Pack": 0, "X Base": 1}
    got = ce.placed(Listed, toggle, keep=True)
    assert got == {"X Base": 0, "Winter Pack": 1}, got
    return "moved without it, as it is with it"


@case
def t_the_mods_seasons_makes_stay_put_too():
    """The soundscape and Seasonal LUT are placed by the same step as the seasonal mods:
    kept, one below its source stays there and is named, not moved."""
    import season
    try:
        for keep, want in ((True, ["+Sound Src", "+Seasonal Soundscape"]),
                           (None, ["+Seasonal Soundscape", "+Sound Src"])):
            season.KEEP_ORDER = keep
            del season.UNPLACED[:]
            lines = ["+Sound Src", "-Seasonal Soundscape"]
            got = season._place(lines, "Seasonal Soundscape", "Sound Src", "+")
            assert lines == want, (keep, lines)
            assert got == (("-", "+") if keep else ("misplaced", "+")), (keep, got)
            assert season.UNPLACED == ([("Seasonal Soundscape", "Sound Src")] if keep else []), \
                season.UNPLACED
    finally:
        season.KEEP_ORDER = None
        del season.UNPLACED[:]
    return "switched on where it stands and named; moved without it"


def main():
    bad = 0
    for fn in CASES:
        try:
            said = fn()
            print("  PASS  %-56s %s" % (fn.__name__[2:], said))
        except Exception as e:
            bad += 1
            print("  FAIL  %-56s %s" % (fn.__name__[2:], (str(e) if isinstance(e, AssertionError)
                                                          else repr(e))[:900]))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
