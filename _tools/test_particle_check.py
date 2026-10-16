"""A launch that would crash on a particle a script makes as a save loads is stopped.

The game loads every script in gamedata\\scripts as a game starts, and a particles_object()
outside a script's functions runs then: a name the game doesn't have is a fatal error no
Lua can catch. INVERNO 1.09's snowfall makes its particles that way, from the ones its base
module carries, so with the script in a mod that stays on and the base module seasonal,
every launch outside the winters crashed as the save loaded. These cases build that install
and the places a particle can come from, and run the shipped tools on them.

  python _tools/test_particle_check.py
"""
import io
import os
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402
import test_save_content as tsc                                 # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


def xr(path, effects, groups, version=1, packed=False, refs=()):
    """A particles.xr as the SDK writes one, written out here on its own: the version, then
    the effects and the groups, each def a chunk numbered from 0 with its version in chunk 1
    and its name in chunk 2. Each group lists the effects `refs` in a chunk of its own, as
    names that are not defs."""
    def chunk(cid, data):
        return struct.pack("<II", cid, len(data)) + data

    def defs(names, ver, more=b""):
        return b"".join(chunk(i, chunk(1, struct.pack("<H", ver))
                              + chunk(2, n.encode("cp1251") + b"\0") + more)
                        for i, n in enumerate(names))
    listed = chunk(4, b"".join(r.encode("cp1251") + b"\0" for r in refs))
    data = (chunk(1, struct.pack("<H", version))
            + chunk(3 | (0x80000000 if packed else 0), defs(effects, 1, chunk(5, b"\0" * 12)))
            + chunk(4, defs(groups, 3, listed)))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


# a snowfall that makes its particles as it loads, as INVERNO 1.09's does
SNOWFALL = r"""-- snowfall, made of particles kept in a table as the script loads
function on_game_start()
    RegisterScriptCallback("actor_on_update", actor_on_update)
end

local particles = {
    dust   = particles_object("graupel\\dust"),
    flakes = particles_object("graupel\\snowflakes"),
    mist   = particles_object("lanforse\\fog_mist"),
    light  = particles_object('lanforse\\fog_light'),
    drift  = particles_object("graupel\\dust"),
}

function actor_on_update()
    -- only when it runs, and a save loads without it
    local front = particles_object("graupel\\blizzard_front")
end
"""
SCRIPT = "Inverno_snowfall_system.script"
SEASONAL = "INVERNO Winter (seasonal)"
SNOW = ["particles/graupel/dust.pg", "particles/graupel/effects/dust.pe",
        "particles/graupel/snowflakes.pg", "particles/graupel/effects/snowflakes.pe",
        "particles/graupel/blizzard_front.pg", "textures/terrain/t.dds"]
# highest priority first, as modlist.txt lists them
MODS = [
    ("INVERNO mechanics", True, []),
    (SEASONAL, False, SNOW),
    ("Particles Pack", True, ["particles/lanforse/fog_light.pe"]),
    ("Unused Fog", False, ["particles/fog/unused.pe"]),
    ("Old Particles", True, []),
    ("Base Textures", True, ["textures/terrain/t.dds"]),
    ("Base Grass", True, ["textures/grass/a.dds"]),
    ("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"]),
]
CONFIG = ('TOGGLE_MODS = {\n    "%s": {"when": ("winter",), "above": "Base Textures"},\n}\n'
          % SEASONAL)
SAID = ('! %s, in "INVERNO mechanics", makes 2 particle effects as a save loads that only '
        'mods off for this launch have: graupel\\dust, graupel\\snowflakes.' % SCRIPT)
FIX = ('Copy gamedata\\particles from "%s" into "INVERNO mechanics", the mod with the '
       'script' % SEASONAL)
STOP = "Stopped before the launch"


def mod(root, name, *rel):
    return os.path.join(root, "mods", name, "gamedata", *rel)


def install(root):
    """The setup that crashed: the script in a mod on all year, the particles only in the
    seasonal one; a loose particles.xr that wins, with the fog, and one below it with the
    snow that loses."""
    tc.install(root, config=CONFIG, mods=MODS)
    tc.with_mod(root)
    os.makedirs(mod(root, "INVERNO mechanics", "scripts"))
    io.open(mod(root, "INVERNO mechanics", "scripts", SCRIPT), "w",
            encoding="cp1251").write(SNOWFALL)
    xr(mod(root, "Particles Pack", "particles.xr"), ["lanforse\\fog_mist", "lanforse\\fog_dust"],
       ["explosions\\campfire"])
    xr(mod(root, "Old Particles", "particles.xr"), ["graupel\\effects\\dust"],
       ["graupel\\dust", "graupel\\snowflakes"])


