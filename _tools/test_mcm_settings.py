"""MCM settings that follow the season: another mod's option in MCM, set by play.bat before
the game starts, to its value for what is on that day or its value the rest of the year.
Made on the command line and in the windows, carried by presets, kept in step when what
they follow is renamed or removed, and written into MCM's own file without touching the
rest of it.

  python _tools/test_mcm_settings.py
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
HERE_NOW = season.season_for(TODAY)
OTHER = "winter" if HERE_NOW != "winter" else "summer"
CRLF = "\r\n"
# MCM's file as the engine writes it: sections, padded keys, a space-only line between
STORE = CRLF.join([
    "[character_creation]",
    "        new_game_money                   =",
    " ",
    "[mcm]",
    "        cold_system/debugx               = false",
    "        cold_system/wind                 = 1",
    "        cold_system/winter               = false",
    "        other_mod/name                   = Зима",   # Cyrillic
    " ",
    "[options]",
    "        x                                = 1",
    ""])


def case(fn):
    CASES.append(fn)
    return fn


def store(d, text=STORE):
    """MCM's file in the scratch install's overwrite/, as bytes; its path."""
    ow = os.path.join(d, "overwrite", "gamedata", "configs")
    os.makedirs(ow, exist_ok=True)
    p = os.path.join(ow, "axr_options.ltx")
    open(p, "wb").write(text.encode("cp1251"))
    return p


@case
def t_play_bat_sets_each_option_and_leaves_the_rest_of_the_file_be():
    """status says what each option will be and what MCM has now; apply sets them in
    MCM's file, line by line, with the file kept first; the next run has nothing to do; a
    change made in MCM is set back at the next launch; an option MCM hasn't saved yet is
    added to [mcm]."""
    config = ('MCM_SETTINGS = {"cold_system/winter": {%r: True, "else": False},\n'
              '                "cold_system/wind": {%r: 2.5, "else": 1},\n'
              '                "new_mod/level": {%r: 3, "else": 1}}\n'
              % (HERE_NOW, OTHER, HERE_NOW))
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        tc.with_mod(d)
        p = store(d)
        before = open(p, "rb").read()
        rc, out = tc.run(d, "status", tool="season.py")
        rows = [l for l in out.splitlines() if "cold_system/" in l or "new_mod/" in l]
        assert rc == 0 and rows == [
            "  MCM settings    cold_system/winter = true   (%s)   (now false)"
            % season.season_label(HERE_NOW),
            "                  cold_system/wind = 1   (the rest of the year)",
            "                  new_mod/level = 3   (%s)   (not in MCM's file yet)"
            % season.season_label(HERE_NOW)], out
        assert "MCM settings need setting" in out and open(p, "rb").read() == before, out
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "false -> true" in out and "not set -> 3" in out \
            and "MCM settings set" in out, out
        after = open(p, "rb").read()
        want = before.replace(b"cold_system/winter               = false",
                              b"cold_system/winter               = true").replace(
            b"        other_mod/name                   = \xc7\xe8\xec\xe0\r\n",
            b"        other_mod/name                   = \xc7\xe8\xec\xe0\r\n"
            b"        new_mod/level                    = 3\r\n")
        assert after == want, after
        kept = os.listdir(os.path.join(d, "_baseline", "modfile-backups"))
        assert [k for k in kept if k.startswith("axr_options-")], kept
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "already on" in out and open(p, "rb").read() == after, out
        open(p, "wb").write(after.replace(b"= true", b"= false"))
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "false -> true" in out and open(p, "rb").read() == after, out
    return "said, set line by line, kept first, idle next time, set back after MCM"


@case
def t_a_store_left_in_the_game_folder_is_the_one_set():
    """With none in overwrite/ and no mod shipping one, the file a start without MO2 left in
    the game's own gamedata/ is MCM's: apply sets the line there and keeps the rest, rather
    than making one in overwrite/ that would hide the player's other settings."""
    config = 'MCM_SETTINGS = {"cold_system/winter": {%r: True, "else": False}}\n' % HERE_NOW
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        tc.with_mod(d)
        game = os.path.join(d, "ANOMALY")
        io.open(os.path.join(d, "ModOrganizer.ini"), "a", encoding="utf-8").write(
            "gamePath=@ByteArray(%s)\r\n" % game.replace("\\", "\\\\"))
        p = os.path.join(game, "gamedata", "configs", "axr_options.ltx")
        os.makedirs(os.path.dirname(p))
        open(p, "wb").write(STORE.encode("cp1251"))
        rc, out = tc.run(d, "apply", tool="season.py")
        want = STORE.encode("cp1251").replace(b"cold_system/winter               = false",
                                              b"cold_system/winter               = true")
        assert rc == 0 and open(p, "rb").read() == want, out
        assert not os.path.exists(os.path.join(d, "overwrite", "gamedata", "configs",
                                               "axr_options.ltx")), out
    return "set in place there, and none made in overwrite/"


