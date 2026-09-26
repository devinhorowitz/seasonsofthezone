"""The guided setup configure.bat opens to, and the summary it opens to once there is one.

Each case drives the window in a scratch install, as a player would click through it,
and checks the file it saves the way the game reads it: season.py has to accept it.

  python _tools/test_guide.py
"""
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
import test_configure as tc                                     # noqa: E402

OFFLINE = dict(os.environ, SEASONS_OFFLINE="1")
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# The GAMMA example, for the scratch install: two mods it has installed, one it hasn't
EXAMPLE = {"seasons_of_the_zone_preset": 1, "shipped": True,
           "about": "The setup these tools were made on.",
           "mods": {"Winter Pack": {"when": ["winter", "winter_snow"],
                                    "above": "Grass Compat"},
                    "Map Pack": {"when": ["summer"], "above": "Lonely Mod"},
                    "Not Here": {"when": ["autumn"], "above": "Base Grass"}},
           "events": {}, "periods": {}}
CALENDARS = ("Polesia", "Meteorological", "Two seasons", "Southern hemisphere")
ENTRIES = "[customExecutables]\n1\\title=Anomaly (DX11-AVX)\n2\\title=Anomaly (DX11)\n"


def sandbox(d, config=None, example=True, play=True):
    tc.install(d, config=config)
    tc.with_mod(d)
    presets = os.path.join(d, "_tools", "presets")
    os.makedirs(presets)
    for name in CALENDARS:
        shutil.copy2(os.path.join(HERE, "presets", name + ".json"), presets)
    if example:
        io.open(os.path.join(presets, "GAMMA example.json"), "w",
                encoding="utf-8").write(json.dumps(EXAMPLE))
    if play:
        shutil.copy2(os.path.join(os.path.dirname(HERE), "play.bat"), d)
        io.open(os.path.join(d, "ModOrganizer.ini"), "a", encoding="utf-8").write(ENTRIES)


DRIVER = r"""
import sys, time
sys.path.insert(0, sys.argv[1])
sys.dont_write_bytecode = True
import tkinter as tk
from tkinter import messagebox
said = []
for f in ("showerror", "showinfo", "showwarning"):
    setattr(messagebox, f, lambda *a, _f=f, **k: said.append((_f, a[1] if len(a) > 1 else "")))
messagebox.askyesno = lambda *a, **k: True
messagebox.askyesnocancel = lambda *a, **k: False
import config_edit as ce
import configure as cf
import guide
root = tk.Tk()
root.withdraw()

def settle(n=10):
    for _ in range(n):
        root.update()
        time.sleep(0.01)

def widgets(w):
    for c in w.winfo_children():
        yield c
        yield from widgets(c)

def texts(w):
    out = []
    for c in widgets(w):
        try:
            out.append(str(c.cget("text")))
        except tk.TclError:
            pass
    return out

g = guide.Guide(root, ce.Calendar(), ce.Install())
settle()
"""


def drive(d, script):
    p = os.path.join(d, "drive.py")
    io.open(p, "w", encoding="utf-8").write(DRIVER + script + "\nroot.destroy()\n")
    r = subprocess.run([sys.executable, "-B", p, os.path.join(d, "_tools")], cwd=d,
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       env=OFFLINE, timeout=180)
    return r.returncode, r.stdout + r.stderr


def table(d):
    ns = {}
    exec(tc.config(d) or "", ns)
    return ns


@case
def t_a_first_run_goes_through_the_steps():
    """No setup yet: the steps, starting from the GAMMA example with the mods it knows
    that are installed, then a calendar, the weather, a review, and a save the game
    accepts."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        rc, out = drive(d, r"""
