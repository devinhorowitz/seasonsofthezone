"""Where the real weather comes from: WEATHER_PLACE, the fetcher, the game and the tools.

The place is Chornobyl unless configure.bat picks another. Nothing here talks to the
network: open-meteo's answers are stood in for, and SEASONS_OFFLINE keeps the fetch a save
starts from going out.

  python _tools/test_place.py
"""
import datetime
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_api as ta                                           # noqa: E402
import test_configure as tc                                     # noqa: E402
import test_forecast as tf                                      # noqa: E402

OFFLINE = dict(os.environ, SEASONS_OFFLINE="1")
# open-meteo stood in for inside the process: the fetcher runs as if online
ONLINE = {k: v for k, v in os.environ.items() if k != "SEASONS_OFFLINE"}
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def sandbox(d, config=None):
    """A scratch install with the tools, the fetcher, and the mod's marker script."""
    tc.install(d, config=config)
    tc.with_mod(d)
    shutil.copy2(os.path.join(HERE, "fetch_weather.py"), os.path.join(d, "_tools"))
    scripts = os.path.join(d, "mods", "Seasons of the Zone", "gamedata", "scripts")
    os.makedirs(scripts, exist_ok=True)
    io.open(os.path.join(scripts, "zzz_seasons_of_the_zone.script"), "w").write("-- marker")
    return os.path.join(d, "mods", "Seasons of the Zone", "gamedata", "configs",
                        "season_weather.ltx")


def drive(d, driver, *args, env=None):
    """Run `driver` with the sandbox's tools first on the path; its output."""
    p = os.path.join(d, "drive.py")
    io.open(p, "w", encoding="utf-8").write(
        "import sys\nsys.path.insert(0, %r)\nsys.dont_write_bytecode = True\n"
        % os.path.join(d, "_tools") + driver)
    r = subprocess.run([sys.executable, "-B", p] + list(args), cwd=d, capture_output=True,
                       text=True, encoding="utf-8", errors="replace", env=env or OFFLINE,
                       timeout=120)
    return r.returncode, r.stdout + r.stderr


def sections(path):
    out, here = {}, None
    for line in io.open(path, encoding="cp1251"):
        line = line.split(";")[0].strip()
        if line.startswith("[") and line.endswith("]"):
            here = out.setdefault(line[1:-1], {})
        elif here is not None and "=" in line:
            k, v = line.split("=", 1)
            here[k.strip()] = v.strip()
    return out


# open-meteo, stood in for: a forecast, ten years of daily history, and a place search.
# Each January day of the history has a high of 27 and a low of 19, each July day 22 and
# 12, and the rest a high of 20 and a low of 10.
FAKE_WEB = r'''
import datetime, json
import fetch_weather as fw
asked = []

def history(url):
    d, days = datetime.date(2016, 1, 1), []
    while d.year < 2026:
        days.append(d)
        d += datetime.timedelta(days=1)
    hi = {1: 27.0, 7: 22.0}
    lo = {1: 19.0, 7: 12.0}
    return {"daily": {"time": [x.isoformat() for x in days],
                      "temperature_2m_max": [hi.get(x.month, 20.0) for x in days],
                      "temperature_2m_min": [lo.get(x.month, 10.0) for x in days]}}

def fake_get(url, timeout=12):
    asked.append(url)
    if FAIL.get("all"):
        raise OSError("no network")
    if "geocoding-api" in url:
        return {"results": [
            {"name": "Springfield", "latitude": 37.21533, "longitude": -93.29824,
             "admin1": "Missouri", "country": "United States"},
            {"name": "Springfield", "latitude": 39.80172, "longitude": -89.64371,
             "admin1": "Illinois", "country": "United States"},
            {"name": "Kyiv", "latitude": 50.45466, "longitude": 30.5238,
             "admin1": "Kyiv City", "country": "Ukraine"}]}
    if "archive-api" in url:
        return history(url)
    if FAIL.get("forecast"):
        raise OSError("no network")
    return {"daily": {"time": ["2026-09-25", "2026-09-26"],
                      "temperature_2m_max": [18.4, 19.0], "temperature_2m_min": [7.5, -1.0],
                      "weather_code": [2, 61]}}

FAIL = {}
fw.get = fake_get
'''


