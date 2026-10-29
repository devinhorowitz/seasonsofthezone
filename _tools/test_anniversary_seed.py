"""The anniversary artefacts against Dynamic Anomalies Overhaul's level refresh.

On a marked day the mod seeds a few artefacts on each level through DAO's
spawn_artefacts_on_level, once a day per level. After an emission DAO refreshes a level the
first time it runs there (its last_surge_time is past the level's time), and the refresh
clears the level's artefacts. The seed waits for that refresh, or the day's crop goes with it.

The seeding function is cut from the shipped script and run in LuaJIT with DAO's tables
stood in for. Every case has a control on the code before the wait came in.

  python _tools/test_anniversary_seed.py
"""
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
from lua_runtime import LuaRuntime, NAME                        # noqa: E402

MAIN = os.path.join(HERE, "..", "mods", "Seasons of the Zone", "gamedata", "scripts",
                    "zzz_seasons_of_the_zone.script")


def seeding(src):
    """local ARTE_PASSES through the end of anniversary_artefacts, from the script."""
    m = re.search(r"(local ARTE_PASSES.*?\nlocal function anniversary_artefacts\(\).*?\nend\n)",
                  src.replace("\r\n", "\n"), re.S)
    assert m, "anniversary_artefacts not found"
    return m.group(1)


SHIPPED = seeding(io.open(MAIN, encoding="utf-8").read())
# the code before the wait: the same function without its three lines
BEFORE = re.sub(r"    local surge = tonumber\(drx_da_main\.last_surge_time\)\n.*?\n", "",
                SHIPPED, count=1, flags=re.S)

STAGE = """
local seeded = 0
arte_done = {}
level = {name = function() return "l02_garbage" end}
function zone_today() return {iso = "2026-04-26"} end
function IsArtefact() return true end
function alife()
    return {iterate_objects = function(_, fn)
        for i = 1, seeded do fn({clsid = function() return 1 end}) end
    end}
end
drx_da_main = {
    last_surge_time = %s,
    updated_anomaly_levels = {l02_garbage = {anomaly_types_by_smart = {}, time = %s}},
    spawn_artefacts_on_level = function() seeded = seeded + 1 end,
}
-- DAO's refresh on the level: clean its artefacts, then mark it current
function dao_refresh()
    seeded = 0
    drx_da_main.updated_anomaly_levels.l02_garbage.time = drx_da_main.last_surge_time
end
function crop() return seeded end
"""


def world(code, surge, level_time):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STAGE % (surge, level_time))
    lua.execute(code + "\nfunction tick() return anniversary_artefacts() end\n")
    return lua.globals()


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_back_on_a_level_after_an_emission_the_seed_waits():
    g = world(SHIPPED, surge=5000, level_time=1000)
    assert g.tick() is None and g.crop() == 0, "nothing before DAO's refresh"
    assert not g.arte_done["2026-04-26|l02_garbage"], "the day isn't latched yet"
    g.dao_refresh()
    msg = g.tick()
    assert g.crop() == 5 and "seeded" in msg, (g.crop(), msg)
    c = world(BEFORE, surge=5000, level_time=1000)
    c.tick()
    c.dao_refresh()
    assert c.crop() == 0 and c.tick() is None, "control: seeded, cleared, and the day latched"
    return "5 artefacts after the refresh; before the wait, none for the day"


@case
def t_a_level_already_current_is_seeded_at_once():
    g = world(SHIPPED, surge=1000, level_time=1000)
    g.tick()
    assert g.crop() == 5, g.crop()
    g.tick()
    assert g.crop() == 5, "once a day per level"
    return "no emission since the last visit: seeded on the first tick"


@case
def t_without_dao_s_times_the_seed_goes_ahead():
    g = world(SHIPPED, surge="nil", level_time="nil")
    g.tick()
    assert g.crop() == 5, g.crop()
    return "a DAO without last_surge_time is seeded as before"


if __name__ == "__main__":
    print("  the anniversary artefacts against DAO's refresh")
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
    print("\n  %d/%d passed on %s" % (len(CASES) - bad, len(CASES), NAME))
    sys.exit(1 if bad else 0)
