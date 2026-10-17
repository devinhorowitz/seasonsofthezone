"""The rain gameplay still goes by: with No Rain in Winter's copies served, the scripts that use
rain for gameplay get a `level` whose rain_factor() reads the rain each copy kept, blended
across the hour, and every other script reads the real, dry value.

The shipped zzz_seasons_of_the_zone.script runs in its own environment, as X-Ray runs it
(test_api's harness), next to stand-ins: xr_combat_ignore, one of the gameplay readers,
ssfx_rain_hud_raindrops, which draws rain and must stay dry, and, for the cases that ask, other
readers' copies and a module loaded with require, as Useful Idiots' combat range is.

  python _tools/test_wet_rain.py
"""
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

import test_api as ta  # noqa: E402

CASES = []
RAIN1 = "environment\\weathers\\w_rain1.ltx"


def case(fn):
    CASES.append(fn)
    return fn


class World(object):
    pass


TEMP = []
MODULE = """
local PATCH = {}
function PATCH.getRainMultiplier() return level.rain_factor() end
function PATCH.cap(x) return math.min(x, level.rain_factor()) end
function PATCH.mark() marked = true end
function PATCH.own() return level.rain_factor() end
setfenv(PATCH.own, {level = {rain_factor = function() return -1 end}})
function dry_probe() return level.rain_factor() end
return PATCH
"""


def chunk(name):
    """The name the game gives a script's chunk: its full path."""
    return "@d:/anomaly/bin/..\\gamedata\\scripts\\%s.script" % name


# a script that keeps `level` in a local, as REDone Combat AI's do; probe() reads it directly,
# probe_local() through a local function
LOCAL_LEVEL = ("local level = level\nlocal function wet() return level.rain_factor() end\n"
               "function probe_local() return wet() end\n")
# one whose only reader of the local is a local function, reached through probe()'s upvalue
DEEP_LOCAL = ("local level = level\nlocal function wet() return level.rain_factor() end\n"
              "function probe() return wet() end\nfunction hour() return -1 end\n")
# one whose local `level` is its own, not the game's
OWN_LOCAL = "local level = {rain_factor = function() return -1 end}\n"


def world(sections, rain=0.0, weather="w_rain1", hour=12.5, on_disk=("xr_combat_ignore",),
          own_level=(), local_level=(), deep_local=(), own_local=(), loose=None, modules=(),
          call=True):
    """`sections` is the weather file as {time: {key: value}}; the stand-in scripts are
    loaded as their own files, named as the game names them; `on_disk` is which of the
    gameplay readers exist; `own_level`, `local_level`, `deep_local` and `own_local` are
    scripts that set a `level` of their own, keep the game's in a local (LOCAL_LEVEL,
    DEEP_LOCAL) or keep one of their own in a local (OWN_LOCAL); `loose` is {file: text} for
    the files that can be read as loose files (any other can't be, as one packed in a .db
    can't); `modules` are names loaded with require, each a copy of MODULE. `call` runs
    wet_readers() and keeps what it returned in w.done."""
    w = World()
    w.rain, w.weather, w.hour, w.clock = [rain], [weather], [hour], [0]
    lua, g = ta.build(hour=hour, level_extra={
        "rain_factor": lambda: w.rain[0],
        "get_weather": lambda: w.weather[0],
    })
    g.level.get_time_hours = lambda: int(w.hour[0])
    g.level.get_time_minutes = lambda: int(round((w.hour[0] - int(w.hour[0])) * 60))
    g.time_global = lambda: w.clock[0]
    scripts = set(n + ".script" for n in on_disk) | {"ssfx_rain_hud_raindrops.script"}
    tmp = tempfile.mkdtemp(prefix="sotz_wet_")
    TEMP.append(tmp)
    paths = {}
    for i, (name, text) in enumerate(sorted((loose or {}).items())):
        paths[name] = os.path.join(tmp, "%d.txt" % i)
        with open(paths[name], "w") as fh:
            fh.write(text)
    g.getFS = lambda: lua.table_from({
        "exist": lambda self, alias, name: (
            name in scripts if alias == "$game_scripts$" else name == RAIN1 and sections is not None),
        "update_path": lambda self, alias, name: paths.get(str(name), os.path.join(tmp, "packed")),
    })
    others = g.ini_file

    def ini(name):
        if str(name) != RAIN1 or sections is None:
            return others(name)
        secs = w.sections

        def each(self, fn):
            for s in secs:
                fn(s)
        return lua.table_from({
            "section_exist": lambda self, s: s in secs,
            "r_float_ex": lambda self, s, k: secs.get(s, {}).get(k),
            "section_for_each": each,
        })
    w.sections = sections or {}
    g.ini_file = ini
    loader = lua.eval("""
        function (src, name, shared, chunk)
            local env = setmetatable({}, {__index = shared, __newindex =
                function (t, k, v) rawset(t, k, v) end})
            local f, err = load(src, chunk or name, "t", env)
            if not f then error(name .. ": " .. tostring(err)) end
            f()
            return env
        end
    """)
    probe = "function probe() return level.rain_factor() end\nfunction hour() return level.get_time_hours() end\n"
    for name in sorted(set(on_disk) | {"xr_combat_ignore", "ssfx_rain_hud_raindrops"}):
        if name in deep_local:
            src = DEEP_LOCAL
        else:
            head = (LOCAL_LEVEL if name in local_level else
                    OWN_LOCAL if name in own_local else "")
            src = head + probe + ("level = {rain_factor = function() return -1 end}\n"
                                  if name in own_level else "")
        g[name] = loader(src, name, g, chunk(name))
    required = lua.eval("""
        function (src, name)
            local f, err = load(src, name, "t", _G)
            if not f then error(name .. ": " .. tostring(err)) end
            package.loaded[name] = f()
        end
    """)
    for name in modules:
        required(MODULE, name)
    w.lua, w.g, w.loader = lua, g, loader
    w.done = list(g.zzz_seasons_of_the_zone.wet_readers().values()) if call else None
    return w


