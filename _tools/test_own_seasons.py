"""Seasons of the player's own, and spells: made in the windows and on the command line,
checked the way play.bat runs them.

A season of one's own runs on top of the season it falls in, for a week or longer, up to 52
of them. A spell starts by chance on a day of the seasons it names, runs 1 to 6 days, and
may bring another season, which play.bat then stages and hands to the game. The date
decides a spell, so each case that needs one on today gives it a chance of 100.

  python _tools/test_own_seasons.py
"""
import datetime
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402
import test_guide as tg                                         # noqa: E402

CASES = []
TODAY = datetime.date.today()


def case(fn):
    CASES.append(fn)
    return fn


def md(d):
    return "%02d-%02d" % (d.month, d.day)


def now_season():
    """The season Polesia's calendar has on today, which the scratch installs use."""
    return season.season_for(TODAY)


def other_season():
    return "winter" if now_season() != "winter" else "summer"


FIND = r"""
from tkinter import ttk
def find(win, kind, text=None):
    return [w for w in widgets(win) if w.winfo_class() == kind
            and (text is None or str(w.cget("text")) == text)]
def fill_own(win, name, first=None, last=None):
    box = find(win, "TEntry")[0]
    box.delete(0, "end")
    box.insert(0, name)
    months, days = find(win, "TCombobox"), find(win, "TSpinbox")
    for i, md in enumerate((first, last)):
        if md:
            months[i].set(ce.MONTHS[md[0] - 1])
            days[i].set(str(md[1]))
    settle()
"""


@case
def t_a_season_of_your_own_is_made_used_and_saved():
    """Added from the Seasons step, checked for a mod, saved; a season of six days is
    refused, and the saved file puts the mod on for the season's days."""
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d)
        a = TODAY - datetime.timedelta(days=2)
        b = TODAY + datetime.timedelta(days=6)
        rc, out = tg.drive(d, FIND + r"""
g.edit("seasons")
win = cf.own_season_dialog(root, g.cal, done=lambda n: g.show_own())
fill_own(win, "Short one", (1, 1), (1, 6))
print("SHORT", [t for t in texts(win) if "at least a week" in t])
find(win, "TButton", "Add")[0].invoke()
print("REFUSED", len(said), "Short one" in g.cal.own)
fill_own(win, "Fair week", (%d, %d), (%d, %d))
print("WORDS", [t for t in texts(win) if t.startswith("Runs")])
find(win, "TButton", "Add")[0].invoke()
settle()
print("OWN", g.cal.own)
print("LISTED", [t for t in texts(g.page) if t == "Fair week"])
dlg = guide.ModDialog(g, "Lonely Mod")
print("OFFERED", "Fair week" in dlg.vars)
dlg.vars["Fair week"].set(True)
dlg.ok()
print("WHEN", g.cal.toggle["Lonely Mod"]["when"])
g.save_edit()
print("SAVED", said[-1][0])
""" % (a.month, a.day, b.month, b.day))
        assert rc == 0, out
        assert "SHORT ['Short one: it runs 6 days, Jan 1 to Jan 6. A season of your own " \
            "runs at least a week.']" in out, out
        assert "REFUSED 1 False" in out, out
        assert "WORDS ['Runs 9 days, " in out, out
        assert "OWN {'Fair week': ((%d, %d), (%d, %d))}" % (a.month, a.day, b.month, b.day) \
            in out, out
        assert "LISTED ['Fair week']" in out and "OFFERED True" in out, out
        assert "WHEN ['Fair week']" in out and "SAVED showinfo" in out, out
        ns = tg.table(d)
        assert ns["OWN_SEASONS"] == {"Fair week": ((a.month, a.day), (b.month, b.day))}, ns
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc == 0 and "also today      Fair week" in out, out
        assert [l for l in out.splitlines() if l.strip().startswith("Lonely Mod")
                and "(today: on)" in l], out
    return "six days refused in the dialog; nine days saved, and play.bat puts its mod on today"


