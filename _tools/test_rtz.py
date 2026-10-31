"""Real Time Zone, DamageZedd's add-on: what this mod does so that the two work together.

The sky's hours play.bat fetches, on the PC's clock; the line in play.bat that RTZ's setup
would add; season.py's report of the hours RTZ reads; RTZ's real weather standing aside on a
day this mod holds the sky; and the read API's answer to the same question. Nothing here
talks to the network, and no RTZ code is run: what RTZ does is stood in for, from its 1.0.1
and 1.0.2 releases.

  python _tools/test_rtz.py
"""
import datetime
import io
import os
import re
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import fetch_weather as fw                                      # noqa: E402
import test_api as ta                                           # noqa: E402
import test_configure as tc                                     # noqa: E402
import test_forecast as tf                                      # noqa: E402
import test_place as tp                                         # noqa: E402

ROOT = os.path.dirname(HERE)
RTZ = "Seasons of the Zone - Real Time Zone (RTZ)"
# the line RTZ 1.0.1's setup_rtz.bat adds to play.bat, and the test it adds it by
RTZ_LINE = 'if exist "_tools\\fetch_rtz_hourly.py" %PY% "_tools\\fetch_rtz_hourly.py"'
OTTAWA = ("; Real Time Zone (RTZ) - Live Hourly Weather Data\n\n[place]\nname = Ottawa\n"
          "lat  = 45.4112\nlon  = -75.6981\n\n[hourly]\n" +
          "".join("%d = clear ; 3.0C\n" % h for h in range(24)))
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def payload(offset_h, first, codes):
    """Open-Meteo's answer, hourly: the place `offset_h` hours from UTC, its hours from
    `first` (a naive datetime in the place's time), one code an hour."""
    times = [(first + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
             for i in range(len(codes))]
    return {"utc_offset_seconds": int(offset_h * 3600),
            "hourly": {"time": times, "weather_code": codes}}


class Eastern(datetime.tzinfo):
    """A PC in New York around 2026's and 2027's clock changes: back from 2:00 EDT to 1:00
    EST on November 1, forward from 2:00 EST to 3:00 EDT on March 14. zoneinfo would need
    tzdata, which Windows doesn't always have."""
    BACK = datetime.datetime(2026, 11, 1, 6, 0)                 # UTC
    FORWARD = datetime.datetime(2027, 3, 14, 7, 0)              # UTC
    EDT, EST = datetime.timedelta(hours=-4), datetime.timedelta(hours=-5)

    def summer(self, utc):
        return utc < self.BACK or utc >= self.FORWARD

    def fromutc(self, dt):
        utc = dt.replace(tzinfo=None)
        wall = utc + (self.EDT if self.summer(utc) else self.EST)
        # the hour after 2:00 EDT is 1:00 again, the second one
        fold = int(self.BACK <= utc < self.BACK + datetime.timedelta(hours=1))
        return wall.replace(tzinfo=self, fold=fold)

    def utcoffset(self, dt):
        wall = dt.replace(tzinfo=None, fold=0)
        edt, est = self.summer(wall - self.EDT), not self.summer(wall - self.EST)
        if edt and est:                                         # the repeated hour
            return self.EST if dt.fold else self.EDT
        return self.EDT if edt else self.EST

    def dst(self, dt):
        return self.utcoffset(dt) - self.EST

    def tzname(self, dt):
        return "EDT" if self.utcoffset(dt) == self.EDT else "EST"


# --- the hours play.bat fetches ------------------------------------------------------------

@case
def t_each_hour_is_the_place_s_sky_at_that_moment():
    # Chornobyl at UTC+3, a PC at UTC-4 at 14:20: its 14:00 is 18:00 UTC, which is 21:00 in
    # Chornobyl. Codes by the place's hour: 0 clear at even hours, 61 rain at odd ones,
    # except 21:00, which is a storm.
    pc = datetime.timezone(datetime.timedelta(hours=-4))
    first = datetime.datetime(2026, 10, 21, 0, 0)
    codes = [95 if i == 21 else (61 if i % 2 else 0) for i in range(72)]
    now = datetime.datetime(2026, 10, 21, 14, 20, tzinfo=pc)
    got = fw.to_hours(payload(3, first, codes), now=now, tz=pc)
    assert len(got) == fw.HOURS, got
    assert got[0] == (14, "storm"), got[:3]
    # the next PC hour is Chornobyl's 22:00 (even, clear), then 23:00 (odd, rain)
    assert got[1] == (15, "clear") and got[2] == (16, "rain"), got[:3]
    assert [h for h, _c in got] == [(14 + i) % 24 for i in range(24)], got
    # the place's own time read as the PC's would put 14:00 on Chornobyl's 14:00 (clear)
    wrong = fw.to_hours(payload(-4, first, codes), now=now, tz=pc)
    assert wrong[0] == (14, "clear"), "the offset changed nothing: " + str(wrong[:2])
    # a place half an hour off the PC's hours: India, UTC+5:30. The PC's 14:00 (18:00 UTC)
    # is 23:30 there, inside the place's 23:00 hour
    half = fw.to_hours(payload(5.5, first, codes), now=now, tz=pc)
    assert half[0] == (14, "rain"), half[:2]
    return "the PC's 14:00 is Chornobyl's 21:00; the place's own clock would give 14:00"


@case
def t_hours_without_values_are_left_out():
    pc = datetime.timezone.utc
    first = datetime.datetime(2026, 10, 21, 0, 0)
    now = datetime.datetime(2026, 10, 21, 10, 0, tzinfo=pc)
    codes = [None if i in (10, 11) else 3 for i in range(48)]
    got = fw.to_hours(payload(0, first, codes), now=now, tz=pc)
    hours = [h for h, _c in got]
    assert 10 not in hours and 11 not in hours and 12 in hours and len(got) == 22, got
    # a forecast that ends early leaves the hours past it out
    short = fw.to_hours(payload(0, first, [3] * 15), now=now, tz=pc)
    assert [h for h, _c in short] == [10, 11, 12, 13, 14], short
    assert fw.to_hours({"daily": {}}, now=now, tz=pc) == []
    assert fw.to_hours({"hourly": {"time": ["bad"], "weather_code": [1]}}, now=now,
                       tz=pc) == []
    return "an hour without a value, past the forecast, or unreadable is left out"


@case
def t_the_nights_the_clock_changes_keep_every_hour_it_shows():
    # Chornobyl at UTC+2, a PC in New York at 13:20 the day before the clock goes back:
    # 25 real hours to 13:00 tomorrow. Codes by the place's hour: clear at even hours, cloudy
    # at odd ones; 07:00 (the first 1:00 here) a storm, 08:00 (the second) snow, and 19:00
    # tomorrow (12:00 here, the 25th hour) fog
    pc = Eastern()
    first = datetime.datetime(2026, 10, 31, 0, 0)
    marks = {31: 95, 32: 71, 43: 45}
    codes = [marks.get(i, 3 if i % 2 else 0) for i in range(72)]
    now = datetime.datetime(2026, 10, 31, 13, 20, tzinfo=pc)
    back = fw.to_hours(payload(2, first, codes), now=now, tz=pc)
    assert [h for h, _c in back] == list(range(13, 24)) + list(range(13)), back
    assert dict(back)[1] == "storm" and dict(back)[12] == "foggy", back
    # from inside the first 1:00, the 24 hours run to 0:00
    inside = fw.to_hours(payload(2, first, codes), now=now.replace(day=1, month=11, hour=1),
                         tz=pc)
    assert [h for h, _c in inside] == list(range(1, 24)) + [0], inside
    # 13:20 the day before it goes forward: 23 real hours to 13:00 tomorrow, and no 2:00.
    # Today's 13:00 is the place's 20:00 (a storm); tomorrow's would be its 19:00 (snow)
    first = datetime.datetime(2027, 3, 13, 0, 0)
    marks = {20: 95, 43: 71}
    codes = [marks.get(i, 3 if i % 2 else 0) for i in range(72)]
    now = datetime.datetime(2027, 3, 13, 13, 20, tzinfo=pc)
    fwd = fw.to_hours(payload(2, first, codes), now=now, tz=pc)
    assert [h for h, _c in fwd] == list(range(13, 24)) + [0, 1] + list(range(3, 13)), fwd
    assert dict(fwd)[13] == "storm", fwd
    return "the night it goes back, 1:00 is the first one and 12:00 is there; forward, no 2:00"


@case
def t_the_file_gets_the_hours_with_the_day():
    rows = [{"date": "2026-10-21", "high": 12.0, "low": 4.0, "cycle": "cloudy"}]
    hours = [(14, "rain"), (15, "storm"), (16, "cloudy")]
    start = datetime.datetime(2026, 10, 21, 14, 0)
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "season_weather.ltx")
        was = fw.OUTS
        fw.OUTS = [out]
        try:
            fw.write(rows, fw.DEFAULT, None, hours, start=start)
            s = tp.sections(out)
            raw = io.open(out, "rb").read()
            fw.write(rows, fw.DEFAULT, None, [])
            bare = tp.sections(out)
            fw.write([], fw.DEFAULT, None, hours)
            none = tp.sections(out)
        finally:
            fw.OUTS = was
    assert s["hourly"] == {"start": "2026-10-21T14:00", "14": "rain", "15": "storm",
                           "16": "cloudy"}, s["hourly"]
    assert s["weather"]["cycle"] == "cloudy", s
    # the game's reader drops spaces in a value; the start has none to drop
    assert b"start        = 2026-10-21T14:00\r\n" in raw, raw[-200:]
    assert "hourly" not in bare and "hourly" not in none, (bare, none)
    return "[hourly] has the start and an hour a line; none without hours or a day"


