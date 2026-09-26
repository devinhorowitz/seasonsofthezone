"""Pull the real weather and leave it where the game can read it.

Seasons of the Zone already runs its calendar on real dates. This closes the loop on
temperature: instead of climate normals, the day's high and low come from what the place
is actually doing - Chornobyl, unless configure.bat has picked another. The in-game curve
between them is still modeled - the game's day is accelerated and its sky is
Atmospherics', so only the endpoints are real.

What leaves the machine: the latitude and longitude of that place. No account, no key, no
identifiers. The response is about 500 bytes. For a place picked in configure.bat, the
first run there also asks for its last ten years of daily highs and lows, once, so the
game can model its climate on days without a connection.

This must never be the reason a launch fails. Every failure path - no network, a slow
endpoint, a malformed response, a read-only disk - leaves the previous file alone and
exits 0. Without a usable file the game falls back to climate normals and says so.

  python fetch_weather.py              fetch if the cache is stale
  python fetch_weather.py --force      fetch regardless
  python fetch_weather.py --offline    do nothing, for testing the fallback
  python fetch_weather.py --show       print what the game would read
"""
import datetime
import io
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request

import lang
from lang import _, ngettext, pgettext

# what it says can be in any language, and play.bat's window or a pipe may not take it
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
MODS = os.path.join(os.path.dirname(HERE), "mods")
# The mod is found by its main script, not its folder name: MO2 names a mod after the
# archive it was installed from.
MARKER = ("gamedata", "scripts", "zzz_seasons_of_the_zone.script")
REL = ("gamedata", "configs", "season_weather.ltx")


def outputs():
    """season_weather.ltx in each installed copy of the mod. There should be one; writing
    every copy keeps whichever one MO2 loads current."""
    try:
        names = sorted(os.listdir(MODS))
    except OSError:
        return []
    return [os.path.join(MODS, n, *REL) for n in names
            if os.path.isfile(os.path.join(MODS, n, *MARKER))]


OUTS = outputs()
OUT = OUTS[0] if OUTS else None

# Chornobyl. Slavutych (51.5194, 30.7511) is the nearest inhabited town and reads within
# a degree of this; the Zone itself is the more honest anchor for a mod about the Zone.
DEFAULT = {"name": "Chornobyl", "lat": 51.2763, "lon": 30.2219}

URL = ("https://api.open-meteo.com/v1/forecast"
       "?latitude=%s&longitude=%s"
       "&daily=temperature_2m_max,temperature_2m_min,weather_code"
       "&timezone=auto&forecast_days=%d")
# as many days ahead as Open-Meteo gives: the game reads each day's row while it lasts, so a
# launch without play.bat, or without a connection, keeps the real forecast that long
FORECAST_DAYS = 16
SEARCH_URL = ("https://geocoding-api.open-meteo.com/v1/search"
              "?name=%s&count=%d&language=en&format=json")
ARCHIVE_URL = ("https://archive-api.open-meteo.com/v1/archive"
               "?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
               "&daily=temperature_2m_max,temperature_2m_min&timezone=auto")
NORMAL_YEARS = 10

REFRESH_HOURS = 6
TIMEOUT = 12

# Open-Meteo's data is CC BY 4.0, credited wherever it is shown: here, in configure.bat
# and on the PDA. Its place search is built on GeoNames, and its history on Copernicus'
# ERA5 reanalysis. credit() and the two after it say so in the player's language.
SOURCE = "Open-Meteo.com"
LINK = "https://open-meteo.com/"

# the longest name the Forecast page has room for, beside its credit
PLACE_CHARS = 24

# WMO codes, collapsed onto the cycle names Atmospherics uses. Only ever advisory: the
# sky the player is standing under is the game's, not the real one's.
WMO = [
    ({0}, "clear"), ({1, 2}, "partly"), ({3}, "cloudy"),
    ({45, 48}, "foggy"),
    ({51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82}, "rain"),
    ({71, 73, 75, 77, 85, 86}, "snow"),
    ({95, 96, 99}, "storm"),
]


def get(url, timeout=TIMEOUT):
    """JSON from open-meteo. SEASONS_OFFLINE set stands for no connection, as the tests
    and anyone who wants nothing sent use it."""
    if os.environ.get("SEASONS_OFFLINE"):
        raise OSError("offline")
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


def code_to_cycle(code):
    for codes, name in WMO:
        if code in codes:
            return name
    return "cloudy"


def sky_word(cycle):
    """A cycle name as the lines here show it, in the player's language; one this doesn't
    know, as it is."""
    return {"clear": pgettext("sky", "clear"),
            # translators: partly cloudy
            "partly": pgettext("sky", "partly"),
            "cloudy": pgettext("sky", "cloudy"), "foggy": pgettext("sky", "foggy"),
            "rain": pgettext("sky", "rain"), "snow": pgettext("sky", "snow"),
            "storm": pgettext("sky", "storm")}.get(cycle, cycle)


