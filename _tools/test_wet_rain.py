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


def world(sections, rain=0.0, weather="w_rain1", hour=12.5, on_disk=("xr_combat_ignore",),
          own_level=(), loose=None, modules=(), call=True):
    """`sections` is the weather file as {time: {key: value}}; the stand-in scripts are
    loaded as their own files; `on_disk` is which of the gameplay readers exist; `loose` is
    {file: text} for the files that can be read as loose files (any other can't be, as one
    packed in a .db can't); `modules` are names loaded with require, each a copy of MODULE.
    `call` runs wet_readers() and keeps what it returned in w.done."""
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
        function (src, name, shared)
            local env = setmetatable({}, {__index = shared, __newindex =
                function (t, k, v) rawset(t, k, v) end})
            local f, err = load(src, name, "t", env)
            if not f then error(name .. ": " .. tostring(err)) end
            f()
            return env
        end
    """)
    probe = "function probe() return level.rain_factor() end\nfunction hour() return level.get_time_hours() end\n"
    for name in sorted(set(on_disk) | {"xr_combat_ignore", "ssfx_rain_hud_raindrops"}):
        src = probe + ("level = {rain_factor = function() return -1 end}\n" if name in own_level else "")
        g[name] = loader(src, name, g)
    required = lua.eval("""
        function (src, name)
            local f, err = load(src, name, "t", _G)
            if not f then error(name .. ": " .. tostring(err)) end
            package.loaded[name] = f()
        end
    """)
    for name in modules:
        required(MODULE, name)
    w.lua, w.g = lua, g
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
    return "on_game_start hands it out and says which scripts in the log"


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