@case
def t_the_year_holds_52_seasons_of_ones_own():
    """52 is as many as there is room for, a week each: the 53rd can't be added in the
    window or on the command line, and play.bat refuses a file that has one."""
    fifty_two = ",\n".join('    "Week %d": ((1, 1), (1, 7))' % i for i in range(52))
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config="OWN_SEASONS = {\n%s,\n}\n" % fifty_two)
        rc, out = tg.drive(d, r"""
print("DIALOG", cf.own_season_dialog(root, g.cal), said)
""")
        assert rc == 0, out
        assert "DIALOG None [('showinfo', 'You have 52 seasons of your own, as many as the " \
            "year has room for, a week each. Remove one to add another.')]" in out, out
        rc, out = tc.run(d, "season", "Week 52", "02-01", "02-07")
        assert rc == 1 and "You have 52 seasons of your own" in out, out
        tc.accepted(d)
        fifty_three = fifty_two + ',\n    "Week 52": ((1, 1), (1, 7))'
        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w", encoding="utf-8").write(
            "OWN_SEASONS = {\n%s,\n}\n" % fifty_three)
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc != 0 and "53 seasons of your own, and the year has room for 52" in out, out
    return "the 53rd refused in the window, on the command line and by play.bat"


@case
def t_seasons_of_ones_own_follow_their_rules():
    """What season.py says about each way a season of one's own can be wrong."""
    got = season.own_problems({
        "Ok": ((8, 1), (8, 7)),
        "Six": ((8, 1), (8, 6)),
        "Across the year": ((12, 28), (1, 3)),
        "Summer": ((6, 1), (6, 30)),
        "christmas": ((12, 1), (12, 31)),
        " spaced": ((1, 1), (1, 31)),
        "x" * 25: ((1, 1), (1, 31)),
        "Leap": ((2, 29), (3, 10)),
        "Bad": ((13, 1), (1, 1)),
        "ok": ((3, 1), (3, 31)),
    }, events={"christmas": ((12, 24), (12, 26))})
    want = [
        "OWN_SEASONS['Six']: it runs 6 days, Aug 1 to Aug 6. A season of your own runs at "
        "least a week.",
        "OWN_SEASONS['Summer']: that is already the name of a season. Give it another name.",
        "OWN_SEASONS['christmas']: that is already an event. Give it another name.",
        "OWN_SEASONS[' spaced']: the name has spaces at its start or end. Take them out.",
        "OWN_SEASONS['%s']: the name is 25 characters long; it can have 24 at most." % ("x" * 25),
        "OWN_SEASONS['Leap'] can't start or end on February 29, which three years in four "
        "don't have. Use February 28 or March 1.",
        "OWN_SEASONS['Bad']: give its first and last day, like ((8, 1), (8, 31)).",
        "OWN_SEASONS['ok']: \"Ok\" is a season of yours already. Give this one another name.",
    ]
    assert got == want, "\n".join(got)
    assert season.own_days(((12, 28), (1, 3))) == 7 and season.own_days(((8, 1), (8, 7))) == 7
    return "%d problems, each as season.py says it; 7 days across the new year is a week" % (
        len(want))