@case
def t_a_place_is_checked():
    good = {"name": "Kyiv", "lat": 50.45, "lon": 30.52}
    assert season.place_problems(good) == [], season.place_problems(good)
    assert season.config_problems({}, {}, None, {}, {}, None, None, good) == []
    import fetch_weather
    assert fetch_weather.DEFAULT == season.DEFAULT_PLACE, "two Chornobyls"
    bad = {
        "not a table": ["Kyiv", 50.45, 30.52],
        "no name": {"lat": 1, "lon": 2},
        "an empty name": {"name": "  ", "lat": 1, "lon": 2},
        "a long name": {"name": "x" * (season.PLACE_CHARS + 1), "lat": 1, "lon": 2},
        "a name that breaks the file": {"name": "a;b", "lat": 1, "lon": 2},
        "latitude past the pole": {"name": "a", "lat": 90.5, "lon": 2},
        "longitude past 180": {"name": "a", "lat": 1, "lon": -181},
        "a latitude in quotes": {"name": "a", "lat": "50", "lon": 2},
        "true for a number": {"name": "a", "lat": True, "lon": 2},
        "not a number": {"name": "a", "lat": float("nan"), "lon": 2},
        "a part it doesn't have": {"name": "a", "lat": 1, "lon": 2, "alt": 100},
    }
    for why, place in bad.items():
        got = season.config_problems({}, {}, None, {}, {}, None, None, place)
        assert got and all(p.startswith("WEATHER_PLACE") for p in got), (why, got)
    return "a usable place passes; %d kinds of mistake refused" % len(bad)


@case
def t_the_fetcher_takes_the_weather_there():
    with tempfile.TemporaryDirectory() as d:
        ltx = sandbox(d, config='WEATHER_PLACE = {"name": "São Paulo", "lat": -23.5475, '
                                '"lon": -46.6361}\n')
        driver = FAKE_WEB + r'''
import io, os, sys
sys.argv = ["fetch_weather.py"]
fw.main()
print("ASKED", asked)
asked.clear()
fw.main()
print("AGAIN", len(asked))
cfg = os.path.join(fw.HERE, "seasons_config.py")
io.open(cfg, "w", encoding="utf-8").write(
    'WEATHER_PLACE = {"name": "Kyiv", "lat": 50.4547, "lon": 30.5238}\n')
FAIL["forecast"] = True
fw.main()
'''
        rc, out = drive(d, driver, env=ONLINE)
        assert rc == 0, out
        asked = [l for l in out.splitlines() if l.startswith("ASKED")][0]
        assert "latitude=-23.5475" in asked and "timezone=auto" in asked \
            and "forecast_days=16" in asked, asked
        assert "Weather data by Open-Meteo.com (CC BY 4.0)" in out, out
        assert "Copernicus" in out, "the climate lookup was not credited:\n" + out
        assert "AGAIN 0" in out, "a fresh file for the same place was fetched again:\n" + out
        s = sections(ltx)
        # the last run: Kyiv, whose forecast failed - no weather from Sao Paulo under its name
        assert s["place"]["name"] == "Kyiv" and "weather" not in s, s
        assert s["normals"]["m1"] == "27.0, 19.0" and s["normals"]["m7"] == "22.0, 12.0", s
    with tempfile.TemporaryDirectory() as d:
        ltx = sandbox(d, config='WEATHER_PLACE = {"name": "São Paulo", "lat": -23.5475, '
                                '"lon": -46.6361}\n')
        rc, out = drive(d, FAKE_WEB + 'import sys\nsys.argv = ["x"]\nfw.main()\n',
                        env=ONLINE)
        s = sections(ltx)
        assert s["place"]["name"] == "Sao_Paulo" and s["weather"]["place"] == "Sao_Paulo", s
        assert s["weather"]["high"] == "18.4" and s["weather_next"]["freezing"] == "true", s
        # every day fetched is kept, for the days play.bat isn't run
        assert s["forecast"] == {"2026-09-25": "18.4, 7.5, partly",
                                 "2026-09-26": "19.0, -1.0, rain"}, s["forecast"]
        # Chornobyl again: its normals are the game's own, so none are written
        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w").write(
            "WEATHER_PLACE = None\n")
        rc, out = drive(d, FAKE_WEB + 'import sys\nsys.argv = ["x"]\nfw.main()\n'
                        'print("ASKED", asked)\n', env=ONLINE)
        s = sections(ltx)
        assert s["place"]["name"] == "Chornobyl" and "normals" not in s, s
        assert "latitude=51.2763" in out and "archive-api" not in out, out
    return ("the place's coordinates asked for, its name as the game can show it, its "
            "climate once; a failed fetch for a new place keeps no other place's weather")


