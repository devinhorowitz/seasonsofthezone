"""MCM's dice: at each launch play.bat can roll another of the seasons the calendar has on,
at a chance set in MCM or in configure.bat. Only an apply that writes rolls; a season
fixed by --season or a pin is never rolled over; a hit always changes the season. The roll
goes to the game in season_calendar.ltx's [roll], and every layer there follows it until
the next launch, with the pin still over it.

  python _tools/test_dice.py
"""
import datetime
import io
import os
import random
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402
import test_calendar as tcal                                    # noqa: E402

CASES = []
CRLF = "\r\n"
TODAY = datetime.date.today()
NOW = season.season_for(TODAY)                  # the sandbox's calendar is Polesia's
ON = list(season.SEASONS)


def case(fn):
    CASES.append(fn)
    return fn


class Draws(object):
    """A stand-in for random: hands out the draws it is given, and the first of a pool."""

    def __init__(self, *draws):
        self.draws, self.pools = list(draws), []

    def randint(self, a, b):
        assert (a, b) == (1, 100), (a, b)
        return self.draws.pop(0)

    def choice(self, pool):
        self.pools.append(list(pool))
        return pool[0]


def store(d, values):
    """MCM's file in the scratch install's overwrite/, with `values` under [mcm]."""
    ow = os.path.join(d, "overwrite", "gamedata", "configs")
    os.makedirs(ow, exist_ok=True)
    p = os.path.join(ow, "axr_options.ltx")
    lines = ["[mcm]"] + ["        %-32s = %s" % kv for kv in sorted(values.items())] + [""]
    open(p, "wb").write(CRLF.join(lines).encode("cp1251"))
    return p


def mcm(d):
    return season.mcm_saved(os.path.join(d, "overwrite", "gamedata", "configs",
                                         "axr_options.ltx"))


def section(d, name, fname="season_calendar.ltx"):
    """A section of one of the files play.bat writes for the game, as {key: value}; None
    when the file or the section is not there."""
    p = os.path.join(d, "mods", "Seasons of the Zone", "gamedata", "configs", fname)
    if not os.path.isfile(p):
        return None
    out, here = None, None
    for line in io.open(p, encoding="cp1251").read().splitlines():
        s = line.strip()
        if s.startswith("["):
            here = s[1:-1].lower()
            if here == name:
                out = {}
        elif here == name and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def sandbox(d, values):
    tc.install(d)
    tc.with_mod(d)
    store(d, values)


def apply(d, seed="1", *args):
    return tc.run(d, "apply", *args, tool="season.py",
                  env=dict(os.environ, SOTZ_DICE_SEED=seed, PYTHONIOENCODING="utf-8"))


def row(out, label):
    m = re.search(r"^  %s +(.*)$" % re.escape(label), out, re.M)
    return m.group(1) if m else None


@case
def t_a_hit_is_a_fair_pick_of_another_season():
    """roll_season(): off is no draw at all; a draw at the chance hits and one over it
    misses; a hit picks from the seasons that are on, never the one that would run anyway;
    with no other season on there is nothing to pick. Over 20,000 seeded launches, 25%
    hits about a quarter of them, spread evenly over the other five."""
    off = {"dice": False, "dice_chance": 25}
    assert season.roll_season(off, ON, "autumn", Draws(1)) == (None, None, None)
    on = {"dice": True, "dice_chance": 25}
    r = Draws(25)
    assert season.roll_season(on, ON, "autumn", r) == ("spring", 25, 25)
    assert r.pools == [[s for s in ON if s != "autumn"]], r.pools
    assert season.roll_season(on, ON, "autumn", Draws(26)) == (None, 26, 25)
    every = {"dice": True, "dice_chance": 100}
    assert season.roll_season(every, ON, "autumn", Draws(100))[0] == "spring"
    assert season.roll_season(on, ["autumn"], "autumn", Draws(1)) == (None, 1, 25)

    rng = random.Random(20261003)
    got = [season.roll_season(on, ON, "autumn", rng)[0] for _ in range(20000)]
    hits = [s for s in got if s]
    share = len(hits) / float(len(got))
    assert 0.23 < share < 0.27, share
    assert "autumn" not in hits, "rolled the season that was running anyway"
    each = {s: hits.count(s) / float(len(hits)) for s in ON if s != "autumn"}
    assert all(0.17 < v < 0.23 for v in each.values()), each
    return "25 hits, 26 misses, %.1f%% of 20,000 hit, five seasons at %.0f-%.0f%% each" % (
        100 * share, 100 * min(each.values()), 100 * max(each.values()))


