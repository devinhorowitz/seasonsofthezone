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
import lang                                                     # noqa: E402
import season                                                   # noqa: E402
from PIL import Image, ImageChops, ImageDraw                    # noqa: E402

TEX = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone", "gamedata",
                   "textures")
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_the_shipped_sets_are_what_the_code_draws():
    """Redrawn today, each shipped set comes out pixel for pixel in its language. English's
    position 16 is the one that moved a day, when round() halving to even gave way to the
    floor Lua uses; the Russian set was drawn after, so all of it is checked."""
    cols = b.season_colors()
    same = 0
    with tempfile.TemporaryDirectory() as d:
        for code, prefix in b.SETS:
            with lang.speaking(code) as got:
                assert got == code, "no %s translation to draw %s with" % (code, prefix)
                for i, day in b.positions():
                    if code == "en" and i == 16:
                        continue
                    p = os.path.join(d, "%s%02d.dds" % (code, i))
                    b.save_dds(b.render(day, cols), p)
                    shipped = Image.open(os.path.join(TEX, "%s%02d.dds" % (prefix, i)))
                    diff = ImageChops.difference(shipped.convert("RGBA"),
                                                 Image.open(p).convert("RGBA")).getbbox()
                    assert diff is None, "%s position %d differs in %s" % (code, i, diff)
                    same += 1
    assert same == 32 * len(b.SETS) - 1, same
    return "%d of %d identical, English and Russian; English's 16 a day later on purpose" % (
        same, 32 * len(b.SETS))


@case
def t_the_dial_says_its_words_in_the_language_in_use():
    """The names, the lines under them and the days come from the translation, Russian's
    three forms for a count included; English when the language has none of them."""
    with lang.speaking("ru"):
        ru = [b.label("late_winter"), b.themes("autumn"), b.days_text(41), b.days_text(94),
              b.days_text(118)]
    with lang.speaking("en"):
        en = [b.label("late_winter"), b.themes("autumn"), b.days_text(41), b.days_text(94),
              b.days_text(118)]
    assert ru == ["Поздняя зима", ("туман,", "янтарный свет"), "41 день", "94 дня",
                  "118 дней"], ru
    assert en == ["Late Winter", ("fog, low sun,", "amber light"), "41 days", "94 days",
                  "118 days"], en
    return "Поздняя зима, 41 день, 94 дня, 118 дней; Late Winter, 41 days in English"


@case
def t_lines_too_long_for_their_arc_shrink_or_go():
    """The two lines under a season's name stay inside its arc: at full size when they
    fit, smaller when that is enough, left out when it is not. Polesia's autumn, the
    tightest arc that has them."""
    dr = ImageDraw.Draw(Image.new("RGBA", (512, 512)))
    a0, a1 = [(s0, s1) for s0, s1, s, _ in b.arcs(b.YEAR) if s == "autumn"][0]
    x, y = b.polar((a0 + a1) / 2.0, b.R_LABEL)
    sizes = [getattr(b.theme_font(dr, lines, x, y, a0, a1), "size", None)
             for lines in (("fog, low sun,", "amber light"), ("туман,", "янтарный свет"),
                           ("туман, низкое солнце,", "янтарный свет"))]
    assert sizes == [14, 12, None], sizes
    return "English at 14px, туман / янтарный свет at 12px, a 21-letter line left out"


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


@case
def t_the_hand_shown_is_always_in_the_day_s_season():
    rnd = random.Random(9)
    tried = 0
    while tried < 20:
        cal = {s: divmod(rnd.randrange(1, 13) * 100 + rnd.randrange(1, 29), 100)
               for s in rnd.sample(season.SEASONS, rnd.randrange(1, 7))}
        if season.calendar_problems(cal):
            continue
        bounds = sorted((m, d, s) for s, (m, d) in cal.items())
        day = datetime.date(2026, 1, 1)
        while day.year == 2026:
            _, at = b.shown(day, bounds)
            assert b.season_on(at, bounds) == b.season_on(day, bounds), (cal, day, at)
            # and never the far side of the year: round the year end, Dec 31 is next to Jan 3
            gap = abs((at - day).days)
            assert min(gap, 365 - gap) <= 183, (cal, day, at)
            day += datetime.timedelta(days=1)
        tried += 1
    return "20 calendars, every day: the hand shown is in the day's own season"


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
