"""A seasonal mod that puts things into saves is left as it is, unless its entry allows it.

A save keeps each object by its section's name. Switched off, a mod that adds items, puts
them in traders' stock or a loadout, adds spawns or creates objects from its scripts takes
those sections with it: current Modded Exes delete the objects as the save loads, and one
on a quick-use slot stops every load. INVERNO 1.09 is such a mod. season.py looks through
each seasonal mod's files, and the .db file lists, before it switches it; these cases build
mods that hold each kind of file and run the shipped tools on them.

  python _tools/test_save_content.py
"""
import io
import json
import os
import random
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- X-Ray's LZHUF, packing --------------------------------------------------------------
#
# Okumura's LZHUF as xrCore's LzHuf.cpp has it, written out here on its own, so season.py's
# unpacker is checked against code it doesn't share: N 4096, F 60, THRESHOLD 2, the size
# first, and the tree rebuilt at 0x4000, where Okumura's own rebuilds at 0x8000.
N, F, THRESHOLD = 4096, 60, 2
N_CHAR = 256 - THRESHOLD + F
T = N_CHAR * 2 - 1
R = T - 1
MAX_FREQ = 0x4000
P_LEN = [3] + [4] * 3 + [5] * 8 + [6] * 12 + [7] * 24 + [8] * 16
P_CODE = (0x00, 0x20, 0x30, 0x40, 0x50, 0x58, 0x60, 0x68, 0x70, 0x78, 0x80, 0x88, 0x90, 0x94,
          0x98, 0x9C, 0xA0, 0xA4, 0xA8, 0xAC, 0xB0, 0xB4, 0xB8, 0xBC, 0xC0, 0xC2, 0xC4, 0xC6,
          0xC8, 0xCA, 0xCC, 0xCE, 0xD0, 0xD2, 0xD4, 0xD6, 0xD8, 0xDA, 0xDC, 0xDE, 0xE0, 0xE2,
          0xE4, 0xE6, 0xE8, 0xEA, 0xEC, 0xEE, 0xF0, 0xF1, 0xF2, 0xF3, 0xF4, 0xF5, 0xF6, 0xF7,
          0xF8, 0xF9, 0xFA, 0xFB, 0xFC, 0xFD, 0xFE, 0xFF)
REBUILT = {"n": 0}                      # how often the packer's tree has been rebuilt


def lzhuf_pack(data):
    """`data` packed as X-Ray packs a .db's file list: literals, and back references where
    the last few places the next three bytes were seen match."""
    freq, prnt, son = [0] * (T + 1), [0] * (T + N_CHAR), [0] * T
    for i in range(N_CHAR):
        freq[i], son[i], prnt[i + T] = 1, i + T, i
    i, j = 0, N_CHAR
    while j <= R:
        freq[j] = freq[i] + freq[i + 1]
        son[j] = i
        prnt[i] = prnt[i + 1] = j
        i, j = i + 2, j + 1
    freq[T], prnt[R] = 0xFFFF, 0
    bits = []

    def reconst():
        REBUILT["n"] += 1
        j = 0
        for i in range(T):
            if son[i] >= T:
                freq[j], son[j] = (freq[i] + 1) // 2, son[i]
                j += 1
        i, j = 0, N_CHAR
        while j < T:
            f = freq[j] = freq[i] + freq[i + 1]
            k = j - 1
            while f < freq[k]:
                k -= 1
            k += 1
            freq[k + 1:j + 1], son[k + 1:j + 1] = freq[k:j], son[k:j]
            freq[k], son[k] = f, i
            i, j = i + 2, j + 1
        for i in range(T):
            k = son[i]
            prnt[k] = i
            if k < T:
                prnt[k + 1] = i

    def update(c):
        if freq[R] == MAX_FREQ:
            reconst()
        c = prnt[c + T]
        while True:
            freq[c] += 1
            k = freq[c]
            l = c + 1
            if k > freq[l]:
                while k > freq[l + 1]:
                    l += 1
                freq[c], freq[l] = freq[l], k
                i, j = son[c], son[l]
                prnt[i] = l
                if i < T:
                    prnt[i + 1] = l
                son[l], prnt[j] = i, c
                if j < T:
                    prnt[j + 1] = c
                son[c] = j
                c = l
            c = prnt[c]
            if not c:
                break

    def put(n, value):
        bits.extend((value >> (n - 1 - k)) & 1 for k in range(n))

    def char(c):
        path, k = [], prnt[c + T]
        while k != R:
            path.append(k & 1)
            k = prnt[k]
        bits.extend(reversed(path))
        update(c)

    p, seen = 0, {}
    while p < len(data):
        best, at = 0, 0
        for q in reversed(seen.get(data[p:p + 3], [])[-8:]):
            if p - q >= N - F:
                break
            n = 0
            while n < F and p + n < len(data) and data[q + n] == data[p + n]:
                n += 1
            if n > best:
                best, at = n, q
        if best > THRESHOLD:
            char(255 - THRESHOLD + best)
            pos = p - at - 1
            put(P_LEN[pos >> 6], P_CODE[pos >> 6] >> (8 - P_LEN[pos >> 6]))
            put(6, pos & 0x3F)
        else:
            best = 1
            char(data[p])
        for k in range(p, p + best):
            seen.setdefault(data[k:k + 3], []).append(k)
        p += best
    bits += [0] * (-len(bits) % 8)
    return struct.pack("<I", len(data)) + bytes(
        int("".join(map(str, bits[k:k + 8])), 2) for k in range(0, len(bits), 8))


