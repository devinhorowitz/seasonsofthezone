"""Run the SHIPPED snowfall patcher against a stand-in for INVERNO's script.

INVERNO's yawm_snowfall.script is not ours to ship, so this builds a small script with
the same anchors and particle locals and runs the patcher on it as a user would, in a
scratch folder. Older copies come from the patcher's own git history, so the update
path is tested against what earlier releases actually wrote.

  python _tools/test_snowfall_patch.py
"""
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCHER = os.path.join(ROOT, "patches", "apply_seasonal_snowfall.py")
SRC = io.open(PATCHER, encoding="utf-8").read()
NEEDS = re.findall(r"'(snow_particle_\w+)'", re.search(r"NEEDS = \[([^\]]+)\]", SRC).group(1))
A_HOOK = re.search(r"A_HOOK = '([^']+)'", SRC).group(1)

# The first patcher that shipped, and the last release. The first has a different banner
# title and no blank line above the helpers.
OLD = ["c43348c", "v1.7.0"]


def fixture(blank_before_update=False, nl="\n"):
    lines = ["-- stand-in for yawm_snowfall.script: the anchors and locals the patcher reads",
             "",
             "function on_game_start()",
             '\tRegisterScriptCallback("actor_on_update", actor_on_update)',
             "end",
             ""]
    lines += ['local %s = particles_object("fixture")' % n for n in NEEDS]
    lines += ["",
              "local weather_to_particles = {}",
              "local function switch_particles(tbl, pos, inside) end",
              "",
              "local inside_pos"]
    lines += [""] if blank_before_update else []
    lines += ["function actor_on_update()",
              "\tlocal weather = level.get_weather()",
              "\tif weather then",
              "\t\t" + A_HOOK,
              "\tend",
              "end",
              ""]
    return nl.join(lines)


def load_patcher():
    """The patcher's functions, without running its main()."""
    body, tail = SRC.rsplit("\nmain()", 1)
    assert not tail.strip(), "the patcher no longer ends with main()"
    ns = {"__name__": "patcher_under_test", "__file__": PATCHER}
    exec(compile(body, PATCHER, "exec"), ns)
    return ns


def old_patcher(rev, where):
    r = subprocess.run(["git", "-C", ROOT, "show", "%s:patches/apply_seasonal_snowfall.py" % rev],
                       capture_output=True)
    assert r.returncode == 0, "git could not produce the %s patcher" % rev
    p = os.path.join(where, "old_%s.py" % rev.replace(".", "_"))
    open(p, "wb").write(r.stdout)
    return p