def credit():
    # translators: %s is Open-Meteo.com; CC BY 4.0 is the data's license, as it is
    return _("Weather data by %s (CC BY 4.0)") % SOURCE


def places_credit():
    # translators: %s is Open-Meteo.com; GeoNames and CC BY 4.0 stay as they are
    return _("Places from %s, based on GeoNames (CC BY 4.0)") % SOURCE


def climate_credit():
    # translators: %s is Open-Meteo.com; CC BY 4.0 is the data's license, as it is
    return _("Climate from %s (CC BY 4.0); contains modified Copernicus Climate Change "
             "Service information") % SOURCE


# --- the place ----------------------------------------------------------------------------

def is_default(place):
    return (abs(place["lat"] - DEFAULT["lat"]) < 1e-3
            and abs(place["lon"] - DEFAULT["lon"]) < 1e-3)


def configured_place():
    """(place, note): the place seasons_config.py names as WEATHER_PLACE, or Chornobyl. A
    config that can't be read, or a WEATHER_PLACE season.py refuses, falls back to
    Chornobyl, with a note saying so; season.py itself says what is wrong."""
    try:
        sys.path.insert(0, HERE)
        import season
        mod, err = season._load_config()
        value = getattr(mod, "WEATHER_PLACE", None) if mod else None
        if err:
            return DEFAULT, _("seasons_config.py can't be read, so the weather is "
                              "Chornobyl's")
        if value is None:
            return DEFAULT, None
        if season.place_problems(value):
            return DEFAULT, _("WEATHER_PLACE can't be used, so the weather is Chornobyl's")
        return {"name": value["name"].strip(), "lat": float(value["lat"]),
                "lon": float(value["lon"])}, None
    except Exception:
        return DEFAULT, None


# letters that take no accent off, and have no letter of cp1251 to stand for them
PLAIN = {"\u0142": "l", "\u0141": "L", "\u00df": "ss", "\u00f8": "o", "\u00d8": "O",
         "\u00e6": "ae", "\u00c6": "Ae", "\u0153": "oe", "\u0152": "Oe", "\u0111": "d",
         "\u0110": "D", "\u00f0": "d", "\u00d0": "D", "\u00fe": "th", "\u00de": "Th",
         "\u0131": "i", "\u0127": "h", "\u0126": "H", "\u0167": "t", "\u0166": "T"}


def shown_name(name):
    """The place's name as the game can show it: in cp1251, with accents taken off the
    letters it lacks, and nothing that would break the file. An underscore is a space:
    the file writes a space as one, since the game's reader drops spaces."""
    out = []
    for ch in unicodedata.normalize("NFC", name):
        try:
            ch.encode("cp1251")
            out.append(ch)
        except UnicodeEncodeError:
            out.append(PLAIN.get(ch) or unicodedata.normalize("NFKD", ch).encode(
                "ascii", "ignore").decode())
    text = " ".join(re.sub(r"[;\[\]=_]", " ", "".join(out)).split())
    return text[:PLACE_CHARS].strip() or "?"


def search(name, count=8):
    """Places open-meteo's geocoder knows by `name`, best first: [{name, lat, lon, where}].
    Raises when it can't be reached; the caller says so."""
    data = get(SEARCH_URL % (urllib.parse.quote(name.strip()), count))
    out = []
    for p in data.get("results") or []:
        try:
            lat, lon = round(float(p["latitude"]), 4), round(float(p["longitude"]), 4)
        except (KeyError, TypeError, ValueError):
            continue
        where = [x for x in (p.get("admin1"), p.get("country")) if x and x != p.get("name")]
        out.append({"name": str(p.get("name") or "?"), "lat": lat, "lon": lon,
                    "where": ", ".join(where)})
    return out


def normals(lat, lon, years=NORMAL_YEARS):
    """The place's mean daily high and low for each month, over the last `years` whole
    years on open-meteo's record: ((high, low), ...) for January to December. Raises when
    the record can't be had or is too thin to trust."""
    last = datetime.date.today().year - 1
    d = get(ARCHIVE_URL % (lat, lon, "%d-01-01" % (last - years + 1), "%d-12-31" % last),
            timeout=30)["daily"]
    sums = [[0.0, 0.0, 0] for _ in range(12)]
    for day, hi, lo in zip(d["time"], d["temperature_2m_max"], d["temperature_2m_min"]):
        if hi is None or lo is None:
            continue
        m = int(day[5:7]) - 1
        sums[m][0] += float(hi)
        sums[m][1] += float(lo)
        sums[m][2] += 1
    if any(n < 28 for _, _, n in sums):
        raise ValueError("too few days on record")
    return tuple((round(h / n, 1), round(l / n, 1)) for h, l, n in sums)