def xdb(path, names, packed=True):
    """An X-Ray .db holding `names`, empty files, with a folder entry first as the game's
    own have: a data chunk, then the file list in chunk 1."""
    table = b""
    for name in ["textures\\"] + [n.replace("/", "\\") for n in names]:
        rec = struct.pack("<III", 0, 0, 0) + name.encode("cp1251") + struct.pack("<I", 0)
        table += struct.pack("<H", len(rec)) + rec
    body = lzhuf_pack(table) if packed else table
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(struct.pack("<II", 0, 4) + b"data"
                + struct.pack("<II", 1 | (0x80000000 if packed else 0), len(body)) + body)


# --- the mods ------------------------------------------------------------------------------

ITEMS = """; frozen drinks, as INVERNO 1.09 adds them
[frozen_flask]:booster_multi
$spawn          = "food and drugs\\energy_drink"
description     = "frozen; thaw it at a fire"   ; a ; inside quotes is not a comment
inv_name        = st_frozen_flask
inv_weight      = 0.5

[frozen_tea]:booster            // no $spawn: an item all the same
inv_weight      = 0.3

![bread]                        ; DLTX: another file's section, changed
$spawn          = "food and drugs\\bread"

!![vodka]

[st_not_an_item]
text            = an inventory key, inv_weight, only in a value
"""
CREATES = """local sim = alife()
-- alife():create("commented_out", ...) is not a call
local s = "alife_create_item(in a string)"
--[[ a long comment
alife_create("x")
]]
function alife_create_item(section, obj)        -- a definition is not a call
end

local function freeze(sec, actor)
    sim:create(sec, actor:position(), actor:level_vertex_id(), actor:game_vertex_id(),
               actor:id())
end
"""
# highest priority first, as modlist.txt lists them
MODS = [
    ("Winter Items", False, ["configs/items/items/items_winter.ltx", "textures/item/a.dds"]),
    ("Winter Trade", False, ["configs/items/trade/mod_trade_sidorovich_winter.ltx"]),
    ("Winter Script", False, ["scripts/winter_freezing.script"]),
    ("Winter Db", False, []),
    ("Winter Pack", False, ["textures/grass/a.dds", "configs/environment/weathers/w_snow.ltx",
                            "scripts/winter_fog.script"]),
    ("Grass Base", True, ["textures/grass/a.dds"]),
    ("Seasons of the Zone", True, ["scripts/zzz_seasons_of_the_zone.script"]),
]
HELD = ("Winter Items", "Winter Trade", "Winter Script", "Winter Db")