def run(patcher, script, *extra):
    r = subprocess.run([sys.executable, patcher, script] + list(extra),
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def put(folder, text, name="yawm_snowfall.script"):
    p = os.path.join(folder, name)
    io.open(p, "w", encoding="latin-1", newline="").write(text)
    return p


def data(p):
    return open(p, "rb").read()


def fresh_patch(text):
    """What the current patcher makes of a pristine copy of `text`."""
    d = tempfile.mkdtemp()
    try:
        p = put(d, text)
        rc, out = run(PATCHER, p)
        assert rc == 0, "a fresh patch failed:\n" + out
        return data(p)
    finally:
        shutil.rmtree(d)


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_a_fresh_copy_is_patched_and_backed_up():
    with tempfile.TemporaryDirectory() as d:
        orig = fixture()
        p = put(d, orig)
        rc, out = run(PATCHER, p)
        assert rc == 0 and "patched" in out, out
        assert data(p + ".orig") == orig.encode("latin-1"), "the backup is not the original"
        text = data(p).decode("latin-1")
        assert "zzz_seasons_of_the_zone" in text, "no seasonal gate in the patched copy"
        lines = text.split("\n")
        assert ("\t\t" + A_HOOK) not in lines, "the original hook line is still there"
        n = sum(1 for l in lines if l == "\t\tswitch_particles(resolved, inside_pos, is_inside)")
        assert n == 1, "the new hook line appears %d times with the caller's indent" % n
    return "gate in, hook replaced at the caller's indent, backup identical"


@case
def t_a_second_run_changes_nothing():
    with tempfile.TemporaryDirectory() as d:
        p = put(d, fixture())
        run(PATCHER, p)
        before = data(p)
        rc, out = run(PATCHER, p)
        assert rc == 0 and "already up to date" in out, out
        assert data(p) == before, "an up-to-date copy was rewritten"
    return "an up-to-date copy is left byte for byte"


@case
def t_an_older_patch_is_brought_up_to_date():
    done = []
    with tempfile.TemporaryDirectory() as d:
        for rev in OLD:
            old = old_patcher(rev, d)
            orig = fixture()
            p = put(d, orig, "yawm_%s.script" % rev.replace(".", "_"))
            rc, out = run(old, p)
            assert rc == 0, "the %s patcher failed on the fixture:\n%s" % (rev, out)
            want = fresh_patch(orig)
            assert data(p) != want, ("the %s patch already matches the current one, so this "
                                     "case proves nothing" % rev)
            rc, out = run(PATCHER, p)
            assert rc == 0 and "updated" in out, "%s: %s" % (rev, out)
            assert data(p) == want, "the %s copy, updated, differs from a fresh patch" % rev
            assert data(p + ".orig") == orig.encode("latin-1"), "the update touched the backup"
            done.append(rev)
    return "%s copies updated to exactly a fresh patch" % " and ".join(done)


@case
def t_unpatch_gives_back_the_original():
    ns = load_patcher()
    with tempfile.TemporaryDirectory() as d:
        orig = fixture(blank_before_update=True)
        p = put(d, orig)
        run(PATCHER, p)
        got = ns["unpatch"](data(p).decode("latin-1").splitlines())
        assert got == orig.splitlines(), "unpatch did not return the original lines"

        # without a blank above actor_on_update, patch() adds one and unpatch keeps it
        orig = fixture()
        p = put(d, orig)
        os.remove(p + ".orig")
        run(PATCHER, p)
        got = ns["unpatch"](data(p).decode("latin-1").splitlines())
        want = fixture(blank_before_update=True).splitlines()
        assert got == want, "unpatch did not return the original plus the one blank line"
    return "original lines back, with the one documented blank line"


@case
def t_a_hand_edited_copy_is_refused():
    with tempfile.TemporaryDirectory() as d:
        p = put(d, fixture())
        run(PATCHER, p)
        text = data(p).decode("latin-1")
        edited = "\n".join(l for l in text.split("\n")
                           if l.strip() != "report(resolved, weather, w)")
        assert edited != text
        put(d, edited)
        rc, out = run(PATCHER, p)
        assert rc != 0 and "Nothing was changed" in out, out
        assert data(p) == edited.encode("latin-1"), "a refused copy was written anyway"
    return "a copy it cannot take apart is refused and left alone"


@case
def t_crlf_survives_an_update():
    with tempfile.TemporaryDirectory() as d:
        old = old_patcher(OLD[-1], d)
        orig = fixture(nl="\r\n")
        p = put(d, orig)
        run(old, p)
        rc, out = run(PATCHER, p)
        assert rc == 0 and "updated" in out, out
        b = data(p)
        assert b.count(b"\n") == b.count(b"\r\n") > 100, "line endings were changed"
        assert b == fresh_patch(orig), "the CRLF copy, updated, differs from a fresh patch"
    return "all %d line endings still CRLF" % b.count(b"\r\n")


@case
def t_revert_restores_the_original():
    with tempfile.TemporaryDirectory() as d:
        orig = fixture()
        p = put(d, orig)
        run(PATCHER, p)
        rc, out = run(PATCHER, p, "--revert")
        assert rc == 0 and "restored" in out, out
        assert data(p) == orig.encode("latin-1"), "revert did not restore the original"
    return "the backup comes back byte for byte"


@case
def t_every_particle_season_exists():
    """A misspelt season in SEASON_OF never matches season_mix(), so that particle would
    quietly never play. Every name has to be one of season.py's."""
    seasons = re.search(r"^SEASONS = \(([^)]*)\)", io.open(
        os.path.join(ROOT, "_tools", "season.py"), encoding="utf-8").read(), re.M).group(1)
    seasons = set(re.findall(r'"(\w+)"', seasons))
    table = re.search(r"local SEASON_OF = \{(.*?)\n\}", SRC, re.S).group(1)
    table = re.sub(r"--[^\n]*", "", table)
    rows = re.findall(r"\[(snow_particle_\w+)\]\s*=\s*\{([^}]*)\}", table)
    assert len(rows) >= 8, "read only %d rows of SEASON_OF" % len(rows)
    named = set()
    for particle, names in rows:
        for s in re.findall(r'"(\w+)"', names):
            assert s in seasons, "%s names %r, which is not a season" % (particle, s)
            named.add(s)
    fog1 = dict(rows)["snow_particle_fog1"]
    assert "late_winter" in fog1, "the thaw has no mist"
    return "%d particles, %d seasons named, all real" % (len(rows), len(named))


if __name__ == "__main__":
    print("  running the shipped snowfall patcher in a scratch folder")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-38s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-38s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-38s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
