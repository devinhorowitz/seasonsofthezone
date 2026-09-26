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

from lua_runtime import LuaRuntime, NAME as LUA_NAME
from test_strings import install

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

HOUR = 3600


def build(hour=12.0, cycle="clear", month=None, day=15, standing=900,
          surge_left=4 * HOUR, psi_left=9 * HOUR, clock_ms=0, observed=None,
          units=None):
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
    install(lua, g)
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
    mcm_vals = {"forecast": True, "forecast_coarse": 200, "forecast_exact": 700}
    if units is not None:
        mcm_vals["units"] = units
    g.ui_mcm = lua.table_from({
        "get": lambda p: mcm_vals.get(str(p).split("/")[-1]),
    })
    # ini_file, section-aware like the engine's. `observed` is a dict of the [weather]
    # section, or None for "the file is not there".
    def make_ini(name):
        if "season_weather" not in str(name) or observed is None:
            return lua.table_from({
                "section_exist": lambda self, s: False,
                "r_float_ex": lambda self, s, k: None,
                "r_string_ex": lambda self, s, k: None,
            })
        sec = {"weather": observed}
        if isinstance(observed, dict) and observed.get("_next"):
            sec["weather_next"] = observed["_next"]
        return lua.table_from({
            "section_exist": lambda self, s: s in sec,
            "r_float_ex": lambda self, s, k: (
                float(sec.get(s, {}).get(k)) if sec.get(s, {}).get(k) is not None
                else None),
            "r_string_ex": lambda self, s, k: (
                str(sec.get(s, {}).get(k)) if sec.get(s, {}).get(k) is not None
                else None),
        })
    g.ini_file = make_ini

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
    assert F(em, "band") == "WITHIN 2 HOURS", F(em, "band")
    # and the gauge position must come from THAT bracket, not the fallback. When the
    # brackets were renamed this mapping was left behind and every coarse reading landed
    # on 0.70 - a needle near "quiet" beside a panel reading WITHIN 2 HOURS.
    assert F(em, "fraction") is not None, "coarse tier gave a gauge nothing to sit on"
    assert F(em, "fraction") < 0.2, F(em, "fraction")
    return "coarse tier: bracket, a matching gauge position, no number"


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


# --- the real Zone's numbers -----------------------------------------------------------
def _pinned(month, day):
    """The date the harness pins os.date to, as the ltx would spell it.

    build() overrides os.date to a fixed month and day, so a reading stamped with the
    real calendar date looks days old to the code under test - which is what made the
    first version of these cases fail against perfectly good code.
    """
    import datetime
    return "%04d-%02d-%02d" % (datetime.date.today().year, month, day)


def t_observed_used():
    obs = {"high": 14.5, "low": 7.8, "cycle": "rain", "date": _pinned(9, 15),
           "place": "Chornobyl"}
    _, g = build(hour=15.0, month=9, cycle="clear", observed=obs)
    t = g.sotz_api.temperature()
    assert F(t, "source") == "observed", F(t, "source")
    assert F(t, "place") == "Chornobyl"
    # clear weather leaves the swing alone, so the endpoints survive to the page
    assert F(t, "high") == 14 or F(t, "high") == 15, F(t, "high")
    assert F(t, "low") == 8, F(t, "low")
    # the control: without the file the same call must fall back and say so
    _, g = build(hour=15.0, month=9, cycle="clear", observed=None)
    assert F(g.sotz_api.temperature(), "source") == "model"
    return "observed endpoints used, and marked observed"


def t_observed_stale():
    obs = {"high": 14.5, "low": 7.8, "cycle": "rain", "date": "2020-01-05",
           "place": "Chornobyl"}
    _, g = build(hour=15.0, month=9, observed=obs)
    t = g.sotz_api.temperature()
    assert F(t, "source") == "model", "a five-year-old reading was used"
    return "a reading from another day is ignored"