@case
def t_the_fetcher_writes_the_hours():
    with tempfile.TemporaryDirectory() as d:
        ltx = tp.sandbox(d)
        driver = tp.FAKE_WEB + r'''
import datetime, sys
def hourly_get(url, timeout=12):
    asked.append(url)
    if "archive-api" in url:
        return history(url)
    now = datetime.datetime.now().astimezone()
    off = int(now.utcoffset().total_seconds())
    first = datetime.datetime(now.year, now.month, now.day) - datetime.timedelta(days=1)
    times = [(first + datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M")
             for i in range(96)]
    return {"utc_offset_seconds": off,
            "daily": {"time": [now.date().isoformat()], "temperature_2m_max": [10.0],
                      "temperature_2m_min": [2.0], "weather_code": [3]},
            "hourly": {"time": times, "weather_code": [0 if i % 2 else 61 for i in range(96)]}}
fw.get = hourly_get
sys.argv = ["fetch_weather.py"]
fw.main()
print("ASKED", asked)
print("HOUR", datetime.datetime.now().hour)
sys.argv = ["fetch_weather.py", "--show"]
fw.main()
'''
        rc, out = tp.drive(d, driver, env=tp.ONLINE)
        assert rc == 0, out
        s = tp.sections(ltx)
    asked = [l for l in out.splitlines() if l.startswith("ASKED")][0]
    assert "hourly=weather_code" in asked, asked
    hour = int([l for l in out.splitlines() if l.startswith("HOUR")][0].split()[1])
    h = s.get("hourly", {})
    keys = sorted(int(k) for k in h if k.isdigit())
    # every hour this PC's clock shows from the start to the same one tomorrow: all 24, but
    # 23 the night it goes forward
    start = datetime.datetime.strptime(h.get("start", ""), "%Y-%m-%dT%H:%M")
    walls = [start + datetime.timedelta(hours=i) for i in range(24)]
    shown = sorted(w.hour for w in walls if w.astimezone().replace(tzinfo=None) == w)
    assert keys == shown, (shown, h)
    # the fake's hours, from yesterday's midnight: odd ones clear, even ones rain
    want = "clear" if (hour + 24) % 2 else "rain"
    assert h[str(hour)] == want, (hour, h[str(hour)])
    assert h["start"].endswith("T%02d:00" % hour), h["start"]
    assert "hour by hour: %d hours from" % len(shown) in out, out
    return "play.bat's fetch asks for the hours and writes the clock's next 24, from this one"


