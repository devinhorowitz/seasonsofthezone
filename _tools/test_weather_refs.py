"""A launch whose weathers name a sun, a thunderbolt collection or an ambient that no config
has is stopped before the game crashes on it.

The game loads every weather as it starts, before the main menu, and fails on a name its
suns.ltx, thunderbolt_collections.ltx or ambients.ltx lacks: "Can't open section". A player
hit it on 2026-10-24: Weather Expansion for Atmospherics was off, while the copies No Rain in
Winter had made of its weathers still named its sun, cloudy_dark_special. These cases build
that install and the places a name can come from, and run the shipped tools on them.

  python _tools/test_weather_refs.py
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


NO_RAIN = "No Rain in Winter (seasonal)"
EXPANSION = "Weather Expansion"
ATMOS = "Atmospherics"
# highest priority first, as modlist.txt lists them
MODS = [
    (NO_RAIN, False, []),
    (EXPANSION, False, []),
    (ATMOS, True, []),
    ("Seasons of the Zone", True, []),
]
CONFIG = ('TOGGLE_MODS = {\n    "%s": {"when": ("winter",), "above": "%s"},\n}\n'
          % (NO_RAIN, ATMOS))
SAID = ('! w_rain6.ltx, in "%s", names the sun "cloudy_dark_special", which no config in '
        'this launch has. The game stops on it as it starts ("Can\'t open section").' % NO_RAIN)
HOLDER = '"%s", off in MO2, has it: turn it on, or take out the weathers that name it.' % EXPANSION
REMAKE = '"%s" made its copies from the weathers that won then.' % NO_RAIN
STOP = "Stopped before the launch: the game would stop as it starts."


def weather(sun, ambient="amb_day", thunder="tb_day"):
    """A weather of two hours, laid out as Atmospherics writes them."""
    hours = []
    for t in ("00:00:00", "12:00:00"):
        hours += ["[%s]" % t,
                  "        ambient                          = %s" % ambient,
                  "        sun                              = %s ; the sun's flares" % sun,
                  "        thunderbolt_collection           = %s" % thunder,
                  "        rain_density                     = 0", ""]
    return "\r\n".join(hours)


def put(root, mod, rel, text):
    p = os.path.join(root, "mods", mod, "gamedata", *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="latin-1", newline="").write(text)
    return p


def sections(*names):
    return "\r\n".join("[%s]\r\nflares = off\r\n" % n for n in names)


def install(root):
    """The setup that crashed: No Rain in Winter's copy of an Expansion weather naming the
    Expansion's sun, the Expansion off, and Atmospherics' configs, which lack that sun."""
    tc.install(root, config=CONFIG, mods=MODS)
    tc.with_mod(root)
    env = "configs/environment/"
    put(root, NO_RAIN, env + "weathers/w_rain6.ltx", weather("cloudy_dark_special"))
    put(root, EXPANSION, env + "weathers/w_rain6.ltx", weather("cloudy_dark_special"))
    put(root, EXPANSION, env + "suns.ltx", sections("cloudy_dark_special", "clear_sun"))
    put(root, ATMOS, env + "weathers/w_clear1.ltx", weather("clear_sun"))
    put(root, ATMOS, env + "suns.ltx", sections("clear_sun"))
    put(root, ATMOS, env + "ambients.ltx", sections("amb_day"))
    put(root, ATMOS, env + "thunderbolt_collections.ltx", sections("tb_day"))


def set_state(root, name, sign):
    """`name` on ("+") or off ("-") in MO2's list, where it stands."""
    p = os.path.join(root, "profiles", "Default", "modlist.txt")
    lines = io.open(p, encoding="utf-8", newline="").read().split(tc.CRLF)
    lines = [sign + name if l[1:] == name else l for l in lines]
    io.open(p, "w", encoding="utf-8", newline="").write(tc.CRLF.join(lines))


def insert(root, name, above):
    """A mod, on, put directly above `above` in MO2's list."""
    p = os.path.join(root, "profiles", "Default", "modlist.txt")
    lines = io.open(p, encoding="utf-8", newline="").read().split(tc.CRLF)
    i = next(i for i, l in enumerate(lines) if l[1:] == above)
    lines.insert(i, "+" + name)
    io.open(p, "w", encoding="utf-8", newline="").write(tc.CRLF.join(lines))


def modlist(root):
    return [l.strip() for l in io.open(os.path.join(root, "profiles", "Default",
                                                    "modlist.txt"), encoding="utf-8")][1:]


def run(root, *args):
    return tc.run(root, *args, tool="season.py")


def flat(out):
    """The output with the wrapped lines joined, as one line of words."""
    return " ".join(out.split())


