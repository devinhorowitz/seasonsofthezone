"""Run the SHIPPED sotz_api.script under a real Lua runtime.

This harness is stricter than test_forecast.py in one way that matters: it gives each
script its OWN environment table and publishes it under the script's filename, which is
what X-Ray actually does. So sotz_api's calls to zzz_seasons_of_the_zone.forecast_page()
are resolved the same way the engine resolves them, and a bare-name reference that would
silently fail in game fails here too. (The Wearable Devices PDA Messages mod documents
that exact trap in zz_wd_pda_redirect.script, having hit it the hard way.)

Every case has a control that must move the other way, so a constant would be caught.
"""
import io
import os
import sys

from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

HOUR = 3600


def build(hour=12.0, cycle="clear", month=None, day=15, standing=900,
          surge_left=4 * HOUR, psi_left=9 * HOUR, clock_ms=0):
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()

    g.printf = lambda *a: None
    g.time_global = lambda: clock_ms
    g.level = lua.table_from({
        "get_time_hours": lambda: int(hour),
        "get_time_minutes": lambda: int(round((hour - int(hour)) * 60)),
        "name": lambda: "l01_escape",
    })
    g.db = lua.table_from({"actor": lua.table_from({"id": lambda self: 0})})
    g.relation_registry = lua.table_from({
        "community_goodwill": lambda faction, aid: standing})
    opts = {"alife/event/emission_frequency": 24,
            "alife/event/psi_storm_frequency": 48}
    g.ui_options = lua.table_from({"get": lambda k: opts.get(k)})
    g.game = lua.table_from({"get_game_time": lambda: lua.table_from({
        "diffSec": lambda self, other: other["elapsed"] if other is not None else 0,
        "get": lambda self, *a: 2026,
    })})
    g.surge_manager = lua.table_from({"SurgeManager": lua.table_from({
        "_delta": 24 * HOUR,
        "last_surge_time": lua.table_from({"elapsed": 24 * HOUR - surge_left})})})
    g.psi_storm_manager = lua.table_from({"PsiStormManager": lua.table_from({
        "_delta": 48 * HOUR,
        "last_psi_storm_time": lua.table_from({"elapsed": 48 * HOUR - psi_left})})})

    wm = lua.table_from({
        "cycle": cycle,
        "day_plan": lua.table_from([lua.table_from({"minute": 700, "cycle": "rain"})]),
        "day_plan_index": 1,
        "abs_schedule_minute": lambda self: 600,
    })
    g.level_weathers = lua.table_from({"get_weather_manager": lambda: wm})
    g.ui_mcm = lua.table_from({"get": lambda p: {
        "forecast": True, "forecast_coarse": 200, "forecast_exact": 700,
    }.get(str(p).split("/")[-1])})
    g.alife = lambda: None
    g.axr_main = lua.table_from({})
    g.RegisterScriptCallback = lambda *a: None
    g.device = lambda: lua.table_from({"width": 1920, "height": 1080})

    # Pin the date the model sees. The mod reads os.date, so override it rather than
    # pretending: the real function still serves every format it is not asked about.
    if month is not None:
        lua.execute("""
            local real = os.date
            local M, D = %d, %d
            os.date = function(fmt, t)
                if fmt == "*t" then
                    local r = real("*t"); r.month = M; r.day = D; return r
                elseif fmt == "%%d" then return string.format("%%02d", D)
                elseif fmt == "%%j" then
                    return string.format("%%03d", (M - 1) * 30 + D)
                end
                return real(fmt, t)
            end
        """ % (month, day))

    # X-Ray gives each file its own table and exposes it under the FILE's name.
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
    for fname in ("zzz_seasons_of_the_zone", "sotz_api"):
        src = io.open(os.path.join(SCRIPTS, fname + ".script"), encoding="utf-8").read()
        g[fname] = loader(src, fname, g)
    return lua, g


def F(t, k):
    try:
        return t[k]
    except Exception:
        return None


# --- the contract resolves the way the engine resolves it ------------------------------
def t_namespacing():
    _, g = build()
    assert g.sotz_api is not None, "sotz_api did not publish under its filename"
    assert F(g.sotz_api, "VERSION") == 1, F(g.sotz_api, "VERSION")
    # the API reaches the other script only through its file table
    assert g.sotz_api.temperature() is not None
    assert g.sotz_api.weather() is not None
    assert g.sotz_api.blowout() is not None
    assert g.sotz_api.calendar() is not None
    return "all four accessors resolve across files"


# --- temperature -----------------------------------------------------------------------
def t_curve_shape():
    # coldest near 05:00, warmest near 15:00, and nothing outside the endpoints
    readings = {}
    for h in (0, 3, 5, 9, 12, 15, 18, 21):
        _, g = build(hour=float(h), month=4)
        t = g.sotz_api.temperature()
        readings[h] = F(t, "now")
        assert F(t, "low") <= readings[h] <= F(t, "high"), (h, t)
    coldest = min(readings, key=lambda k: readings[k])
    warmest = max(readings, key=lambda k: readings[k])
    assert coldest == 5, (coldest, readings)
    assert warmest == 15, (warmest, readings)
    return "min at 05:00, max at 15:00, always within the day's band"


def t_rising_flag():
    _, g = build(hour=9.0, month=4)
    assert F(g.sotz_api.temperature(), "rising") is True
    _, g = build(hour=20.0, month=4)
    assert F(g.sotz_api.temperature(), "rising") is False
    return "rising true while climbing, false after the peak"