# --- play.bat ---------------------------------------------------------------------------

def rtz_setup(raw):
    """RTZ 1.0.1's install_hook on play.bat's bytes: the line goes in after the weather
    fetch unless the file names its fetcher already. The new bytes, or None for untouched."""
    nl = b"\r\n" if b"\r\n" in raw else b"\n"
    hook = RTZ_LINE.encode()
    if b"fetch_rtz_hourly.py" not in raw:
        target = b'%PY% "_tools\\fetch_weather.py"'
        if target in raw:
            return raw.replace(target, target + nl + hook, 1)
    return None


@case
def t_play_bat_carries_rtz_s_line():
    raw = io.open(os.path.join(ROOT, "play.bat"), "rb").read()
    lines = raw.decode("cp1252").split("\r\n")
    fetch = lines.index('%PY% "_tools\\fetch_weather.py"')
    after = [l for l in lines[fetch + 1:] if not l.startswith("REM")]
    assert after[0] == RTZ_LINE, after[:2]
    assert rtz_setup(raw) is None, "RTZ's setup would still edit play.bat"
    # the control: the same file without the line is edited, at the same place
    bare = raw.replace(RTZ_LINE.encode() + b"\r\n", b"")
    edited = rtz_setup(bare)
    assert edited is not None and edited.count(RTZ_LINE.encode()) == 1, "control"
    # both go through the block that cmd reads whole, which must stay below
    assert lines.index(RTZ_LINE) < lines.index("set \"FAILED=\""), "after the setup block"
    return "the line RTZ's setup adds is there, so the setup leaves play.bat alone"


