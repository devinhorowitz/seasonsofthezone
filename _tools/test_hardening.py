"""The shipped season.py against configs built to break it.

Each case is a config someone could write, or a state an install could be in, that once
crashed season.py with a traceback, was read as something else without a word, or wrote
something wrong into modlist.txt. season.py promises a plain message naming the entry
instead, and nothing changed on a refusal. Every case runs the real tools in a scratch
install, and each fails on the code before it was fixed.

  python _tools/test_hardening.py
"""
import io
import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import test_configure as tc                                     # noqa: E402

BASE = '''LAYOUT = {}
TOGGLE_MODS = {}
SOUND_SRC = None
PERIODS = {}
EVENTS = {}
CALENDAR = None
NAMES = None
'''


def cfg(**tables):
    """BASE with the named tables replaced by the given source text."""
    lines = []
    for line in BASE.splitlines():
        var = line.split(" = ")[0]
        lines.append("%s = %s" % (var, tables.pop(var)) if var in tables else line)
    assert not tables, tables
    return "\n".join(lines) + "\n"


def status(d, *args):
    """season.py status (or another command) in `d`: (exit code, output). run() fails the
    case on a traceback, which is what most of these are about."""
    return tc.run(d, *(args or ("status",)), tool="season.py")


def refused(text, says, command="status"):
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=text)
        tc.with_mod(d)
        rc, out = status(d, command)
        assert rc != 0 and "needs fixing" in out and says in out, \
            "%r did not refuse with %r:\n%s" % (text, says, out)


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_a_calendar_of_the_wrong_shape_is_a_message():
    shape = "CALENDAR['summer']: the start must be (month, day)"
    for table, says in (
            ('{"summer": {"month": 5, "day": 20}}', shape),
            ('{"summer": "5-20"}', shape),
            ('[("summer", 5, 20)]', "CALENDAR must be a table"),
            ('{"summer": "51"}', shape),
            ('{"summer": (5.9, 20)}', shape),
            ('{"summer": (True, 1)}', shape),
            ('{"summer": (5, 20), "winter": (float("inf"), 1)}', "CALENDAR['winter']")):
        refused(cfg(CALENDAR=table), says)
    # whowins runs before the config is read, so a broken calendar never blocks it
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(CALENDAR='{"summer": "5-20"}'))
        rc, out = status(d, "whowins", "textures/grass/a.dds")
        assert rc == 0 and "Base Grass" in out, out
    return "7 shapes refused with the entry named; whowins still answers"


@case
def t_periods_and_events_are_checked():
    for tables, says in (
            (dict(PERIODS='{"high_summer": (2, 29)}'), "February 29"),
            (dict(PERIODS='{"high_summer": (13, 1)}'), "PERIODS['high_summer']: the start"),
            (dict(PERIODS='{"high_summer": "7-1"}'), "PERIODS['high_summer']: the start"),
            (dict(PERIODS="None"), "PERIODS must be a table"),
            (dict(PERIODS='{"early_autumn": (9, 15)}'), "the same day as autumn"),
            (dict(PERIODS='{"summer": (7, 1)}'),
             "PERIODS['summer']: that is already a season"),
            (dict(EVENTS='{"christmas": ("12-24", "12-26")}'),
             "EVENTS['christmas']: give its first and last day"),
            (dict(EVENTS='{"christmas": ((12, 24),)}'),
             "EVENTS['christmas']: give its first and last day"),
            (dict(EVENTS='{"summer": ((9, 20), (9, 30))}'),
             "EVENTS['summer']: that is already a season"),
            (dict(EVENTS='{"odd": {"days": (31,), "months": (2,)}}'), "never happens"),
            (dict(EVENTS='{"x": ((12, 24), (12, 26))}', PERIODS='{"x": (7, 1)}'),
             "both a period and an event")):
        refused(cfg(**tables), says)
    return "11 bad periods and events refused, each named"