def t_seasonal():
    _, g = build(hour=12.0, month=1)
    jan = F(g.sotz_api.temperature(), "now")
    _, g = build(hour=12.0, month=7)
    jul = F(g.sotz_api.temperature(), "now")
    assert jan < 5 and jul > 15, (jan, jul)
    assert jul - jan > 15, (jan, jul)
    return "January %d C, July %d C" % (jan, jul)


def t_month_blend():
    # late January must lean toward February, not jump on the 1st
    _, g = build(hour=15.0, month=1, day=15)
    mid = F(g.sotz_api.temperature(), "high")
    _, g = build(hour=15.0, month=1, day=30)
    late = F(g.sotz_api.temperature(), "high")
    # strict: >= would be satisfied by no blending at all, which is the whole thing
    # under test. January's high is -2 mid-month and must lean toward February's -1.
    assert late > mid, (mid, late, "the month is stepping, not sliding")
    return "the month slides rather than steps (%d -> %d)" % (mid, late)


def t_weather_compresses():
    _, g = build(hour=15.0, month=6, cycle="clear")
    clear = g.sotz_api.temperature()
    _, g = build(hour=15.0, month=6, cycle="storm")
    storm = g.sotz_api.temperature()
    cs = F(clear, "high") - F(clear, "low")
    ss = F(storm, "high") - F(storm, "low")
    assert ss < cs, (cs, ss)
    assert F(storm, "high") < F(clear, "high"), (clear, storm)
    return "storm narrows the swing %d -> %d and cools the day" % (cs, ss)


def t_model_is_labelled():
    _, g = build()
    t = g.sotz_api.temperature()
    assert F(t, "source") == "model", F(t, "source")
    assert F(t, "unit") == "C"
    return "reading is labelled a model, not a sensor"


# --- blowout ---------------------------------------------------------------------------
def t_blowout_fraction():
    _, g = build(standing=900, surge_left=4 * HOUR)
    b = g.sotz_api.blowout()
    assert F(b, "tier") == "exact"
    em = F(b, "emission")
    assert F(em, "seconds") == 4 * HOUR, F(em, "seconds")
    # 4h of a 24h period
    assert abs(F(em, "fraction") - 4.0 / 24.0) < 0.01, F(em, "fraction")
    return "exact tier carries seconds and a 0-1 fraction"


def t_blowout_fraction_moves():
    # the control: a nearer emission must give a smaller fraction
    _, g = build(standing=900, surge_left=2 * HOUR)
    near = F(F(g.sotz_api.blowout(), "emission"), "fraction")
    _, g = build(standing=900, surge_left=20 * HOUR)
    far = F(F(g.sotz_api.blowout(), "emission"), "fraction")
    assert near < far, (near, far)
    return "fraction tracks the wait (%.2f near, %.2f far)" % (near, far)


def t_blowout_locked():
    _, g = build(standing=0)
    b = g.sotz_api.blowout()
    assert F(b, "tier") == "locked"
    em = F(b, "emission")
    assert F(em, "seconds") is None and F(em, "band") is None, "locked tier leaked"
    assert F(em, "fraction") is None, "locked tier leaked a gauge position"
    return "locked tier exposes nothing a gauge could read"


def t_blowout_coarse():
    _, g = build(standing=300, surge_left=1 * HOUR)
    b = g.sotz_api.blowout()
    assert F(b, "tier") == "coarse"
    em = F(b, "emission")
    assert F(em, "seconds") is None, "coarse tier leaked the number"
    assert F(em, "band") == "imminent", F(em, "band")
    assert F(em, "fraction") is not None, "coarse tier gave a gauge nothing to sit on"
    return "coarse tier: band and a gauge position, no number"


# --- the cache is real ------------------------------------------------------------------
def t_cache():
    lua, g = build(hour=6.0, month=4, clock_ms=0)
    first = F(g.sotz_api.temperature(), "now")
    # move the game clock a long way WITHOUT advancing the real clock the cache reads
    g.level["get_time_hours"] = lambda: 15
    same = F(g.sotz_api.temperature(), "now")
    assert same == first, (first, same, "cache did not hold")
    # now let the cache expire
    g.time_global = lambda: 9999
    fresh = F(g.sotz_api.temperature(), "now")
    assert fresh != first, (first, fresh, "cache never expired")
    return "held inside the window (%d), recomputed after it (%d)" % (same, fresh)


CASES = [
    ("namespacing", t_namespacing),
    ("curve shape", t_curve_shape),
    ("rising flag", t_rising_flag),
    ("seasonal", t_seasonal),
    ("month blend", t_month_blend),
    ("weather swing", t_weather_compresses),
    ("model labelled", t_model_is_labelled),
    ("blowout fraction", t_blowout_fraction),
    ("fraction moves", t_blowout_fraction_moves),
    ("blowout locked", t_blowout_locked),
    ("blowout coarse", t_blowout_coarse),
    ("cache", t_cache),
]

if __name__ == "__main__":
    bad = 0
    for name, fn in CASES:
        try:
            print("  PASS  %-18s %s" % (name, fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-18s %s" % (name, e))
        except Exception as e:
            bad += 1
            print("  ERROR %-18s %s: %s" % (name, type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