@case
def t_a_spell_brings_its_season_to_play_bat_and_the_game():
    """A spell on today (chance 100, one day) that brings another season: play.bat stages
    that season - the season's mods off, the brought season's and the spell's own on - and
    writes it for the game, with its dates: starting on every day of the season, it runs the
    season long. A spell that can't start today is not on."""
    here, other = now_season(), other_season()
    one = datetime.timedelta(days=1)
    first, last = TODAY, TODAY
    while season.season_for(first - one) == here:
        first -= one
    while season.season_for(last + one) == here:
        last += one
    later = [s for s in season.SEASONS if s not in (here, other)][0]
    config = ('SPELLS = {"Cold snap": {"in": (%r,), "chance": 100, "days": 1, "as": %r},\n'
              '          "Never today": {"in": (%r,), "chance": 100, "days": 1}}\n'
              'TOGGLE_MODS = {\n'
              '    "Map Pack": {"when": (%r,), "above": "Lonely Mod"},\n'
              '    "Winter Maps": {"when": (%r,), "above": "Map Pack"},\n'
              '    "Lonely Mod": {"when": ("Cold snap",), "above": "Base Grass"},\n'
              '}\n' % (here, other, later, here, other))
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        ltx, _ = tc.with_mod(d)
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc == 0, out
        assert "season          %s   (a spell: Cold snap, %s to %s)" % (
            season.season_label(other), season._md(first.month, first.day),
            season._md(last.month, last.day)) in out, out
        assert "calendar says   %s" % season.season_label(here) in out, out
        lines = {l.split()[0] + " " + l.split()[1]: l for l in out.splitlines()
                 if "(today:" in l}
        assert "(today: off)" in lines["Map Pack"], out
        assert "(today: on)" in lines["Winter Maps"] and "(today: on)" in lines["Lonely Mod"], out
        assert "Never today" not in out, out
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0, out
        text = io.open(ltx, encoding="cp1251").read()
        assert "[spell]\r\nseason = %s\r\nname = Cold snap\r\nfirst = %s\r\nlast = %s" % (
            other, first.isoformat(), last.isoformat()) in text.replace("\n", "\r\n").replace(
                "\r\r\n", "\r\n"), text
    return "%s brought in %s; its mods on, %s's off; [spell] written for the game" % (
        other, here, here)