@case
def t_mcm_s_chance_reads_as_saved():
    """MCM saves the chance as a number; whatever is in the file, play.bat reads a whole
    percent from 1 to 100, and the default where it isn't a number."""
    cases = {"25": 25, "25.0": 25, " 40 ": 40, "99.6": 100, "0": 1, "-5": 1, "150": 100,
             "x": season.DICE_CHANCE, "": season.DICE_CHANCE}
    got = {k: season.dice_chance(k) for k in cases}
    assert got == cases, got
    return "%d spellings read" % len(cases)


@case
def t_apply_rolls_and_tells_the_game():
    """With the dice on at 100, apply stages another season, says what it drew and what
    the calendar says, and writes [roll] for the game; season_staged.ltx agrees. A dial
    redraw keeps the roll. The next apply with the dice off clears it and goes back to
    the calendar."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, {"seasons_zone/main/dice": "true", "seasons_zone/main/dice_chance": "100"})
        rc, out = apply(d)
        assert rc == 0, out
        roll = section(d, "roll")
        assert roll and roll["season"] in ON and roll["season"] != NOW, (roll, out)
        assert roll["chance"] == "100" and 1 <= int(roll["draw"]) <= 100, roll
        assert roll["day"] == TODAY.isoformat(), roll
        said = row(out, "season")
        assert said == "%s   (rolled by MCM's dice: %s, at or under 100)" % (
            season.season_label(roll["season"]), roll["draw"]), out
        assert row(out, "calendar says") == season.season_label(NOW), out
        assert row(out, "dice") is None, "a roll that hit also said the setting: " + out
        staged = section(d, "staged", "season_staged.ltx")
        assert staged and staged["season"] == roll["season"], staged

        rc, out = tc.run(d, "dial", tool="season.py")
        assert section(d, "roll") == roll, "a dial redraw dropped the roll"

        store(d, {"seasons_zone/main/dice": "false", "seasons_zone/main/dice_chance": "100"})
        rc, out = apply(d)
        assert rc == 0 and section(d, "roll") is None, (section(d, "roll"), out)
        assert section(d, "staged", "season_staged.ltx")["season"] == NOW
        assert row(out, "calendar says") is None and row(out, "dice") is None, out
    return "rolled %s over %s, kept by a dial redraw, cleared with the dice off" % (
        roll["season"], NOW)


@case
def t_status_and_a_dry_run_say_the_chance_and_roll_nothing():
    """Only an apply that writes rolls: status and a dry run say the setting, run the
    calendar's season, and leave the game's files as they were."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, {"seasons_zone/main/dice": "true", "seasons_zone/main/dice_chance": "25"})
        for args in (("status",), ("apply", "--dry-run")):
            rc, out = tc.run(d, *args, tool="season.py")
            assert rc == 0, out
            assert row(out, "dice") == "a 25% chance at each launch of another season", out
            assert row(out, "season") == season.season_label(NOW), out
            assert section(d, "roll") is None, "%s wrote a roll" % args[0]
        store(d, {"seasons_zone/main/dice": "true", "seasons_zone/main/dice_chance": "100"})
        rc, out = tc.run(d, "status", tool="season.py")
        assert row(out, "dice") == "every launch rolls another season", out
    return "status and --dry-run: the chance said, the calendar's season, no [roll]"