@case
def t_the_game_models_the_place_s_own_climate():
    def ini_with(secs):
        def make(lua, name):
            return lua.table_from({
                "section_exist": lambda self, s: s in secs,
                "r_float_ex": lambda self, s, k: None,
                "r_string_ex": lambda self, s, k: secs.get(s, {}).get(k),
            })
        return make

    normals = {"m%d" % m: "20.0, 10.0" for m in range(1, 13)}
    normals["m1"] = "27.1, 18.8"
    own = {"place": {"name": "Sao Paulo"}, "normals": normals}
    lua, g = ta.build(hour=15.0, month=1, cycle="clear", observed=None)
    g.ini_file = lambda name: ini_with(own)(lua, name)
    t = g.sotz_api.temperature()
    assert ta.F(t, "source") == "model" and ta.F(t, "place") == "Sao Paulo", \
        (ta.F(t, "source"), ta.F(t, "place"))
    assert ta.F(t, "high") == 27, ta.F(t, "high")
    # eleven months is not a climate: Chornobyl's own, as before
    short = {"place": {"name": "X"}, "normals": {k: v for k, v in normals.items()
                                                 if k != "m12"}}
    lua, g = ta.build(hour=15.0, month=1, cycle="clear", observed=None)
    g.ini_file = lambda name: ini_with(short)(lua, name)
    t = g.sotz_api.temperature()
    assert ta.F(t, "high") < 5 and ta.F(t, "place") is None, (ta.F(t, "high"),
                                                              ta.F(t, "place"))
    # what the PDA's Forecast page says under the temperature, with the credit
    lua, _, fx = tf.expose("ui_seasons_forecast.script", ["source_line"])
    line = {k: fx.source_line(lua.table_from(v)) for k, v in (
        ("live", {"source": "observed", "place": "Kyiv"}),
        ("modeled here", {"source": "model", "place": "Kyiv"}),
        ("modeled", {"source": "model"}))}
    assert line == {"live": "Live from Kyiv - weather data by Open-Meteo.com",
                    "modeled here": "No station data - modeled on Kyiv's climate "
                                    "(Open-Meteo.com)",
                    "modeled": "No station data - temperature modeled"}, line
    return "January at 27, not Chornobyl's -2; a short table ignored; the page credits it"


def engine_sections(path):
    """season_weather.ltx as the game reads it: r_string_ex drops a value's spaces."""
    out, here = {}, None
    for line in io.open(path, encoding="cp1251"):
        line = line.split(";")[0].strip()
        if line.startswith("[") and line.endswith("]"):
            here = out.setdefault(line[1:-1], {})
        elif "=" in line and here is not None:
            k, v = line.split("=", 1)
            here[k.strip()] = "".join(v.split())
    return out


@case
def t_a_place_s_name_reaches_the_page_whole():
    """The game's reader drops the spaces in a value, so "New York" read as "NewYork", and
    letters with no accent to take off were dropped: Lodz lost its first letter. The file
    writes each space as an underscore, which the game turns back, and those letters as
    plain ones. Chornobyl, the default, is the string table's, in the player's language."""
    import fetch_weather as fw
    got = {}
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "season_weather.ltx")
        was = fw.OUTS, fw.OUT
        fw.OUTS, fw.OUT = [path], path
        try:
            for name in ("New York", "Łódź", "Gießen", "Tromsø"):
                fw.write([], {"name": name, "lat": 1.0, "lon": 2.0}, [(20.0, 10.0)] * 12)
                secs = engine_sections(path)
                lua, g = ta.build(hour=15.0, month=1, cycle="clear", observed=None)
                g.ini_file = lambda n, lua=lua, secs=secs: lua.table_from({
                    "section_exist": lambda self, s: s in secs,
                    "r_float_ex": lambda self, s, k: None,
                    "r_string_ex": lambda self, s, k: secs.get(s, {}).get(k)})
                got[name] = ta.F(g.sotz_api.temperature(), "place")
                assert fw.read_existing("place")["name"] == got[name], got
        finally:
            fw.OUTS, fw.OUT = was
    assert list(got.values()) == ["New York", "Lodz", "Giessen", "Tromso"], got

    def russian(lua, g):
        real = g.game.translate_string
        g.game.translate_string = lambda s: ("Chornobyl-RU" if s == "st_sotz_fc_chornobyl"
                                             else real(s))
    lua, _, fx = tf.expose("ui_seasons_forecast.script", ["source_line"], russian)
    line = [fx.source_line(lua.table_from({"source": "observed", "place": p}))
            for p in ("Chornobyl", "Kyiv")]
    assert line == ["Live from Chornobyl-RU - weather data by Open-Meteo.com",
                    "Live from Kyiv - weather data by Open-Meteo.com"], line
    return "New York, Lodz, Giessen and Tromso whole; Chornobyl in the player's language"