UI = "illish.patches.xr_combat_ignore"
UI_FILE = "illish\\patches\\xr_combat_ignore.lua"


def kept(at_noon=0.8, at_one=0.4):
    return {"12:00:00": {"rain_density": 0, "sotz_rain_density": at_noon},
            "13:00:00": {"rain_density": 0, "sotz_rain_density": at_one},
            "00:00:00": {"rain_density": 0}}


def near(a, b):
    return abs(a - b) < 1e-6


@case
def t_gameplay_reads_the_kept_rain_the_rest_stay_dry():
    w = world(kept())
    assert w.done == ["xr_combat_ignore"], w.done
    got = w.g.xr_combat_ignore.probe()
    assert near(got, 0.6), "12:30 between 0.8 and 0.4 read %r, not 0.6" % got
    assert w.g.ssfx_rain_hud_raindrops.probe() == 0, "the raindrops script read the kept rain"
    assert w.g.xr_combat_ignore.hour() == 12, "the gameplay script's level lost the rest of level"
    return "the stealth script reads 0.6 at 12:30, the raindrops 0; the rest of level is there"


@case
def t_real_rain_comes_first_and_a_weather_that_is_no_copy_stays_dry():
    w = world(kept(), rain=0.3)
    assert near(w.g.xr_combat_ignore.probe(), 0.3), "the kept rain beat the real rain"
    w = world({"12:00:00": {"rain_density": 0}, "13:00:00": {"rain_density": 0}})
    assert w.g.xr_combat_ignore.probe() == 0, "a weather with nothing kept read as wet"
    w = world(None)
    assert w.g.xr_combat_ignore.probe() == 0, "a weather with no file read as wet"
    return "rain that falls is read as it is; no kept rain, no rain"


@case
def t_the_blend_wraps_past_midnight():
    secs = {"23:00:00": {"sotz_rain_density": 1.0}, "01:00:00": {"rain_density": 0}}
    w = world(secs, hour=0.0)
    got = w.g.xr_combat_ignore.probe()
    assert near(got, 0.5), "midnight between 1.0 at 23:00 and 0 at 01:00 read %r" % got
    w = world(secs, hour=23.5)
    got = w.g.xr_combat_ignore.probe()
    assert near(got, 0.75), "23:30 read %r, not 0.75" % got
    return "midnight halfway from 23:00 to 01:00; 23:30 a quarter of the way"


