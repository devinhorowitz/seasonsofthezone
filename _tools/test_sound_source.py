"""Run the SHIPPED season.py and configure.py against scratch installs where another
soundscape pack sits above SOUND_SRC.

The generated soundscape is placed directly above SOUND_SRC, so a pack installed over the
source wins those files back and the seasons never reach them, without a word anywhere.
That is ROMEO's setup out of the box: Dark Signal Amplified's soundscape above GAMMA's Dark
Signal. status has to name the pack and the command that fixes it, and `configure.py sound`
has to show the choices, switch, and refuse a mod that cannot be one.

  python _tools/test_sound_source.py
"""
import io
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


# --- the generated soundscape itself -----------------------------------------------------

REL = ("gamedata", "configs", "environment", "ambients", "presets")
# the source alone, then the mod: the generated soundscape is made from nothing else
ALONE = [("Old Ambience", True, []),
         ("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"])]


def presets(root, files, mod="Old Ambience"):
    """The ambient presets `files`, {name: bytes}, in `mod`."""
    d = os.path.join(root, "mods", mod, *REL)
    os.makedirs(d, exist_ok=True)
    for f, data in files.items():
        open(os.path.join(d, f), "wb").write(data)


def soundscape(root):
    """The generated soundscape's line in MO2's list, and its files: {name: bytes}."""
    ml = io.open(os.path.join(root, "profiles", "Default", "modlist.txt"),
                 encoding="utf-8").read().splitlines()
    gen = os.path.join(root, "mods", "Seasonal Soundscape", *REL)
    files = ({f: open(os.path.join(gen, f), "rb").read() for f in os.listdir(gen)}
             if os.path.isdir(gen) else None)
    return [l for l in ml if l[1:] == "Seasonal Soundscape"], files


@case
def t_the_soundscape_turned_off_goes_off():
    """configure.py sound --off sets SOUND_SRC to None, and the last season's soundscape
    stayed on all year, its cuts and all, while the report said "none set up" and nothing
    to do. Now the next launch takes its files out and turns it off in MO2's list."""
    with tempfile.TemporaryDirectory() as d:
        setup(d, mods=ALONE)
        presets(d, {"environment_field.ltx": b"[a]\r\nsound_channels_dynamic = wind, Insects, "
                                             b"birds\r\n"})
        rc, out = tc.run(d, "apply", "--season", "winter_snow", tool="season.py")
        line, files = soundscape(d)
        assert rc == 0 and line == ["+Seasonal Soundscape"] and files, (line, out)
        rc, out = tc.run(d, "sound", "--off")
        assert rc == 0 and sound_src(d) is None, out
        rc, out = tc.run(d, "status", "--season", "summer", tool="season.py")
        assert rc == 0 and "off (no ambient sound mod is set)" in out, out
        rc, out = tc.run(d, "apply", "--season", "summer", tool="season.py")
        line, files = soundscape(d)
        assert rc == 0 and line == ["-Seasonal Soundscape"] and files is None, (line, files, out)
        rc, out = tc.run(d, "apply", "--season", "summer", tool="season.py")
        assert rc == 0 and "already on summer, nothing to do" in out, out
    return "deep winter's set out and off in MO2 the launch after --off, then nothing to do"


# A comment saved as UTF-8: "И" is D0 98 there, and ‘ is E2 80 98; cp1251 has no 0x98
UTF8 = "; Источник: DSA ‘Night’".encode("utf-8")
SOURCE = {"a_field.ltx": b"[a]\r\nsound_channels_dynamic = wind, Insects, birds\r\n",
          "b_swamp.ltx": b"[b]\r\n" + UTF8 + b"\r\nsound_channels_dynamic = Insects, "
                         b"birds_swamp, wind\r\n",
          "c_forest.ltx": b"[c]\r\nsound_channels_dynamic = Insects_night, birds_night;\r\n"}
# what winter keeps of each: no insects, no swamp birds, every other byte as it was
WINTER = {"a_field.ltx": b"[a]\r\nsound_channels_dynamic = wind, birds\r\n",
          "b_swamp.ltx": b"[b]\r\n" + UTF8 + b"\r\nsound_channels_dynamic = wind\r\n",
          "c_forest.ltx": b"[c]\r\nsound_channels_dynamic = birds_night;\r\n"}


@case
def t_a_source_saved_as_utf8_is_copied_byte_for_byte():
    """A preset saved as UTF-8 holds bytes cp1251 has no letter for. Read as cp1251, one
    became a letter it can't write, and the run stopped with the file it was writing left
    empty, in an enabled mod, the rest not written and the last season's gone. Each file
    is now its source with the channels cut, byte for byte; what a run that stopped part
    way left beside the set is cleared."""
    with tempfile.TemporaryDirectory() as d:
        setup(d, mods=ALONE)
        presets(d, SOURCE)
        gen = os.path.join(d, "mods", "Seasonal Soundscape", *REL)
        os.makedirs(gen + ".building")
        open(os.path.join(gen + ".building", "environment_old.ltx"), "wb").write(b"x")
        for season, want in (("winter", WINTER), ("summer", SOURCE)):
            rc, out = tc.run(d, "apply", "--season", season, tool="season.py")
            assert rc == 0 and "VERIFIED" in out, out
            line, files = soundscape(d)
            assert sorted(files or ()) == sorted(SOURCE), (season, sorted(files or ()))
            for f, data in files.items():
                first, rest = data.split(b"\r\n", 1)
                assert first.startswith(b";; seasonal-soundscape season=%s cuts="
                                        % season.encode()), (season, f, first)
                assert rest == want[f], (season, f, rest, want[f])
            left = [p for p in (gen + ".building", gen + ".previous") if os.path.exists(p)]
            assert not left, "left beside the set: %s" % left
    return "winter's cuts and summer's none, the UTF-8 comment kept; a leftover cleared"


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