def modlist(root):
    return [l.strip() for l in io.open(os.path.join(root, "profiles", "Default",
                                                    "modlist.txt"), encoding="utf-8")][1:]


def set_state(root, name, sign):
    """`name` on ("+") or off ("-") in MO2's list, where it stands."""
    p = os.path.join(root, "profiles", "Default", "modlist.txt")
    lines = io.open(p, encoding="utf-8", newline="").read().split(tc.CRLF)
    lines = [sign + name if l[1:] == name else l for l in lines]
    io.open(p, "w", encoding="utf-8", newline="").write(tc.CRLF.join(lines))


def run(root, *args):
    return tc.run(root, *args, tool="season.py")


# --- the cases -----------------------------------------------------------------------------

@case
def t_the_launch_that_would_crash_is_stopped_once_staged():
    """Outside the winters the seasonal mod is off and the script on: apply stages the
    season, names the script, its mod, the particles and where they are, and stops before
    the launch. In winter the mod is on and the launch goes ahead; status and a dry run say
    so for autumn, and stop nothing."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 1 and SAID in out and FIX in out and STOP in out, out
        assert "The game crashes on the first" in out, out
        assert "lanforse" not in out and "blizzard_front" not in out, out
        # all was staged before it stopped: the panel the game reads is written
        assert os.path.isfile(mod(d, "Seasons of the Zone", "configs", "season_mods.ltx")), out
        assert "-" + SEASONAL in modlist(d), modlist(d)

        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 0 and "particle effect" not in out and STOP not in out, out
        assert "+" + SEASONAL in modlist(d), modlist(d)

        rc, out = run(d, "status", "--season", "autumn")
        assert rc == 0 and SAID in out and FIX in out and STOP not in out, out
        rc, out = run(d, "apply", "--season", "autumn", "--dry-run")
        assert rc == 0 and SAID in out and STOP not in out, out
        assert "+" + SEASONAL in modlist(d), "a dry run switched it"
        rc, out = run(d, "status", "--season", "winter")
        assert rc == 0 and "particle effect" not in out, out
    return "autumn: staged, named and stopped; winter: launched; status and --dry-run say it"


@case
def t_the_fix_it_names_clears_it():
    with tempfile.TemporaryDirectory() as d:
        install(d)
        shutil.copytree(mod(d, SEASONAL, "particles"), mod(d, "INVERNO mechanics", "particles"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "particle effect" not in out and STOP not in out, out
        assert "-" + SEASONAL in modlist(d), modlist(d)
    return "the seasonal mod's gamedata\\particles copied into the script's mod: launched"


@case
def t_a_particle_from_anywhere_the_game_reads_is_fine():
    """The names can come from a loose particles.xr that wins, a .db in a mod on, MO2's
    overwrite or another mod on; from a particles.xr that loses, they don't."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        xr(mod(d, "Particles Pack", "particles.xr"), ["lanforse\\fog_mist"],
           ["graupel\\dust", "explosions\\campfire"])
        rc, out = run(d, "status", "--season", "autumn")
        assert "only mods off for this launch have: graupel\\snowflakes." in out, out
        assert "makes a particle effect as a save loads" in out and "on it (" in out, out
        db = os.path.join(d, "mods", "Base Textures", "db", "addons", "snow.db")
        for listed in ("particles/graupel/snowflakes.pg", "gamedata/particles/graupel/Snowflakes.pg"):
            tsc.xdb(db, ["textures/sky/a.dds", listed], packed=True)
            rc, out = run(d, "status", "--season", "autumn")
            assert rc == 0 and "particle effect" not in out, (listed, out)

        install_to = os.path.join(d, "overwrite", "gamedata", "particles", "graupel")
        os.remove(os.path.join(d, "mods", "Base Textures", "db", "addons", "snow.db"))
        os.makedirs(install_to)
        io.open(os.path.join(install_to, "Snowflakes.PG"), "w").write("[_group]\n")
        rc, out = run(d, "status", "--season", "autumn")
        assert rc == 0 and "particle effect" not in out, out
        shutil.rmtree(os.path.join(d, "overwrite"))
        os.makedirs(mod(d, "Base Textures", "particles", "graupel"))
        io.open(mod(d, "Base Textures", "particles", "graupel", "snowflakes.pe"), "w").write("")
        rc, out = run(d, "status", "--season", "autumn")
        assert rc == 0 and "particle effect" not in out, out
    return "the winning .xr, a .db, overwrite (any case), a mod lower down; not the losing .xr"


