"""A PDA message as the weather turns, when MCM asks for one.

The sky is named as the Forecast page names it, so the message says snow or sleet in the
winters and nothing for a change the page wouldn't show. Nothing for the sky a game loads
under, during an emission or a psi storm, or underground, and nothing at all with the switch
off, which it is as it ships, or with every PDA message silenced. The game side runs under
LuaJIT through test_calendar's harness.

  python _tools/test_weather_news.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import test_calendar as tcal                                    # noqa: E402

CASES = []
ON = {"seasons_zone/main/pda_weather": True}
HOLD = 120000               # ms a new sky holds before it is told (WX_HOLD_MS)


def case(fn):
    CASES.append(fn)
    return fn


def sky(mcm=ON, strings=None):
    """The game with a weather manager whose cycle the test moves, and what falls now; tell()
    moves them, ticks, waits `wait` ms (a hold, unless given) and ticks again, and gives what
    the PDA was sent. tell.wm is the manager, tell.state["wm"] what get_weather_manager()
    hands back, and tell.clock["t"] the time_global() the ticks read."""
    lua, g = tcal.build(2026, 10, 8, mcm=mcm, strings=strings)
    clock = {"t": 0}
    g.time_global = lambda: clock["t"]
    state = {"falls": "rain", "wfx": False}
    wm = lua.table_from({"cycle": "clear"})
    state["wm"] = wm
    g.level_weathers = lua.table_from({"get_weather_manager": lambda: state["wm"]})
    g.level["is_wfx_playing"] = lambda: state["wfx"]
    g.zzz_seasons_of_the_zone.falls = lambda: state["falls"]
    sent = []
    g.CreateTimeEvent = lambda ev, act, delay, fn, *a: fn()
    g.news_manager = lua.table_from({"send_tip": lambda a, msg, *r: sent.append(msg)})

    def tell(cycle=None, falls=None, wfx=False, under=False, wait=HOLD):
        if cycle:
            wm["cycle"] = cycle
        if falls:
            state["falls"] = falls
        state["wfx"] = wfx
        g.level_weathers["bLevelUnderground"] = under
        del sent[:]
        g.zzz_seasons_of_the_zone.weather_tick()
        if wait:
            clock["t"] += wait
            g.zzz_seasons_of_the_zone.weather_tick()
        return list(sent)
    tell.wm, tell.state, tell.lua, tell.g, tell.clock = wm, state, lua, g, clock
    return tell


@case
def t_the_sky_turning_is_told():
    tell = sky()
    script = [
        ("clear", None, []),                                # the sky a game loads under
        ("clear", None, []),                                # no change
        ("cloudy", None, ["It has clouded over."]),
        ("rain", None, ["Rain is setting in."]),
        ("storm", None, ["A storm is breaking."]),
        ("rain", None, ["The storm is easing."]),
        ("clear", None, ["The rain has stopped. The sky is clearing."]),
        ("partly", None, ["Clouds are gathering."]),
        ("cloudy", None, ["It has clouded over."]),
        ("partly", None, ["The clouds are breaking up."]),
        ("foggy", None, ["Fog is rolling in."]),
        ("cloudy", None, ["The fog is lifting."]),
        ("rain", None, ["Rain is setting in."]),
        ("cloudy", None, ["The rain has stopped."]),
        ("foggy", None, ["Fog is rolling in."]),
        ("rain", None, ["The fog is lifting. Rain is setting in."]),
        ("foggy", None, ["The rain has stopped. Fog is rolling in."]),
        ("storm", None, ["The fog is lifting. A storm is breaking."]),
        ("clear", None, ["The storm has passed. The sky is clearing."]),
        ("storm", None, ["A storm is breaking."]),
        ("cloudy", None, ["The storm has passed."]),
    ]
    for cycle, falls, want in script:
        got = tell(cycle, falls)
        assert got == want, (cycle, falls, got, want)
    return "%d turns: setting in, breaking, easing, passing, clearing, gathering, fog" % len(
        script)


@case
def t_the_winters_say_snow_or_sleet():
    tell = sky()
    script = [
        ("cloudy", "snow", []),
        ("rain", "snow", ["It has started to snow."]),
        ("storm", "snow", ["A snowstorm is setting in."]),
        ("rain", "snow", ["The storm is easing."]),
        ("clear", "snow", ["The snow has stopped. The sky is clearing."]),
        ("rain", "sleet", ["Sleet is falling."]),
        ("storm", "sleet", ["A sleet storm is setting in."]),
        ("cloudy", "sleet", ["The sleet has stopped."]),
        # No Rain in Winter with nothing in its place: a rain sky is overcast, no change,
        # and a storm is dry, so it passes rather than its rain stopping
        ("rain", "none", []),
        ("storm", "none", ["A storm is breaking."]),
        ("cloudy", "none", ["The storm has passed."]),
    ]
    for cycle, falls, want in script:
        got = tell(cycle, falls)
        assert got == want, (cycle, falls, got, want)
    return "snow, a snowstorm easing, sleet and a sleet storm; a dry rain sky says nothing"


@case
def t_a_new_sky_is_told_once_it_has_held_two_minutes():
    """Atmospherics' planner can stop the rain for a few minutes and bring it back. A new sky
    is told once it has held for two minutes, against the sky last told, so a pause like that
    says nothing, and a sky that came and went on the way isn't named."""
    tell = sky()
    tell("rain", wait=0)                                # the sky the game loads under
    assert tell("cloudy", wait=HOLD - 5000) == [], "told before the new sky had held"
    assert tell("rain") == [], "a pause in the rain was told"
    assert tell("cloudy") == ["The rain has stopped."]
    assert tell("cloudy") == [], "a sky already told was told again"
    # a sky on the way restarts the wait, and isn't named
    assert tell("foggy", wait=HOLD - 10000) == []
    assert tell("clear", wait=15000) == [], "the wait didn't restart for the next sky"
    assert tell(wait=HOLD) == ["The sky is clearing."], "the fog that came and went was named"
    # a minute to the millisecond
    assert tell("partly", wait=HOLD - 1) == []
    assert tell(wait=1) == ["Clouds are gathering."]
    return "a pause says nothing; told once, two minutes on, against the sky last told"