@case
def t_the_command_sets_and_resets_a_place():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        rc, out = tc.run(d, "place", env=OFFLINE)
        assert rc == 0 and "Chornobyl" in out and "the default" in out, out
        rc, out = tc.run(d, "place", "--at", "50.45", "30.52", "--name", "Kyiv", env=OFFLINE)
        assert rc == 0, out
        text = tc.config(d)
        assert 'WEATHER_PLACE = {"name": "Kyiv", "lat": 50.45, "lon": 30.52}' in text, text
        assert "# Where the real weather comes from" in text, text
        tc.accepted(d)
        rc, out = tc.run(d, "place", env=OFFLINE)
        assert "Kyiv (50.45 N, 30.52 E)" in out, out
        for args, says in ((["--at", "95", "0"], "latitude"),
                           (["Kyiv"], "Couldn't reach open-meteo.com"),
                           (["Kyiv", "--at", "1", "2"], "not both")):
            before = tc.config(d)
            rc, out = tc.run(d, "place", *args, env=OFFLINE)
            assert rc == 1 and says in out, (args, out)
            assert tc.config(d) == before, "a refused place changed the file"
        # a preset never carries where you live
        rc, out = tc.run(d, "preset", "save", "Mine", env=OFFLINE)
        saved = io.open(os.path.join(d, "_tools", "presets", "Mine.json"),
                        encoding="utf-8").read()
        assert rc == 0 and "Kyiv" not in saved and "50.45" not in saved, saved
        rc, out = tc.run(d, "place", "--reset", env=OFFLINE)
        assert rc == 0 and "WEATHER_PLACE = None" in tc.config(d), out
    # a place the file can't use is refused by season.py, and a new one replaces it
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config='WEATHER_PLACE = {"name": "Kyiv", "lat": 500, "lon": 30.52}\n')
        rc, out = tc.run(d, "status", tool="season.py", env=OFFLINE)
        assert rc != 0 and "WEATHER_PLACE" in out, out
        rc, out = tc.run(d, "place", "--at", "50.45", "30.52", "--name", "Kyiv", env=OFFLINE)
        assert rc == 0, out
        tc.accepted(d)
    return "set, shown, three mistakes refused, kept out of presets, reset; a bad one replaced"


@case
def t_the_search_lists_and_picks():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        driver = FAKE_WEB + r'''
import configure
sys.argv = ["configure.py", "place"] + sys.argv[1:]
try:
    configure.main()
except SystemExit as e:
    print("EXIT", e.code)
'''
        rc, out = drive(d, driver, "Springfield")
        assert "EXIT 1" in out and "Missouri" in out and "Illinois" in out, out
        assert "--pick" in out and "based on GeoNames" in out, out
        assert "WEATHER_PLACE" not in (tc.config(d) or "") or \
            "WEATHER_PLACE = None" in tc.config(d), "a list of choices changed the file"
        rc, out = drive(d, driver, "Springfield", "--pick", "2")
        assert "EXIT" not in out, out
        assert '"lat": 39.8017' in tc.config(d) and "Springfield" in tc.config(d), out
    return "several found: listed with their states, credited, nothing changed; --pick 2 taken"