print("MODE", g.mode, g.current())
opts = g.start_options()
print("OPTIONS", [k for k, _, _ in opts], g.default_start())
print("ABOUT", [a for k, _, a in opts if k == "default"][0])
g.next()
print("MODS", g.current(), sorted(g.cal.toggle))
print("WINTER", g.cal.toggle["Winter Pack"]["when"], g.cal.toggle["Winter Pack"]["above"])
g.next()
print("SEASONS", g.current(), g.cal_var.get())
g.cal_var.set("Two seasons")
g.pick_calendar()
g.next()
print("WEATHER", g.current(), g.where.get(), g.cal.place)
g.next()
print("REVIEW", g.current(), [r[0] for r in g.review_rows()])
print("TODAY", [t for t in texts(g.body) if t.startswith("Today is")])
g.next()
print("DONE", g.current(), bool(g.saved_lines), said)
print("PLAY", g.shortcut_status.cget("text"))
""")
        assert rc == 0, out
        assert "MODE steps start" in out, out
        assert "OPTIONS ['default', 'clean'] default" in out, out
        assert "set up for the 2 of 3 you have installed" in out, out
        assert "MODS mods ['Map Pack', 'Winter Pack']" in out, out
        assert "WINTER ['winter', 'winter_snow'] Grass Compat" in out, out
        assert "SEASONS seasons Polesia" in out and "WEATHER weather chornobyl None" in out, out
        assert "REVIEW review ['Seasonal mods', 'Seasons', 'Weather from']" in out, out
        assert "TODAY ['Today is" in out, out
        assert "DONE done True []" in out, out
        assert "PLAY ✓ MO2 has this entry" in out, out
        t = table(d)
        assert set(t["TOGGLE_MODS"]) == {"Winter Pack", "Map Pack"}, t["TOGGLE_MODS"]
        assert t["CALENDAR"] == {"summer": (5, 1), "winter_snow": (11, 15)}, t["CALENDAR"]
        tc.accepted(d)
    return ("the GAMMA example's 2 installed mods of 3, Two seasons, Chornobyl, reviewed and "
            "saved; season.py accepts it")


@case
def t_what_the_steps_change_survives_back_and_next():
    """Going back to Start and on again keeps what the later steps changed; a new choice
    there starts over from it."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        rc, out = drive(d, r"""
g.next()
g.check_mod("Map Pack", False)
print("DROPPED", sorted(g.cal.toggle))
g.back()
g.next()
print("KEPT", sorted(g.cal.toggle))
g.check_mod("Map Pack", True)
print("BACK", sorted(g.cal.toggle), g.cal.toggle["Map Pack"]["when"])
g.back()
g.start_choice = "clean"
g.next()
print("CLEAN", sorted(g.cal.toggle))
""")
        assert rc == 0, out
        assert "DROPPED ['Winter Pack']" in out and "KEPT ['Winter Pack']" in out, out
        assert "BACK ['Map Pack', 'Winter Pack'] ['summer']" in out, out
        assert "CLEAN []" in out, out
        assert tc.config(d) is None, "the steps wrote the file before Review"
    return "an unchecked mod stays unchecked through Back; a new start choice starts over"


@case
def t_a_mod_is_added_and_changed_from_its_dialog():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        rc, out = drive(d, r"""
g.start_choice = "clean"
g.next()
dlg = guide.ModDialog(g)
dlg.query.set("lonely")
settle()
print("LISTED", dlg.shown)
dlg.list.selection_set(0)
dlg.vars["spring"].set(True)
dlg.vars["freezing"].set(True)
dlg.ok()
print("ADDED", g.cal.toggle["Lonely Mod"]["when"], repr(g.cal.toggle["Lonely Mod"]["above"]))
dlg = guide.ModDialog(g, "Lonely Mod")
for s in dlg.vars:
    dlg.vars[s].set(False)
dlg.ok()
print("EMPTY", said[-1])
dlg.win.destroy()
""")
        assert rc == 0, out
        assert "LISTED ['Lonely Mod']" in out, out
        assert "ADDED ['spring', 'freezing'] 'Base Grass'" in out, out
        assert "Check at least one season" in out, out
    return "found by a search, on in spring and on freezing days, placed for you"


@case
def t_the_seasons_step_holds_a_bad_calendar():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        rc, out = drive(d, r"""
g.start_choice = "clean"
g.next(); g.next()
g.cal_var.set("own")
g.pick_calendar()
on, mon, day, runs = g.own_rows["winter"]
day.set("22")
g.own_edited()
print("BAD", g.seasons_bad, g.dial.text.cget("text") if g.dial.bsd else "no dial")
g.next()
print("STAYED", g.current(), said[-1][1][:40])
day.set("1")
g.own_edited()
g.name_vars["winter_snow"].set("The Long Cold")
g.names_on.set(True)
g.show_names()
g.names_edited()
print("NAMED", g.cal.names, g.seasons_bad, g.names_bad)
g.next()
print("ON", g.current())
""")
        assert rc == 0, out
        assert "BAD ['Winter would last 9 days" in out, out
        assert "STAYED seasons Fix the seasons first" in out, out
        assert "NAMED {'winter_snow': 'The Long Cold'} [] []" in out and "ON weather" in out, out
    return "a 9-day winter keeps the step, and the dial blank; fixed, and a name given, it goes on"


@case
def t_the_summary_saves_one_part_at_a_time():
    """With a setup, the window opens to the summary; Change opens one step, and Save
    there writes only that."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                          '"above": "Grass Compat"}}\n')
        rc, out = drive(d, r"""
print("MODE", g.mode)
print("ROWS", [t for t in texts(g.body) if t.startswith(("1:", "Polesia", "Chornobyl"))])
g.edit("seasons")
g.cal_var.set("Meteorological")
g.pick_calendar()
g.save_edit()
print("BACK", g.mode, said[-1][0])
g.edit("mods")
g.check_mod("Winter Pack", False)
g.summary()
print("CANCELLED", sorted(g.cal.toggle))
""")
        assert rc == 0, out
        assert "MODE summary" in out, out
        assert "1: Winter Pack" in out, out
        assert "BACK summary showinfo" in out, out
        assert "CANCELLED ['Winter Pack']" in out, out
        t = table(d)
        assert t["CALENDAR"]["spring"] == (4, 1) and set(t["TOGGLE_MODS"]) == {"Winter Pack"}, t
        tc.accepted(d)
    return "opened to the summary; the calendar saved from its own step; a cancel kept nothing"


