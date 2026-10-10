"""Run the SHIPPED season.py and configure.py against scratch installs where another
soundscape pack sits above SOUND_SRC.

The generated soundscape is placed directly above SOUND_SRC, so a pack installed over the
source wins those files back and the seasons never reach them, without a word anywhere.
That is ROMEO's setup out of the box: Dark Signal Amplified's soundscape above GAMMA's Dark
Signal. status has to name the pack and the command that fixes it, and `configure.py sound`
has to show the choices, switch, and refuse a mod that cannot be one.

  python _tools/test_sound_source.py
"""
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import test_configure as tc                                     # noqa: E402

P = "configs/environment/ambients/presets/"

# highest priority first, as modlist.txt lists them
MODS = [
    ("Seasonal Soundscape", True, [P + "environment_field.ltx"]),
    ("Pack On Top", True, [P + "environment_field.ltx", P + "environment_forest.ltx",
                           P + "environment_new.ltx"]),
    ("Off Pack", False, [P + "environment_swamp.ltx"]),
    ("Old Ambience", True, [P + "environment_field.ltx", P + "environment_forest.ltx",
                            P + "environment_swamp.ltx"]),
    ("Lonely Mod", True, ["scripts/lonely.script"]),
    ("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"]),
]
SHADOW = '"Pack On Top" is above "Old Ambience" and wins 2 of its 3 ambient sound files'


def setup(root, src="Old Ambience", mods=MODS):
    tc.install(root, config="SOUND_SRC = %r\n" % src, mods=mods)
    tc.with_mod(root)


def sound_src(root):
    ns = {}
    exec(tc.config(root), ns)
    return ns.get("SOUND_SRC")


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_status_names_the_pack_above_the_source():
    with tempfile.TemporaryDirectory() as d:
        setup(d)
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc == 0, out
        assert SHADOW in out, out
        assert 'configure.py sound "Pack On Top"' in out, out
        assert 'pick it in configure.bat under "Texture sets and ambient sound"' in out, out
        assert "Off Pack" not in out and '"Seasonal Soundscape" is above' not in out, out
    return "the pack, 2 of 3 files, and the command; not the disabled pack or the generated one"


@case
def t_status_is_quiet_with_the_source_on_top():
    with tempfile.TemporaryDirectory() as d:
        setup(d, src="Pack On Top")
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc == 0, out
        assert "is above" not in out, out
    return "nothing said once the pack on top is the source"


@case
def t_the_command_shows_the_choices():
    with tempfile.TemporaryDirectory() as d:
        setup(d)
        rc, out = tc.run(d, "sound")
        assert rc == 0, out
        assert 'taken from "Old Ambience"' in out and SHADOW in out, out
        listed = [l.split()[0] for l in out.splitlines() if l.startswith("    ")]
        assert listed == ["Pack", "Old"], out              # highest first; names start so
        assert "Off Pack" not in out and "Lonely Mod" not in out, out
    return "the source, what hides it, and the two enabled mods with ambient files"


@case
def t_the_command_switches_and_turns_off():
    with tempfile.TemporaryDirectory() as d:
        setup(d)
        rc, out = tc.run(d, "sound", "Pack On Top")
        assert rc == 0 and sound_src(d) == "Pack On Top", out
        tc.accepted(d)
        rc, out = tc.run(d, "status", tool="season.py")
        assert "is above" not in out, out
        rc, out = tc.run(d, "sound", "--off")
        assert rc == 0 and sound_src(d) is None, out
        tc.accepted(d)
    return "SOUND_SRC written, season.py accepts it, and --off writes None"


@case
def t_the_command_refuses_what_cannot_be_a_source():
    with tempfile.TemporaryDirectory() as d:
        setup(d)
        before = tc.config(d)
        rc, out = tc.run(d, "sound", "No Such Mod")
        assert rc != 0 and "No mod named" in out, out
        rc, out = tc.run(d, "sound", "Lonely Mod")
        assert rc != 0 and "not an enabled mod with ambient sound files" in out, out
        assert "Pack On Top" in out and "Old Ambience" in out, out
        rc, out = tc.run(d, "sound", "Off Pack")
        assert rc != 0 and "not an enabled mod with ambient sound files" in out, out
        rc, out = tc.run(d, "sound", "Old Ambience", "--off")
        assert rc != 0, out
        assert tc.config(d) == before, "a refused change was written"
    return "an unknown mod, one with no ambient files, a disabled one, and both at once"


@case
def t_two_packs_above_split_what_they_win():
    """The higher pack takes a file both ship; the lower is named for the rest only."""
    mods = [("Top Pack", True, [P + "environment_field.ltx"])] + MODS
    with tempfile.TemporaryDirectory() as d:
        setup(d, mods=mods)
        rc, out = tc.run(d, "status", tool="season.py")
        assert '"Top Pack" is above "Old Ambience" and wins 1 of its 3' in out, out
        assert '"Pack On Top" is above "Old Ambience" and wins 1 of its 3' in out, out
    return "1 file each, not the shared file twice"


@case
def t_a_pack_below_the_source_is_not_named():
    """The check reads MO2's order: the same pack under the source hides nothing."""
    mods = [m for m in MODS if m[0] != "Pack On Top"]
    mods.insert(mods.index([m for m in mods if m[0] == "Old Ambience"][0]) + 1, MODS[1])
    with tempfile.TemporaryDirectory() as d:
        setup(d, mods=mods)
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc == 0 and "is above" not in out, out
    return "moved below the source, the pack goes unmentioned"


if __name__ == "__main__":
    print("  running the shipped tools against an ambient sound pack above the source")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-46s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-46s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-46s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