@case
def t_a_pin_or_season_is_never_rolled_over():
    """MCM's pin and --season fix the season, so the dice don't roll, and the report says
    so; a miss says what it drew."""
    pin = [s for s in ON if s != NOW][0]
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, {"seasons_zone/main/dice": "true", "seasons_zone/main/dice_chance": "100",
                    "seasons_zone/main/mode": pin})
        rc, out = apply(d)
        assert rc == 0 and section(d, "roll") is None, out
        assert row(out, "season") == "%s   (pinned in MCM)" % season.season_label(pin), out
        assert row(out, "dice") == "on, but a pinned or forced season is never rolled over", out
        store(d, {"seasons_zone/main/dice": "true", "seasons_zone/main/dice_chance": "100"})
        rc, out = apply(d, "1", "--season", pin)
        assert rc == 0 and section(d, "roll") is None, out
        assert row(out, "dice") == "on, but a pinned or forced season is never rolled over", out

        seed = "miss"
        draw = random.Random(seed).randint(1, 100)
        assert draw > 1, "the seed must draw over 1"
        store(d, {"seasons_zone/main/dice": "true", "seasons_zone/main/dice_chance": "1"})
        rc, out = apply(d, seed)
        assert rc == 0 and section(d, "roll") is None, out
        assert row(out, "dice") == "drew %d, over 1, so the calendar's season" % draw, out
        assert row(out, "season") == season.season_label(NOW), out
    return "a pin and --season held %s; a 1%% chance drew %d and missed" % (pin, draw)


@case
def t_configure_sets_the_dice_in_mcm_s_file():
    """configure.py dice shows the setting; on, off and --chance write MCM's own file, where
    the game's page reads them, and keep the rest; a chance out of range is refused."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d)
        rc, out = tc.run(d, "dice")
        assert rc == 0 and "The dice: off." in out and "dice on --chance 25" in out, out
        rc, out = tc.run(d, "dice", "on", "--chance", "40")
        assert rc == 0, out
        got = mcm(d)
        assert got.get("seasons_zone/main/dice") == "true", got
        assert got.get("seasons_zone/main/dice_chance") == "40", got
        assert "a 40% chance at each launch of another season" in out, out
        rc, out = tc.run(d, "dice", "off")
        got = mcm(d)
        assert got.get("seasons_zone/main/dice") == "false", got
        assert got.get("seasons_zone/main/dice_chance") == "40", "off lost the chance: %s" % got
        rc, out = tc.run(d, "dice", "--chance", "0")
        assert rc == 1 and "whole number from 1 to 100" in out, out
        assert mcm(d).get("seasons_zone/main/dice_chance") == "40", "a refused chance was saved"
        rc, out = tc.run(d, "dice", "on", "--chance", "100")
        assert "every launch rolls another season" in out, out
        rc, out = tc.run(d, "status", tool="season.py")
        assert row(out, "dice") == "every launch rolls another season", out
    return "shown, 40% on, off with 40 kept, 0 refused, 100 read back by season.py"


@case
def t_the_window_saves_the_dice_with_everything_else():
    """The advanced editor's dice, driven the way a click would: an unsaved change shows, a
    chance that isn't 1 to 100 holds Save back, and Save writes MCM's file. Switched off, a
    chance that can't be typed over goes back to the saved one."""
    driver = r'''
import sys
sys.path.insert(0, sys.argv[1])
import tkinter as tk
import config_edit as ce
import configure
root = tk.Tk()
root.withdraw()
cal, inst = ce.Calendar(), ce.Install()
app = configure.App(root, cal, inst)
print("dirty at start", app.dice.dirty())
app.dice.on.set(True)
app.dice.chance.set("140")
app.dice.changed()
print("note", app.dice.note.cget("text"))
print("saved bad", app.save(quiet=True))
app.dice.chance.set("40")
app.dice.changed()
print("note", app.dice.note.cget("text"))
print("status", app.status.cget("text"))
print("dirty before", app.dice.dirty())
print("saved", app.save(quiet=True))
print("dirty after", app.dice.dirty())
app.dice.chance.set("x")
app.dice.on.set(False)
app.dice.changed()
print("off", app.dice.chance.get(), app.dice.box.cget("state"))
root.destroy()
'''
    with tempfile.TemporaryDirectory() as d:
        tc.install(d)
        p = os.path.join(d, "drive.py")
        io.open(p, "w", encoding="utf-8").write(driver)
        r = subprocess.run([sys.executable, p, os.path.join(d, "_tools")], cwd=d,
                           capture_output=True, text=True)
        out = r.stdout + r.stderr
        assert r.returncode == 0, out
        for want in ("dirty at start False", "note The chance is a whole number from 1 to 100.",
                     "saved bad False", "note A 40% chance at each launch of another season.",
                     "the dice at 40%", "dirty before True", "saved True", "dirty after False",
                     "off 40 disabled"):
            assert want in out, "%r not in:\n%s" % (want, out)
        got = mcm(d)
        assert got.get("seasons_zone/main/dice") == "true", got
        assert got.get("seasons_zone/main/dice_chance") == "40", got
    return "140 held back, 40 saved to MCM's file, nothing left unsaved, off puts 40 back"