@case
def t_play_bat_s_entry_is_checked_and_set():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                          '"above": "Grass Compat"}}\n')
        rc, out = drive(d, r"""
import installer
print("NOW", g.shortcut_combo.get(), "|", g.shortcut_status.cget("text"))
g.shortcut_combo.set("Anomaly (DX11)")
g.shortcut_combo.event_generate("<<ComboboxSelected>>")
settle()
print("SET", installer.read_shortcut(sys.argv[1] + "/../play.bat"), "|",
      g.shortcut_status.cget("text"))
""")
        assert rc == 0, out
        assert "NOW Anomaly (DX11-AVX) | ✓ MO2 has this entry" in out, out
        assert "SET Anomaly (DX11) | ✓ MO2 has this entry" in out, out
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, play=False)
        rc, out = drive(d, r"""
g.shortcut_row(g.body)
print("MISSING", g.shortcut_status.cget("text"))
""")
        assert rc == 0 and "MISSING play.bat isn't in your GAMMA folder" in out, out
    return "MO2's entry confirmed, another picked and written to play.bat; a missing play.bat said"


@case
def t_the_advanced_editor_is_a_button_away():
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                          '"above": "Grass Compat"}}\n')
        rc, out = drive(d, r"""
def close_it():
    tops = [w for w in root.winfo_children() if isinstance(w, tk.Toplevel)]
    print("EDITOR", [t.title() for t in tops], root.state())
    for t in tops:
        t.destroy()
root.after(600, close_it)
g.advanced()
print("AFTER", g.mode, root.state())
""")
        assert rc == 0, out
        assert "EDITOR ['Seasons of the Zone setup'] withdrawn" in out, out
        assert "AFTER summary normal" in out, out
    return "the tabbed editor opens in its own window, and the summary comes back after it"


@case
def t_a_file_broken_meanwhile_is_said_not_summed_up():
    """seasons_config.py broken by hand while the window is open: the summary says so,
    rather than showing an empty setup as if it were the saved one."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                          '"above": "Grass Compat"}}\n')
        rc, out = drive(d, r"""
import io
io.open(ce.CONFIG, "w", encoding="utf-8").write("TOGGLE_MODS = {\n")
g.summary()
print("SAYS", [t for t in texts(g.body) if "can't be read now" in t][:1])
print("ROWS", [t for t in texts(g.body) if t == "Change..."])
""")
        assert rc == 0, out
        assert "SAYS [\"seasons_config.py can't be read now:" in out, out
        assert "ROWS []" in out, out
    return "the summary names the file and the line, and offers nothing to change"


@case
def t_the_weather_step_takes_a_place_found_or_given():
    """A place from the search, or by its coordinates; a bad latitude said and not taken;
    Next held until a place is picked; the credits beside what came from Open-Meteo."""
    with tempfile.TemporaryDirectory() as d:
        sandbox(d)
        rc, out = drive(d, r"""
import fetch_weather
fetch_weather.search = lambda text, count=8: [
    {"name": "Kyiv", "lat": 50.4547, "lon": 30.5238, "where": "Kyiv City, Ukraine"}]
