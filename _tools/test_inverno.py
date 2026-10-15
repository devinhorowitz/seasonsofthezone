"""Project INVERNO by the season: the shipped sotz_inverno.script against the shipped sotz_api.

INVERNO is FabioConte's and licensed for ModDB only, so none of its files can be here. The
stand-ins below hold what the bridge relies on and nothing of INVERNO's own: options read
through project_inverno_mcm.get_config, a freezing file that reads its temperature by name
on every tick, and a snowfall file that asks for enable_snowfall. A run against INVERNO's
real scripts needs them on disk, so it lives outside the repo.

Every case has a control without the bridge that comes out the other way.

  python _tools/test_inverno.py
"""
import io
import math
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import test_api as ta                                           # noqa: E402
import test_calendar as tcal                                    # noqa: E402

SCRIPTS = ta.SCRIPTS
BRIDGE = io.open(os.path.join(SCRIPTS, "sotz_inverno.script"), encoding="utf-8").read()
MCM = io.open(os.path.join(SCRIPTS, "zzz_seasons_of_the_zone_mcm.script"),
              encoding="utf-8").read()

OPTIONS = """
-- stand-in for INVERNO's options file: every option is read through get_config
function get_config(key)
    return ui_mcm.get("project_inverno/" .. key)
end
"""

FREEZING = """
-- stand-in for INVERNO's freezing file: a temperature of its own, read by name on every
-- tick, and what the cold costs
current_temperature_c = -25.0
freeze_level = 0.0
function update_ambient_temperature()
    current_temperature_c = -25.0
end
function tick()
    if project_inverno_mcm.get_config("enable_inverno_mechanics") == false then
        freeze_level = 0.0
        return
    end
    update_ambient_temperature()
    COST
end
"""
# the winter mechanics update: a freeze at -10 C or below, and it saves its state
UPDATE = FREEZING.replace("COST", """if current_temperature_c <= -10.0 then
        freeze_level = freeze_level + 0.01
    else
        freeze_level = math.max(0.0, freeze_level - 0.0005)
    end""") + "function save_state(m_data) end\n"
# 1.09: a freeze at any temperature, by its absolute value
OLD = FREEZING.replace("COST", "freeze_level = freeze_level + math.abs(current_temperature_c) / 1000")

SNOWFALL = """
-- stand-in for INVERNO's snowfall file
falling = false
function tick()
    falling = project_inverno_mcm.get_config("enable_snowfall") ~= false
end
"""

# X-Ray gives each file its own table and exposes it under the file's name
LOADER = """
function (src, name, shared)
    local env = setmetatable({}, {__index = shared})
    local f, err = load(src, name, "t", env)
    if not f then error(name .. ": " .. tostring(err)) end
    shared[name] = env
    f()
    return env
end
"""

COLD_SNAP = {"high": -12.0, "low": -20.0, "cycle": "clear", "date": ta._pinned(1, 15),
             "place": "Chornobyl"}
FROST_DAY = {"high": 2.0, "low": -6.0, "cycle": "clear", "date": ta._pinned(1, 15),
             "place": "Chornobyl"}
MILD_DAY = {"high": 14.5, "low": 7.8, "cycle": "clear", "date": ta._pinned(9, 15),
            "place": "Chornobyl"}


# "Now" pinned to noon on the day: os.date and os.time without a time give it, and with one
# behave as always. test_api's own pin answers "*t", "%d" and "%j" with the pinned day even
# for a time it is handed, which sets every season boundary on that day.
PIN = """
local real_date, real_time = os.date, os.time
local now = real_time({year = %d, month = %d, day = %d, hour = 12})
os.date = function(fmt, t) return real_date(fmt or "%%c", t or now) end
os.time = function(t) if t == nil then return now end return real_time(t) end
"""