@case
def t_a_script_with_its_own_level_and_one_not_there_are_left_alone():
    w = world(kept(), own_level=("xr_combat_ignore",))
    assert w.done == [], w.done
    assert w.g.xr_combat_ignore.probe() == -1, "a script's own level was replaced"
    w = world(kept(), on_disk=())
    assert w.done == [], "a script that is not on disk was reached: %s" % w.done
    return "its own level kept; a missing script never loaded"


@case
def t_a_script_that_keeps_level_in_a_local_reads_the_kept_rain():
    """REDone Combat AI's scripts start `local level = level`, so a `level` set in the
    script's table never reaches them. The local itself is given the wet level, and every
    function in the file shares it, the local ones too. REDone's detection script is one of
    the readers; a script that is not one keeps its local as it was."""
    on = ("xr_combat_ignore", "redone_ai_detection", "xr_conditions")
    w = world(kept(), on_disk=on, local_level=("xr_combat_ignore", "redone_ai_detection",
                                               "ssfx_rain_hud_raindrops"),
              deep_local=("xr_conditions",))
    assert w.done == ["xr_combat_ignore", "xr_conditions", "redone_ai_detection"], w.done
    for name in ("xr_combat_ignore", "redone_ai_detection"):
        s = w.g[name]
        assert near(s.probe(), 0.6), "%s's local read %r, not 0.6" % (name, s.probe())
        assert near(s.probe_local(), 0.6), "%s's local function read the dry rain" % name
        assert s.hour() == 12, "%s's level lost the rest of level" % name
    got = w.g.xr_conditions.probe()
    assert near(got, 0.6), "a local read only by a local function read %r, not 0.6" % got
    assert w.g.ssfx_rain_hud_raindrops.probe() == 0, \
        "the raindrops script's local was given the kept rain"
    again = list(w.g.zzz_seasons_of_the_zone.wet_readers().values())
    assert again == [], "a second pass named what it had already reached: %s" % again
    return "the local read 0.6 in all three, through a local function too; raindrops stay dry"


@case
def t_another_mods_wrapper_and_a_local_level_of_its_own_are_left_alone():
    """A function another mod put in the script's table keeps the `level` of its own file,
    even one whose name ends like the script's: only functions compiled from the script's
    own file are looked into. And a local `level` that isn't the game's stays as it is."""
    w = world(kept(), local_level=("xr_combat_ignore",), call=False)
    other = w.loader("local level = level\nfunction dry() return level.rain_factor() end\n",
                     "zz_xr_combat_ignore", w.g, chunk("zz_xr_combat_ignore"))
    w.g.xr_combat_ignore["wrapped"] = other.dry
    done = list(w.g.zzz_seasons_of_the_zone.wet_readers().values())
    assert done == ["xr_combat_ignore"], done
    assert near(w.g.xr_combat_ignore.probe(), 0.6), "the script's own local was not reached"
    assert w.g.xr_combat_ignore.wrapped() == 0, "another mod's file was given the kept rain"
    w = world(kept(), own_local=("xr_combat_ignore",))
    assert w.g.xr_combat_ignore.probe() == -1, "a local level of the script's own was replaced"
    return "a wrapper from zz_xr_combat_ignore.script reads 0; a local level of its own, -1"


@case
def t_worked_out_every_two_seconds():
    w = world(kept())
    first = w.g.xr_combat_ignore.probe()
    w.hour[0] = 13.0
    assert near(w.g.xr_combat_ignore.probe(), first), "worked out again within two seconds"
    w.clock[0] = 2001
    assert near(w.g.xr_combat_ignore.probe(), 0.4), "not worked out again after two seconds"
    w.weather[0] = "w_clear1"
    w.clock[0] = 4002
    assert w.g.xr_combat_ignore.probe() == 0, "a dry weather kept the last storm's rain"
    return "the same answer within two seconds; the new hour, then a clear sky, after"