g.start_choice = "clean"
g.next(); g.next(); g.next()
g.where.set("elsewhere")
g.pick_where()
g.next()
print("HELD", g.current(), said[-1][1][:30])
print("CREDITS", "Places from Open-Meteo.com," in texts(g.page),
      any("Copernicus" in x for x in texts(g.page)))
g.query.set("Kyiv")
g.find_place()
for _ in range(100):
    settle(1)
    if g.found.size():
        break
g.use_found()
print("FOUND", g.cal.place)
g.lat.set("95"); g.lon.set("30"); g.named.set("Home")
g.use_coords()
print("BAD", g.found_msg.cget("text")[:40], g.cal.place["name"])
g.lat.set("48,85"); g.lon.set("2.35")
g.use_coords()
print("GIVEN", g.cal.place)
g.next()
print("ON", g.current())
""")
        assert rc == 0, out
        assert "HELD weather Pick a place from the search" in out, out
        assert "CREDITS True True" in out, out
        assert "FOUND {'name': 'Kyiv', 'lat': 50.4547, 'lon': 30.5238}" in out, out
        assert "BAD Lat must be the latitude in degrees, -90 Kyiv" in out, out
        assert "GIVEN {'name': 'Home', 'lat': 48.85, 'lon': 2.35}" in out, out
        assert "ON review" in out, out
    return "found by name, given by coordinates (a comma for the point too), 95 refused"


@case
def t_an_overlap_in_a_season_is_asked_not_picked():
    """A mod made seasonal where another seasonal mod on at the same time ships some of the
    same files: the player says whose the game uses, and that decides which one wins over
    the other."""
    got = {}
    for answer in (True, False):
        with tempfile.TemporaryDirectory() as d:
            sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                              '"above": "Grass Compat"}}\n')
            rc, out = drive(d, r"""
asked = []
def fake(g, name, other, n, seasons, parent=None):
    asked.append((name, other, n, seasons))
    return %s
guide.ask_winner = fake
g.edit("mods")
dlg = guide.ModDialog(g)
dlg.query.set("overlay")
settle()
dlg.list.selection_set(0)
dlg.vars["winter"].set(True)
dlg.ok()
print("ASKED", asked)
print("ABOVE", g.cal.toggle["Winter Overlay"]["above"], "|", g.cal.toggle["Winter Pack"]["above"])
""" % answer)
            assert rc == 0, out
            assert "ASKED [('Winter Overlay', 'Winter Pack', 1, 'winter')]" in out, out
            got[answer] = [l for l in out.splitlines() if l.startswith("ABOVE")][0]
    assert got[True] == "ABOVE Winter Pack | Grass Compat", got
    assert got[False].endswith("| Winter Overlay"), got
    return "asked whose files; Winter Overlay's puts it over Winter Pack, Winter Pack's the other way"


@case
def t_backing_out_of_the_overlap_questions_changes_nothing():
    """Two seasonal mods share files with the one being added. The first question answered
    the other mod's way, the second backed out of: nothing may have moved, in memory or in
    the file a save then writes."""
    config = ('TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), "above": "Grass Compat"},\n'
              '               "Base Grass": {"when": ("winter",), "above": "Lonely Mod"}}\n')
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config=config)
        before = tc.config(d)
        rc, out = drive(d, r"""
answers = [False, None]
asked = []
def fake(g, name, other, n, seasons, parent=None):
    asked.append(other)
    return answers[len(asked) - 1]