def world(version="update", bridge=True, inverno=True, mcm=None, units=None, month=1,
          day=15, **kw):
    """The data layer and sotz_api as test_api builds them on the given day, MCM's saved values
    by full path, INVERNO's stand-ins and the bridge."""
    lua, g = ta.build(units=units, **kw)
    year = int(ta._pinned(month, day)[:4])
    lua.execute(PIN % (year, month, day))
    vals = dict(mcm or {})
    if units is not None:
        vals["seasons_zone/main/units"] = units
    g.ui_mcm = lua.table_from({"get": lambda p: vals.get(str(p))})
    load = lua.eval(LOADER)
    if inverno:
        load(OPTIONS, "project_inverno_mcm", g)
        load(UPDATE if version == "update" else OLD, "inverno_freezing_mechanic", g)
        load(SNOWFALL, "Inverno_snowfall_system", g)
    if bridge:
        load(BRIDGE, "sotz_inverno", g)
        g.sotz_inverno.on_game_start()
    return g


def run(g, ticks=30):
    for _ in range(ticks):
        g.inverno_freezing_mechanic.tick()
    m = g.inverno_freezing_mechanic
    return m.current_temperature_c, m.freeze_level


def snowing(g):
    g.Inverno_snowfall_system.tick()
    return g.Inverno_snowfall_system.falling


def option(g, key):
    return g.project_inverno_mcm.get_config(key)


def celsius_now(g):
    """What the PDA says it is now, in Celsius at INVERNO's tenth of a degree."""
    t = g.sotz_api.temperature()
    c = t.curve[1]
    if t.unit == "F":
        c = (c - 32) * 5 / 9
    return math.floor(c * 10 + 0.5) / 10


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_a_cold_snap_reaches_inverno():
    g = world(month=1, hour=5.0, cycle="clear", observed=COLD_SNAP)
    temp, cold = run(g)
    assert temp == celsius_now(g) == -20.0, (temp, celsius_now(g))
    assert cold > 0, cold
    c = world(bridge=False, month=1, hour=5.0, cycle="clear", observed=COLD_SNAP)
    assert run(c)[0] == -25.0, "control: INVERNO's own roll"
    return "-20 C at dawn in a cold snap, and it freezes"


@case
def t_a_july_afternoon_warms():
    g = world(month=7, hour=15.0)
    temp, cold = run(g)
    assert temp == celsius_now(g) and temp > 15, temp
    assert cold == 0, cold
    c = world(bridge=False, month=7, hour=15.0)
    assert run(c)[1] > 0, "control: INVERNO freezes in July"
    return "%.1f C in July, and no cold" % temp


@case
def t_fahrenheit_on_the_pda_still_feeds_celsius():
    g = world(month=1, hour=5.0, cycle="clear", observed=COLD_SNAP, units="fahrenheit")
    assert g.sotz_api.temperature().unit == "F", "the PDA should show Fahrenheit here"
    temp, _ = run(g)
    assert temp == -20.0, temp
    c = world(month=1, hour=5.0, cycle="clear", observed=COLD_SNAP, units="celsius")
    assert run(c)[0] == temp, "the same day in Celsius"
    return "-4 F on the PDA, -20 C to INVERNO"


@case
def t_the_update_keeps_its_mechanics_all_year():
    g = world(month=7, hour=15.0)
    assert option(g, "enable_inverno_mechanics") is not False, \
        "spring's campfires thaw what froze in winter"
    assert run(g)[0] == celsius_now(g), "the temperature should be the Zone's"
    return "on in July; the temperature keeps it harmless"


@case
def t_1_09_rests_on_a_day_without_frost():
    g = world(version="1.09", month=9, hour=5.0, observed=MILD_DAY)
    assert option(g, "enable_inverno_mechanics") is False
    assert run(g)[1] == 0
    c = world(version="1.09", bridge=False, month=9, hour=5.0, observed=MILD_DAY)
    assert run(c)[1] > 0, "control: 1.09 freezes on any day"
    return "off on a mild day"