def t_freezing_flags():
    obs = {"high": 2.0, "low": -6.0, "cycle": "snow", "date": _pinned(1, 15),
           "place": "Chornobyl"}
    # 05:00 is the daily minimum, so `now` sits at the low
    _, g = build(hour=5.0, month=1, cycle="clear", observed=obs)
    cold = g.sotz_api.temperature()
    assert F(cold, "frost") is True, "frost false on a day with a sub-zero low"
    assert F(cold, "freezing") is True, F(cold, "now")
    # 15:00 is the maximum: the day still dips below zero, but right now it does not
    _, g = build(hour=15.0, month=1, cycle="clear", observed=obs)
    warm = g.sotz_api.temperature()
    assert F(warm, "frost") is True, "frost should describe the whole day"
    assert F(warm, "freezing") is False, F(warm, "now")
    return "frost is the day, freezing is the moment"


def t_no_frost_when_mild():
    obs = {"high": 14.5, "low": 7.8, "cycle": "rain", "date": _pinned(9, 15),
           "place": "Chornobyl"}
    _, g = build(hour=5.0, month=9, observed=obs)
    t = g.sotz_api.temperature()
    assert F(t, "frost") is False and F(t, "freezing") is False, (F(t, "low"), F(t, "now"))
    return "a mild day raises neither flag"


def t_tomorrow():
    obs = {"high": 14.5, "low": 7.8, "cycle": "rain", "date": _pinned(9, 15),
           "place": "Chornobyl",
           "_next": {"high": 2.0, "low": -4.0, "cycle": "snow", "date": _pinned(9, 16)}}
    _, g = build(hour=12.0, month=9, observed=obs)
    tm = g.sotz_api.tomorrow()
    assert F(tm, "high") == 2 and F(tm, "low") == -4, (F(tm, "high"), F(tm, "low"))
    assert F(tm, "cycle") == "snow", F(tm, "cycle")
    assert F(tm, "frost") is True, "a -4 low did not raise frost"
    # the control: today must NOT come back as tomorrow. Both sections carry the same
    # key names, and a flat read hands over the wrong day looking perfectly valid.
    today = g.sotz_api.temperature()
    assert F(today, "low") != F(tm, "low"), "today and tomorrow returned the same low"
    # and with no fetched file at all there is no modelled stand-in
    _, g = build(hour=12.0, month=9, observed=None)
    assert g.sotz_api.tomorrow() is None, "invented a tomorrow with no observations"
    # a file from an earlier day holds that day's tomorrow, which is today or before
    for stale in (_pinned(9, 15), _pinned(9, 10)):
        _, g = build(hour=12.0, month=9, observed=dict(obs, _next=dict(obs["_next"],
                                                                       date=stale)))
        assert g.sotz_api.tomorrow() is None, "an old file's tomorrow was shown: " + stale
    return "tomorrow read from its own section, no modelled fallback, none from an old file"


def t_units_both_shapes():
    """MCM hands a list option back as a string OR as an index, depending.

    Reading only for the string is what made the page's degrees button work once and
    then stop: every later click saw something that was not "fahrenheit" and wrote
    "fahrenheit" again. Both shapes have to mean the same thing.
    """
    obs = {"high": 10.0, "low": 0.0, "cycle": "clear", "date": _pinned(9, 15),
           "place": "Chornobyl"}
    seen = {}
    for label, val in (("default", None), ("string c", "celsius"),
                       ("string f", "fahrenheit"), ("index 1", 1)):
        _, g = build(hour=15.0, month=9, cycle="clear", observed=obs, units=val)
        seen[label] = F(g.sotz_api.temperature(), "unit")
    assert seen["default"] == "C", seen
    assert seen["string c"] == "C", seen
    assert seen["string f"] == "F", seen
    assert seen["index 1"] == "F", seen
    return "C by default and for 'celsius'; F for 'fahrenheit' and for index 1"