@case
def t_the_game_hears_of_a_spell_only_once_it_is_staged():
    """On a spell's first day, configure.bat's calendar send and a play.bat stopped by an
    open MO2 leave the spell out of the file the game reads, so a game started from MO2
    stays on what is staged. The play.bat that stages it hands it over, and a later send
    keeps it."""
    here, other = now_season(), other_season()
    config = ('SPELLS = {"Cold snap": {"in": (%r,), "chance": 100, "days": 1, "as": %r}}\n'
              'TOGGLE_MODS = {\n'
              '    "Map Pack": {"when": (%r,), "above": "Lonely Mod"},\n'
              '    "Winter Maps": {"when": (%r,), "above": "Map Pack"},\n'
              '}\n' % (here, other, here, other))
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        ltx, _ = tc.with_mod(d)
        modlist = os.path.join(d, "profiles", "Default", "modlist.txt")
        before = io.open(modlist, encoding="utf-8").read()
        rc, out = tc.run(d, "dial", tool="season.py")
        assert rc == 0 and "[spell]" not in io.open(ltx, encoding="cp1251").read(), out
        busy = os.path.join(d, "busy.py")
        io.open(busy, "w", encoding="utf-8").write(
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import season\n"
            "season.running = lambda: ['modorganizer.exe']\n"
            "sys.argv = ['season.py', 'apply']\n"
            "season.main()\n")
        r = subprocess.run([sys.executable, "-B", busy, os.path.join(d, "_tools")], cwd=d,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        assert r.returncode == 1 and "Close modorganizer.exe first. Nothing was changed." \
            in out, out
        text = io.open(ltx, encoding="cp1251").read()
        assert "[spell]" not in text, text
        assert io.open(modlist, encoding="utf-8").read() == before
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "[spell]" in io.open(ltx, encoding="cp1251").read(), out
        rc, out = tc.run(d, "dial", tool="season.py")
        assert rc == 0 and "name = Cold snap" in io.open(ltx, encoding="cp1251").read(), out
    return "not sent by configure.bat or a stopped play.bat; sent once staged, then kept"


@case
def t_spells_are_the_same_on_every_run_and_as_likely_as_they_say():
    """The same date gives the same spells in two processes with different hash seeds; over
    60 years a 3%% spell starts on about 3%% of its days, as often as configure.bat says it
    comes, and only in its season, and runs 1 or 2 days - longer only where it starts again
    while it runs. One that starts every summer day is one spell a year, the summer long."""
    snippet = (
        "import datetime, sys; sys.path.insert(0, %r); import season\n"
        "sp = {'Frost': {'in': ('summer',), 'chance': 3, 'days': (1, 2), 'as': 'winter'}}\n"
        "w = lambda day: [season.season_for(day)]\n"
        "d = datetime.date(2026, 1, 1)\n"
        "out = []\n"
        "while d.year < 2029:\n"
        "    out += [(n, f.isoformat(), l.isoformat()) for n, f, l in season.spells_on(d, sp, w)]\n"
        "    d += datetime.timedelta(days=1)\n"
        "print(sorted(set(out)))\n" % HERE)
    runs = []
    for seed in ("1", "2"):
        r = subprocess.run([sys.executable, "-B", "-c", snippet], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONHASHSEED=seed))
        assert r.returncode == 0, r.stderr
        runs.append(r.stdout)
    assert runs[0] == runs[1] and runs[0].count("Frost") > 3, runs
    spec = {"in": ("summer",), "chance": 3, "days": (1, 2), "as": "winter"}
    sp = {"Frost": spec}
    where = lambda day: [season.season_for(day)]                        # noqa: E731
    one = datetime.timedelta(days=1)

    def starts(x):
        return season.spell_draws("Frost", x)[0] * 100 < 3 and season.season_for(x) == "summer"

    runs, lengths, outside, alone = 0, set(), 0, 0
    d, end = datetime.date(2026, 1, 1), datetime.date(2086, 1, 1)
    summer_days = 0
    while d < end:
        if season.season_for(d) == "summer":
            summer_days += 1
        for n, first, last in season.spells_on(d, sp, where):
            if first == d:
                runs += 1
                days = (last - first).days + 1
                lengths.add(days)
                if season.season_for(first) != "summer":
                    outside += 1
                if days > 2 and not any(starts(first + one * k) for k in range(1, days)):
                    alone += 1
        d += one
    rate = runs / float(summer_days)
    assert 0.024 < rate < 0.036, (runs, summer_days, rate)
    assert {1, 2} <= lengths and outside == 0 and alone == 0, (lengths, outside, alone)
    said = season.spells_a_year(spec, where)
    assert abs(said * 60 - runs) < 0.15 * runs, (said, runs)
    every = {"in": ("summer",), "chance": 100, "days": (1, 2), "as": "winter"}
    mid = datetime.date(2026, 7, 15)
    begin, finish = mid, mid
    while season.season_for(begin - one) == "summer":
        begin -= one
    while season.season_for(finish + one) == "summer":
        finish += one
    [(n, first, last)] = season.spells_on(mid, {"Every": every}, where)
    assert first == begin and last in (finish, finish + one), (first, last, begin, finish)
    assert abs(season.spells_a_year(every, where) - 1) < 0.01, season.spells_a_year(every, where)
    return ("identical in two processes; %d runs on %.2f%% of %d summer days over 60 years, "
            "%.2f a year said" % (runs, rate * 100, summer_days, said))