@case
def t_1_09_runs_on_a_freezing_day_with_its_own_numbers():
    g = world(version="1.09", month=1, hour=15.0, observed=FROST_DAY)
    assert option(g, "enable_inverno_mechanics") is not False
    temp, cold = run(g)
    assert temp == -25.0, "1.09 freezes on abs(temperature): it keeps its own"
    assert cold > 0
    return "on, at its own -25 C"


@case
def t_snow_falls_in_the_winters_only():
    for version in ("update", "1.09"):
        assert snowing(world(version=version, month=1)) is True, version
        assert snowing(world(version=version, month=7)) is False, version
        assert option(world(version=version, month=7), "enable_fog") is False, version
        assert snowing(world(version=version, bridge=False, month=7)) is True, \
            "control: INVERNO snows in July"
    return "January yes, July no, for both"


@case
def t_a_winter_pinned_in_july_snows():
    g = world(month=7, mcm={"seasons_zone/main/mode": "winter"})
    assert g.sotz_api.season().snow > 0, "the pin should bring snow"
    assert snowing(g) is True
    assert snowing(world(month=7)) is False, "control: July without the pin"
    return "the pin, not the date"


@case
def t_inverno_s_own_off_stays_off():
    g = world(month=1, mcm={"project_inverno/enable_snowfall": False})
    assert snowing(g) is False
    g = world(version="1.09", month=1, hour=15.0, observed=FROST_DAY,
              mcm={"project_inverno/enable_inverno_mechanics": False})
    assert option(g, "enable_inverno_mechanics") is False
    return "an option turned off on INVERNO's page never comes back on"


@case
def t_when_seasons_can_t_say_inverno_s_own_values_stand():
    for version in ("update", "1.09"):
        g = world(version=version, month=7, hour=15.0, observed=None)
        g.sotz_api.season = g.sotz_api.temperature = lambda: None
        assert snowing(g) is True, version
        assert option(g, "enable_inverno_mechanics") is not False, version
        assert run(g)[0] == -25.0, version
    c = world(month=7)
    assert snowing(c) is False, "control: July, when it can say"
    return "no season or temperature: INVERNO as it ships"


@case
def t_either_switch_off_leaves_inverno_as_it_ships():
    for path in ("seasons_zone/main/enabled", "seasons_zone/main/inverno"):
        g = world(month=7, hour=15.0, mcm={path: False})
        assert snowing(g) is True, path
        assert run(g)[0] == -25.0, path
        g = world(version="1.09", month=9, hour=5.0, observed=MILD_DAY, mcm={path: False})
        assert option(g, "enable_inverno_mechanics") is not False, path
    return "the master switch and the INVERNO switch"


@case
def t_nothing_without_inverno():
    g = world(inverno=False, month=1)
    assert g.sotz_inverno.present() is False
    return "loads and stays out of the way"


def main_page(with_inverno):
    lua, g = tcal.build(2026, 7, 1)
    if with_inverno:
        g.project_inverno_mcm = g.load_in(OPTIONS, "project_inverno_mcm", g)
    g.sotz_inverno = g.load_in(BRIDGE, "sotz_inverno", g)
    op = g.load_in(MCM, "zzz_seasons_of_the_zone_mcm", g).on_mcm_load()
    main = op.gr[1].gr
    return [main[i].id for i in range(1, len(main) + 1)]


@case
def t_the_switch_shows_only_with_inverno():
    assert "inverno" in main_page(True)
    assert "inverno" not in main_page(False)
    return "on MCM's Main page when INVERNO is installed"


if __name__ == "__main__":
    bad = 0
    for fn in CASES:
        name = fn.__name__[2:].replace("_", " ")
        try:
            print("  PASS  %-48s %s" % (name, fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-48s %s" % (name, e))
        except Exception as e:
            bad += 1
            print("  ERROR %-48s %s: %s" % (name, type(e).__name__, e))
    print("\n  %d/%d passed on %s" % (len(CASES) - bad, len(CASES), ta.LUA_NAME))
    sys.exit(1 if bad else 0)
