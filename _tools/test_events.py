"""Events that repeat: days of the week, days of the month, which week, which months.

The dates are checked against Python's own calendar, not against a copy of the rules, and
every rule is also run through season.py's active_for(), which is what staging uses.

  python _tools/test_events.py
"""
import calendar
import datetime
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402

D = datetime.date
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def days(year=2026):
    d = D(year, 1, 1)
    while d.year == year:
        yield d
        d += datetime.timedelta(days=1)


@case
def t_each_part_of_a_rule_picks_its_own_days():
    last = {m: calendar.monthrange(2028, m)[1] for m in range(1, 13)}
    checks = {
        "weekends": ({"weekdays": ("sat", "sun")}, lambda d: d.weekday() >= 5),
        "the 1st, 15th, last": ({"days": (1, 15, -1)},
                                lambda d: d.day in (1, 15, last[d.month])),
        "the day before the last": ({"days": (-2,)}, lambda d: d.day == last[d.month] - 1),
        "first Monday": ({"weekdays": ("mon",), "weeks": (1,)},
                         lambda d: d.weekday() == 0 and d.day <= 7),
        "last Friday": ({"weekdays": ("fri",), "weeks": (-1,)},
                        lambda d: d.weekday() == 4 and d.day > last[d.month] - 7),
        "Friday the 13th": ({"weekdays": ("fri",), "days": (13,)},
                            lambda d: d.weekday() == 4 and d.day == 13),
        "December and January": ({"months": (12, 1)}, lambda d: d.month in (12, 1)),
        "weekends over the new year": (
            {"weekdays": ("sat", "sun"), "within": ((12, 20), (1, 10))},
            lambda d: d.weekday() >= 5 and ((d.month, d.day) >= (12, 20)
                                            or (d.month, d.day) <= (1, 10))),
    }
    for name, (spec, truth) in checks.items():
        assert not season.event_problems(name, spec), season.event_problems(name, spec)
        for d in days(2028):                   # a leap year: Feb 29 is the last day
            assert season.event_on(d, spec) == truth(d), "%s on %s" % (name, d)
    return "%d rules against every day of 2028" % len(checks)


@case
def t_a_rule_that_never_happens_is_refused():
    for spec in ({"days": (31,), "months": (2, 4)}, {"days": (30,), "months": (2,)},
                 {"weekdays": ("mon",), "weeks": (5,), "months": (2,), "days": (1,)}):
        got = season.event_problems("x", spec)
        assert got and "never happens" in got[0], (spec, got)
    # and the control: rare is not never - Feb 29, and a fifth Monday
    for spec in ({"days": (29,), "months": (2,)}, {"weekdays": ("mon",), "weeks": (5,)}):
        assert not season.event_problems("x", spec), spec
    return "three impossible rules refused; Feb 29 and a fifth Monday allowed"


@case
def t_a_rule_of_the_wrong_shape_is_named():
    for spec, says in (
            ({"weekdays": ("Sat",)}, '"weekdays" must list'),
            ({"weekdays": "sat"}, '"weekdays" must list'),
            ({"days": (0,)}, '"days" must list'),
            ({"days": (32,)}, '"days" must list'),
            ({"days": (True,)}, '"days" must list'),
            ({"weeks": (1,)}, '"weeks" needs "weekdays"'),
            ({"weekdays": ("mon",), "weeks": (6,)}, '"weeks" must say which'),
            ({"months": (13,)}, '"months" must list'),
            ({"within": ((12, 1),)}, '"within" must be'),
            ({"when": ("sat",)}, '"when" is not a part of a rule'),
            ({}, "give its first and last day"),
            ("weekends", "give its first and last day")):
        got = season.event_problems("x", spec)
        assert got and says in got[0], (spec, got)
    return "12 shapes, each with its own message"


@case
def t_rules_read_as_words():
    for spec, words in (
            (((12, 24), (12, 26)), "Dec 24 - Dec 26"),
            ({"weekdays": ("sat", "sun")}, "weekends"),
            ({"weekdays": ("mon", "tue", "wed", "thu", "fri")}, "workdays"),
            ({"days": (1, 15, -1)}, "the 1st, 15th and last day of the month"),
            ({"weekdays": ("mon",), "weeks": (1,)}, "the first Mon of the month"),
            ({"weekdays": ("fri",), "days": (13,)}, "Fri, the 13th of the month"),
            ({"months": (12, 1)}, "in Dec and Jan")):
        assert season.event_text(spec) == words, (spec, season.event_text(spec))
    return "7 rules"


@case
def t_staging_overlays_a_rule_on_the_season():
    """active_for() is what decides the mods: the season, then every event on that day."""
    old = season.EVENTS
    try:
        season.EVENTS = {"weekend": {"weekdays": ("sat", "sun")},
                         "christmas": ((12, 24), (12, 26))}
        assert season.active_for(D(2026, 9, 26)) == ["autumn", "weekend"]    # a Saturday
        assert season.active_for(D(2026, 9, 25)) == ["autumn"]               # a Friday
        assert season.active_for(D(2026, 12, 26)) == ["winter_snow", "weekend", "christmas"] \
            or season.active_for(D(2026, 12, 26)) == ["winter_snow", "christmas", "weekend"]
    finally:
        season.EVENTS = old
    return "a Saturday in autumn is autumn and weekend; Friday is autumn alone"


if __name__ == "__main__":
    print("  events that repeat")
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