# --- the file -----------------------------------------------------------------------------

def read_existing(section="weather"):
    """One section of the ltx.

    Section-aware on purpose: [weather] and [weather_next] carry the same key names, so a
    flat read silently hands back tomorrow's numbers labeled as today's. The Lua side
    reads this file too and has to make the same distinction.
    """
    if not OUT or not os.path.exists(OUT):
        return {}
    out, here = {}, None
    try:
        for line in io.open(OUT, encoding="cp1251"):
            line = line.split(";")[0].strip()
            if line.startswith("[") and line.endswith("]"):
                here = line[1:-1].strip()
                continue
            if here == section and "=" in line:
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip()
                out[k] = v.replace("_", " ") if k in ("name", "place") else v
    except Exception:
        return {}
    return out


def same_place(place):
    """Is the file there for `place`? One from before places were set has no [place]
    section, and is Chornobyl's."""
    there = read_existing("place")
    try:
        return (abs(float(there["lat"]) - place["lat"]) < 1e-3
                and abs(float(there["lon"]) - place["lon"]) < 1e-3)
    except (KeyError, ValueError):
        return bool(read_existing()) and is_default(place)


def kept_normals():
    """The [normals] in the file there, when it has all twelve months."""
    n = read_existing("normals")
    out = []
    for m in range(1, 13):
        try:
            hi, lo = (float(x) for x in n["m%d" % m].split(","))
        except (KeyError, ValueError):
            return None
        out.append((hi, lo))
    return tuple(out)


def is_fresh(existing):
    stamp = existing.get("fetched_at")
    if not stamp:
        return False
    try:
        when = datetime.datetime.strptime(stamp, "%Y-%m-%d %H:%M")
    except ValueError:
        return False
    age = (datetime.datetime.now() - when).total_seconds() / 3600.0
    return 0 <= age < REFRESH_HOURS


def fetch(place=DEFAULT):
    return get(URL % (place["lat"], place["lon"], FORECAST_DAYS))


def to_rows(payload):
    d = payload["daily"]
    rows = []
    for i, day in enumerate(d["time"]):
        rows.append({
            "date": day,
            "high": float(d["temperature_2m_max"][i]),
            "low": float(d["temperature_2m_min"][i]),
            "cycle": code_to_cycle(int(d["weather_code"][i])),
        })
    return rows


HEAD = """; Seasons of the Zone - the real weather, at the place set in configure.bat.
;
; Generated by _tools/fetch_weather.py, which play.bat runs before launching. Do not
; hand-edit: the next run overwrites it. Deleting it is safe - the game falls back to
; climate normals and marks the reading as modeled.
;
; Only the day's endpoints are real. The curve between them is modeled, because the
; game's day is accelerated and its sky belongs to Atmospherics, not to the real place.
; [forecast] keeps the days ahead, so the game has them while play.bat isn't run.

[place]
name         = %(name)s
lat          = %(lat).4f
lon          = %(lon).4f
"""

WEATHER = """
[weather]
source       = open-meteo
place        = %(name)s
fetched_at   = %(fetched_at)s
date         = %(date)s
high         = %(high).1f
low          = %(low).1f
cycle        = %(cycle)s
freezing     = %(freezing)s

[weather_next]
date         = %(n_date)s
high         = %(n_high).1f
low          = %(n_low).1f
cycle        = %(n_cycle)s
freezing     = %(n_freezing)s
"""

# the days ahead, one a line: date = high, low, sky
FORECAST = """
[forecast]
%s
"""

# a place's own climate, for days without a reading: mean daily high, low by month
NORMALS = """
[normals]
%s
"""


def write(rows, place=DEFAULT, norms=None):
    """The file for `place`: today and tomorrow when `rows` has them, and the place's own
    normals when there are any. With no rows the game models the day from the normals."""
    # "_" for each space: X-Ray's reader drops the spaces in a value, and sotz_api turns the
    # underscores back
    fields = {"name": shown_name(place["name"]).replace(" ", "_"), "lat": place["lat"],
              "lon": place["lon"]}
    body = HEAD % fields
    if rows:
        today = rows[0]
        nxt = rows[1] if len(rows) > 1 else rows[0]
        body += WEATHER % dict(
            fields, fetched_at=datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            date=today["date"], high=today["high"], low=today["low"], cycle=today["cycle"],
            freezing="true" if today["low"] <= 0.0 else "false",
            n_date=nxt["date"], n_high=nxt["high"], n_low=nxt["low"], n_cycle=nxt["cycle"],
            n_freezing="true" if nxt["low"] <= 0.0 else "false")
        body += FORECAST % "\n".join("%-12s = %.1f, %.1f, %s" % (r["date"], r["high"], r["low"],
                                                                  r["cycle"]) for r in rows)
    if norms:
        body += NORMALS % "\n".join("m%-11d= %.1f, %.1f" % (m, hi, lo)
                                    for m, (hi, lo) in enumerate(norms, 1))
    for out in OUTS:
        tmp = out + ".tmp"
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with io.open(tmp, "w", encoding="cp1251", errors="replace", newline="\r\n") as fh:
            fh.write(body)
        os.replace(tmp, out)       # atomic: the game never sees a half-written file