def write(root, mod, rel, text):
    p = os.path.join(root, "mods", mod, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    io.open(p, "w", encoding="cp1251").write(text)


def install(root, config):
    """The mods above in a scratch install, each holding the file that ties a save to it,
    and Winter Pack only textures, weather and a fog script."""
    tc.install(root, config=config, mods=MODS)
    tc.with_mod(root)
    write(root, "Winter Items", "gamedata/configs/items/items/items_winter.ltx", ITEMS)
    write(root, "Winter Trade", "gamedata/configs/items/trade/mod_trade_sidorovich_winter.ltx",
          "![supplies_1]\nfrozen_flask = 2, 1\n")
    write(root, "Winter Script", "gamedata/scripts/winter_freezing.script", CREATES)
    xdb(os.path.join(root, "mods", "Winter Db", "db", "addons", "winter.db"),
        ["textures/sky/a.dds", "scripts/winter_db.script"])
    write(root, "Winter Pack", "gamedata/configs/environment/weathers/w_snow.ltx",
          "[00:00:00]\nsky_texture = sky\\sky_9_cube\n")
    write(root, "Winter Pack", "gamedata/scripts/winter_fog.script",
          "local p = particles_object(\"fog\")\nfunction on_game_start() end\n")
    xdb(os.path.join(root, "mods", "Winter Pack", "db", "addons", "winter_sky.db"),
        ["textures/sky/a.dds", "textures/sky/a.thm"])
    write(root, "Winter Pack", "db/addons/Thumbs.db", "not an archive")


def config(allow=False):
    entries = []
    for name in HELD + ("Winter Pack",):
        extra = ', "save_content": True' if allow and name != "Winter Pack" else ""
        entries.append('    "%s": {"when": ("winter",), "above": "Grass Base"%s},'
                       % (name, extra))
    return "TOGGLE_MODS = {\n%s\n}\n" % "\n".join(entries)


def modlist(root):
    return [l.strip() for l in io.open(os.path.join(root, "profiles", "Default",
                                                    "modlist.txt"), encoding="utf-8")][1:]


# --- the cases -----------------------------------------------------------------------------

@case
def t_the_file_list_of_a_db_is_read_packed_or_not():
    """X-Ray packs a .db's file list. The unpacker against an encoder of its own: names
    that repeat, for the back references, and names that don't, so the tree is rebuilt,
    which happens at 0x4000 in X-Ray, not Okumura's 0x8000; a wrong limit garbles every
    name after it."""
    rnd = random.Random(1457)
    names = ["textures/terrain/terrain_%s_%03d.dds" % (lvl, i)
             for lvl in ("escape", "garbage", "agroprom", "darkvalley") for i in range(100)]
    names += ["textures/%s.dds" % "".join(rnd.choice("abcdefghijklmnopqrstuvwxyz_")
                                         for _ in range(24)) for _ in range(900)]
    names.append("scripts/frozen.script")
    table = b"".join(struct.pack("<H", 16 + len(n)) + struct.pack("<III", 0, 0, 0)
                     + n.replace("/", "\\").encode("cp1251") + struct.pack("<I", 0)
                     for n in names)
    REBUILT["n"] = 0
    packed = lzhuf_pack(table)
    assert season.lzhuf_unpack(packed) == table, "the round trip garbles it"
    # what the packer's own tree saw: past 0x4000, so the rebuild ran
    assert REBUILT["n"], "the list is too short to reach the rebuild"
    with tempfile.TemporaryDirectory() as d:
        for packed in (True, False):
            p = os.path.join(d, "a%d.db" % packed)
            xdb(p, names, packed)
            got = season.db_files(p)
            assert got == names, (packed, got[:3], len(got))
        io.open(os.path.join(d, "bad.db"), "wb").write(b"\x01\x00\x00\x80\xff\xff\x00\x00")
        try:
            season.db_files(os.path.join(d, "bad.db"))
            raise AssertionError("a file that isn't a .db was read as one")
        except ValueError:
            pass
    return ("%d names, %d bytes of list, the tree rebuilt %d times; packed and not; a "
            "broken file refused" % (len(names), len(table), REBUILT["n"]))


@case
def t_each_kind_of_file_that_ties_a_save_is_found():
    with tempfile.TemporaryDirectory() as d:
        install(d, config(False))
        found = {n: season.save_content(os.path.join(d, "mods", n)) for n, _, _ in MODS}
    assert found["Winter Items"] == [("gamedata/configs/items/items/items_winter.ltx",
                                      "items", ["frozen_flask", "frozen_tea"])], found
    assert found["Winter Trade"] == [
        ("gamedata/configs/items/trade/mod_trade_sidorovich_winter.ltx", "trade", None)], found
    assert found["Winter Script"] == [("gamedata/scripts/winter_freezing.script", "script",
                                       (11, "sim:create"))], found
    assert found["Winter Db"] == [("db/addons/winter.db", "db",
                                   ("scripts/winter_db.script", 1))], found
    assert found["Winter Pack"] == [] and found["Grass Base"] == [], found
    # the rest of the kinds, from the files' names
    more = {"gamedata/spawns/all.spawn": "spawns",
            "gamedata/configs/mod_system_trade_winter.ltx": "trade",
            "gamedata/configs/items/settings/mod_new_game_loadouts_winter.ltx": "loadout",
            "gamedata/configs/scripts/escape/mod_esc_trader_door.ltx": None}
    with tempfile.TemporaryDirectory() as d:
        for rel in more:
            write(d, "M", rel, "[logic]\nactive = walker\n")
        got = {rel: kind for rel, kind, _ in season.save_content(os.path.join(d, "mods", "M"))}
    assert got == {k: v for k, v in more.items() if v}, got
    return "items (not DLTX edits), trade, a sim:create script, a .db's script; spawns, " \
           "loadouts; a trader's door and a texture-only mod pass"


@case
def t_a_mod_that_puts_things_into_saves_is_left_as_it_is():
    """Without "save_content": True each of the four stays as it is in MO2, said and counted;
    the texture mod is switched. With it, all five are."""
    with tempfile.TemporaryDirectory() as d:
        install(d, config(False))
        before = modlist(d)
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        after = modlist(d)
        assert rc == 0, out
        for name in HELD:
            assert "-" + name in after and after.index("-" + name) == before.index("-" + name), \
                (name, after)
            assert "! %s is left as it is in MO2" % name in out, (name, out)
        assert after.index("+Winter Pack") < after.index("+Grass Base"), after
        for said in ("items_winter.ltx: defines items or other objects: frozen_flask, "
                     "frozen_tea", "mod_trade_sidorovich_winter.ltx: puts items in traders' "
                     "stock", "winter_freezing.script: creates objects (line 11: sim:create)",
                     "db/addons/winter.db: holds scripts/winter_db.script",
                     '"save_content": True', "4 seasonal mods skipped",
                     "(left as it is: it puts things into saves)"):
            assert said in out, (said, out)
        panel = io.open(os.path.join(d, "mods", "Seasons of the Zone", "gamedata", "configs",
                                     "season_mods.ltx"), encoding="cp1251").read()
        listed = [l for l in panel.splitlines() if l.startswith("list = ")]
        assert listed == ["list = winter_pack"], listed

        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w",
                encoding="utf-8").write(config(True))
        rc, out = tc.run(d, "apply", "--season", "winter", tool="season.py")
        after = modlist(d)
        assert rc == 0 and "left as it is" not in out and "skipped" not in out, out
        for name in HELD:
            assert after.index("+" + name) < after.index("+Grass Base"), (name, after)
        rc, out = tc.run(d, "status", "--season", "winter", tool="season.py")
        assert rc == 0 and "- Winter Items puts things into saves (1 file); its entry says " \
            "\"save_content\": True" in out, out
    return "4 left as they were and named, Winter Pack switched; allowed, all 5 switched"