# --- what season.py reports -------------------------------------------------------------

def rtz_install(d, on=True, own=None, fetcher=False, days_old=0.0, sky=None, version="1.0.1"):
    """RTZ in MO2; its main script logs `version` as RTZ's do, or nothing when it is None."""
    mods = list(tc.MODS) + [(RTZ, on, ["scripts/rtz_main.script"])]
    tc.install(d, mods=mods)
    if version is not None:
        io.open(os.path.join(d, "mods", RTZ, "gamedata", "scripts", "rtz_main.script"), "w",
                encoding="utf-8").write(
            '    printf_rtz("Initializing Real Time Zone (RTZ) v%s...")\n' % version)
    if own is not None:
        p = os.path.join(d, "mods", RTZ, "gamedata", "configs", "rtz_weather.ltx")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8").write(own)
        if days_old:
            t = os.path.getmtime(p) - days_old * 86400
            os.utime(p, (t, t))
    if fetcher:
        io.open(os.path.join(d, "_tools", "fetch_rtz_hourly.py"), "w").write("# RTZ's")
    if sky is not None:
        p = os.path.join(d, "mods", "Seasons of the Zone", "gamedata", "configs",
                         "season_weather.ltx")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="cp1251").write(sky)


def report(d):
    rc, out = tc.run(d, "status", tool="season.py")
    assert rc == 0, out
    row = [l for l in out.splitlines() if l.strip().startswith("Real Time Zone")]
    bangs = [l for l in out.splitlines() if l.startswith("  ! ") and "Real Time Zone" in l]
    notes = [l for l in out.splitlines() if l.startswith("  - ") and "Real Time Zone" in l]
    return (row[0] if row else None), bangs, notes


@case
def t_the_report_names_rtz_s_sample_day():
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=OTTAWA)
        row, bangs, notes = report(d)
    assert row and "its own hours of the sky, for Ottawa" in row, row
    assert len(bangs) == 1, bangs
    b = bangs[0]
    for want in ("Ottawa", "Chornobyl", os.path.join("mods", RTZ, "gamedata", "configs",
                                                     "rtz_weather.ltx"), "setup_rtz.bat"):
        assert want in b, (want, b)
    return "RTZ's own day for Ottawa is named, with the file to delete and the setup to run"


@case
def t_a_fetcher_or_seasons_hours_leave_nothing_to_fix():
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=OTTAWA, fetcher=True)
        row, bangs, _n = report(d)
    assert row and "refreshed at each launch" in row and not bangs, (row, bangs)
    sky = "[place]\nname = Chornobyl\nlat = 51.2763\nlon = 30.2219\n[hourly]\n14 = rain\n"
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, sky=sky)
        row, bangs, notes = report(d)
    assert row and "the hours of the sky play.bat fetches, for Chornobyl" in row, row
    assert not bangs and not notes, (bangs, notes)
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d)
        row, bangs, notes = report(d)
    assert not bangs and len(notes) == 1 and "no hours yet" in notes[0], (bangs, notes)
    return "its fetcher, or Seasons' hours, is a line with nothing to fix"