@case
def t_the_most_specific_name_wins():
    """Of an option's names on today, a kind of weather wins, then a spell, an event, a
    season of one's own, and the season; of two alike, the first listed; with none on, its
    "else"."""
    spec = {"winter": 1, "Frost": 2, "christmas": 3, "Deep days": 4, "freezing": 5,
            "new_year": 6, "else": 0}

    def rank(n):
        return season.mcm_rank(n, spells={"Frost": {}}, events={"christmas": 1, "new_year": 1},
                               own={"Deep days": 1})
    got = [season.mcm_values(on, {"x/y": spec}, rank)["x/y"] for on in (
        ["winter", "Deep days", "christmas", "Frost", "freezing"],
        ["winter", "Deep days", "christmas", "Frost"],
        ["winter", "Deep days", "christmas"],
        ["winter", "Deep days"],
        ["winter"],
        ["summer", "new_year", "christmas"],
        ["summer"])]
    assert got == [(5, "freezing"), (2, "Frost"), (3, "christmas"), (4, "Deep days"),
                   (1, "winter"), (3, "christmas"), (0, None)], got
    return "weather, spell, event, own, season; the first of two events; else"


@case
def t_mcm_settings_follow_their_rules():
    """What season.py says about each way an MCM setting can be wrong."""
    known = list(season.SEASONS) + ["christmas"] + list(season.WEATHER_NAMES)
    got = season.mcm_problems({
        "cold_system/winter": {"winter": True, "else": False},
        "nopage": {"winter": 1, "else": 0},
        "seasons_zone/main/mode": {"winter": "winter", "else": "auto"},
        "a/b": {"winter": True},
        "a/c": {"else": 1},
        "a/d": {"winterr": 1, "else": 0},
        "a/e": {"winter": True, "else": 1},
        "a/f": {"winter": " x", "else": "y"},
        "a/g": {"winter": float("nan"), "else": 1.0},
        "a/h": {"winter": [1], "else": 1},
        "a/i": ["winter"],
    }, known)
    want = [
        "MCM_SETTINGS['nopage']: an option is named as MCM saves it: its page and the option, "
        "with / between, like \"cold_system/winter\".",
        "MCM_SETTINGS['seasons_zone/main/mode']: that is one of this mod's own options, which "
        "follow the season already. Take the entry out.",
        "MCM_SETTINGS['a/b']: it needs \"else\", its value the rest of the year.",
        "MCM_SETTINGS['a/c']: it names no season, event, spell or weather, so it would never "
        "change.",
        "MCM_SETTINGS['a/d']: \"winterr\" is not a season, an event, a spell or weather. "
        "Valid: %s." % ", ".join(known),
        "MCM_SETTINGS['a/e']: its values are of more than one kind; MCM keeps an option as a "
        "checkbox, a number or text. Give each the same kind.",
        "MCM_SETTINGS['a/f']: the value for \"winter\" can't be empty, start or end with a "
        "space, or hold ; [ ], a line break or a letter the game can't show.",
        "MCM_SETTINGS['a/g']: the value for \"winter\" isn't a number MCM can hold.",
        "MCM_SETTINGS['a/h']: the value for \"winter\" must be True, False, a number or text in "
        "quotes.",
        "MCM_SETTINGS['a/i'] must be {\"winter\": True, \"else\": False}: a value for each "
        "season, event, spell or weather it names, and one for the rest of the year.",
    ]
    assert got == want, "\n".join(got)
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config='MCM_SETTINGS = {"a/b": {"winter": True}}\n')
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc != 0 and "it needs \"else\"" in out, out
    return "%d problems, one per fault; play.bat refuses a file with one" % len(want)