def t_units_convert():
    obs = {"high": 10.0, "low": 0.0, "cycle": "clear", "date": _pinned(9, 15),
           "place": "Chornobyl"}
    _, g = build(hour=5.0, month=9, cycle="clear", observed=obs, units="celsius")
    c = g.sotz_api.temperature()
    _, g = build(hour=5.0, month=9, cycle="clear", observed=obs, units="fahrenheit")
    f = g.sotz_api.temperature()
    assert F(c, "low") == 0 and F(f, "low") == 32, (F(c, "low"), F(f, "low"))
    assert F(c, "high") == 10 and F(f, "high") == 50, (F(c, "high"), F(f, "high"))
    # zero is a property of water, not of the unit: a 0 C low is frost in both
    assert F(c, "frost") is True and F(f, "frost") is True, "frost changed with the unit"
    return "0/10 C reads 32/50 F, and frost is unchanged by the unit"


def t_sky_moves_the_base():
    """The observation is the BASE; the in-game sky moves it.

    Real world decides what kind of day it is, Atmospherics decides what standing in it
    costs you - so a storm has to read colder than clear sky off the same station
    numbers, and base_high/base_low have to keep saying what the station actually said.
    """
    obs = {"high": 14.0, "low": 4.0, "cycle": "rain", "date": _pinned(9, 15),
           "place": "Chornobyl"}
    _, g = build(hour=15.0, month=9, cycle="clear", observed=obs)
    clear = g.sotz_api.temperature()
    _, g = build(hour=15.0, month=9, cycle="storm", observed=obs)
    storm = g.sotz_api.temperature()

    # the station's own numbers survive intact under either sky
    assert F(clear, "base_high") == F(storm, "base_high") == 14, (
        F(clear, "base_high"), F(storm, "base_high"))
    assert F(clear, "base_low") == F(storm, "base_low") == 4

    # but standing in the storm is colder, and the page can say by how much
    assert F(storm, "now") < F(clear, "now"), (F(clear, "now"), F(storm, "now"))
    assert F(storm, "sky_shift") < 0, F(storm, "sky_shift")
    assert F(clear, "sky_shift") == 0, F(clear, "sky_shift")
    return "storm reads %d, clear reads %d, base holds at 14/4" % (
        F(storm, "now"), F(clear, "now"))


def t_bands_and_thaw():
    def at(hi, lo, hour):
        obs = {"high": hi, "low": lo, "cycle": "clear", "date": _pinned(1, 15),
               "place": "Chornobyl"}
        _, g = build(hour=hour, month=1, cycle="clear", observed=obs)
        return g.sotz_api.temperature()

    hard = at(-2.0, -9.0, 15.0)        # never gets above zero
    thaw = at(6.0, -3.0, 15.0)         # froze, now above
    warm = at(24.0, 14.0, 15.0)
    assert F(hard, "frost") is True and F(hard, "thaw") is False, "a hard freeze thawed"
    assert F(thaw, "frost") is True and F(thaw, "thaw") is True, "freeze-thaw missed"
    assert F(hard, "band") == "freezing", F(hard, "band")
    assert F(warm, "band") == "warm", F(warm, "band")
    assert F(warm, "frost") is False and F(warm, "thaw") is False
    return "bands name the moment; thaw needs a freeze AND a rise above zero"


def t_alert_hook():
    """`alert` is what a wearable device pulses on, so it must be gated like the rest.

    A device re-deriving it from `seconds` would drift out of step with the page the
    moment either threshold moved, which is the whole reason it is published.
    """
    obs = {"high": 10.0, "low": 4.0, "cycle": "clear", "date": _pinned(9, 15),
           "place": "Chornobyl"}
    _, g = build(hour=12.0, month=9, observed=obs, standing=900,
                 surge_left=1 * HOUR, psi_left=30 * HOUR)
    b = g.sotz_api.blowout()
    assert F(F(b, "emission"), "alert") is True, "no alert an hour out"
    assert F(F(b, "psi"), "alert") is False, "alert 30 hours out"

    _, g = build(hour=12.0, month=9, observed=obs, standing=0,
                 surge_left=1 * HOUR, psi_left=1 * HOUR)
    b = g.sotz_api.blowout()
    assert F(b, "tier") == "locked"
    assert F(F(b, "emission"), "alert") is False, "a locked tier leaked an alert"
    return "published, gated by tier, and false when the tier may not know"