@case
def t_the_guided_setup_shows_and_saves_the_dice():
    """configure.bat's summary says the dice. Its Seasons step sets them, won't be left
    with a chance that isn't 1 to 100, counts them unsaved until Save, and saves them to
    MCM's file on their own when nothing else changed."""
    import test_guide as tg
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                             '"above": "Grass Compat"}}\n')
        before = tc.config(d)
        rc, out = tg.drive(d, r'''
t = texts(g.body)
print("ROW", t[t.index("The dice") + 1])
g.edit("seasons")
settle()
print("UNSAVED AT START", g.unsaved())
g.dice.on.set(True)
g.dice.chance.set("0")
g.dice.changed()
print("LEAVE BAD", g.leave("seasons"), said[-1])
g.dice.chance.set("40")
g.dice.changed()
print("UNSAVED", g.unsaved())
print("REVIEW", [r for r in g.review_rows() if r[0] == "The dice"])
g.save_edit()
print("SAID", said[-1])
t = texts(g.body)
print("MODE", g.mode, "ROW AFTER", t[t.index("The dice") + 1])
''')
        assert rc == 0, out
        for want in ("ROW off", "UNSAVED AT START False",
                     "LEAVE BAD False ('showerror', \"The dice's chance is a whole number "
                     "from 1 to 100.\")", "UNSAVED True",
                     "REVIEW [('The dice', 'a 40% chance at each launch of another season')]",
                     "SAID ('showinfo', 'The dice: a 40% chance at each launch of another "
                     "season.\\nplay.bat rolls them at each launch from the next one.')",
                     "MODE summary ROW AFTER a 40% chance at each launch of another season"):
            assert want in out, "%r not in:\n%s" % (want, out)
        got = mcm(d)
        assert got.get("seasons_zone/main/dice") == "true", got
        assert got.get("seasons_zone/main/dice_chance") == "40", got
        assert tc.config(d) == before, "the dice changed seasons_config.py"
    return "summary off, 0 held on the step, 40 saved alone to MCM's file, summary updated"


# --- the game's side ----------------------------------------------------------------------

ROLL_FILE = ("; generated by _tools/season.py from seasons_config.py - do not edit by hand\r\n"
             "[calendar]\r\ncustom = false\r\ndial = default\r\n\r\n"
             "[roll]\r\nseason = %s\r\ndraw = %s\r\nchance = %s\r\nday = 2026-07-15\r\n")
SPELL = ("\r\n[spell]\r\nseason = autumn\r\nname = Early frost\r\nfirst = 2026-07-14\r\n"
         "last = 2026-07-16\r\n")


def mix(g):
    return dict(g.zzz_seasons_of_the_zone.season_mix())


def engine(lua, g):
    """The console, time events and PDA news a first update reaches for; the news sent."""
    lua.execute("""
        function fake_console()
            local c = {}
            function c:execute(cmd) end
            function c:get_string(name) return nil end
            return c
        end""")
    con = g.fake_console()
    g.get_console = lambda: con
    g.CreateTimeEvent = lambda *a: None
    sent = []
    g.news_manager = lua.table_from({"send_tip": lambda actor, msg, *a: sent.append(msg)})
    return sent