@case
def t_the_window_finds_checks_and_credits_a_place():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        driver = FAKE_WEB + r'''
import time
import tkinter as tk
from tkinter import messagebox
said = []
messagebox.showerror = lambda *a, **k: said.append(a[1])
import config_edit as ce
import configure
root = tk.Tk()
root.withdraw()
app = configure.App(root, ce.Calendar(), ce.Install())

def settle(until=lambda: True):
    for _ in range(100):
        root.update()
        if until():
            break
        time.sleep(0.02)

def widgets(w):
    for c in w.winfo_children():
        yield c
        yield from widgets(c)

texts = []
for w in widgets(root):
    try:
        texts.append(str(w.cget("text")))
    except tk.TclError:
        pass
print("CREDITS", "Weather data by Open-Meteo.com" in texts, "based on GeoNames" in texts,
      any("Copernicus" in x for x in texts))
app.place_query.set("Springfield")
app.find_place()
settle(lambda: app.place_found.size() > 0)
print("FOUND", app.place_found.size(), app.place_found.get(1))
app.place_found.selection_clear(0, "end")
app.place_found.selection_set(2)
app.use_found()
print("PLACE", app.cal.place, "|", app.status.cget("text"))
app.select("Winter Pack")
print("BOX", [x for x in (str(w.cget("text")) for w in widgets(app.side)
                          if w.winfo_class() == "TLabelframe") if "weather" in x])
app.check_place()
settle(lambda: app.place_check.cget("text").startswith("Today"))
print("CHECK", app.place_check.cget("text"), app.place_check_credit.winfo_manager())
app.place_lat.set("95")
app.place_lon.set("30")
app.use_coords()
print("REFUSED", any("latitude" in x for x in said), app.cal.place["name"])
print("SAVED", app.save(quiet=True))
root.destroy()
'''
        rc, out = drive(d, driver)
        assert rc == 0, out
        assert "CREDITS True True True" in out, out
        assert "FOUND 3 Springfield - Illinois, United States   39.80 N, 89.64 W" in out, out
        assert "'name': 'Kyiv', 'lat': 50.4547" in out and "weather from Kyiv" in out, out
        assert "BOX ['And on these kinds of weather at Kyiv']" in out, out
        assert "CHECK Today in Kyiv: high 18°C (65°F), low 8°C (46°F), " \
               "partly cloudy. pack" in out, out
        assert "REFUSED True Kyiv" in out and "SAVED True" in out, out
        assert '"name": "Kyiv"' in tc.config(d), tc.config(d)
    return ("credited three ways; found, picked, shown on the Mods tab, checked with its "
            "credit; a bad latitude refused; saved")


@case
def t_weather_days_come_from_the_place_s_own_reading():
    """freezing, thaw and heat come from the file fetch_weather.py leaves - but only when
    it is for the place the config names, and whatever alphabet the place's name is in."""
    import datetime
    today = datetime.date.today().isoformat()

    def ltx(lat, lon, name):
        return ("[place]\r\nname = %s\r\nlat = %.4f\r\nlon = %.4f\r\n\r\n[weather]\r\n"
                "place = %s\r\ndate = %s\r\nhigh = 5.0\r\nlow = -3.0\r\n" % (
                    name, lat, lon, name, today))

    with tempfile.TemporaryDirectory() as d:
        path = sandbox(d, config='WEATHER_PLACE = {"name": "\u041a\u0438\u0457\u0432", '
                                 '"lat": 50.4547, "lon": 30.5238}\n')
        os.makedirs(os.path.dirname(path), exist_ok=True)
        io.open(path, "w", encoding="cp1251", newline="").write(
            ltx(50.4547, 30.5238, "\u041a\u0438\u0457\u0432"))
        rc, out = tc.run(d, "status", tool="season.py", env=OFFLINE)
        assert rc == 0 and "(today: freezing, thaw)" in out, out
        # the file is still Chornobyl's: the config moved, the fetch hasn't run yet
        io.open(path, "w", encoding="cp1251", newline="").write(
            ltx(51.2763, 30.2219, "Chornobyl"))
        rc, out = tc.run(d, "status", tool="season.py", env=OFFLINE)
        assert rc == 0 and "weather from" in out and "(today:" not in out, out
    return "a Cyrillic place's frost counted; another place's reading ignored"


@case
def t_a_launch_without_a_connection_keeps_the_forecast_it_has():
    """play.bat run days after its last fetch, with no connection: today's day comes from
    the forecast the file kept, so a freezing day is still one; with today past the last
    day it kept, no weather day is claimed."""
    import fetch_weather as fw
    today = datetime.date.today()
    with tempfile.TemporaryDirectory() as d:
        path = sandbox(d)
        was = fw.OUTS, fw.OUT
        fw.OUTS, fw.OUT = [path], path
        try:
            # fetched five days ago: [weather] is that day's, and today is row six of 16
            rows = [{"date": (today + datetime.timedelta(days=i - 5)).isoformat(),
                     "high": 4.0 if i == 5 else 15.0, "low": -3.0 if i == 5 else 5.0,
                     "cycle": "clear"} for i in range(16)]
            fw.write(rows)
            rc, out = tc.run(d, "status", tool="season.py", env=OFFLINE)
            assert rc == 0 and "(today: freezing, thaw)" in out, out
            fw.write(rows[:3])              # its last day is three days ago
            rc, out = tc.run(d, "status", tool="season.py", env=OFFLINE)
            assert rc == 0 and "(today:" not in out, out
        finally:
            fw.OUTS, fw.OUT = was
    return "a frost five days after the fetch still counted; none past the last kept day"


if __name__ == "__main__":
    print("  where the real weather comes from")
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