@case
def t_the_copy_the_game_loads_is_the_one_read():
    """Two mods ship the script: the copy that wins decides. A copy above that makes its
    particles in a function clears it; the mods' order the other way, it doesn't, and the
    finding names the mod with the copy that wins."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        os.makedirs(os.path.join(d, "mods", "Snow Fix", "gamedata", "scripts"))
        io.open(mod(d, "Snow Fix", "scripts", SCRIPT.lower()), "w").write(
            "local particles\nfunction on_game_start()\n    particles = {particles_object("
            "\"graupel\\\\dust\")}\nend\n")
        p = os.path.join(d, "profiles", "Default", "modlist.txt")
        lines = io.open(p, encoding="utf-8", newline="").read().split(tc.CRLF)
        io.open(p, "w", encoding="utf-8", newline="").write(
            tc.CRLF.join(lines[:1] + ["+Snow Fix"] + lines[1:]))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "particle effect" not in out, out
        io.open(p, "w", encoding="utf-8", newline="").write(
            tc.CRLF.join(lines[:1] + ["+INVERNO mechanics", "+Snow Fix"]
                         + [l for l in lines[1:] if l != "+INVERNO mechanics"]))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 1 and SAID in out, out
        io.open(p, "w", encoding="utf-8", newline="").write(
            tc.CRLF.join(lines[:1] + ["+Snow Fix", "-INVERNO mechanics"]
                         + [l for l in lines[1:] if l != "+INVERNO mechanics"]))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "particle effect" not in out, out
    return "the fixed copy above wins; below, the shipped one stops it; its mod off, nothing"


@case
def t_when_it_can_t_be_sure_it_warns_and_launches():
    """With no loose particles.xr the game's own, in its .db, may have the names, and a .db
    in a mod on that can't be read may too: a warning, and the launch goes ahead."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        os.remove(mod(d, "Particles Pack", "particles.xr"))
        os.remove(mod(d, "Old Particles", "particles.xr"))
        rc, out = run(d, "apply", "--season", "autumn")
        said = SAID.replace("! ", "- ", 1).replace("graupel\\snowflakes.",
                                                   "graupel\\snowflakes. Unless the game's own "
                                                   "particles.xr has them")
        assert rc == 0 and said in out and FIX in out and STOP not in out, out
    with tempfile.TemporaryDirectory() as d:
        install(d)
        db = os.path.join(d, "mods", "Base Textures", "db", "addons")
        os.makedirs(db)
        io.open(os.path.join(db, "broken.db"), "wb").write(b"\x01\x00\x00\x80\xff\xff\x00\x00")
        io.open(os.path.join(db, "Thumbs.db"), "wb").write(b"not an archive")
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "- " + SCRIPT in out and STOP not in out, out
        os.remove(os.path.join(db, "broken.db"))
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 1 and SAID in out, "Thumbs.db made it unsure: " + out
    return "no loose .xr: warned and launched; a .db that can't be read too; not Thumbs.db"


@case
def t_with_the_textures_off_the_mod_is_off_too():
    with tempfile.TemporaryDirectory() as d:
        install(d)
        rc, out = run(d, "apply", "--season", "winter", "--no-textures")
        assert rc == 1 and SAID in out and STOP in out, out
    return "--no-textures in winter takes the seasonal mod off, and the check sees it"


@case
def t_a_launch_that_restages_textures_is_checked_too():
    """A texture set to restage takes apply down its other road: status says it there, and
    apply restages, switches and then stops."""
    import test_hardening as th
    with tempfile.TemporaryDirectory() as d:
        install(d)
        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w", encoding="utf-8").write(
            CONFIG + 'LAYOUT = {"Base Grass": {"archive": "grass.7z", "options": '
            '{"summer": ["Summer"], "autumn": ["Winter"]}}}\n')
        th.with_archive(d)
        rc, out = run(d, "status", "--season", "autumn")
        assert rc == 0 and "Base Grass (summer) -> autumn" in out and SAID in out, out
        assert STOP not in out, out
        rc, out = run(d, "apply", "--season", "autumn")
        grass = mod(d, "Base Grass", "textures", "grass", "a.dds")
        assert rc == 1 and SAID in out and STOP in out, out
        assert io.open(grass).read() == "Winter", "stopped before restaging the textures"
    return "status on the restaging road says it; apply restages, then stops"


@case
def t_a_mod_play_bat_leaves_as_it_is_counts_as_it_is():
    """A seasonal mod with things that go into saves stays as it is in MO2, so it is judged
    as it is: on, the particles are there all year; off, they never are."""
    with tempfile.TemporaryDirectory() as d:
        install(d)
        p = mod(d, SEASONAL, "configs", "items", "items", "items_frozen.ltx")
        os.makedirs(os.path.dirname(p))
        io.open(p, "w", encoding="cp1251").write(tsc.ITEMS)
        set_state(d, SEASONAL, "+")
        rc, out = run(d, "status", "--season", "autumn")
        assert rc == 0 and "left as it is" in out and "particle effect" not in out, out
        rc, out = run(d, "apply", "--season", "autumn")
        assert rc == 0 and "particle effect" not in out and "+" + SEASONAL in modlist(d), out
        set_state(d, SEASONAL, "-")
        rc, out = run(d, "apply", "--season", "winter")
        assert rc == 1 and SAID in out and "-" + SEASONAL in modlist(d), out
    return "on and left on: fine all year; off and left off: stopped even in winter"