@case
def t_the_game_follows_the_roll_until_the_next_launch():
    """season_calendar.ltx's [roll] runs its season in every layer, the day after too: a
    roll lasts the launch, not a date. An MCM pin wins over it, and it wins over a spell. A
    roll the file gets wrong, or on a season the calendar has off, is left out, with a line
    in the log."""
    roll = ROLL_FILE % ("winter", "5", "25")
    for day in (15, 16):
        _, g = tcal.build(2026, 7, day, calendar=roll)
        m = mix(g)
        assert m["winter"] == 1.0 and m["summer"] == 0, (day, m)
        assert abs(g.zzz_seasons_of_the_zone.snow_factor() - 0.60) < 1e-9
    _, g = tcal.build(2026, 7, 15, calendar=roll, mcm={"seasons_zone/main/mode": "spring"})
    assert mix(g)["spring"] == 1.0, "the roll won over a pin: %s" % mix(g)
    _, g = tcal.build(2026, 7, 15, calendar=roll + SPELL)
    assert mix(g)["winter"] == 1.0, "a spell won over the roll: %s" % mix(g)
    _, g = tcal.build(2026, 7, 15)
    assert mix(g)["summer"] == 1.0, "no roll, and not the calendar: %s" % mix(g)

    bad = [ROLL_FILE % ("winterr", "5", "25"), ROLL_FILE % ("winter", "x", "25"),
           (ROLL_FILE % ("winter", "5", "25")).replace("chance = 25\r\n", "")]
    for b in bad:
        _, g = tcal.build(2026, 7, 15, calendar=b)
        assert mix(g)["summer"] == 1.0, "a broken roll was followed: %s" % mix(g)
        assert any("roll in it can't be used" in l for l in tcal.LOG), tcal.LOG
    off = dict(tcal.OWN)
    text = tcal.calendar_text(off) + "\r\n[roll]\r\nseason = spring\r\ndraw = 5\r\nchance = 25\r\n"
    _, g = tcal.build(2026, 7, 1, calendar=text)
    assert mix(g)["spring"] == 0, "a roll on a season turned off was followed: %s" % mix(g)
    return "winter both days, a pin over it, it over a spell; 4 bad rolls left out"


@case
def t_the_game_says_what_was_rolled():
    """MCM's calendar rows and the PDA greeting name the rolled season beside the
    calendar's, sotz_api.season() says rolled, and the textures staged for it raise no
    warning while textures staged for another season still do."""
    roll = ROLL_FILE % ("winter", "5", "25")
    lua, g = tcal.build(2026, 7, 15, calendar=roll, mcm={"seasons_zone/main/blend_days": 0},
                        staged={"season": "winter", "staging": "on"})
    sent = engine(lua, g)
    run, rows, announce = tcal.probe(lua, g, "actor_on_first_update", "calendar_rows",
                                     "pda_announce")
    run()
    got = [r["text"] for r in rows().values()]
    assert ("Rolled winter for this launch - the calendar reads summer. The next launch "
            "through play.bat rolls again.") in got, got
    announce()
    assert sent == ["Winter in the Zone, by the dice. The calendar reads summer."], sent
    assert not any("TEXTURES ARE STAGED" in l for l in tcal.LOG), tcal.LOG

    src = io.open(os.path.join(tcal.SCRIPTS, "sotz_api.script"), encoding="utf-8").read()
    s = g.load_in(src, "sotz_api", g).season()
    assert (s["key"], s["calendar"], s["pinned"], s["rolled"], s["spell"]) == (
        "winter", "summer", False, True, None), dict(s)

    lua, g = tcal.build(2026, 7, 15, calendar=roll, staged={"season": "summer", "staging": "on"})
    engine(lua, g)
    tcal.probe(lua, g, "actor_on_first_update")[0]()
    assert any("TEXTURES ARE STAGED FOR SUMMER" in l for l in tcal.LOG), tcal.LOG

    _, g = tcal.build(2026, 7, 15, calendar=roll, mcm={"seasons_zone/main/mode": "spring"})
    s = g.load_in(src, "sotz_api", g).season()
    assert (s["key"], s["pinned"], s["rolled"]) == ("spring", True, False), dict(s)
    return "the MCM row, the greeting and the API name winter; staged summer still warned"


if __name__ == "__main__":
    print("  the dice, under %s for the game's side" % tcal.LUA_NAME)
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