@case
def t_the_mcm_command():
    """configure.py mcm: finds MCM's options, adds one by --in and --to, one by --set with a
    decimal comma, refuses a number for a checkbox, lists them, keeps an event they follow,
    and removes one."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config='EVENTS = {"christmas": ((12, 24), (12, 26))}\n')
        store(d)
        rc, out = tc.run(d, "mcm", "--find", "cold wind")
        assert rc == 0 and out.split() == ["cold_system/wind", "1"], out
        rc, out = tc.run(d, "mcm", "cold_system/winter", "--in", "winter", "deep winter",
                         "freezing", "christmas", "--to", "true", "--else", "false")
        assert rc == 0 and "added an MCM setting for cold_system/winter: true in winter, " \
            "deep winter, freezing and christmas; false the rest of the year" in out, out
        rc, out = tc.run(d, "mcm", "cold_system/wind", "--set", "deep winter=2", "winter=1,5")
        assert rc == 0 and "2 in deep winter; 1.5 in winter; 1 the rest of the year" in out, out
        rc, out = tc.run(d, "mcm", "cold_system/winter", "--set", "summer=2")
        assert rc == 1 and "isn't true or false, and this option is a checkbox" in out, out
        rc, out = tc.run(d, "mcm", "typo/option", "--in", "winter", "--to", "1")
        assert rc == 1 and "needs --else" in out, out
        rc, out = tc.run(d, "event", "christmas", "--remove")
        assert rc == 1 and "These MCM settings still follow christmas" in out, out
        rc, out = tc.run(d, "mcm", "cold_system/wind", "--remove")
        assert rc == 0 and "MCM keeps the value it has now" in out, out
        ns = tg.table(d)
        assert list(ns["MCM_SETTINGS"]) == ["cold_system/winter"], ns
        assert ns["MCM_SETTINGS"]["cold_system/winter"] == {
            "winter": True, "winter_snow": True, "freezing": True, "christmas": True,
            "else": False}, ns
        tc.accepted(d)
    return "found, added two ways, a checkbox kept a checkbox, listed, the event kept, removed"


@case
def t_mcm_settings_follow_renames_and_removals():
    """A season of one's own renamed is renamed in the settings that follow it; a spell
    taken off takes off the settings that follow nothing else, and says so."""
    config = ('OWN_SEASONS = {"Wormhole season": ((8, 1), (8, 31))}\n'
              'SPELLS = {"Frost": {"in": ("summer",), "chance": 3, "days": 1, "as": None}}\n'
              'MCM_SETTINGS = {"a/b": {"Wormhole season": 2, "winter": 3, "else": 1},\n'
              '                "a/c": {"Frost": True, "else": False}}\n')
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        rc, out = tc.run(d, "season", "Wormhole season", "--rename", "Rostok wormhole")
        assert rc == 0, out
        assert tg.table(d)["MCM_SETTINGS"]["a/b"] == {"Rostok wormhole": 2, "winter": 3,
                                                      "else": 1}, tg.table(d)
        rc, out = tc.run(d, "spell", "Frost", "--remove")
        assert rc == 0 and "stopped setting a/c, which followed nothing else" in out, out
        rc, out = tc.run(d, "season", "Rostok wormhole", "--remove")
        assert rc == 0, out
        assert tg.table(d)["MCM_SETTINGS"] == {"a/b": {"winter": 3, "else": 1}}, tg.table(d)
        tc.accepted(d)
    return "renamed with the season; the spell's own setting taken off with it, and said"


@case
def t_the_game_running_holds_the_settings_for_the_next_launch():
    """With the game open, MCM would save its own values over the file as it closes: apply
    leaves the file be and says so."""
    config = 'MCM_SETTINGS = {"cold_system/winter": {%r: True, "else": False}}\n' % HERE_NOW
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=config)
        tc.with_mod(d)
        p = store(d)
        before = open(p, "rb").read()
        drive = os.path.join(d, "busy.py")
        io.open(drive, "w", encoding="utf-8").write(
            "import sys\nsys.path.insert(0, sys.argv[1])\nimport season\n"
            "season.running = lambda: ['anomalydx11avx.exe']\n"
            "sys.argv = ['season.py', 'apply']\nseason.main()\n")
        r = subprocess.run([sys.executable, "-B", drive, os.path.join(d, "_tools")], cwd=d,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        assert r.returncode == 0 and "wait for the next launch: anomalydx11avx.exe is " \
            "running" in out and open(p, "rb").read() == before, out
    return "the file left as it was, and why"


@case
def t_a_preset_carries_mcm_settings_and_what_they_follow():
    """A preset of the mods carries the MCM settings, and loaded elsewhere brings the
    season of one's own they follow."""
    config = ('OWN_SEASONS = {"Wormhole season": ((8, 1), (8, 31))}\n'
              'MCM_SETTINGS = {"a/b": {"Wormhole season": 2, "else": 1}}\n')
    with tempfile.TemporaryDirectory() as d, tempfile.TemporaryDirectory() as e:
        tc.install(d, config=config)
        rc, out = tc.run(d, "preset", "save", "Mine", "--parts", "mods")
        assert rc == 0, out
        tc.install(e)
        os.makedirs(os.path.join(e, "_tools", "presets"))
        src = os.path.join(d, "_tools", "presets", "Mine.json")
        io.open(os.path.join(e, "_tools", "presets", "Mine.json"), "wb").write(
            open(src, "rb").read())
        rc, out = tc.run(e, "preset", "load", "Mine")
        assert rc == 0 and "season Wormhole season came with a/b" in out \
            and "MCM settings: 1" in out, out
        ns = tg.table(e)
        assert ns["MCM_SETTINGS"] == {"a/b": {"Wormhole season": 2, "else": 1}} \
            and ns["OWN_SEASONS"] == {"Wormhole season": ((8, 1), (8, 31))}, ns
        tc.accepted(e)
    return "carried, with the season it follows"