@case
def t_mods_that_cannot_work_are_refused():
    entry = '{"when": ("winter",), "above": "Grass Compat"}'
    for table, says in (
            ('{"Seasons of the Zone": %s}' % entry, "that is this mod itself"),
            ('{"Winter Pack": {"when": ("winter",), "above": "Winter Pack"}}',
             '"above" is the mod itself'),
            ('{"Winter Pack": {"when": ("winter",), "above": "Map Pack"}, '
             '"Map Pack": {"when": ("winter",), "above": "Winter Pack"}}', "in a circle"),
            ('{"Winter Pack": {"when": ("winter",), "seasons": ("winter",), '
             '"above": "Grass Compat"}}', 'both "when" and "seasons"'),
            ('{"Winter Pack ": %s}' % entry, "spaces at its start or end"),
            ('{5: %s}' % entry, "is not a name in quotes"),
            ('{"Winter Pack": {"When": ("winter",), "above": "Grass Compat"}}',
             '(it has "When")'),
            ('{"Winter Pack": {"when": (), "above": "Grass Compat"}}', '"when" is empty')):
        refused(cfg(TOGGLE_MODS=table), says)
    return "8 kinds of entry refused, from the mod itself to a loop of anchors"


@case
def t_the_weather_a_mod_can_be_scoped_to_is_accepted():
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS='{"Winter Pack": {"when": ("freezing", "thaw"), '
                                               '"above": "Grass Compat"}}'))
        rc, out = status(d)
        assert rc == 0 and "needs fixing" not in out, out
    return "freezing and thaw, as docs/API.md says"


@case
def t_texture_sets_that_cannot_be_read_are_refused():
    for table, says in (
            ('{"Base Grass": {"archive": "grass.zip", "options": {"summer": ["Summer"]}}}',
             "must be a .7z or .rar"),
            ('{"Base Grass": {"archive": "grass.7z", "options": {"christmas": ["X"]}}}',
             '"christmas" in "options" is not a season or a period')):
        refused(cfg(LAYOUT=table, EVENTS='{"christmas": ((12, 24), (12, 26))}'), says)
    return "a .zip and an event's options"


@case
def t_the_config_is_read_fresh_every_time():
    """Python's bytecode cache trusts a copy whose source has the same size and whole-second
    time. configure.py can save twice in a second, and season.py then ran the first."""
    a = cfg(TOGGLE_MODS='{"Winter Pack": {"when": ("spring",), "above": "Grass Compat"}}')
    b = a.replace('("spring",)', '("autumn",)')
    assert len(a) == len(b)
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=a)
        path = os.path.join(d, "_tools", "seasons_config.py")
        st = os.stat(path)
        import subprocess
        # without -B, as play.bat runs it: the old import would cache this version
        subprocess.run([sys.executable, os.path.join(d, "_tools", "season.py"), "status"],
                       capture_output=True, cwd=d)
        io.open(path, "w", encoding="utf-8").write(b)
        os.utime(path, (st.st_atime, st.st_mtime))
        r = subprocess.run([sys.executable, os.path.join(d, "_tools", "season.py"), "status"],
                           capture_output=True, text=True, cwd=d)
        out = r.stdout + r.stderr
        # 2026-09-25 is autumn, so the new version switches Winter Pack on
        assert "(today: on)" in out, "ran the old config:\n" + out
    return "a second save in the same second, same size, is what runs"


@case
def t_a_config_in_another_encoding_is_a_message():
    head = "# Зимние текстуры\n"
    with tempfile.TemporaryDirectory() as d:
        tc.install(d)
        path = os.path.join(d, "_tools", "seasons_config.py")
        io.open(path, "w", encoding="utf-16").write(BASE)
        rc, out = status(d)
        assert rc != 0 and "UTF-16" in out, out
        io.open(path, "w", encoding="cp1251").write(head + BASE)
        rc, out = status(d)
        assert rc != 0 and "not saved as UTF-8" in out, out
        io.open(path, "w", encoding="cp1251").write("# -*- coding: cp1251 -*-\n" + head + BASE)
        rc, out = status(d)
        assert rc == 0 and "needs fixing" not in out, out
    return "UTF-16 and cp1251 named; cp1251 with a coding line runs"


@case
def t_exit_in_the_config_is_a_message():
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config="import sys\nsys.exit(0)\n" + BASE)
        rc, out = status(d)
        assert rc != 0 and "stops the program" in out and "line 2" in out, out
    return "line 2, and a message, not a silent exit 0"


