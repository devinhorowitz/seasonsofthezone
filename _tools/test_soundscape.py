"""The seasons must not sound alike.

season.py gates the soundscape by cutting channels per season. A season missing from
SOUND_CUT cuts nothing and sounds like summer, two seasons with the same cuts sound the
same, and a cut spelled differently from the presets removes nothing. None of that shows
anywhere but in the game, so this runs season.py's own line editor over preset lines
written the way the soundscape mods write them.

  python _tools/test_soundscape.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import season  # noqa: E402

# As the soundscape mods write them: channel case varies between files, some lines end in
# ';' and some do not.
PRESETS = [
    "    sound_channels_dynamic  = wind_normal, Insects, birds_night, wind_heavy, out_drone;",
    "    sound_channels_dynamic  = wind_normal, Insects, Insects_night, birds, birds_swamp;",
    "    sound_channels_dynamic  = insects, birds, birds_swamp, birds_night, wind_normal",
    "    sound_channels_dynamic  = Insects_night, birds_night, out_night_amb;",
]


def standing(season_key, cut_table=None):
    """What each preset line keeps in that season."""
    cut = set((cut_table or season.SOUND_CUT).get(season_key, ()))
    return tuple(season._strip_channels(line, cut) for line in PRESETS)


def clashes(cut_table=None):
    seen = {}
    for s in season.SEASONS:
        seen.setdefault(standing(s, cut_table), []).append(s)
    return [v for v in seen.values() if len(v) > 1]


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_every_season_has_its_own_entry():
    missing = [s for s in season.SEASONS if s not in season.SOUND_CUT]
    assert not missing, "no SOUND_CUT entry for %s, so it sounds like summer" % missing
    extra = [s for s in season.SOUND_CUT if s not in season.SEASONS]
    assert not extra, "SOUND_CUT names %s, which is not a season" % extra
    return "%d seasons, %d entries" % (len(season.SEASONS), len(season.SOUND_CUT))


@case
def t_no_two_seasons_sound_alike():
    c = clashes()
    assert not c, "these sound identical: %s" % c
    return "%d seasons leave %d different soundscapes" % (
        len(season.SEASONS), len(set(standing(s) for s in season.SEASONS)))


@case
def t_every_cut_removes_something():
    """A cut that matches no channel in any preset is a typo, and does nothing."""
    names = set()
    for line in PRESETS:
        names |= {c.strip() for c in line.split("=", 1)[1].rstrip("; ").split(",")}
    for s, cut in season.SOUND_CUT.items():
        dead = [c for c in cut if c not in names]
        assert not dead, "%s cuts %s, which no preset carries" % (s, dead)
    full = standing("summer")
    assert full == tuple(PRESETS), "summer changed a line, and it should cut nothing"
    return "every cut matches a channel, and summer keeps every line as it is"


@case
def t_the_lines_keep_their_shape():
    got = season._strip_channels(PRESETS[1], {"Insects", "insects", "Insects_night"})
    want = "    sound_channels_dynamic  = wind_normal, birds, birds_swamp;"
    assert got == want, repr(got)
    return "spacing and the trailing ';' survive a cut"


@case
def t_the_distinctness_check_can_fail():
    table = dict(season.SOUND_CUT)
    table["late_winter"] = table["winter"]
    assert clashes(table), "a duplicate cut list was not caught"
    return "late winter given winter's cuts is caught"


@case
def t_each_season_has_its_own_signature():
    """The generated files carry this, so a SOUND_CUT edit rebuilds them."""
    sigs = {season._sound_signature(s) for s in season.SEASONS}
    assert len(sigs) == len(season.SEASONS), "two seasons share a signature"
    return "%d signatures, all different" % len(sigs)


if __name__ == "__main__":
    print("  checking the seasonal soundscape cuts")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-36s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-36s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-36s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