@case
def t_a_stale_file_for_this_place_is_named():
    here = OTTAWA.replace("Ottawa", "Chornobyl").replace("45.4112", "51.2763").replace(
        "-75.6981", "30.2219")
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=here, days_old=3)
        _r, bangs, _n = report(d)
    assert len(bangs) == 1 and "3 days old" in bangs[0], bangs
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=here)
        row, bangs, _n = report(d)
    assert row and not bangs, (row, bangs)
    return "three days old is named; today's, for this place, is fine"


@case
def t_no_line_without_rtz_on():
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, on=False, own=OTTAWA)
        row, bangs, notes = report(d)
    assert row is None and not bangs and not notes, (row, bangs, notes)
    with tempfile.TemporaryDirectory() as d:
        tc.install(d)
        row, _b, _n = report(d)
    assert row is None, row
    return "disabled or missing, RTZ gets no line"


def sky(hours_ago=1):
    """season_weather.ltx with hours that start `hours_ago` hours back, on this PC's clock, as
    play.bat's fetch writes them; RTZ 1.0.3 reads them for a day from their start."""
    start = datetime.datetime.now() - datetime.timedelta(hours=hours_ago)
    return ("[place]\nname = Chornobyl\nlat = 51.2763\nlon = 30.2219\n[hourly]\nstart = %s\n"
            "14 = rain\n" % start.strftime("%Y-%m-%dT%H:00"))


SKY = sky()


def own_today(day=None):
    """RTZ's own file as its 1.0.2 fetcher writes it: for Chornobyl, dated `day`."""
    return ("[place]\nname = Chornobyl\nlat  = 51.2763\nlon  = 30.2219\ndate = %s\n\n[hourly]\n"
            % (day or datetime.date.today().isoformat()) +
            "".join("%d = cloudy ; 9.0C\n" % h for h in range(24)))


@case
def t_from_1_0_2_rtz_reads_seasons_hours_first():
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=OTTAWA, sky=SKY, version="1.0.2")
        row, bangs, notes = report(d)
    assert row and "the hours of the sky play.bat fetches, for Chornobyl" in row, row
    assert not bangs and not notes, (bangs, notes)
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=own_today(), fetcher=True, sky=SKY, version="1.0.2")
        row, bangs, _n = report(d)
    assert row and "play.bat fetches" in row and not bangs, (row, bangs)
    return "Ottawa's day or a fresh file of its own, RTZ 1.0.2 reads Seasons' hours"


@case
def t_from_1_0_2_its_own_file_counts_only_the_day_it_was_written():
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, own=own_today(), version="1.0.2")
        row, bangs, notes = report(d)
    assert row and "its own hours of the sky, for Chornobyl" in row, row
    assert not bangs and not notes, (bangs, notes)
    for own in (OTTAWA, own_today("2026-01-02")):
        with tempfile.TemporaryDirectory() as d:
            rtz_install(d, own=own, days_old=3, version="1.0.2")
            row, bangs, notes = report(d)
        assert row and "play.bat fetches" in row, row
        assert not bangs and len(notes) == 1 and "no hours yet" in notes[0], (bangs, notes)
    return "today's own file is read without Seasons' hours; Ottawa's or an old one isn't"


@case
def t_rtz_s_version_comes_from_its_main_script():
    # 1.0.1 and anything earlier read their own file first; 1.0.2, a later release, or one
    # that doesn't say read Seasons' hours first
    for version, own_first in (("1.0.0", True), ("1.0.1", True), ("1.0.2", False),
                               ("1.0.10", False), (None, False)):
        with tempfile.TemporaryDirectory() as d:
            rtz_install(d, own=OTTAWA, sky=SKY, version=version)
            row, bangs, _n = report(d)
        assert row, version
        assert ("for Ottawa" in row) == own_first, (version, row)
        assert (len(bangs) == 1) == own_first, (version, bangs)
    return "1.0.0 and 1.0.1 read their own; 1.0.2, 1.0.10 and an unlabeled one read Seasons'"