@case
def t_spells_follow_their_rules():
    """What season.py says about each way a spell can be wrong."""
    on = [s for s in season.SEASONS if s != "winter_snow"]
    got = []
    for spec in ({"in": ("summer",), "chance": 0},
                 {"in": ("summer",), "chance": 3, "days": (1, 7)},
                 {"in": ("summer",), "chance": 3, "days": (2, 1)},
                 {"in": ("sumer",), "chance": 3},
                 {"in": ("winter_snow",), "chance": 3},
                 {"in": ("summer",), "chance": 3, "as": "summer"},
                 {"in": ("summer",), "chance": 3, "as": "winter_snow"},
                 {"in": ("summer",), "chance": 3, "color": 1}):
        got += season.spell_problems({"X": spec}, on)
    got += season.spell_problems({"Summer": {"in": ("summer",), "chance": 3}}, on)
    got += season.spell_problems({"Wormhole": {"in": ("summer",), "chance": 3}}, on,
                                 own={"Wormhole": ((8, 1), (8, 31))})
    got += season.spell_problems({"Snow;y": {"in": ("summer",), "chance": 3}}, on)
    assert len(got) == 11, "\n".join(got)
    assert got[1].endswith("A week or longer is a season of your own.") and got[1] == got[2]
    assert "deep winter is off in your calendar, so it never starts." in got[4], got[4]
    assert got[5].endswith("it would bring summer to summer, which changes nothing."), got[5]
    assert got[6].endswith("it brings deep winter, which is off in your calendar."), got[6]
    assert got[9].endswith("that is already a season of your own. Give it another name.")
    ok = {"Frost": {"in": ("summer", "Wormhole"), "chance": 2.5, "days": 3, "as": None}}
    assert season.spell_problems(ok, on, own={"Wormhole": ((8, 1), (8, 31))}) == []
    return "11 problems, one per fault; a good spell with a season of one's own passes"


@case
def t_a_spell_in_the_command_line_and_the_list():
    """configure.py spell: added, listed with how often it comes, used for a mod, renamed
    with the mod following, and removed with the mod on in nothing else."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d)
        rc, out = tc.run(d, "spell", "Summer frost", "--in", "summer", "--chance", "3",
                         "--days", "1", "2", "--as", "winter")
        assert rc == 0 and "added spell Summer frost  in summer, 3% a day, 1 to 2 days; " \
            "brings winter; about 3 times a year" in out, out
        rc, out = tc.run(d, "spell", "Long", "--in", "summer", "--chance", "3", "--days", "7")
        assert rc == 1 and "A week or longer is a season of your own." in out, out
        rc, out = tc.run(d, "add", "Lonely Mod", "--when", "summer frost")
        assert rc == 0 and "on in     Summer frost" in out, out
        rc, out = tc.run(d, "spell", "Summer frost", "--rename", "Frost")
        assert rc == 0, out
        assert tg.table(d)["TOGGLE_MODS"]["Lonely Mod"]["when"] == ("Frost",)
        rc, out = tc.run(d, "spell", "Frost", "--remove")
        assert rc == 0 and "stopped switching Lonely Mod, on in nothing else; play.bat " \
            "leaves it as it is in MO2" in out, out
        ns = tg.table(d)
        assert ns["SPELLS"] == {} and "Lonely Mod" not in ns["TOGGLE_MODS"], ns
        tc.accepted(d)
        # a season of one's own taken off takes the spells that start only in it, and says so
        for args in (("season", "Wormhole season", "08-01", "08-31"),
                     ("spell", "Storm", "--in", "Wormhole season", "--chance", "3"),
                     ("add", "Lonely Mod", "--when", "Storm")):
            rc, out = tc.run(d, *args)
            assert rc == 0, out
        rc, out = tc.run(d, "season", "Wormhole season", "--remove")
        assert rc == 0 and "removed spell Storm, which could start only in it" in out \
            and "stopped switching Lonely Mod, on in nothing else; play.bat leaves it as it " \
            "is in MO2" in out, out
        assert tg.table(d)["SPELLS"] == {}, tg.table(d)
    config = ('OWN_SEASONS = {"Wormhole season": ((8, 1), (8, 31))}\n'
              'SPELLS = {"Storm": {"in": ("Wormhole season",), "chance": 3, "days": 1}}\n'
              'TOGGLE_MODS = {"Lonely Mod": {"when": ("Storm",), "above": "Base Grass"}}\n')
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config=config)
        rc, out = tg.drive(d, r"""
asked = []
messagebox.askyesno = lambda *a, **k: asked.append(a[1]) or True
print("TAKEN", cf.remove_own_season(root, g.cal, "Wormhole season"), g.cal.spells,
      sorted(g.cal.toggle))