@case
def t_the_pause_seen_in_game_says_nothing():
    """The test game of 2026-10-17: the rain stopped for 63 s, six game minutes, and came back.
    A one-minute hold still told both; two minutes tells neither."""
    tell = sky()
    tell("rain", wait=0)                                # the sky the game loaded under
    got = []
    for _ in range(13):                                 # cloudy, seen every 5 s for 60 s
        tell.clock["t"] += 5000
        got += tell("cloudy", wait=0)
    tell.clock["t"] += 3000
    for _ in range(40):                                 # and the rain back for good
        got += tell("rain", wait=0)
        tell.clock["t"] += 5000
    assert got == [], "the pause was told: %s" % got
    return "63 s of cloud between rains: nothing"


@case
def t_the_first_sky_seen_is_the_one_a_game_loads_under():
    """Until there is a manager with a sky there is nothing to compare with, and the first
    sky it shows is the one the game came in on."""
    tell = sky()
    tell.state["wm"] = None
    assert tell() == [], "told with no weather manager"
    tell.g.level_weathers["get_weather_manager"] = tell.lua.eval(
        "function() error('not built yet') end")
    assert tell() == [], "told with a manager that failed"
    tell.g.level_weathers["get_weather_manager"] = lambda: tell.state["wm"]
    tell.state["wm"] = tell.wm
    tell.wm["cycle"] = None
    assert tell() == [], "told with a manager that has no sky yet"
    assert tell("rain") == [], "the sky the game loaded under was told"
    assert tell("clear") == ["The rain has stopped. The sky is clearing."]
    return "no manager, a failing one, no sky yet: quiet; then the first sky says nothing"


@case
def t_quiet_through_an_emission_and_underground():
    tell = sky()
    tell("clear")
    assert tell("storm", wfx=True) == [], "told during an emission"
    assert tell("rain", wfx=True) == []
    # after it, the sky is told against the one before it
    assert tell("rain") == ["Rain is setting in."]
    assert tell("clear", under=True) == [], "told underground"
    assert tell("clear") == ["The rain has stopped. The sky is clearing."]
    return "nothing while an emission plays or underground; told after, against the sky before"


@case
def t_off_as_it_ships_and_silenced_with_the_rest():
    tell = sky(mcm={})
    tell("clear")
    assert tell("rain") == [], "a message with the switch as it ships"
    tell = sky(mcm={"seasons_zone/main/pda_weather": True, "seasons_zone/main/pda_news": False})
    tell("clear")
    assert tell("rain") == [], "a message with every PDA message silenced"
    # the switch turned on mid-game: the next change is told, not the one before it
    mcm = {}
    tell = sky(mcm=mcm)
    tell("clear")
    tell("rain")
    mcm["seasons_zone/main/pda_weather"] = True
    assert tell("rain") == [], "the change before the switch went on was told"
    assert tell("clear") == ["The rain has stopped. The sky is clearing."]
    # and off and on again: what changed while it was off isn't told either
    mcm["seasons_zone/main/pda_weather"] = False
    assert tell("rain") == []
    mcm["seasons_zone/main/pda_weather"] = True
    assert tell("rain") == [], "a change made while the switch was off was told"
    assert tell("cloudy") == ["The rain has stopped."]
    return "off as it ships; silenced; on mid-game or again, only the changes after it"


@case
def t_a_sky_no_message_is_written_for_says_nothing():
    tell = sky()
    tell("clear")
    assert tell("dream") == [], "a cycle another pack adds was told"
    assert tell("clear") == ["The sky is clearing."], "the way back was not told plainly"
    # and weather_message() on its own says nothing for a sky turning into itself
    z = tell.g.zzz_seasons_of_the_zone
    for s in ("clear", "rain", "storm", "snow", "sleet"):
        assert z.weather_message(s, s) is None, "%s to %s: %r" % (s, s, z.weather_message(s, s))
    return "an unknown cycle says nothing, the way back says only the sky, a sky into itself nothing"