@case
def t_from_1_0_3_hours_a_day_past_their_start_are_said():
    """RTZ 1.0.3 reads Seasons' hours for a day from their start, then its own file of
    today, else the sky modeled from the forecast; the report named play.bat's hours all the
    same. 1.0.2 reads them at any age, and fresh ones are read by both."""
    old = sky(hours_ago=30)
    start = old.split("start = ")[1].split("\n")[0].replace("T", " ")
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, sky=old, own=own_today(), version="1.0.3")
        row, bangs, notes = report(d)
    assert row and "its own hours of the sky, for Chornobyl" in row and not bangs, (row, bangs)
    assert len(notes) == 1 and "(%s) are over a day old" % start in notes[0] \
        and "its own, dated today" in notes[0], notes
    for version in ("1.0.3", "1.0.10", None):
        with tempfile.TemporaryDirectory() as d:
            rtz_install(d, sky=old, version=version)
            row, bangs, notes = report(d)
        assert row and "the sky modeled from the day's forecast, for Chornobyl" in row, (
            version, row)
        assert not bangs and len(notes) == 1 and "models the sky from the day's forecast" \
            in notes[0], (version, bangs, notes)
    for text, version in ((sky(), "1.0.3"), (old, "1.0.2")):
        with tempfile.TemporaryDirectory() as d:
            rtz_install(d, sky=text, own=own_today(), version=version)
            row, bangs, notes = report(d)
        assert row and "play.bat fetches" in row and not bangs and not notes, (version, row)
    return "a day old: its own of today, or the forecast's model, said with the start; " \
        "fresh ones, or 1.0.2, read as before"


@case
def t_from_1_0_7_its_own_file_is_dated_by_its_place():
    """RTZ 1.0.7 dates its own file by its place's clock and keeps the place's UTC offset
    beside the date: near the place's midnight its today is not this PC's."""
    now = time.time()
    pc = time.strftime("%Y-%m-%d", time.localtime(now))
    off = next(h * 3600 for h in range(-12, 15)
               if time.strftime("%Y-%m-%d", time.gmtime(now + h * 3600)) != pc)
    there = time.strftime("%Y-%m-%d", time.gmtime(now + off))
    dated = own_today(there)
    with_offset = dated.replace("date = %s\n" % there, "date = %s\nutc_offset = %d\n" % (there, off))
    old = sky(hours_ago=30)
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, sky=old, own=with_offset, version="1.0.7")
        row, bangs, _n = report(d)
    assert row and "its own hours of the sky, for Chornobyl" in row and not bangs, (row, bangs)
    with tempfile.TemporaryDirectory() as d:
        rtz_install(d, sky=old, own=dated, version="1.0.7")
        row, _b, _n = report(d)
    assert row and "modeled from the day's forecast" in row, \
        "control: without the offset, the place's date reads as another day: %s" % row
    return "its own file of the place's today read as today, wherever this PC's day is"


# --- RTZ's real weather on a held day ---------------------------------------------------

PIN = ('local real = os.date\n'
       'os.date = function(fmt, t)\n'
       '  if fmt == "*t" and t == nil then\n'
       '    return {year = 2026, month = %d, day = %d, hour = 12, min = 0, sec = 0}\n'
       '  end\n'
       '  return real(fmt, t)\n'
       'end\n')
TAIL = "return rtz_bridge, weather_held, weather_driver, remembrance_tick"


def game(month, day, mcm=None, rtz=True, saved=None):
    """The script with RTZ's settings reader stood in for: it answers True to everything
    and records what it was asked."""
    lua, g, fns = tf.build(standing=0, surge_left=tf.HOUR, psi_left=tf.HOUR,
                           weather="cloudy", tail=TAIL, disk=None if rtz else False)
    lua.execute(PIN % (month, day))
    vals = dict(mcm or {})
    g.ui_mcm = lua.table_from({"get": lambda p: vals.get(str(p).split("/")[-1])})
    asked = []
    # a Lua function, as RTZ's is: the bridge wraps nothing else
    as_lua = lua.eval("function(f) return function(...) return f(...) end end")
    g.rtz_mcm = lua.table_from({"get_config": as_lua(lambda *a: (asked.append(a), True)[1])})
    store = dict(saved or {})
    g.axr_main = lua.table_from({"config": lua.table_from({
        "r_value": lambda self, sec, key, typ: store.get(key)})})
    return lua, g, fns, asked