print("ASKED", asked)
""")
        assert rc == 0 and "TAKEN True {} []" in out, out
        assert "Storm can start only in it, so it goes too. Lonely Mod is on in nothing " \
            "else, so play.bat stops switching it and leaves it as it is in MO2." in out, out
    return "added, refused at 7 days, used, renamed with its mod, removed with it; a season " \
        "of one's own removed with its spell and the spell's mod, each said"


@case
def t_what_cant_be_used_is_refused_in_words():
    """February 29, a chance that isn't a finite number, a name taken by the other kind or
    with a character the game's files can't hold, and an odd season in a spell's "in": each
    refused in words, on the command line, in the window and by play.bat. A decimal comma is
    a decimal point. A spell's season that is off in the calendar has no box in its dialog,
    and stays in the spell when it is saved."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d)
        for first, last in (("02-29", "03-10"), ("02-23", "02-29")):
            rc, out = tc.run(d, "season", "Leap", first, last)
            assert rc == 1 and "can't start or end on February 29" in out, out
        for bad in ("inf", "nan", "1e999"):
            rc, out = tc.run(d, "spell", "E", "--in", "summer", "--chance", bad)
            assert rc == 2 and "invalid decimal value" in out, out
        rc, out = tc.run(d, "spell", "E", "--in", "summer", "--chance", "1e308")
        assert rc == 1 and "\"chance\" is the percent chance" in out, out
        rc, out = tc.run(d, "spell", "Frost", "--in", "summer", "--chance", "0,5")
        assert rc == 0 and "0.5% a day" in out, out
        rc, out = tc.run(d, "season", "frost", "08-01", "08-31")
        assert rc == 1 and "You have a spell called \"frost\" already." in out, out
        rc, out = tc.run(d, "event", "frost", "12-24")
        assert rc == 1 and "is already the name of a season of your own or a spell" in out, out
        for name in ("Early, late", "Snow;y", "[x]", "a=b", "雪"):
            rc, out = tc.run(d, "season", name, "08-01", "08-31")
            assert rc == 1 and ("the name can't contain , ; [ ] = or a line break." in out
                                or "letters the game can't show" in out), out
            rc, out = tc.run(d, "spell", name, "--in", "summer", "--chance", "3")
            assert rc == 1 and ("the name can't contain , ; [ ] = or a line break." in out
                                or "letters the game can't show" in out), out
        tc.accepted(d)
    got = season.spell_problems({"X": {"in": (["summer"], 3), "chance": 3}})
    assert got == ["SPELLS['X']: \"in\" names \"['summer']\" and \"3\", which are not seasons. "
                   "The seasons are spring, summer, autumn, winter, winter_snow and "
                   "late_winter."], got
    config = ('CALENDAR = {"spring": (3, 1), "summer": (6, 1), "autumn": (9, 1), '
              '"winter": (12, 1)}\n'
              'SPELLS = {"Frost": {"in": ("summer", "winter_snow"), "chance": 3, '
              '"days": (1, 2), "as": "winter"}}\n')
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config=config)
        rc, out = tg.drive(d, r"""
win = cf.spell_dialog(root, g.cal, editing="Frost")
settle()
boxes = [w for w in widgets(win) if w.winfo_class() == "TSpinbox"]
for typed in ("inf", "nan", "1e999", "2,5"):
    boxes[0].set(typed)
    settle()
    print("TYPED", typed, [t for t in texts(win) if t.startswith(("The chance", "In "))])
[w for w in widgets(win) if w.winfo_class() == "TButton"
 and str(w.cget("text")) == "Save"][0].invoke()
settle()
print("SPELL", g.cal.spells["Frost"])
""")
    assert rc == 0 and "Traceback" not in out, out
    for typed in ("inf", "nan", "1e999"):
        assert "TYPED %s ['The chance and the days are numbers.']" % typed in out, out
    assert "TYPED 2,5 ['In summer and deep winter, 2.5% a day, 1 to 2 days; brings winter; " \
        "about 2 times a year.']" in out, out
    assert "SPELL {'in': ('summer', 'winter_snow'), 'chance': 2.5" in out, out
    return "Feb 29, inf, nan, 1e308, taken names and , ; [ ] = refused; 0,5 is 0.5; an off " \
        "season kept"