# --- the cases -----------------------------------------------------------------------------

@case
def t_the_launch_that_would_stop_on_a_weather_is_stopped_once_staged():
    """In winter No Rain in Winter is on, and its copy names a sun only the Expansion, off,
    has: apply stages the season, names the weather, its mod, the sun and the mod that has
    it, and stops before the launch. Outside the winters the copy is off and the launch goes
    ahead; status and a dry run say it for winter, and stop nothing."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        rc, out = run(d, "apply", "--season", "winter")
        f = flat(out)
        assert rc == 1 and SAID in f and HOLDER in f and REMAKE in f and STOP in f, out
        assert "+" + NO_RAIN in modlist(d), modlist(d)
        assert "w_clear1" not in out and "clear_sun" not in out, out

        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out and STOP not in out, out
        assert "-" + NO_RAIN in modlist(d), modlist(d)

        rc, out = run(d, "status", "--season", "winter")
        assert rc == 0 and SAID in flat(out) and STOP not in flat(out), out
        rc, out = run(d, "apply", "--season", "winter", "--dry-run")
        assert rc == 0 and SAID in flat(out) and STOP not in flat(out), out
        assert "-" + NO_RAIN in modlist(d), "a dry run switched it"
    return "winter: staged, named and stopped; autumn: launched; status and --dry-run say it"


@case
def t_turning_the_mod_that_has_it_on_clears_it():
    with tempfile.TemporaryDirectory() as d:
        install(d)
        set_state(d, EXPANSION, "+")
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "Can't open section" not in out and STOP not in flat(out), out
    return "the Expansion on, its suns.ltx wins and has the sun: launched"


@case
def t_a_name_from_an_include_or_a_dltx_file_counts():
    """The game reads what suns.ltx #includes, and the DLTX files beside it, from wherever
    they win; a name in any of them is there."""
    env = "configs/environment/"
    with tempfile.TemporaryDirectory() as d:
        install(d)
        put(d, ATMOS, env + "suns.ltx", sections("clear_sun") + '#include "suns\\extra.ltx"\r\n')
        put(d, "Seasons of the Zone", env + "suns/extra.ltx", sections("cloudy_dark_special"))
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "Can't open section" not in out, out

        put(d, ATMOS, env + "suns.ltx", sections("clear_sun"))
        for header in ("[cloudy_dark_special]", "@[cloudy_dark_special]", "![Cloudy_Dark_Special]"):
            put(d, "Seasons of the Zone", env + "mod_suns_dark.ltx", header + "\r\nflares = off\r\n")
            rc, out = run(d, "apply", "--season", "winter")
            assert rc == 0 and "Can't open section" not in out, (header, out)
        put(d, "Seasons of the Zone", env + "mod_ambients_dark.ltx", "[cloudy_dark_special]\r\n")
        os.remove(os.path.join(d, "mods", "Seasons of the Zone", "gamedata", "configs",
                               "environment", "mod_suns_dark.ltx"))
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 1 and SAID in flat(out), "a DLTX file of another config counted: " + out
    return "an #include from another mod, mod_suns_*.ltx in three header forms; not mod_ambients_"


@case
def t_the_copy_that_wins_is_the_one_read():
    """A suns.ltx above Atmospherics' hides it, and MO2's overwrite folder is above them all:
    the name has to be in the copy the game gets, and the lines say which copy that is."""
    env = "configs/environment/"
    with tempfile.TemporaryDirectory() as d:
        install(d)
        set_state(d, NO_RAIN, "-")
        put(d, ATMOS, env + "suns.ltx", sections("clear_sun", "cloudy_dark_special"))
        put(d, ATMOS, env + "weathers/w_rain6.ltx", weather("cloudy_dark_special"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out, out

        insert(d, "Lens Flares", above=ATMOS)
        put(d, "Lens Flares", env + "suns.ltx", sections("clear_sun"))
        rc, out = run(d, "apply", "--season", "autumn")
        f = flat(out)
        said = SAID.replace('"%s"' % NO_RAIN, '"%s"' % ATMOS)
        hidden = ('"%s" has it in its suns.ltx, but the copy in "Lens Flares" wins: take that '
                  'copy out of "Lens Flares", or put "%s" below it in MO2\'s left pane.'
                  % (ATMOS, ATMOS))
        assert rc == 1 and said in f and hidden in f and HOLDER in f, out
        assert REMAKE not in f and "No mod in MO2's list" not in f, out
        assert "is a seasonal mod" not in f, "Lens Flares isn't on the calendar: " + out

        set_state(d, "Lens Flares", "-")
        ow = os.path.join(d, "overwrite", "gamedata", "configs", "environment", "suns.ltx")
        os.makedirs(os.path.dirname(ow))
        io.open(ow, "w", encoding="latin-1").write(sections("clear_sun"))
        rc, out = run(d, "apply", "--season", "autumn")
        f = flat(out)
        assert rc == 1 and said in f, "MO2's overwrite didn't win: " + out
        assert ('"%s" has it in its suns.ltx, but the copy in MO2\'s overwrite folder wins: '
                'take that copy out of overwrite.' % ATMOS) in f, out
    return "a mod's suns.ltx above hides Atmospherics', overwrite's hides them all: both named"


@case
def t_a_seasonal_mod_whose_suns_ltx_wins_is_named_as_such():
    """The second crash the player hit, once the Expansion was back on: INVERNO 1.09's base
    module, seasonal and above Atmospherics, carries a whole configs\\environment folder,
    with weathers that replace Atmospherics' and a suns.ltx that lacks sunset_sunrise, an
    Atmospherics sun the Expansion's extra weathers still name. In winter its copy wins over
    both mods that have the sun. The lines name both moves and say the mod is seasonal; in
    autumn it's off and the launch goes ahead; taken out, its suns.ltx no longer hides theirs."""
    env = "configs/environment/"
    inverno = "INVERNO (seasonal)"
    config = ('TOGGLE_MODS = {\n    "%s": {"when": ("winter",), "above": "%s"},\n'
              '    "%s": {"when": ("winter",), "above": "%s"},\n}\n'
              % (NO_RAIN, ATMOS, inverno, ATMOS))
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config, mods=[(inverno, False, [])] + MODS)
        tc.with_mod(d)
        put(d, NO_RAIN, env + "weathers/w_rain6.ltx", weather("cloudy_dark_special"))
        put(d, EXPANSION, env + "weathers/w_rain6.ltx", weather("cloudy_dark_special"))
        put(d, EXPANSION, env + "weathers/w_partly4.ltx", weather("sunset_sunrise"))
        put(d, EXPANSION, env + "suns.ltx",
            sections("cloudy_dark_special", "clear_sun", "sunset_sunrise"))
        put(d, ATMOS, env + "weathers/w_clear1.ltx", weather("sunset_sunrise"))
        put(d, ATMOS, env + "suns.ltx", sections("clear_sun", "sunset_sunrise"))
        put(d, ATMOS, env + "ambients.ltx", sections("amb_day"))
        put(d, ATMOS, env + "thunderbolt_collections.ltx", sections("tb_day"))
        put(d, inverno, env + "weathers/w_clear1.ltx", weather("clear_sun"))
        put(d, inverno, env + "suns.ltx", sections("clear_sun"))
        set_state(d, EXPANSION, "+")

        rc, out = run(d, "apply", "--season", "winter")
        f = flat(out)
        assert rc == 1 and STOP in f, out
        assert ('w_partly4.ltx, in "%s", names the sun "sunset_sunrise"' % EXPANSION) in f, out
        assert ('"%s" and "%s" have it in their suns.ltx, but the copy in "%s" wins: take that '
                'copy out of "%s", or put one of them below it in MO2\'s left pane.'
                % (EXPANSION, ATMOS, inverno, inverno)) in f, out
        assert ('w_rain6.ltx, in "%s", names the sun "cloudy_dark_special"' % NO_RAIN) in f, out
        assert ('"%s" has it in its suns.ltx, but the copy in "%s" wins: take that copy out of '
                '"%s", or put "%s" below it in MO2\'s left pane.'
                % (EXPANSION, inverno, inverno, EXPANSION) in f), out
        assert f.count('"%s" is a seasonal mod, on for this season.' % inverno) == 1, out
        assert "w_clear1" not in out and HOLDER not in f, out

        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out, out

        os.remove(os.path.join(d, "mods", inverno, "gamedata", "configs", "environment",
                               "suns.ltx"))
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "Can't open section" not in out and STOP not in flat(out), out
    return "winter: both suns, both moves, seasonal said once; autumn and without its suns.ltx: launched"