@case
def t_the_permission_is_a_true_or_false():
    with tempfile.TemporaryDirectory() as d:
        install(d, config(False).replace('"above": "Grass Base"},',
                                         '"above": "Grass Base", "save_content": "yes"},', 1))
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc != 0 and "needs fixing" in out and \
            "TOGGLE_MODS['Winter Items']: \"save_content\" is True or False" in out, out
    assert not season.config_problems(
        {"A": {"when": ("winter",), "above": "B", "save_content": False}}, {}, None, {}, {})
    return "\"yes\" refused, naming the entry; False accepted"


@case
def t_the_setup_says_so_and_keeps_the_permission():
    """configure.py add says what the files put into saves and that play.bat won't switch
    the mod; list marks it. A permission written by hand comes through a change made with
    the tool, and loading a preset keeps it and names the mods it leaves as they are."""
    with tempfile.TemporaryDirectory() as d:
        install(d, None)
        rc, out = tc.run(d, "add", "Winter Script", "--when", "winter")
        assert rc == 0 and "careful" in out and "leaves it as it is in MO2 until its entry" \
            in out and "winter_freezing.script: creates objects (line 11: sim:create)" in out, out
        assert "play.bat switches it from the next launch" not in out, out
        rc, out = tc.run(d, "add", "Winter Pack", "--when", "winter")
        assert rc == 0 and "puts things into saves" not in out and \
            "play.bat switches it from the next launch" in out, out
        rc, out = tc.run(d, "list")
        assert "left as it is: its files put things into saves" in out, out
        assert out.count("left as it is") == 1, out

        p = os.path.join(d, "_tools", "seasons_config.py")
        text = io.open(p, encoding="utf-8").read()
        io.open(p, "w", encoding="utf-8").write(text.replace(
            '"above": "Grass Base",\n    },', '"above": "Grass Base",\n'
            '        "save_content": True,\n    },', 1))
        assert '"save_content": True' in tc.config(d), tc.config(d)
        rc, out = tc.run(d, "add", "Winter Script", "--when", "winter", "deep winter")
        assert rc == 0 and "note" in out and "switches it all the same" in out, out
        assert '"save_content": True' in tc.config(d), "the tool dropped the permission"
        t, _ = tc.table(d)
        assert t["Winter Script"]["save_content"] is True, t

        presets = os.path.join(d, "_tools", "presets")
        os.makedirs(presets, exist_ok=True)
        io.open(os.path.join(presets, "Mine.json"), "w", encoding="utf-8").write(json.dumps(
            {"seasons_of_the_zone_preset": 1, "mods": {
                "Winter Script": {"when": ["winter"], "above": "Grass Base"},
                "Winter Items": {"when": ["winter"], "above": "Grass Base"}}}))
        rc, out = tc.run(d, "preset", "load", "Mine", "--parts", "mods", "--force")
        assert rc == 0 and "until their entries allow it: Winter Items" in out, out
        t, _ = tc.table(d)
        assert t["Winter Script"].get("save_content") is True, t
        assert "save_content" not in t["Winter Items"], t
        tc.accepted(d)
    return "add warns and says play.bat won't switch it; list marks it; the permission " \
           "survives a change and a preset, which never brings one"