@case
def t_every_assignment_to_a_table_is_seen():
    refused(cfg(TOGGLE_MODS='{"Winter Pack": {"when": ("winter",), "above": "Grass Compat"}}')
            + "if True:\n    TOGGLE_MODS = {}\n", "sets TOGGLE_MODS again")
    refused(cfg(TOGGLE_MODS='{\n    "Winter Pack": {"when": ("winter",), "above": "Grass Compat"},'
                            '\n    "Winter Pack": {"when": ("spring",), "above": "Grass Compat"},'
                            '\n}'), 'lists "Winter Pack" twice')
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=BASE.replace("CALENDAR = None",
                                          "CALENDAR: dict\nCALENDAR = None"))
        rc, out = status(d)
        assert rc == 0 and "needs fixing" not in out, "a bare annotation was counted:\n" + out
    return "a table replaced in an if, an entry listed twice; a bare annotation is no assignment"


def with_archive(d):
    """downloads/grass.7z with a Summer and a Winter set, and Base Grass holding Summer."""
    import py7zr
    src = os.path.join(d, "_arch")
    for opt in ("Summer", "Winter"):
        p = os.path.join(src, opt, "gamedata", "textures", "grass", "a.dds")
        os.makedirs(os.path.dirname(p))
        io.open(p, "w").write(opt)
    os.makedirs(os.path.join(d, "downloads"), exist_ok=True)
    with py7zr.SevenZipFile(os.path.join(d, "downloads", "grass.7z"), "w") as z:
        for opt in ("Summer", "Winter"):
            z.writeall(os.path.join(src, opt), opt)
    live = os.path.join(d, "mods", "Base Grass", "gamedata", "textures", "grass")
    for f in os.listdir(live):
        os.remove(os.path.join(live, f))
    io.open(os.path.join(live, "a.dds"), "w").write("Summer")


@case
def t_gaps_in_the_texture_sets_do_not_stop_a_launch():
    """A LAYOUT mod that is not installed, or has no option for today's season, is left as
    it is. Both crashed apply, which play.bat runs before every launch."""
    layout = ('{"Ghost Grass": {"archive": "grass.7z", "options": {"autumn": ["Summer"]}}, '
              '"Base Grass": {"archive": "grass.7z", "options": {"summer": ["Summer"], '
              '"winter": ["Winter"]}}}')
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(LAYOUT=layout))
        with_archive(d)
        rc, out = status(d, "apply")
        assert rc == 0, out
        assert "not in mods/ - left alone" in out, out
        assert "no option for autumn in LAYOUT - what it has stays" in out, out
        assert not os.path.isdir(os.path.join(d, "mods", "Ghost Grass")), "made Ghost Grass"
        grass = os.path.join(d, "mods", "Base Grass", "gamedata", "textures", "grass", "a.dds")
        assert io.open(grass).read() == "Summer", "restaged the textures"
    return "Ghost Grass and a missing autumn option: named, and left alone"