guide.ask_winner = fake
g.edit("mods")
dlg = guide.ModDialog(g)
dlg.query.set("overlay")
settle()
dlg.list.selection_set(0)
dlg.vars["winter"].set(True)
dlg.ok()
dlg.win.destroy()
print("ASKED", asked)
print("TOGGLE", sorted((n, c["above"]) for n, c in g.cal.toggle.items()))
g.save_edit()
""")
        assert rc == 0, out
        assert "ASKED ['Winter Pack', 'Base Grass']" in out or \
            "ASKED ['Base Grass', 'Winter Pack']" in out, out
        assert "TOGGLE [('Base Grass', 'Lonely Mod'), ('Winter Pack', 'Grass Compat')]" in out, \
            out
        assert tc.config(d) == before, "a save after backing out changed the file"
    return "answered once, backed out of the second: nothing moved, and the file unchanged"


@case
def t_a_seasonal_mod_installs_from_its_archive():
    """The case this was made for: an archive in the GAMMA folder whose name says winter,
    an installer of two parts, and a fix file from its author. Found on the step, installed
    with one part and the fix, made seasonal in winter, set to win over the seasonal mod it
    recolors - then saved, and placed by season.py."""
    import test_mod_install as tm
    with tempfile.TemporaryDirectory() as d:
        sandbox(d, config='TOGGLE_MODS = {"Winter Pack": {"when": ("winter",), '
                          '"above": "Grass Compat"}}\n')
        top = "Winter Recolor 1.2"
        xml = tm.fomod_xml([("Parts", [tm.group_xml("Parts", "SelectAtLeastOne", [
            tm.plugin_xml("Grass", [("folder", "gamedata\\textures\\grass",
                                     "gamedata\\textures\\grass")]),
            tm.plugin_xml("Ground", [("folder", "gamedata\\textures\\terrain",
                                      "gamedata\\textures\\terrain")])])])])
        tm.make(os.path.join(d, "Winter Recolor 1.2.7z"), {
            top + "/fomod/ModuleConfig.xml": xml.encode("utf-8"),
            top + "/gamedata/textures/grass/a.dds": b"recolor a",
            top + "/gamedata/textures/grass/b.dds": b"recolor b",
            top + "/gamedata/textures/terrain/t.dds": b"recolor t"})
        io.open(os.path.join(d, "b.dds"), "wb").write(b"the author's fix")
        rc, out = drive(d, r"""
import os
from tkinter import filedialog
gamma = os.path.dirname(sys.argv[1])
filedialog.askopenfilename = lambda **k: os.path.join(gamma, "b.dds")
asked = []
guide.ask_winner = lambda g, name, other, n, seasons, parent=None: (
    asked.append((name, other, n, seasons)) or True)
g.edit("mods")
print("FOUND", [x for x in texts(g.page) if x.startswith("Winter Recolor")])
dlg = guide.InstallDialog(g, os.path.join(gamma, "Winter Recolor 1.2.7z"))
for _ in range(300):
    settle(1)
    if dlg.win is not None:
        break
print("GUESS", sorted(s for s, v in dlg.seasons.items() if v.get()))
dlg.name.set("Winter Recolor")
names = {p["id"]: p["name"] for p in dlg.pkg.fomod.plugins()}
for pid, (var, value) in dlg.chosen.items():
    if names[pid] == "Ground":
        var.set(False)
dlg.add_extra()
print("EXTRA", [(os.path.basename(a), b) for a, b in dlg.extra])
dlg.go()
for _ in range(600):
    settle(1)
    if "Winter Recolor" in g.cal.toggle:
        break
c = g.cal.toggle["Winter Recolor"]
print("SEASONAL", c["when"], c["above"], asked)
print("ROW", [x for x in texts(g.page) if x.startswith("new: ")])
g.save_edit()
print("SAVED", said[-1][0])
""")
        assert rc == 0, out
        assert "FOUND ['Winter Recolor 1.2.7z']" in out, out
        assert "GUESS ['late_winter', 'winter', 'winter_snow']" in out, out
        assert "EXTRA [('b.dds', 'gamedata/textures/grass/b.dds')]" in out, out
        assert ("SEASONAL ['winter', 'winter_snow', 'late_winter'] Winter Pack "
                "[('Winter Recolor', 'Winter Pack', 2, 'winter')]") in out, out
        assert "ROW [\"new: play.bat adds it to MO2's mod list\"]" in out, out
        assert "SAVED showinfo" in out, out
        mod = os.path.join(d, "mods", "Winter Recolor")
        grass = os.path.join(mod, "gamedata", "textures", "grass")
        assert open(os.path.join(grass, "b.dds"), "rb").read() == b"the author's fix"
        assert open(os.path.join(grass, "a.dds"), "rb").read() == b"recolor a"
        assert not os.path.exists(os.path.join(mod, "gamedata", "textures", "terrain"))
        assert os.path.isfile(os.path.join(mod, "meta.ini"))
        assert table(d)["TOGGLE_MODS"]["Winter Recolor"]["above"] == "Winter Pack"
        tc.accepted(d)
        rc, out = tc.run(d, "apply", "--dry-run", "--season", "winter", tool="season.py")
        assert rc == 0 and "Winter Recolor" in out, out
    return ("found, one part of two and the fix installed, winter guessed from its name, set "
            "over the mod it recolors; saved and placed")


if __name__ == "__main__":
    print("  the guided setup")
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