@case
def t_the_windows_say_so():
    """The Seasonal mods step marks the mod, its dialog and the advanced editor say what
    its files put into saves, and the Review step doesn't count it among the mods play.bat
    switches."""
    import test_guide as tg
    with tempfile.TemporaryDirectory() as d:
        install(d, config(False))
        rc, out = tg.drive(d, r"""
g.edit("mods")
settle()
marks = [t for t in texts(g.page) if t.startswith("puts things into saves")]
print("MARKS", len(marks))
held = cf._(cf.SAVES_HELD)
dlg = guide.ModDialog(g, "Winter Items")
settle()
print("DIALOG", any(held in t and "items_winter.ltx" in t for t in texts(dlg.win)))
dlg.win.destroy()
app = cf.App(tk.Toplevel(root), g.cal, g.inst)
settle()
app.select("Winter Trade")
settle()
print("EDITOR", any(held in t for t in texts(app.side)))
app.select("Winter Pack")
settle()
print("PACK", any(held in t for t in texts(app.side)))
g.edit("review")
settle()
print("REVIEW", [t for t in texts(g.body) if "into saves" in t])
g.cal.take("Winter Db")
new = guide.ModDialog(g)
new.query.set("winter")
settle()
print("BEFORE", any(held in t for t in texts(new.win)))
new.list.selection_set(new.shown.index("Winter Db"))
# a hidden window gets no <<ListboxSelect>>, so the handler it is bound to is run here
print("BOUND", "on_pick" in new.list.bind("<<ListboxSelect>>"))
new.on_pick()
settle()
print("PICKED", any(held in t and "winter.db" in t for t in texts(new.win)))
new.win.destroy()
""")
    assert rc == 0, out
    for want in ("MARKS 4", "DIALOG True", "BEFORE False", "BOUND True", "PICKED True",
                 "EDITOR True", "PACK False"):
        assert want in out, (want, out)
    assert "Winter Db, Winter Items, Winter Script and 1 more put things into saves, so " \
           "play.bat leaves them as they are." in out, out
    return "4 marked on the step; the dialog, a pick from its list, the editor; the review"


if __name__ == "__main__":
    print("  a seasonal mod that puts things into saves")
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