@case
def t_a_copy_that_reads_no_rain_is_left_alone():
    w = world(kept(), on_disk=("xr_combat_ignore", "visual_memory_manager", "arti_jamming"),
              loose={"xr_combat_ignore.script": "if level.rain_factor() >= 0.4 then end\n",
                     "visual_memory_manager.script": "-- sees in the dark\n"})
    assert w.done == ["xr_combat_ignore", "arti_jamming"], w.done
    assert near(w.g.xr_combat_ignore.probe(), 0.6), "a copy that reads rain was not reached"
    assert w.g.visual_memory_manager.probe() == 0, "a copy that reads no rain got the kept rain"
    assert near(w.g.arti_jamming.probe(), 0.6), "a script that can't be read was not reached"
    return "a copy with no rain_factor in it is left out; one that can't be read is reached"


@case
def t_a_module_loaded_with_require_reads_the_kept_rain():
    w = world(kept(), modules=(UI,))
    assert w.done == ["xr_combat_ignore", UI], w.done
    mod = w.g.package.loaded[UI]
    got = mod.getRainMultiplier()
    assert near(got, 0.6), "the module read %r at 12:30, not 0.6" % got
    assert near(mod.cap(5), 0.6), "the module lost the rest of _G"
    mod.mark()
    assert w.g.marked is True, "a global the module set did not reach _G"
    assert mod.own() == -1, "a function with an environment of its own was given ours"
    assert w.g.dry_probe() == 0, "the rest of _G read the kept rain"
    again = list(w.g.zzz_seasons_of_the_zone.wet_readers().values())
    assert again == [], "a second pass named what it had already reached: %s" % again
    return "its functions read 0.6 and still see _G; _G and an own environment stay as they were"


@case
def t_a_module_that_reads_no_rain_or_is_not_loaded_is_left_alone():
    w = world(kept(), modules=(UI,), loose={UI_FILE: "-- no weather here\n"})
    assert w.done == ["xr_combat_ignore"], w.done
    assert w.g.package.loaded[UI].getRainMultiplier() == 0, "a module that reads no rain was reached"
    w = world(kept())
    assert w.done == ["xr_combat_ignore"], "a module that is not loaded was reached: %s" % w.done
    return "a copy with no rain_factor in it is left as it was; one not loaded is never touched"


@case
def t_given_out_at_game_start():
    w = world(kept(), modules=(UI,), call=False)
    g = w.g
    log = []
    g.printf = lambda fmt, *a: log.append(str(fmt) % tuple(a) if a else str(fmt))
    g.zzz_seasons_of_the_zone.on_game_start()
    assert near(g.xr_combat_ignore.probe(), 0.6), "on_game_start gave the stealth script no level"
    assert near(g.package.loaded[UI].getRainMultiplier(), 0.6), "on_game_start missed the module"
    line = [l for l in log if "rain for gameplay" in l]
    assert line and "xr_combat_ignore" in line[0] and UI in line[0], \
        "the log does not say which scripts: %s" % log
    assert not [l for l in log if "known by its file" in l], \
        "warned of a script whose functions are named by its path: %s" % log
    return "on_game_start hands it out and says which scripts in the log"


@case
def t_a_script_whose_functions_cant_be_told_by_file_is_said():
    """If the game named a script's chunk some way from_file() doesn't read, its local `level`
    would be missed in silence; the log says so instead, and its table still gets the level."""
    w = world(kept(), call=False)
    w.g.xr_combat_ignore = w.loader("function probe() return level.rain_factor() end\n",
                                    "xr_combat_ignore", w.g, "xr_combat_ignore")
    log = []
    w.g.printf = lambda fmt, *a: log.append(str(fmt) % tuple(a) if a else str(fmt))
    done = list(w.g.zzz_seasons_of_the_zone.wet_readers().values())
    assert done == ["xr_combat_ignore"], done
    said = [l for l in log if "none of xr_combat_ignore's functions" in l]
    assert len(said) == 1 and said[0].startswith("[seasons] !"), log
    assert near(w.g.xr_combat_ignore.probe(), 0.6), "the table's level was not given"
    return "a chunk named only 'xr_combat_ignore' is said once; the table still gets the level"


if __name__ == "__main__":
    print("  rain for gameplay, through each script's own level")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-58s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-58s %s" % (fn.__name__[2:], e))
        except (Exception, SystemExit) as e:
            bad += 1
            print("  ERROR %-58s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    for tmp in TEMP:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
