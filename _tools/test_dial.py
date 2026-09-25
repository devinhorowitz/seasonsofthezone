"""The year dial: the shipped set, and sets drawn for a player's calendar and names.

  python _tools/test_dial.py
"""
import datetime
import os
import random
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import build_season_dial as b                                   # noqa: E402
import season                                                   # noqa: E402
from PIL import Image, ImageChops, ImageDraw                    # noqa: E402

TEX = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone", "gamedata",
                   "textures")
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_the_shipped_set_is_what_the_code_draws():
    """Redrawn today, the shipped dials come out pixel for pixel. Position 16 is the one
    that moved a day, when round() halving to even gave way to the floor Lua uses."""
    cols = b.season_colors()
    with tempfile.TemporaryDirectory() as d:
        for i, day in b.positions():
            if i == 16:
                continue
            p = os.path.join(d, "%02d.dds" % i)
            b.save_dds(b.render(day, cols), p)
            shipped = Image.open(os.path.join(TEX, "ui_seasons_dial_%02d.dds" % i)).convert("RGBA")
            diff = ImageChops.difference(shipped, Image.open(p).convert("RGBA")).getbbox()
            assert diff is None, "position %d differs in %s" % (i, diff)
    return "31 of 32 identical; 16 drawn a day later on purpose"


@case
def t_the_shortest_season_has_a_dial_of_its_own():
    pos = [d.timetuple().tm_yday for _, d in b.positions()]
    worst = min(sum(1 for p in pos if (p - s) % 365 < season.MIN_SEASON_DAYS)
                for s in range(1, 366))
    assert worst >= 1, "a %d-day season can fall between two dials" % season.MIN_SEASON_DAYS
    return "every %d-day stretch of the year holds a dial position" % season.MIN_SEASON_DAYS


@case
def t_any_calendar_and_names_draw():
    rnd = random.Random(5)
    names = {"winter_snow": "The Long Cold", "late_winter": "Распутица",
             "summer": "Blowout Season Twenty", "spring": "Mud"}
    cols = b.season_colors()
    drawn = 0
    while drawn < 12:
        cal = {s: divmod(rnd.randrange(1, 13) * 100 + rnd.randrange(1, 29), 100)
               for s in rnd.sample(season.SEASONS, rnd.randrange(1, 7))}
        if season.calendar_problems(cal):
            continue
        bounds = sorted((m, d, s) for s, (m, d) in cal.items())
        assert all(b.positions_per_season(bounds).values()), cal
        b.render(datetime.date(2026, 1, 1) + datetime.timedelta(days=rnd.randrange(365)),
                 cols, bounds, names)
        drawn += 1
    return "12 random calendars, with Cyrillic and a 20-letter name"


@case
def t_a_name_too_long_for_its_place_is_shortened():
    dr = ImageDraw.Draw(Image.new("RGBA", (512, 512)))
    text, f = b.fit(dr, "BLOWOUT SEASON TWENTY", 60, range(17, 10, -1))
    assert text.endswith("…") and dr.textbbox((0, 0), text, font=f)[2] <= 60, text
    text, f = b.fit(dr, "SPRING", 200, range(31, 13, -1))
    assert text == "SPRING" and f.size == 31, (text, f.size)
    return "shortened with an ellipsis where it must be, and not otherwise"


if __name__ == "__main__":
    print("  the year dial")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-44s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-44s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-44s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