def show():
    e = read_existing()
    p = read_existing("place")
    if not e:
        if p.get("name") and kept_normals():
            print("  " + _("no weather in season_weather.ltx - the game will use climate "
                           "normals for %s") % p["name"])
        else:
            print("  " + _("no weather in season_weather.ltx - the game will use climate "
                           "normals"))
        return
    day = {"place": e.get("place", "?"), "date": e.get("date", "?"),
           "high": e.get("high", "?"), "low": e.get("low", "?"),
           "sky": sky_word(e.get("cycle", "?"))}
    if e.get("freezing") == "true":
        # translators: a day's weather: its place and date, high and low, sky, and a warning
        print("  " + _("%(place)s, %(date)s: high %(high)s low %(low)s, %(sky)s  FREEZING")
              % day)
    else:
        print("  " + _("%(place)s, %(date)s: high %(high)s low %(low)s, %(sky)s") % day)
    if is_fresh(e):
        print("  " + _("fetched %s (fresh)") % e.get("fetched_at", "?"))
    else:
        print("  " + _("fetched %s (stale)") % e.get("fetched_at", "?"))


def main():
    ap = lang.parser(
        description=_("Fetch the day's weather for the place set in configure.bat "
                      "(Chornobyl by default); play.bat runs this."))
    ap.add_argument("--force", action="store_true",
                    help=_("fetch even if the file is fresh"))
    ap.add_argument("--offline", action="store_true",
                    help=_("do nothing, for testing the fallback"))
    ap.add_argument("--show", action="store_true", help=_("print what the game would read"))
    a = ap.parse_args()

    if a.show:
        show()
        return 0
    if a.offline or os.environ.get("SEASONS_OFFLINE"):
        print("  " + _("offline: leaving season_weather.ltx as it is"))
        return 0
    if not OUTS:
        print("  " + _("Seasons of the Zone is not in mods/ - no weather to write"))
        return 0

    place, note = configured_place()
    if note:
        print("  " + note)
    same = same_place(place)
    if same and not a.force and is_fresh(read_existing()):
        # translators: %dh is a number of hours
        print("  " + ngettext("weather is under %dh old, not refetching",
                              "weather is under %dh old, not refetching", REFRESH_HOURS)
              % REFRESH_HOURS)
        return 0

    # a place of the player's own brings its own climate, for days without a reading:
    # looked up once, then carried from file to file
    norms, looked_up = None, False
    if not is_default(place):
        norms = kept_normals() if same else None
        if norms is None:
            try:
                norms = normals(place["lat"], place["lon"])
                looked_up = True
            except Exception as e:
                # translators: %(error)s is the kind of error, as Python names it
                print("  " + _("%(place)s's climate is unavailable (%(error)s) - days without "
                               "a reading will use Chornobyl's")
                      % {"place": shown_name(place["name"]), "error": type(e).__name__})

    try:
        rows = to_rows(fetch(place))
    except Exception as e:
        # Never the reason a launch fails. A file for another place is not kept, though:
        # the game would show that place's weather under this one's name.
        if same:
            print("  " + _("weather unavailable (%s) - keeping what is there")
                  % type(e).__name__)
        else:
            print("  " + _("weather unavailable (%(error)s) - the game models %(place)s's day "
                           "until a reading comes")
                  % {"error": type(e).__name__, "place": shown_name(place["name"])})
            try:
                write([], place, norms)
            except Exception:
                pass
        return 0

    try:
        write(rows, place, norms)
    except Exception as e:
        print("  " + _("could not write season_weather.ltx (%s) - carrying on")
              % type(e).__name__)
        return 0

    t = rows[0]
    day = {"place": shown_name(place["name"]), "date": t["date"], "high": t["high"],
           "low": t["low"], "sky": sky_word(t["cycle"])}
    if t["low"] <= 0.0:
        # translators: a day's weather: its place and date, high and low, sky, and a warning
        print("  " + _("%(place)s %(date)s: high %(high).1f low %(low).1f, %(sky)s  FREEZING")
              % day)
    else:
        print("  " + _("%(place)s %(date)s: high %(high).1f low %(low).1f, %(sky)s") % day)
    print("  " + credit())
    if looked_up:
        print("  " + _("Also looked up %s's climate, for days without a reading.")
              % shown_name(place["name"]))
        print("  " + climate_credit())
    return 0


if __name__ == "__main__":
    sys.exit(main())
