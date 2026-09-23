"""A seasons_config.py with a mistake in it must say where, in one plain message.

The config is the one file users edit by hand, usually from a Discord message, and the
mistakes are small: a comma in the wrong place, a name without quotes, the template's
own empty `TOGGLE_MODS = {}` left below the real one. The first two used to end in a
Python traceback, and the third in nothing at all - the table was thrown away and every
page said no mods were set. Each case writes a config into a scratch install and runs the
packaged season.py on it, as play.bat does.

  python _tools/test_config_errors.py
"""
import sys
import tempfile

from test_whowins import FILE, ON_TOP, answers, install, run

GOOD = '''LAYOUT = {}
TOGGLE_MODS = {
    "INVERNO": {
        "when": ("winter", "winter_snow"),
        "above": "SSS 24",
    },
}
SOUND_SRC = None
PERIODS = {}
EVENTS = {}
'''


def line_of(cfg, text):
    return next(i for i, l in enumerate(cfg.splitlines(), 1) if text in l)


def status(cfg):
    """(exit code, output) of `season.py status`, and whether whowins still answered."""
    with tempfile.TemporaryDirectory() as d:
        install(d, ON_TOP, config=cfg)
        rc, out = run(d, "status")
        wrc, wout = run(d, "whowins", FILE, "--for", "INVERNO")
    assert "Traceback" not in out, "a traceback:\n" + out
    return rc, out, (wrc == 0 and answers(wout) == ["SSS 24"])


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_a_comma_in_the_wrong_place_names_its_line():
    cfg = GOOD.replace('("winter", "winter_snow")', '(, "winter_snow")')
    rc, out, who = status(cfg)
    n = line_of(cfg, '"when"')
    assert rc != 0, "accepted"
    assert "line %d: invalid syntax" % n in out, out
    assert '"when": (, "winter_snow"),' in out and "^" in out, out
    assert who, "whowins stopped working"
    return "line %d, the line itself and a caret" % n


@case
def t_a_missing_comma_between_entries_gives_the_range():
    cfg = GOOD.replace('    },\n}', '    }\n    "Other": {"when": ("winter",), "above": "SSS 24"},\n}')
    rc, out, who = status(cfg)
    first, last = line_of(cfg, '"INVERNO"'), line_of(cfg, '"Other"')
    assert rc != 0, "accepted"
    assert "lines %d to %d" % (first, last) in out and "comma" in out, out
    assert who, "whowins stopped working"
    return "lines %d to %d, and the word comma" % (first, last)


@case
def t_a_name_without_quotes_says_to_quote_it():
    cfg = GOOD.replace('("winter", "winter_snow")', '("winter", winter_snow)')
    rc, out, who = status(cfg)
    n = line_of(cfg, '"when"')
    assert rc != 0, "accepted"
    assert "line %d:" % n in out and 'Names go in quotes: "winter_snow"' in out, out
    assert who, "whowins stopped working"
    return "line %d, with the quoted name to type" % n


@case
def t_a_table_set_twice_is_caught():
    """Valid Python, so only reading the file can find it: the last assignment wins and
    the real table is thrown away without a word."""
    cfg = GOOD + "TOGGLE_MODS = {}\n"
    rc, out, who = status(cfg)
    again, first = len(cfg.splitlines()), line_of(cfg, "TOGGLE_MODS = {")
    assert rc != 0, "accepted a config whose table is thrown away"
    assert ("line %d sets TOGGLE_MODS again, which throws away the one on line %d"
            % (again, first)) in out, out
    assert who, "whowins stopped working"
    return "line %d named as throwing away line %d" % (again, first)


@case
def t_a_config_that_imports_something_missing_is_not_ignored():
    """ImportError used to mean "no config", so a config importing something that is not
    there was dropped in silence, tables and all."""
    cfg = "import notthere\n" + GOOD
    rc, out, who = status(cfg)
    assert rc != 0, "the config was silently ignored"
    assert "line 1:" in out and "notthere" in out, out
    return "line 1, naming the missing module"


@case
def t_a_good_config_and_no_config_both_run():
    rc, out, who = status(GOOD)
    assert rc == 0 and "needs fixing" not in out, out
    assert who
    rc, out, who = status(None)
    assert rc == 0 and "needs fixing" not in out, out
    return "both accepted"


if __name__ == "__main__":
    print("  running the shipped season.py on broken configs")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-52s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-52s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-52s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