@case
def t_the_weather_that_wins_is_the_one_read():
    """Two mods on with the same weather: only the copy that wins is loaded, so only its
    names count, whichever of the two lacks one."""
    env = "configs/environment/"
    with tempfile.TemporaryDirectory() as d:
        install(d)
        set_state(d, NO_RAIN, "-")
        insert(d, "Weather Fix", above=ATMOS)
        put(d, "Weather Fix", env + "weathers/w_clear1.ltx", weather("clear_sun"))
        put(d, ATMOS, env + "weathers/w_clear1.ltx", weather("old_sun"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out, "the copy that loses was read: " + out

        put(d, "Weather Fix", env + "weathers/w_clear1.ltx", weather("old_sun"))
        put(d, ATMOS, env + "weathers/w_clear1.ltx", weather("clear_sun"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 1 and 'w_clear1.ltx, in "Weather Fix", names the sun "old_sun"' in flat(out), out
    return "the copy above is read, both ways round"


@case
def t_a_config_no_mod_has_is_not_checked():
    """A config only the game's own archives have isn't read here, so what it holds isn't
    known: nothing is said about the names it would give."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        for mod in (EXPANSION, ATMOS):
            os.remove(os.path.join(d, "mods", mod, "gamedata", "configs", "environment",
                                   "suns.ltx"))
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "Can't open section" not in out, out
    return "no suns.ltx in any mod: no word about suns"


@case
def t_a_file_only_the_game_has_makes_the_config_unknown():
    """GAMMA's ambients.ltx #includes ambients\\underground.ltx, which only the game has, and
    the Atmospherics indoor weathers name an ambient defined through it: nothing is said, as
    nothing is known. A wildcard #include may reach such a file too."""
    env = "configs/environment/"
    with tempfile.TemporaryDirectory() as d:
        install(d)
        set_state(d, NO_RAIN, "-")
        put(d, ATMOS, env + "weathers/w_indoor_default.ltx",
            weather("clear_sun", ambient="indoor_underground"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 1 and 'names the ambient "indoor_underground"' in flat(out), out
        for include in ('ambients\\underground.ltx', 'ambients\\presets\\*.ltx'):
            put(d, ATMOS, env + "ambients.ltx",
                '#include "%s"\r\n' % include + sections("amb_day"))
            rc, out = run(d, "apply", "--season", "autumn")
            assert rc == 0 and "Can't open section" not in out, (include, out)
        put(d, "Seasons of the Zone", env + "ambients/underground.ltx",
            ';; ambients rely on presets\r\n#include "presets\\environment_underground.ltx"\r\n')
        put(d, ATMOS, env + "ambients.ltx",
            '#include "ambients\\underground.ltx"\r\n' + sections("amb_day"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out, "the game's preset counted: " + out
        put(d, "Seasons of the Zone", env + "ambients/presets/environment_underground.ltx",
            sections("indoor_underground"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out, out
        put(d, "Seasons of the Zone", env + "ambients/presets/environment_underground.ltx",
            sections("indoor_other"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 1 and 'names the ambient "indoor_underground"' in flat(out), \
            "a chain of includes mods have was not read through: " + out
    return "an include only the game has, or a wildcard: unknown, not checked; a chain mods have is"


@case
def t_thunderbolt_collections_and_ambients_too():
    with tempfile.TemporaryDirectory() as d:
        install(d)
        set_state(d, NO_RAIN, "-")
        put(d, ATMOS, "configs/environment/weathers/w_storm1.ltx",
            weather("clear_sun", ambient="amb_storm", thunder="tb_storm"))
        rc, out = run(d, "apply", "--season", "autumn")
        f = flat(out)
        assert rc == 1 and STOP in f, out
        assert ('w_storm1.ltx, in "%s", names the thunderbolt collection "tb_storm"' % ATMOS
                in f), out
        assert 'w_storm1.ltx, in "%s", names the ambient "amb_storm"' % ATMOS in f, out
        assert f.count("No mod in MO2's list has it") == 2, out
        assert "w_clear1" not in out, out
    return "both named, with no mod to turn on"


@case
def t_names_match_whatever_their_case_and_several_files_share_a_line():
    env = "configs/environment/"
    with tempfile.TemporaryDirectory() as d:
        install(d)
        set_state(d, NO_RAIN, "-")
        put(d, ATMOS, env + "weathers/w_clear2.ltx", weather("Clear_Sun"))
        put(d, ATMOS, env + "suns.ltx", sections("CLEAR_SUN"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "Can't open section" not in out, out

        for f in ("w_partly1.ltx", "w_partly2.ltx"):
            put(d, ATMOS, env + "weathers/" + f, weather("partly_sun"))
        rc, out = run(d, "status", "--season", "autumn")
        assert ('w_partly1.ltx, w_partly2.ltx, in "%s", name the sun "partly_sun"' % ATMOS
                in flat(out)), out
    return "Clear_Sun is clear_sun; two weathers on one line"


def main():
    bad = 0
    for fn in CASES:
        try:
            said = fn()
            print("  PASS  %-66s %s" % (fn.__name__[2:], said))
        except Exception as e:
            bad += 1
            print("  FAIL  %-66s %s" % (fn.__name__[2:], (str(e) if isinstance(e, AssertionError)
                                                          else repr(e))[:900]))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