@case
def t_rtz_stands_aside_on_a_held_day():
    lua, g, (bridge, held, _drv, _tick), asked = game(4, 26)
    assert bridge() is True and bridge() is True
    get = g.rtz_mcm.get_config
    assert held() == "clear"
    assert get("enable_real_weather") is False, "a remembrance day kept RTZ's weather on"
    assert get("enabled") is True and get("rest_duration", "x") is True
    assert len(asked) == 2 and tuple(asked[-1]) == ("rest_duration", "x"), asked
    # an anniversary holds a storm, and RTZ stands aside for it too
    lua, g, (bridge, held, _drv, _tick), _a = game(3, 20)
    bridge()
    assert held() == "storm" and g.rtz_mcm.get_config("enable_real_weather") is False
    # the control: an ordinary day leaves RTZ's switch to RTZ, wrapped only once
    lua, g, (bridge, held, _drv, _tick), asked = game(4, 27)
    bridge()
    bridge()
    assert held() is None and g.rtz_mcm.get_config("enable_real_weather") is True
    assert len(asked) == 1, asked
    return "on April 26 and March 20 its real weather reads off; on the 27th it's RTZ's"


@case
def t_a_hold_that_is_off_or_fails_leaves_rtz_alone():
    lua, g, (bridge, held, _drv, _tick), _a = game(4, 26, mcm={"rem_weather": False})
    bridge()
    assert held() is None and g.rtz_mcm.get_config("enable_real_weather") is True
    # March 20 with no storm cycle in the weathers: the hold fails, and RTZ comes back
    lua, g, (bridge, held, _drv, tick), _a = game(3, 20, mcm={"rem_anniversary": False,
                                                              "rem_ann_artefacts": False})
    bridge()
    assert g.rtz_mcm.get_config("enable_real_weather") is False, "before the tick"
    tick()
    assert held() is None and g.rtz_mcm.get_config("enable_real_weather") is True
    # the control: a storm cycle there, the hold works and RTZ stays aside
    lua, g, (bridge, held, _drv, tick), _a = game(3, 20, mcm={"rem_anniversary": False,
                                                              "rem_ann_artefacts": False})
    method = lua.eval("function(f) return function(self, ...) return f(...) end end")
    wm = g.level_weathers.get_weather_manager()
    wm.presets = lua.table_from({"storm": lua.table_from({"w_storm1": True})})
    wm.select_weather = method(lambda at_once: None)
    wm.abs_schedule_minute = method(lambda: 600)
    g.random_key_table = lambda t: list(t.keys())[0]
    g.level["get_time_factor"] = lambda: 6
    bridge()
    tick()
    assert held() == "storm" and g.rtz_mcm.get_config("enable_real_weather") is False
    return "MCM's switch off, or a storm the weathers lack, gives RTZ the day back"


@case
def t_without_rtz_nothing_is_wrapped():
    lua, g, (bridge, held, drv, _tick), asked = game(4, 26, rtz=False)
    # a held day, so a wrapper would answer False
    assert bridge() is False and held() == "clear"
    assert g.rtz_mcm.get_config("enable_real_weather") is True, "wrapped without the file"
    assert drv() is None
    return "no rtz_mcm.script, no wrapper and no driver"


@case
def t_the_driver_is_read_off_the_disk():
    _l, _g, (_b, _h, drv, _t), _a = game(4, 27)
    assert drv() == "rtz"
    _l, _g, (_b, _h, drv, _t), _a = game(4, 27, saved={"rtz/enable_real_weather": False})
    assert drv() is None, "RTZ's weather saved off still named"
    _l, _g, (_b, _h, drv, _t), _a = game(4, 27, saved={"rtz/enabled": False})
    assert drv() is None
    return "installed and on is rtz; either saved switch off is not"


# --- the read API -----------------------------------------------------------------------

@case
def t_the_api_says_what_is_held():
    lua, g = ta.build(month=4, day=26)
    assert g.sotz_api.weather_hold() == "clear"
    w = g.sotz_api.weather()
    assert ta.F(w, "held") == "clear" and ta.F(w, "driver") is None, (ta.F(w, "held"),)
    lua, g = ta.build(month=4, day=27)
    g.getFS = lambda: lua.table_from({"exist": lambda self, alias, name: True})
    assert g.sotz_api.weather_hold() is None
    w = g.sotz_api.weather()
    assert ta.F(w, "held") is None and ta.F(w, "driver") == "rtz", ta.F(w, "driver")
    return "April 26 is held clear with no driver; the 27th, with RTZ, is driven by it"


if __name__ == "__main__":
    print("  Real Time Zone")
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