@case
def t_the_windows_make_and_list_mcm_settings():
    """The setup's Seasonal mods step lists them and adds one through the dialog: a word of
    the option's name finds it, a number for a checkbox is said to be wrong, and one saved
    reads back; the advanced editor lists them too."""
    with tempfile.TemporaryDirectory() as d:
        tg.sandbox(d, config='MCM_SETTINGS = {"cold_system/wind": {"winter": 2, "else": 1}}\n')
        store(d)
        rc, out = tg.drive(d, r"""
g.edit("mods")
settle()
print("LISTED", [t for t in texts(g.mcm_list) if t.strip()])
win = cf.mcm_dialog(root, g.cal, done=lambda k: g.show_mcm())
settle()
entry = [w for w in widgets(win) if w.winfo_class() == "TEntry"][0]
entry.insert(0, "winter")
settle()
box = [w for w in widgets(win) if w.winfo_class() == "Listbox"][0]
print("FOUND", list(box.get(0, "end")))
# a hidden window gets no <<ListboxSelect>>, so the name goes in as typed in full
entry.delete(0, "end")
entry.insert(0, "cold_system/winter")
settle()
pick = [w for w in widgets(win) if w.winfo_class() == "TCombobox"][0]
pick.set("deep winter")
value = [w for w in widgets(win) if w.winfo_class() == "TEntry"][1]
value.insert(0, "2")
settle()
print("WRONG", [t for t in texts(win) if "checkbox" in t])
value.delete(0, "end")
value.insert(0, "true")
settle()
[w for w in widgets(win) if w.winfo_class() == "TButton" and str(w.cget("text")) == "Add"][0].invoke()
settle()
print("CAL", g.cal.mcm)
print("LISTED", [t for t in texts(g.mcm_list) if t.strip()])
app = cf.App(tk.Toplevel(root), g.cal, g.inst)
settle()
print("EDITOR", [t for t in texts(app.mcm_frame) if t.strip()])
""")
        assert rc == 0 and "Traceback" not in out, out
        assert "LISTED ['cold_system/wind', 'Remove', 'Change...', '2 in winter; 1 the rest " \
            "of the year']" in out, out
        assert "FOUND ['cold_system/winter  =  false']" in out, out
        assert "WRONG ['Now false in MCM. A checkbox: true or false.', '\"2\" isn\\'t true or " \
            "false, and this option is a checkbox.']" in out, out
        assert "CAL {'cold_system/wind': {'winter': 2, 'else': 1}, 'cold_system/winter': " \
            "{'winter_snow': True, 'else': False}}" in out, out
        assert "'true in deep winter; false the rest of the year'" in out, out
        assert "EDITOR ['cold_system/wind', 'Delete', 'Edit...', '2 in winter; 1 the rest of " \
            "the year', 'cold_system/winter', 'Delete', 'Edit...', 'true in deep winter; false " \
            "the rest of the year']" in out, out
    return "found by a word, a checkbox kept one, added and listed in both windows"


if __name__ == "__main__":
    failed = 0
    for fn in CASES:
        name = fn.__name__[2:]
        try:
            print("  PASS  %-58s %s" % (name, fn()))
        except AssertionError as e:
            failed += 1
            print("  FAIL  %-58s %s" % (name, str(e)[:1500]))
    print("%d/%d passed" % (len(CASES) - failed, len(CASES)))
    sys.exit(1 if failed else 0)