@case
def t_a_mod_name_in_the_wrong_case_is_kept_out_of_the_modlist():
    """Windows finds "winter pack" for "Winter Pack"; modlist.txt does not, and apply wrote
    a line for a mod MO2 has no folder for."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS='{"winter pack": {"when": ("autumn",), '
                                                '"above": "Grass Compat"}}'))
        ml = os.path.join(d, "profiles", "Default", "modlist.txt")
        before = io.open(ml, encoding="utf-8").read()
        rc, out = status(d, "apply")
        assert rc == 0 and "not installed" in out and 'MO2 has "Winter Pack"' in out, out
        assert io.open(ml, encoding="utf-8").read() == before, "modlist.txt was changed"
    return "not installed, with the right name; modlist.txt untouched"


@case
def t_a_skipped_mod_is_not_reported_as_done():
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS='{"Winter Pack": {"when": ("autumn",), '
                                                '"above": "grass compat"}}',
                                 SOUND_SRC='"No Such Mod"'))
        rc, out = status(d)
        assert "skipped: the mod it wins over" in out and "1 seasonal mod skipped" in out, out
        assert "already on" not in out, out
        assert '"No Such Mod" is not in MO2\'s mod list' in out, out
    return "the anchor typo counted in the summary; the sound source named"


@case
def t_names_reach_the_game():
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(NAMES='{"winter_snow": "The Long Cold"}'))
        game, tex = tc.with_mod(d)
        rc, out = status(d, "dial")
        body = io.open(game, encoding="cp1251").read()
        assert rc == 0 and "custom = true" in body and "name_winter_snow = The Long Cold" in body, \
            out + body
        assert tc.drawn(tex) == 32, "no dial drawn for the name"
    for table, says in (('{"winter_snow": "x" * 21}', "21 characters"),
                        ('{"winter_snow": "Χειμώνας"}', "letters the game can't show"),
                        ('{"summer": "Winter"}', "would both be called"),
                        ('{"winter_snow": "a;b"}', "can't contain"),
                        ('{"deep winter": "Cold"}', "not a season")):
        refused(cfg(NAMES=table), says)
    return "a name drawn and handed on; five bad ones refused"


@case
def t_a_missing_archive_skips_only_its_texture_set():
    """An archive gone from downloads/ stopped status and apply whole, so play.bat launched
    with no seasonal mod switched. Only that texture set is skipped now, and one with no
    option for the day is named but not counted: it would not have changed."""
    layout = ('{"Base Grass": {"archive": "gone.7z", "options": {"summer": ["Summer"], '
              '"autumn": ["Autumn"]}}, "Grass Compat": {"archive": "gone.rar", '
              '"options": {"winter": ["Winter"]}}}')
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(LAYOUT=layout, TOGGLE_MODS='{"Winter Pack": {"when": '
                                 '("autumn",), "above": "Grass Compat"}}'))
        grass = os.path.join(d, "mods", "Base Grass", "gamedata", "textures", "grass")
        before = {f: io.open(os.path.join(grass, f)).read() for f in os.listdir(grass)}
        rc, out = status(d, "apply", "--season", "autumn")
        assert rc == 0, out
        assert "gone.7z is not in downloads" in out and "gone.rar is not in downloads" in out \
            and "1 texture set skipped" in out, out
        ml = io.open(os.path.join(d, "profiles", "Default", "modlist.txt"),
                     encoding="utf-8").read()
        assert "+Winter Pack" in ml, "the seasonal mods were not switched:\n" + out
        after = {f: io.open(os.path.join(grass, f)).read() for f in os.listdir(grass)}
        assert after == before, "the texture set was changed"
    return "both archives named, one set skipped and left alone; Winter Pack still switched"


@case
def t_the_file_check_judges_the_order_apply_leaves():
    """The check ran on MO2's order as it was, not as apply leaves it, so right after a mod
    was set to win over another it still said the other won, and to swap them."""
    def run(mods=tc.MODS, **tables):
        with tempfile.TemporaryDirectory() as d:
            tc.install(d, config=cfg(**tables), mods=mods)
            rc, out = status(d, "status")
            assert rc == 0, out
            return out.splitlines()

    def naming(lines, *names):
        return [i for i, l in enumerate(lines) if all(n in l for n in names)]

    # Winter Overlay is above Winter Pack in MO2, and Winter Pack is set to win over it
    lines = run(TOGGLE_MODS='{"Winter Overlay": {"when": ("winter",), "above": "Base Grass"}, '
                            '"Winter Pack": {"when": ("winter",), "above": "Winter Overlay"}}')
    assert not naming(lines, "Winter Overlay", "Winter Pack"), "\n".join(lines)
    # the control: set to win over Grass Compat, Winter Pack stays under Winter Overlay,
    # which wins one of its files; said beside the mods, not above the date
    lines = run(TOGGLE_MODS='{"Winter Overlay": {"when": ("winter",), "above": "Base Grass"}, '
                            '"Winter Pack": {"when": ("winter",), "above": "Grass Compat"}}')
    both = naming(lines, "Winter Overlay", "Winter Pack")
    assert both and both[0] > naming(lines, "  season ")[0], "\n".join(lines)
    # at the bottom, under both grass mods: apply lifts it above them, so nothing wins
    low = ([m for m in tc.MODS if m[0] != "Winter Pack"]
           + [m for m in tc.MODS if m[0] == "Winter Pack"])
    lines = run(low, TOGGLE_MODS='{"Winter Pack": {"when": ("winter",), '
                                 '"above": "Grass Compat"}}')
    assert not [l for l in lines if l.startswith("  ! Winter Pack")], "\n".join(lines)

    # A mod MO2 does not list yet, and an "above" changed while MO2's list stays as it was:
    # apply runs the check again, and places the mod where apply will add it
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS='{"Winter Pack": {"when": ("winter",), '
                                             '"above": "Grass Compat"}}'))
        ml = os.path.join(d, "profiles", "Default", "modlist.txt")
        text = io.open(ml, encoding="utf-8", newline="").read()
        io.open(ml, "w", encoding="utf-8", newline="").write(
            text.replace("-Winter Pack\r\n", ""))
        rc, out = status(d, "status")
        assert rc == 0 and "  ! Winter Pack" not in out, out
        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w", encoding="utf-8").write(
            cfg(TOGGLE_MODS='{"Winter Pack": {"when": ("winter",), "above": "Base Grass"}}'))
        rc, out = status(d, "apply", "--dry-run")
        assert rc == 0 and '  ! Winter Pack loses 1 file to "Grass Compat"' in out, out
    return "no swap asked for; the rival, the lift and a new above each judged as apply leaves"


@case
def t_sound_gating_switched_off_is_said_as_off():
    """With gating off in MCM apply takes the soundscape out, but status said it would move
    to the season."""
    presets = "configs/environment/ambients/presets/a.ltx"
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(SOUND_SRC='"Ambience"'),
                   mods=tc.MODS + [("Ambience", True, [presets])])
        staged = os.path.join(d, "mods", "Seasonal Soundscape", "gamedata",
                              *presets.split("/"))
        os.makedirs(os.path.dirname(staged))
        io.open(staged, "w").write(";; seasonal-soundscape season=summer cuts=0\n")
        ow = os.path.join(d, "overwrite", "gamedata", "configs")
        os.makedirs(ow)
        io.open(os.path.join(ow, "axr_options.ltx"), "w").write(
            "[mcm]\nseasons_zone/main/stage_sound = false\n")
        rc, out = status(d, "status", "--season", "autumn")
        said = [l for l in out.splitlines() if l.startswith("  => sound")]
        assert rc == 0 and said == ["  => sound   : summer -> off (gating is off in MCM)"], out
        rc, out = status(d, "apply", "--season", "autumn")
        assert rc == 0 and not os.path.exists(staged), out
    return "summer -> off, and apply takes it out"


@case
def t_season_lists_what_it_can_stage():
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(EVENTS='{"xmas": ((12, 24), (12, 26))}'))
        rc, out = status(d, "status", "--season", "wintr")
        assert rc != 0 and ("These are: spring, summer, autumn, winter, winter_snow, "
                            "late_winter, xmas") in out, out
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(CALENDAR='{"summer": (5, 1), "winter_snow": (11, 15)}'))
        rc, out = status(d, "status", "--season", "late_winter")
        assert rc != 0 and "has late winter off. These are: summer, winter_snow" in out, out
    return "the seasons in their usual order, then events; a season that is off said so"


@case
def t_a_mod_set_to_win_through_another_is_not_a_note():
    """Winter Overlay wins over Winter Maps, which wins over Winter Pack: that Overlay wins
    Pack's files is the setup, not a mistake to point at. And the hint to check again after
    enabling a mod is said once, not under every mod it applies to."""
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS=(
            '{"Winter Overlay": {"when": ("winter",), "above": "Winter Maps"}, '
            '"Winter Maps": {"when": ("winter",), "above": "Winter Pack"}, '
            '"Winter Pack": {"when": ("winter",), "above": "Grass Compat"}}')))
        rc, out = status(d, "status")
        assert rc == 0 and "Winter Overlay\" wins" not in out, out
    # the control: set to win over something else, the same overlap is worth a note
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS=(
            '{"Winter Overlay": {"when": ("winter",), "above": "Base Grass"}, '
            '"Winter Pack": {"when": ("winter",), "above": "Grass Compat"}}')))
        rc, out = status(d, "status")
        assert rc == 0 and "\"Winter Overlay\" wins 1 of Winter Pack" in out, out
    with tempfile.TemporaryDirectory() as d:
        tc.install(d, config=cfg(TOGGLE_MODS=(
            '{"Grass Compat": {"when": ("winter",), "above": "Base Grass"}, '
            '"Map Pack": {"when": ("winter",), "above": "Lonely Mod"}}')))
        rc, out = status(d, "status")
        assert out.count("would win some of") == 2, out
        assert out.count("After enabling one") == 1, out
    return "an overlap through the chain left alone, the control noted; one hint for two mods"


if __name__ == "__main__":
    print("  breaking the shipped season.py")
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