LUA = r"""
local a = particles_object("one\\a")               -- a call as it loads
local b = particles_object ( [[one\b]] )           -- a long string, spaces
local c = particles_object([==[
one\c]==])
local d = particles_object('one\\d')
local e = particles_object("one\\" .. name)        -- not a plain string
local f = particles_object(NAME)
-- local g = particles_object("one\\commented")
--[[ local h = particles_object("one\\long_comment") ]]
local i = "particles_object(\"one\\in_a_string\")"
local j = obj:particles_object("one\\method")
local k = obj.particles_object("one\\field")
function particles_object(name) return name end     -- a definition, not a call
function holder.go() local x = particles_object("two\\in_function") end
local go = function() return particles_object("two\\anonymous") end
callback(function() particles_object("two\\passed") end)
if loaded then
    local l = particles_object("one\\in_if")
elseif other then
    local m = particles_object("one\\in_elseif")
end
do local n = particles_object("one\\in_do") end
for i = 1, 3 do local o = particles_object("one\\in_for") end
while again do local p = particles_object("one\\in_while") again = nil end
repeat local q = particles_object("ONE\\Upper\065") until true
local function later()
    for _, v in ipairs(t) do
        while v do
            repeat v = particles_object("two\\nested") until v
        end
    end
end
local r = particles_object("one\\after")
"""


@case
def t_only_calls_as_a_script_loads_count():
    got = season.loaded_particles(LUA)
    names = [n for __, n in got]
    want = ["one\\a", "one\\b", "one\\c", "one\\d", "one\\in_if", "one\\in_elseif",
            "one\\in_do", "one\\in_for", "one\\in_while", "one\\upper" + "a", "one\\after"]
    assert names == want, names
    assert got[0][0] == 2 and got[-1] == (34, "one\\after"), got
    for bad in ("function f()\n  local x = particles_object('a')\n",
                "local x = 1\nend\nlocal y = particles_object('a')\n",
                "for i = 1, 2 end\n", "repeat local x = 1 end\n", "if x then end end\n",
                "local x = 1\nuntil done\n"):
        assert season.loaded_particles(bad) is None, bad
    assert season.loaded_particles("") == [], "an empty script"
    return "%d of the calls as it loads; functions, comments, strings, methods and " \
           "non-strings left out; blocks that don't add up refused" % len(want)


@case
def t_the_particles_xr_is_read_by_its_chunks():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "particles.xr")
        effects = ["a\\effect_%03d" % i for i in range(300)] + ["Mixed\\Case"]
        xr(p, effects, ["a\\group", "explosions\\campfire"], refs=["a\\only_listed"])
        got = season.xr_particles(p)
        assert got == {n.lower() for n in effects} | {"a\\group", "explosions\\campfire"}, \
            sorted(got)[:5]
        # a name in a group's list of effects is not a def of its own
        assert b"a\\only_listed" in open(p, "rb").read() and "a\\only_listed" not in got
        for kind, kw in (("a version the game skips", {"version": 2}),
                         ("packed chunks", {"packed": True})):
            xr(p, ["a\\b"], ["c\\d"], **kw)
            try:
                season.xr_particles(p)
                raise AssertionError("%s read as names" % kind)
            except ValueError:
                pass
        xr(p, ["a\\b"], ["c\\d"])
        data = open(p, "rb").read()
        open(p, "wb").write(data[:-3])
        try:
            season.xr_particles(p)
            raise AssertionError("a file cut short read as names")
        except ValueError:
            pass
    return "301 effects and 2 groups, by name; another version, packed and cut short refused"


@case
def t_loose_particles_are_named_by_their_paths():
    with tempfile.TemporaryDirectory() as d:
        for rel in ("graupel/dust.pg", "graupel/effects/Dust.PE", "graupel/readme.txt",
                    "particles.ltx", "yawm/snow/yawm_snow_light.pg"):
            p = os.path.join(d, "gamedata", "particles", *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            io.open(p, "w").write("")
        got = season.particle_files(d)
    assert got == {"graupel\\dust", "graupel\\effects\\dust", "yawm\\snow\\yawm_snow_light"}, got
    return "graupel\\dust for particles/graupel/dust.pg; .pe and .pg in any case, nothing else"


if __name__ == "__main__":
    print("  a launch that would crash on a particle a script makes as a save loads")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-48s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-48s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-48s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