@case
def t_the_switch_is_on_the_main_page_and_off_as_it_ships():
    """MCM's default and the script's agree: off. Either one on would send the messages to
    everyone who never opens MCM."""
    import re
    import test_mcm_strings as tm
    found = [(page, body) for page, body in tm.calls(tm.read(tm.MCM))
             if re.match(r'\{\s*id\s*=\s*"pda_weather"', body)]
    assert len(found) == 1, "%d pda_weather options in the MCM script" % len(found)
    page, body = found[0]
    assert page == "main", "pda_weather is on page_%s" % page
    for field in ('type = "check"', "val = 1", "def = false"):
        assert field in body, "pda_weather lacks %s: %s" % (field, body)
    main = tm.read(os.path.join(tm.GD, "scripts", "zzz_seasons_of_the_zone.script"))
    asks = re.findall(r'mcm\("pda_weather",\s*(\w+)\)', main)
    assert asks == ["false"], "the script reads pda_weather with defaults %s" % asks
    return "a check on the Main page; off in MCM and in the script"


CONSOLE = """
function fake_console()
    local c, store = {}, {}
    function c:execute(cmd)
        local name, val = cmd:match('^(%S+)%s+(.*)$')
        store[name] = val
    end
    function c:get_string(name) return store[name] end
    return c
end"""


@case
def t_the_update_loop_looks_every_five_seconds():
    """The game reaches weather_tick() through its update loop, on the five-second tick the
    season's turns are read on. One that fails is logged once and stops nothing else."""
    lua, g = tcal.build(2026, 10, 8, mcm=ON)
    lua.execute(CONSOLE)
    con = g.fake_console()
    g.get_console = lambda: con
    g.CreateTimeEvent = lambda *a: None
    hooks = {}
    g.RegisterScriptCallback = lambda name, fn: hooks.setdefault(name, []).append(fn)
    z = g.zzz_seasons_of_the_zone
    z.on_game_start()
    clock = {"t": 0}
    g.time_global = lambda: clock["t"]
    looked, turned = [], []
    z.weather_tick = lambda: looked.append(clock["t"])
    z.turn_tick = lambda: turned.append(clock["t"])
    for fn in hooks["actor_on_first_update"]:
        fn()

    def play(ms, step=1000):
        for _ in range(ms // step):
            clock["t"] += step
            for fn in hooks["actor_on_update"]:
                fn()
    play(20000)
    gaps = set(b - a for a, b in zip(looked, looked[1:]))
    assert len(looked) == 4 and gaps == {5000}, "looked at %s" % looked
    assert looked == turned, (looked, turned)
    z.weather_tick = lua.eval("function() error('no sky') end")
    del tcal.LOG[:]
    n = len(turned)
    play(20000)
    failed = [line for line in tcal.LOG if "weather messages failed" in line]
    assert len(failed) == 1 and "no sky" in failed[0], tcal.LOG
    assert len(turned) - n == 4, "the turns stopped being read: %s" % turned[n:]
    return "every 5 s with the turns; a failure logged once, the turns read on"


@case
def t_every_message_is_written_in_english_and_russian():
    """The ids are put together as the sky turns, so no check of the script's text sees them:
    each one the code can ask for is in both tables, and in Russian a turn reads in Russian."""
    from test_strings import table
    eng, rus = table("eng"), table("rus")
    ids = ["clear", "partly", "partly_gather", "cloudy", "foggy", "rain", "storm", "snow",
           "snowstorm", "sleet", "sleetstorm", "stopped_rain", "stopped_snow",
           "stopped_sleet", "storm_passed", "fog_lifting", "easing"]
    for i in ids:
        for name, t in (("English", eng), ("Russian", rus)):
            assert "st_sotz_news_wx_" + i in t, "no %s st_sotz_news_wx_%s" % (name, i)
    tell = sky(strings=dict(eng, **rus))
    tell("clear")
    got = tell("rain")
    assert got == [rus["st_sotz_news_wx_rain"]], [g.encode("unicode_escape") for g in got]
    got = tell("clear")
    assert got == [rus["st_sotz_news_wx_stopped_rain"] + " " + rus["st_sotz_news_wx_clear"]], \
        [g.encode("unicode_escape") for g in got]
    return "%d ids in English and Russian; a turn in Russian" % len(ids)


@case
def t_the_page_and_the_messages_name_skies_alike():
    """sky_of() here and ui_seasons_forecast's sky() name every cycle the same way under
    every fall, so a message never names a sky the page doesn't show."""
    import test_forecast as tf
    lua, g = tcal.build(2026, 10, 8)
    _, _, fx = tf.expose("ui_seasons_forecast.script", ["sky"])
    n = 0
    for cycle in ("clear", "partly", "cloudy", "foggy", "rain", "storm", "dream"):
        for falls in ("rain", "snow", "sleet", "none", None):
            a = g.zzz_seasons_of_the_zone.sky_of(cycle, falls)
            b = fx.sky(cycle, falls)
            assert a == b, (cycle, falls, a, b)
            n += 1
    return "%d cycle and fall pairs named alike" % n


if __name__ == "__main__":
    print("  a PDA message as the weather turns")
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
