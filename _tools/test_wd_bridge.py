"""Run the integration snippet out of docs/WEARABLE-DEVICES.md.

The proposal asks another author to paste code into their mod. The least that owes them
is that the code is known to work - so this lifts the `get_blowout_sense` block straight
out of the markdown and runs it against the real sotz_api under a real Lua interpreter,
with wd_sensor_pulse stubbed exactly as Wearable Devices defines it.

Reading it out of the document rather than keeping a copy is the point. A snippet that
drifts from the tested version is worse than no snippet, because it looks checked.

  python _tools/test_wd_bridge.py
"""
import io
import os
import re
import sys

from lua_runtime import LuaRuntime, NAME as LUA_NAME
from test_strings import install

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "WEARABLE-DEVICES.md")
SCRIPTS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

HOUR = 3600


def snippet():
    """The first lua block in the proposal that defines get_blowout_sense."""
    body = io.open(DOC, encoding="utf-8").read()
    for block in re.findall(r"```lua\n(.*?)```", body, re.S):
        if "get_blowout_sense" in block:
            return block
    raise AssertionError("no get_blowout_sense block in %s" % DOC)


def build(standing=900, surge_left=4 * HOUR, with_sotz=True):
    """sotz_api as the bridge would meet it, plus wd_sensor_pulse as WD defines it."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()

    g.printf = lambda *a: None
    g.time_global = lambda: 0
    g.level = lua.table_from({"get_time_hours": lambda: 12,
                              "get_time_minutes": lambda: 0,
                              "name": lambda: "l01_escape"})
    g.db = lua.table_from({"actor": lua.table_from({"id": lambda self: 0})})
    g.relation_registry = lua.table_from(
        {"community_goodwill": lambda faction, aid: standing})
    opts = {"alife/event/emission_frequency": 24,
            "alife/event/psi_storm_frequency": 48}
    g.ui_options = lua.table_from({"get": lambda k: opts.get(k)})
    g.game = lua.table_from({"get_game_time": lambda: lua.table_from({
        "diffSec": lambda self, other: other["elapsed"] if other is not None else 0,
        "get": lambda self, *a: 2026})})
    install(lua, g)
    surge = lua.table_from({
        "_delta": 24 * HOUR,
        "last_surge_time": lua.table_from({"elapsed": 24 * HOUR - surge_left})})
    psi = lua.table_from({
        "_delta": 48 * HOUR,
        "last_psi_storm_time": lua.table_from({"elapsed": 48 * HOUR - 30 * HOUR})})
    g.surge_manager = lua.table_from({"SurgeManager": surge,
                                      "get_surge_manager": lambda: surge})
    g.psi_storm_manager = lua.table_from({"PsiStormManager": psi,
                                          "get_psi_storm_manager": lambda: psi})
    g.level_weathers = lua.table_from({})
    g.ini_file = lambda name: lua.table_from({
        "section_exist": lambda self, s: False,
        "r_float_ex": lambda self, s, k: None,
        "r_string_ex": lambda self, s, k: None})
    g.ui_mcm = lua.table_from({"get": lambda p: {
        "forecast": True, "forecast_coarse": 200, "forecast_exact": 700,
    }.get(str(p).split("/")[-1])})
    g.alife = lambda: None
    g.axr_main = lua.table_from({})
    g.RegisterScriptCallback = lambda *a: None
    g.device = lambda: lua.table_from({"width": 1920, "height": 1080})

    loader = lua.eval("""
        function (src, name, shared)
            local env = setmetatable({}, {__index = shared})
            local f, err = load(src, name, "t", env)
            if not f then error(name .. ": " .. tostring(err)) end
            f()
            return env
        end
    """)
    for fname in ("zzz_seasons_of_the_zone", "sotz_api"):
        src = io.open(os.path.join(SCRIPTS, fname + ".script"), encoding="utf-8").read()
        g[fname] = loader(src, fname, g)
    if not with_sotz:
        g.sotz_api = None            # the mod simply is not installed

    # wd_sensor_pulse as Wearable Devices defines it: get_delay verbatim, and a new()
    # that hands the cfg back so the test can call the sense function the bridge wired
    # into it. get_blowout_sense is a `local` in the snippet - correct style, and it
    # means the only way in is the same one WD uses.
    g.wd_sensor_pulse = lua.table_from({
        "get_delay": lambda fraction, lo, hi: hi - (hi - lo) * fraction,
        "new": lambda cfg: cfg})

    bridge = loader(snippet(), "wd_sensor_blowout", g)
    cfg = bridge.new(lua.table_from({"group": "test"}))
    return lua, g, cfg


def F(t, k):
    try:
        return t[k]
    except Exception:
        return None


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_silent_without_the_mod():
    _, _, cfg = build(with_sotz=False)
    assert cfg.sense() is None, "the sensor fired with no mod installed"
    return "no Seasons of the Zone -> nil, so the sensor stops"


@case
def t_silent_when_withheld():
    # standing 0 is CLASSIFIED: the ecologists tell this player nothing at all
    _, _, cfg = build(standing=0, surge_left=1 * HOUR)
    assert cfg.sense() is None, "the sensor fired for a locked player"
    return "withheld by the ecologists -> nil, even an hour out"


@case
def t_quiet_when_far_off():
    _, _, cfg = build(standing=900, surge_left=20 * HOUR)
    assert cfg.sense() is None, "ticking 20 hours out"
    return "20 hours out -> nil, nothing worth ticking about"


@case
def t_ticks_faster_as_it_closes():
    seen = {}
    for label, left in (("far", 10 * HOUR), ("near", 4 * HOUR), ("imminent", 1 * HOUR)):
        _, _, cfg = build(standing=900, surge_left=left)
        s = cfg.sense()
        assert s is not None, "%s produced no reading" % label
        seen[label] = F(s, "delay")
    assert seen["far"] > seen["near"] > seen["imminent"], seen
    assert seen["imminent"] >= 120, ("the pulse must not outrun MIN_REPEAT", seen)
    return "delay falls %d -> %d -> %d ms as the emission closes" % (
        seen["far"], seen["near"], seen["imminent"])


@case
def t_works_at_the_limited_tier_too():
    # standing 200 is LIMITED: a bracket rather than a number, but the fraction is there
    _, _, cfg = build(standing=200, surge_left=1 * HOUR)
    s = cfg.sense()
    assert s is not None, "no pulse at LIMITED an hour out"
    assert F(s, "delay") < 1000, F(s, "delay")
    return "LIMITED drives the pulse from its bracket, without ever exposing the hour"


if __name__ == "__main__":
    print("  running the snippet from docs/WEARABLE-DEVICES.md")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-26s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-26s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-26s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