@case
def t_a_preset_carries_seasons_of_ones_own_and_spells():
    """A preset saved where a mod is on in a season of one's own and during a spell loads
    on another install with both, and the mod on in them."""
    config = ('OWN_SEASONS = {"Wormhole season": ((8, 1), (8, 31))}\n'
              'SPELLS = {"Summer frost": {"in": ("summer",), "chance": 3, "days": (1, 2), '
              '"as": "winter"}}\n'
              'TOGGLE_MODS = {"Winter Maps": {"when": ("Wormhole season", "Summer frost"), '
              '"above": "Map Pack"}}\n')
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e:
        tc.install(d, config=config)
        rc, out = tc.run(d, "preset", "save", "Mine", "--parts", "events", "mods")
        assert rc == 0, out
        tc.install(e)
        os.makedirs(os.path.join(e, "_tools", "presets"))
        src = os.path.join(d, "_tools", "presets", "Mine.json")
        io.open(os.path.join(e, "_tools", "presets", "Mine.json"), "wb").write(
            open(src, "rb").read())
        rc, out = tc.run(e, "preset", "load", "Mine", "--force")
        assert rc == 0, out
        ns = tg.table(e)
        assert ns["OWN_SEASONS"] == {"Wormhole season": ((8, 1), (8, 31))}, ns
        assert ns["SPELLS"]["Summer frost"]["as"] == "winter", ns
        assert ns["TOGGLE_MODS"]["Winter Maps"]["when"] == ("Wormhole season",
                                                            "Summer frost"), ns
        tc.accepted(e)
    return "saved with both, loaded elsewhere with both and the mod on in them"


@case
def t_a_mod_in_a_season_of_ones_own_meets_the_season_it_falls_in():
    """Winter Overlay made seasonal in a season of one's own inside winter, where Winter Pack
    is on and ships a file it ships: the player is asked whose the game uses, as for two
    mods in the same season."""
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config='OWN_SEASONS = {"First frost": ((11, 1), (11, 14))}\n'
                             'TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                             '"above": "Grass Compat"}}\n')
        rc, out = tg.drive(d, r"""
asked = []
guide.ask_winner = lambda g, name, other, n, seasons, parent=None: (
    asked.append((name, other, n, seasons)) or True)
g.edit("mods")
dlg = guide.ModDialog(g)
dlg.query.set("overlay")
settle()
dlg.list.selection_set(0)
dlg.vars["First frost"].set(True)
dlg.ok()
print("ASKED", asked)
""")
        assert rc == 0, out
        assert "ASKED [('Winter Overlay', 'Winter Pack', 1, 'First frost')]" in out, out
    return "asked whose file, in First frost"