def t_kept_forecast_and_climate():
    """play.bat's last fetch keeps 16 days: with the file days old, today's and tomorrow's
    come from those rows and say the day they were fetched; past the last row, the climate
    model takes over. climate() answers for any day of the year with no file at all, and
    nil for a day that doesn't exist."""
    import datetime
    year = datetime.date.today().year

    def with_file(g, lua, secs):
        g.ini_file = lambda name: lua.table_from({
            "section_exist": lambda self, s: s in secs,
            "line_exist": lambda self, s, k: k in secs.get(s, {}),
            "r_float_ex": lambda self, s, k: (float(secs[s][k]) if k in secs.get(s, {})
                                              else None),
            "r_string_ex": lambda self, s, k: secs.get(s, {}).get(k)})
    secs = {"weather": {"date": _pinned(9, 10), "high": "30.0", "low": "20.0",
                        "cycle": "clear", "place": "Kyiv", "fetched_at": "%d-09-1007:30" % year},
            "forecast": {_pinned(9, 15): "3.0,-2.0,snow", _pinned(9, 16): "1.0,-5.0,snow"}}
    lua, g = build(hour=12.0, month=9)
    with_file(g, lua, secs)
    t = g.sotz_api.temperature()
    assert F(t, "source") == "observed" and F(t, "base_low") == -2 \
        and F(t, "fetched") == _pinned(9, 10) and F(t, "date") == _pinned(9, 15), \
        (F(t, "source"), F(t, "base_low"), F(t, "fetched"), F(t, "date"))
    tm = g.sotz_api.tomorrow()
    assert F(tm, "low") == -5 and F(tm, "date") == _pinned(9, 16), (F(tm, "low"), F(tm, "date"))
    # past the last kept day: the model, and no tomorrow
    lua, g = build(hour=12.0, month=9, day=20)
    with_file(g, lua, secs)
    t = g.sotz_api.temperature()
    assert F(t, "source") == "model" and g.sotz_api.tomorrow() is None, F(t, "source")
    # climate(), with no file at all
    lua, g = build(hour=12.0, month=9, observed=None)
    jan, feb30, bad = (g.sotz_api.climate(1, 15), g.sotz_api.climate(2, 30),
                       g.sotz_api.climate(13, 1))
    assert (F(jan, "high"), F(jan, "low")) == (-2, -8) and F(jan, "unit") == "C" \
        and feb30 is None and bad is None, (F(jan, "high"), F(jan, "low"), feb30, bad)
    # the last of March is more than half April's, whatever day it is now
    mar31 = g.sotz_api.climate(3, 31)
    assert (F(mar31, "high"), F(mar31, "low")) == (10, 0), (F(mar31, "high"), F(mar31, "low"))
    # what the Forecast page says of a day from a fetch days ago
    import test_forecast as tf
    lua2, _g2, fx = tf.expose("ui_seasons_forecast.script", ["source_line"])
    line = fx.source_line(lua2.table_from({"source": "observed", "place": "Kyiv",
                                           "date": _pinned(9, 15), "fetched": _pinned(9, 10)}))
    assert line == "Kyiv's forecast from Sep 10 - weather data by Open-Meteo.com", line
    return "today's and tomorrow's from the kept rows, the model after them; climate any day"


CASES = [
    ("namespacing", t_namespacing),
    ("kept forecast", t_kept_forecast_and_climate),
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
    ("observed used", t_observed_used),
    ("observed stale", t_observed_stale),
    ("freezing flags", t_freezing_flags),
    ("mild day", t_no_frost_when_mild),
    ("tomorrow", t_tomorrow),
    ("units both shapes", t_units_both_shapes),
    ("units convert", t_units_convert),
    ("sky moves the base", t_sky_moves_the_base),
    ("bands and thaw", t_bands_and_thaw),
    ("alert hook", t_alert_hook),
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