@case
def t_a_mod_during_a_spell_meets_what_the_spell_runs_in():
    """A spell that brings winter meets the winter mods and not the summer ones it takes the
    place of; one that leaves the season meets the mods of the days it can run. The window
    asks, and status notes, whose file the game uses; renaming the season of one's own a
    spell starts in renames it in the spell."""
    config = ('OWN_SEASONS = {"Wormhole season": ((8, 1), (8, 31))}\n'
              'SPELLS = {"Frost": {"in": ("summer",), "chance": 3, "days": (1, 2), '
              '"as": "winter"},\n'
              '          "Storm": {"in": ("Wormhole season",), "chance": 3, "days": 1}}\n')
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config=config + 'TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                                      '"above": "Grass Compat"}}\n')
        rc, out = tg.drive(d, r"""
cal = g.cal
print("MEET", sorted(cal.together(["Frost"], ["winter"])),
      sorted(cal.together(["Frost"], ["summer"])),
      sorted(cal.together(["Storm"], ["summer"])),
      sorted(cal.together(["Storm"], ["winter"])),
      sorted(cal.together(["Storm"], ["Frost"])))
asked = []
guide.ask_winner = lambda g, name, other, n, seasons, parent=None: (
    asked.append((name, other, n, seasons)) or True)
g.edit("mods")
dlg = guide.ModDialog(g)
dlg.query.set("overlay")
settle()
dlg.list.selection_set(0)
dlg.vars["Frost"].set(True)
dlg.ok()
print("ASKED", asked)
""")
        assert rc == 0, out
        assert "MEET ['Frost'] [] ['Storm'] [] ['Storm']" in out, out
        assert "ASKED [('Winter Overlay', 'Winter Pack', 1, 'Frost')]" in out, out
    for when, noted in (("Frost", True), ("Storm", False)):
        with tempfile.TemporaryDirectory() as d:
            tc.install(d, config=config + (
                'TOGGLE_MODS = {"Winter Overlay": {"when": (%r,), "above": "Base Grass"},\n'
                '               "Winter Pack": {"when": ("winter",), "above": "Grass Compat"}}\n'
                % when))
            rc, out = tc.run(d, "status", tool="season.py")
            assert rc == 0 and ("\"Winter Overlay\" wins 1 of Winter Pack" in out) == noted, out
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        rc, out = tc.run(d, "season", "Wormhole season", "--rename", "Rostok wormhole")
        assert rc == 0, out
        assert tg.table(d)["SPELLS"]["Storm"]["in"] == ("Rostok wormhole",), tg.table(d)
    return "Frost meets winter, not summer; Storm meets summer; asked, noted; renamed with it"


@case
def t_one_play_bat_cant_use_is_shown_with_why():
    """A season of one's own or a spell play.bat would refuse was kept in the file but left
    out of the setup's Seasons step, which said "None yet." over it, and the advanced
    editor's reason missed what only the rest of the setup shows: a name an event has."""
    config = ('OWN_SEASONS = {"Too short": ((8, 1), (8, 3))}\n'
              'EVENTS = {"christmas": ((12, 24), (12, 26))}\n'
              'SPELLS = {"christmas": {"in": ("winter",), "chance": 3, "days": 1}}\n')
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config=config)
        rc, out = tg.drive(d, r"""
g.edit("seasons")
settle()
shown = [t for t in texts(g.own_box_list) + texts(g.spell_box_list) if t.strip()]
print("SHOWN", shown)
print("EDITOR", cf.bad_reasons(g.cal, "spell", "christmas"))
[w for w in widgets(g.own_box_list) if w.winfo_class() == "TButton"
 and str(w.cget("text")) == "Remove"][0].invoke()
settle()
print("AFTER", g.cal._bad_own, [t for t in texts(g.own_box_list) if t.strip()])
""")
        assert rc == 0, out
        assert "'Too short', \"play.bat can't use it as it is\"" in out \
            and "It runs 3 days, Aug 1 to Aug 3. A season of your own runs at least a week." \
            in out and "None yet." not in out.split("AFTER")[0], out
        assert "That is already an event. Give it another name." in out.split("EDITOR")[1], out
        assert "AFTER {} ['None yet.']" in out, out
    return "each listed with why, Change and Remove; the editor's reason sees the event"


if __name__ == "__main__":
    failed = 0
    for fn in CASES:
        name = fn.__name__[2:]
        try:
            print("  PASS  %-58s %s" % (name, fn()))
        except AssertionError as e:
            failed += 1
            print("  FAIL  %-58s %s" % (name, str(e)[:1200]))
    print("%d/%d passed" % (len(CASES) - failed, len(CASES)))
    sys.exit(1 if failed else 0)
