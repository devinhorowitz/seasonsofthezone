"""Seasonal LUTs: play.bat builds the mod Seasonal LUT from SEASON_LUTS - the game's own LUT as
group 0 and each season's LUT moved toward it by its percent - places it just above the mod
whose LUT is the game's, keeps it until something it is built from changes, and turns it off
with no LUT asked for. sotz_lut.script crossfades the groups by the season blend.

  python _tools/test_seasonal_lut.py
"""
import io
import math
import os
import re
import struct
import subprocess
import sys
import tempfile
import zipfile
import zlib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import config_edit as ce                                        # noqa: E402
import season                                                   # noqa: E402
import test_configure as tc                                     # noqa: E402
from lua_runtime import LuaRuntime, NAME as LUA_NAME            # noqa: E402

CASES = []
CRLF = "\r\n"
SCRIPT = os.path.join(os.path.dirname(HERE), "mods", "Seasons of the Zone", "gamedata",
                      "scripts", "sotz_lut.script")
TEXELS = 4096 * 64
BGRA = (0xff0000, 0xff00, 0xff, 0xff000000)      # B, G, R, A: Atmospherics', and most packs'
RGBA = (0xff, 0xff00, 0xff0000, 0xff000000)      # R, G, B, A: a few of Kumo's


def case(fn):
    CASES.append(fn)
    return fn


def pattern(t):
    return (t % 256, (t // 7) % 256, (t // 13) % 256)


def dds(groups, masks=BGRA, fill=None, width=4096, bits=32, fourcc=b"\0\0\0\0"):
    """A LUT atlas: a DDS header and `groups` LUTs of texels. `fill(t)` gives texel t's
    (r, g, b); laid out by `masks`, 4 bytes a texel, or 3 at 24 bits."""
    h = 64 * groups
    size = 3 if bits == 24 else 4
    head = bytearray(128)
    head[0:4] = b"DDS "
    struct.pack_into("<IIIII", head, 4, 124, 0x100f, h, width, width * size)
    struct.pack_into("<II4sI", head, 76, 32, 0x41 if size == 4 else 0x40, fourcc, bits)
    struct.pack_into("<IIII", head, 92, *(masks if size == 4 else masks[:3] + (0,)))
    fill = fill or pattern
    spot = {0xff: 0, 0xff00: 1, 0xff0000: 2, 0xff000000: 3}
    off = [spot[m] for m in masks]
    px = bytearray(width * h * size)
    for c in range(3):
        px[off[c]::size] = bytes(fill(t)[c] for t in range(width * h))
    if size == 4:
        px[off[3]::4] = b"\xff" * (width * h)
    return bytes(head) + bytes(px)


def lut(atlas, group=0):
    """A group of an atlas as season.lut_atlas reads it: B, G, R, A."""
    return season.lut_atlas(atlas)[group]


def shifted(groups):
    """`groups` LUTs as lut_atlas gives them, each its own: group k is the pattern, each
    color moved up by 40 k."""
    one = lut(dds(1))
    out = []
    for k in range(groups):
        table = bytes((v + 40 * k) % 256 for v in range(256))
        group = bytearray(one.translate(table))
        group[3::4] = b"\xff" * TEXELS
        out.append(bytes(group))
    return out


def png(groups, filters=(0,), alpha=False):
    """Groups as lut_atlas gives them, saved as a PNG the way G.A.M.M.A.'s Atmospherics saves
    its atlas: RGB, or RGBA, at 8 bits; row y filtered by filters[y % len(filters)]."""
    px = 4 if alpha else 3
    flat_ = b"".join(groups)
    rgb = bytearray(len(flat_) // 4 * px)
    for c, at in ((0, 2), (1, 1), (2, 0)):              # red, green, blue from B, G, R, A
        rgb[c::px] = flat_[at::4]
    if alpha:
        rgb[3::4] = flat_[3::4]
    stride, raw, up = 4096 * px, bytearray(), bytes(4096 * px)
    for y in range(64 * len(groups)):
        row = rgb[y * stride:(y + 1) * stride]
        kind = filters[y % len(filters)]
        if kind == 0:
            line = bytes(row)
        else:
            line = bytearray(stride)
            for i in range(stride):
                left = row[i - px] if i >= px else 0
                corner = up[i - px] if i >= px else 0
                if kind == 1:
                    guess = left
                elif kind == 2:
                    guess = up[i]
                elif kind == 3:
                    guess = (left + up[i]) >> 1
                else:
                    p = left + up[i] - corner
                    pa, pb, pc = abs(p - left), abs(p - up[i]), abs(p - corner)
                    guess = left if pa <= pb and pa <= pc else up[i] if pb <= pc else corner
                line[i] = (row[i] - guess) & 255
        raw += bytes([kind]) + line
        up = bytes(row)

    def chunk(kind, data):
        return (struct.pack(">I", len(data)) + kind + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff))
    head = struct.pack(">IIBBBBB", 4096, 64 * len(groups), 8, 6 if alpha else 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + chunk(b"sRGB", b"\0")
            + chunk(b"IDAT", zlib.compress(bytes(raw))) + chunk(b"IEND", b""))


def inverted(t):
    return (255 - t % 256, 255 - (t // 7) % 256, 255 - (t // 13) % 256)


def flat(v):
    return lambda t: (v, v, v)


def texel(atlas, group, t):
    """(r, g, b) of texel t in a group of a DDS atlas, read by its own masks."""
    off = season._dds_shape(atlas)[3]
    base = 128 + group * season.LUT_GROUP + t * 4
    return tuple(atlas[base + off[c]] for c in range(3))


def rgb(group, t):
    """(r, g, b) of texel t in a group as lut_atlas gives it."""
    return group[4 * t + 2], group[4 * t + 1], group[4 * t]


def mixed(base, src, share):
    """(r, g, b) of a texel moved from `base` toward `src` by `share`, as lut_mix does it."""
    w = round(share * 256)
    return tuple((b * (256 - w) + s * w + 128) >> 8 for b, s in zip(base, src))


GAMMA_SCRIPT = (
    "local ssfx_lut_default = { group = 1, intensity = 1.00 }\r\n"
    "local ssfx_maps = {\r\n"
    "\t[\"jupiter\"]\t\t= { group = 3, intensity = 1.0 },\r\n"
    "\t-- [\"zaton\"]\t\t= { group = 2, intensity = 1.0 },\r\n"
    "--[[\r\n\t[\"pripyat\"]\t\t= { group = 2, intensity = 0.95 },\r\n]]\r\n"
    "\t[\"labx8\"]\t\t= { group = 9, intensity = 1.0 },\r\n"
    "}\r\n"
    "local ssfx_lut_group1 = 0\r\n")


def scratch(d, config, mods=(), atmos=None):
    """A scratch GAMMA folder: the tools, the mod, a game folder with user.ltx, and these
    mods, (name, enabled, {relative path: bytes}), highest priority first, then Atmospherics
    with its LUT, or the files `atmos` gives. Returns user.ltx's path."""
    tc.install(d, config=config, mods=[])
    tc.with_mod(d)
    lines = ["# This file was automatically generated by Mod Organizer."]
    atmos = atmos or {"textures/shaders/lut_atlas.dds": dds(1)}
    for name, on, files in list(mods) + [("Atmospherics", True, atmos)] + [
            ("Seasons of the Zone", True, {})]:
        lines.append(("+" if on else "-") + name)
        for rel, data in files.items():
            p = os.path.join(d, "mods", name, "gamedata", *rel.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(data)
    io.open(os.path.join(d, "profiles", "Default", "modlist.txt"), "w", encoding="utf-8",
            newline="").write(CRLF.join(lines) + CRLF)
    g = os.path.join(d, "ANOMALY")
    io.open(os.path.join(d, "ModOrganizer.ini"), "a", encoding="utf-8").write(
        "gamePath=@ByteArray(%s)\r\n" % g.replace("\\", "\\\\"))
    user = os.path.join(g, "appdata", "user.ltx")
    os.makedirs(os.path.dirname(user))
    open(user, "wb").write(CRLF.join(["_preset Default", "ssfx_lut (1.000000, 0.000000, "
                                      "0.000000, 0.000000)", "bind left kLEFT", ""])
                           .encode("latin-1"))
    return user


def downloads(d, name, members):
    """A zip in the scratch MO2's downloads folder: {member: bytes}."""
    os.makedirs(os.path.join(d, "downloads"), exist_ok=True)
    with zipfile.ZipFile(os.path.join(d, "downloads", name), "w") as z:
        for m, data in members.items():
            z.writestr(m, data)


def modlist(d):
    return [l for l in io.open(os.path.join(d, "profiles", "Default", "modlist.txt"),
                               encoding="utf-8").read().splitlines() if l[:1] in ("+", "-")]


def built(d, *rel):
    return os.path.join(d, "mods", season.LUT_MOD, "gamedata", *rel)


def ltx(d):
    return io.open(built(d, "configs", "seasons_lut.ltx"), encoding="cp1251").read()


def packs(d):
    """Two packs the way they come: Kumo's with its options under "00 data", Iris R, G, B, A
    and EASTMAN B, G, R, A, as Kumo's differ; Forester's with gamedata under one folder."""
    downloads(d, "Kumo LUTs.zip", {
        "00 data/LUT - Iris/gamedata/textures/shaders/lut_atlas.dds": dds(1, RGBA, inverted),
        "00 data/EASTMAN/gamedata/textures/shaders/lut_atlas.dds": dds(1, BGRA, flat(200)),
        "00 data/Definition/gamedata/shaders/r3/settings_screenspace_LUT.h": b"x",
        "fomod/ModuleConfig.xml": b"<config/>"})
    downloads(d, "Forester_LUT.zip", {
        "Forester_LUT/gamedata/textures/shaders/lut_atlas.dds": dds(1, BGRA, flat(10))})


LUTS = ('SEASON_LUTS = {\n'
        '    "autumn": ("Kumo LUTs.zip", "00 data/EASTMAN", 30),\n'
        '    "winter": ("Kumo LUTs.zip", "00 data/LUT - Iris", 60),\n'
        '}\n')


@case
def t_mix_moves_each_color_by_the_share_in_either_byte_order():
    """Packs differ in byte order: each atlas is read by its own masks, mixed in 256ths of
    the share, and written as B, G, R, A, the alpha kept."""
    base, src = lut(dds(1, BGRA)), lut(dds(1, RGBA, inverted))
    got = season.lut_mix(base, src, 0.3)
    for t in (0, 1, 777, 123456, TEXELS - 1):
        want = mixed(pattern(t), inverted(t), 0.3)
        assert rgb(got, t) == want, (t, rgb(got, t), want)
        assert rgb(src, t) == inverted(t), "R, G, B, A read in the wrong order"
    assert got[3::4] == b"\xff" * TEXELS, "the alpha changed"
    assert season.lut_mix(base, src, 1.0) == src and season.lut_mix(base, src, 0) == base
    return "colors moved 30% at five texels from both orders, alpha kept; 0 and 100% exact"


@case
def t_only_a_whole_4096_wide_uncompressed_atlas_counts():
    one, two = dds(1), dds(2)
    assert season.lut_groups(one) == 1 and season.lut_groups(two) == 2
    assert season.lut_groups(dds(1, bits=24)) == 1, "a 24-bit atlas"
    bad = {"narrow": dds(1, width=2048), "16-bit": dds(1, bits=16)[:128],
           "compressed": dds(1, fourcc=b"DXT5")[:128], "cut short": one[:-4096],
           "not a DDS": b"PNG" + one[3:]}
    wrong = [k for k, v in bad.items() if season.lut_groups(v) is not None]
    assert not wrong, wrong
    for v in bad.values():
        try:
            season.lut_atlas(v)
            raise AssertionError("lut_atlas read one lut_groups refuses")
        except season.LutError:
            pass
    return "one and two LUTs, and 24 bits, counted; narrow, 16-bit, compressed, short, non-DDS refused"


@case
def t_a_png_atlas_reads_as_its_dds_does():
    """G.A.M.M.A.'s Atmospherics saves its atlas as a PNG named .dds: every row filter reads
    back the same texels as the DDS, RGB with alpha 255 and RGBA with its own; a 24-bit DDS
    too."""
    groups = shifted(2)
    got = season.lut_atlas(png(groups, filters=(0, 1, 2, 3, 4)))
    assert got == groups, "a filtered PNG read back wrong"
    assert season.lut_atlas(dds(1, bits=24)) == [lut(dds(1))], "a 24-bit DDS read back wrong"
    see = bytearray(groups[0])
    see[3::4] = bytes(t % 256 for t in range(TEXELS))
    assert season.lut_atlas(png([bytes(see)], filters=(4, 3), alpha=True)) == [bytes(see)]
    assert season.lut_groups(png(groups)) == 2
    return "None, Sub, Up, Average and Paeth rows; RGB and RGBA; a 24-bit DDS"


@case
def t_choices_list_the_luts_in_archives_and_mods():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, "", mods=[("Kumo Macula", False, {
            "textures/shaders/lut_atlas.dds": dds(1)})])
        packs(d)
        rc, out = tc.run(d, "lut", tool="configure.py")
        assert rc == 0, out
        for want in ("Iris  (Kumo LUTs.zip: 00 data/LUT - Iris)", "EASTMAN  (Kumo LUTs.zip",
                     "Forester_LUT  (Forester_LUT.zip: Forester_LUT)", "Atmospherics  (Atmospherics)",
                     "Kumo Macula  (Kumo Macula)"):
            assert want in out, (want, out)
        assert "Definition" not in out and "Seasonal LUT  (" not in out, out
        return "Kumo's two options, Forester's, and two mods' LUTs listed; no Definition"


@case
def t_a_7z_pack_is_listed_once_py7zr_is_in():
    """Without py7zr a .7z can't be looked in: the list says what to install, and doesn't
    remember the archive as holding no LUT, so it shows once py7zr is in."""
    import py7zr
    with tempfile.TemporaryDirectory() as d:
        scratch(d, "")
        os.makedirs(os.path.join(d, "downloads"))
        with py7zr.SevenZipFile(os.path.join(d, "downloads", "Frost LUTs.7z"), "w") as z:
            z.writestr(dds(1), "LUT - Frost/gamedata/textures/shaders/lut_atlas.dds")
        block = os.path.join(d, "no_py7zr")
        os.makedirs(block)
        io.open(os.path.join(block, "py7zr.py"), "w").write(
            "raise ImportError('no py7zr in this test')\n")
        rc, out = tc.run(d, "lut", tool="configure.py",
                         env=dict(os.environ, PYTHONPATH=block))
        assert rc == 0, out
        assert "Frost" not in out, out
        assert ("1 .7z archive in MO2's downloads folder can't be searched for LUTs without "
                "py7zr" in out and "-m pip install py7zr" in out), out
        rc, out = tc.run(d, "lut", tool="configure.py")
        assert rc == 0, out
        assert "Frost  (Frost LUTs.7z: LUT - Frost)" in out, out
        assert "can't be searched" not in out, out
        return "without py7zr the .7z is named with the pip line; with it, its LUT is listed"


@case
def t_apply_builds_the_mod_and_places_it_above_the_base():
    """The atlas: group 0 the game's LUT, one group per season with a LUT, in season order;
    the header lets two groups mix; the ltx names each season's group; the mod goes just
    above Atmospherics, on."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS)
        packs(d)
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "Seasonal LUT" in out and "built: 2 seasons on Atmospherics's LUT" \
            in out, out
        atlas = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        assert season.lut_groups(atlas) == 3, season.lut_groups(atlas)
        assert atlas[:128] == season._dds_header(3), "not Atmospherics 2.69's header"
        base = dds(1)
        assert atlas[128:128 + season.LUT_GROUP] == base[128:], "group 0 is not the game's LUT"
        got = season.lut_atlas(atlas)
        assert got[1] == season.lut_mix(lut(base), lut(dds(1, BGRA, flat(200))), 0.3), \
            "autumn is not Eastman at 30%"
        assert got[2] == season.lut_mix(lut(base), lut(dds(1, RGBA, inverted)), 0.6), \
            "winter is not Iris at 60%"
        head = open(built(d, "shaders", "r3", "settings_screenspace_LUT.h"), "rb").read()
        assert b"#define G_CELLS_GROUPS\t3" in head and b"\n#define G_ADVANCE_TRANSITION" in head
        info = ltx(d)
        for line in ("atlas_bytes = %d" % len(atlas), "header_bytes = %d" % len(head),
                     "base_groups = 1", "autumn = 0:1", "winter = 0:2",
                     "autumn = EASTMAN 30%", "winter = Iris 60%"):
            assert line in info, (line, info)
        assert "\nspring =" not in info and "\nwinter_snow =" not in info, info
        ml = modlist(d)
        assert ml.index("+Seasonal LUT") + 1 == ml.index("+Atmospherics"), ml
        return "3 groups, the header, the ltx, placed on above Atmospherics"


@case
def t_gamma_s_png_atlas_gets_a_mix_for_each_group_its_levels_use():
    """G.A.M.M.A.'s Atmospherics: a PNG atlas of many groups, and a script giving the levels
    some of them. The game's groups stay where they are, as B, G, R, A; each season with a
    LUT adds its mix with each group the script names, commented lines aside."""
    with tempfile.TemporaryDirectory() as d:
        base = shifted(4)
        scratch(d, LUTS, atmos={"textures/shaders/lut_atlas.dds": png(base, filters=(1, 2)),
                                "scripts/ssfx_lut.script": GAMMA_SCRIPT.encode("ascii")})
        packs(d)
        rc, out = tc.run(d, "status", tool="season.py")
        assert "built on the 2 LUTs of Atmospherics that levels use" in out, out
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "built: 2 seasons on Atmospherics's LUT" in out, out
        atlas = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        got = season.lut_atlas(atlas)
        assert len(got) == 8 and got[:4] == base, "the game's 4 groups, then 2 seasons x 2"
        eastman, iris = lut(dds(1, BGRA, flat(200))), lut(dds(1, RGBA, inverted))
        assert got[4:] == [season.lut_mix(base[1], eastman, 0.3),
                           season.lut_mix(base[3], eastman, 0.3),
                           season.lut_mix(base[1], iris, 0.6),
                           season.lut_mix(base[3], iris, 0.6)], "not each level group's mix"
        info = ltx(d)
        for line in ("base_groups = 4", "autumn = 1:4, 3:5", "winter = 1:6, 3:7"):
            assert line in info, (line, info)
        head = open(built(d, "shaders", "r3", "settings_screenspace_LUT.h"), "rb").read()
        assert b"#define G_CELLS_GROUPS\t8" in head, head
        return "4 groups kept, then autumn and winter mixed with groups 1 and 3; 8 in the header"


@case
def t_the_groups_levels_use_come_from_the_script():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "ssfx_lut.script")
        open(p, "wb").write(GAMMA_SCRIPT.encode("ascii"))
        assert season.lut_used(p, 17) == [1, 3, 9], season.lut_used(p, 17)
        assert season.lut_used(p, 4) == [1, 3] and season.lut_used(p, 1) == [0]
        assert season.lut_used(None, 17) == [0]
        open(p, "wb").write(b"local x = { group = 0 }\r\n")
        assert season.lut_used(p, 17) == [0]
        return "1, 3 and 9 of 17; under 4, 1 and 3; none or no script: 0; comments skipped"


@case
def t_a_lut_these_tools_can_t_build_on_is_said():
    """Screen Space Shaders' own LUT, 1024 wide with 32 cells, without Atmospherics': said,
    and nothing built."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS, atmos={"textures/shaders/lut_atlas.dds": dds(1, width=1024)})
        packs(d)
        rc, out = tc.run(d, "status", tool="season.py")
        assert "is not one Seasonal LUTs can build on" in out, out
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and not os.path.exists(built(d)), out
        return "said in status; nothing built"


@case
def t_a_second_launch_keeps_the_build_and_a_change_rebuilds_it():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS)
        packs(d)
        tc.run(d, "apply", tool="season.py")
        p = built(d, "textures", "shaders", "lut_atlas.dds")
        os.utime(p, (1000000000, 1000000000))
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "(to be built)" not in out and "built:" not in out, out
        assert int(os.path.getmtime(p)) == 1000000000, "the atlas was written again"
        cfg = os.path.join(d, "_tools", "seasons_config.py")
        io.open(cfg, "w", encoding="utf-8").write(LUTS.replace("60)", "45)"))
        rc, out = tc.run(d, "status", tool="season.py")
        assert "(to be built)" in out, out
        rc, out = tc.run(d, "apply", tool="season.py")
        assert "built: 2 seasons" in out and "winter = Iris 45%" in ltx(d), out
        return "kept as it was; a new percent said in status, then built"


@case
def t_no_lut_turns_the_mod_off_and_puts_user_ltx_back_on_group_0():
    with tempfile.TemporaryDirectory() as d:
        user = scratch(d, LUTS)
        packs(d)
        tc.run(d, "apply", tool="season.py")
        # the game left a season's group in user.ltx as it closed
        raw = open(user, "rb").read().replace(b"ssfx_lut (1.000000, 0.000000, 0.000000",
                                               b"ssfx_lut (0.800000, 2.000000, 1.000000")
        open(user, "wb").write(raw)
        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w",
                encoding="utf-8").write("SEASON_LUTS = {}\n")
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "-Seasonal LUT" in modlist(d), (modlist(d), out)
        assert open(user, "rb").read() == raw.replace(
            b"ssfx_lut (0.800000, 2.000000, 1.000000, 0.000000)",
            b"ssfx_lut (0.800000, 0.000000, 0.000000, 0.000000)"), open(user, "rb").read()
        return "the mod off; ssfx_lut back on group 0, its intensity and the rest kept"


@case
def t_with_the_mod_on_only_a_group_past_its_atlas_is_put_back():
    """Seasonal LUT on: a season's group of its own stays in user.ltx, one past the atlas
    (from a build that held more) goes back to 0."""
    with tempfile.TemporaryDirectory() as d:
        user = scratch(d, LUTS)
        packs(d)
        tc.run(d, "apply", tool="season.py")
        raw = open(user, "rb").read()
        mine = raw.replace(b"ssfx_lut (1.000000, 0.000000, 0.000000",
                           b"ssfx_lut (1.000000, 2.000000, 1.000000")
        open(user, "wb").write(mine)
        tc.run(d, "apply", tool="season.py")
        assert open(user, "rb").read() == mine, "a group the atlas has was put back"
        open(user, "wb").write(mine.replace(b"2.000000, 1.000000", b"9.000000, 1.000000"))
        tc.run(d, "apply", tool="season.py")
        assert open(user, "rb").read() == raw, open(user, "rb").read()
        return "group 2 of 3 kept; group 9 back to 0"


@case
def t_a_lut_mod_above_becomes_the_base():
    """A LUT mod placed above (ROMEO's Macula) is the game's LUT now: the seasons are built
    on it, and Seasonal LUT moves above it."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS, mods=[("Macula", True, {
            "textures/shaders/lut_atlas.dds": dds(1, BGRA, flat(90))})])
        packs(d)
        rc, out = tc.run(d, "apply", tool="season.py")
        assert "on Macula's LUT" in out, out
        ml = modlist(d)
        assert ml.index("+Seasonal LUT") + 1 == ml.index("+Macula"), ml
        atlas = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        assert texel(atlas, 0, 5) == (90, 90, 90), texel(atlas, 0, 5)
        return "built on Macula's LUT, placed above it"


@case
def t_a_lut_mod_that_is_off_is_not_the_base():
    """A disabled LUT mod above Atmospherics is no LUT the game loads: the seasons are built
    on Atmospherics', and the mod goes just above Atmospherics."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS, mods=[("Macula", False, {
            "textures/shaders/lut_atlas.dds": dds(1, BGRA, flat(90))})])
        packs(d)
        rc, out = tc.run(d, "apply", tool="season.py")
        assert "on Atmospherics's LUT" in out, out
        ml = modlist(d)
        assert ml.index("+Seasonal LUT") + 1 == ml.index("+Atmospherics"), ml
        atlas = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        assert atlas[128:128 + season.LUT_GROUP] == dds(1)[128:], "built on the disabled mod"
        return "built on Atmospherics', not the disabled Macula above it"


@case
def t_a_missing_pack_is_said_and_nothing_is_built():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS)
        rc, out = tc.run(d, "status", tool="season.py")
        assert "Kumo LUTs.zip is not in MO2's downloads folder" in out, out
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and not os.path.exists(built(d)), out
        assert "Seasonal LUT" not in "".join(modlist(d)), modlist(d)
        return "status names the archive; nothing built or listed"


@case
def t_the_config_check_names_each_entry_at_fault():
    bad = {"spring": ("a.zip", None, 50), "neutral": ("a.zip", None, 50),
           "summer": ("a.zip", None), "autumn": ("a.zip", "x", 0), "winter": ("", None, 50),
           "winter_snow": ("Seasonal LUT", None, 40), "late_winter": ("a.zip", 3, 30)}
    got = season.lut_problems(bad)
    joined = "\n".join(got)
    for key, words in (("'neutral'", "six seasons"), ("'summer'", "must be (source"),
                       ("'autumn'", "1 to 100"), ("'winter'", "archive's file name"),
                       ("'winter_snow'", "written by season.py"),
                       ("'late_winter'", "holds gamedata")):
        assert any(key in g and words in g for g in got), (key, words, joined)
    assert not any("'spring'" in g for g in got), joined
    assert season.lut_problems([]) and season.lut_problems({}) == []
    return "%d problems, each naming its entry; a good entry passes" % len(got)


@case
def t_configure_gives_a_season_a_lut_and_takes_it_off():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, "")
        packs(d)
        rc, out = tc.run(d, "lut", "autumn", "eastman", "30", tool="configure.py")
        assert rc == 0, out
        ns = {}
        exec(tc.config(d), ns)
        assert ns["SEASON_LUTS"] == {"autumn": ("Kumo LUTs.zip", "00 data/EASTMAN", 30)}, ns
        tc.accepted(d)
        rc, out = tc.run(d, "lut", "deep winter", "Forester_LUT", tool="configure.py")
        ns = {}
        exec(tc.config(d), ns)
        assert ns["SEASON_LUTS"]["winter_snow"] == ("Forester_LUT.zip", "Forester_LUT", 50), ns
        rc, out = tc.run(d, "lut", "summer", "Nothing", "40", tool="configure.py")
        assert rc != 0 and "No LUT named \"Nothing\"" in out, out
        rc, out = tc.run(d, "lut", "autumn", "--off", tool="configure.py")
        ns = {}
        exec(tc.config(d), ns)
        assert set(ns["SEASON_LUTS"]) == {"winter_snow"}, ns
        rc, out = tc.run(d, "lut", "--off", tool="configure.py")
        ns = {}
        exec(tc.config(d), ns)
        assert not ns.get("SEASON_LUTS"), ns
        return "set by name, 50% when left out, an unknown name refused, taken off"


# --- seasonal accents ------------------------------------------------------------------------

def sweetfx(rgb, accent):
    """The accents on one color, (r, g, b) from 0 to 1, worked one color at a time from
    SweetFX's shader lines: Tonemap's saturation, Curves on luma with curve 4, LiftGammaGain
    and Vibrance, each clamped as a screen pass writing 8-bit color is."""
    def clamp(v):
        return min(1.0, max(0.0, v))
    c = [clamp(v) for v in rgb]
    if accent.get("saturation"):
        s, m = accent["saturation"], sum(c) / 3.0
        c = [clamp((x + (x - m) * s) / (1 + (x - m) * s)) for x in c]
    if accent.get("contrast"):
        luma = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
        x = luma * (luma * (1.5 - luma) + 0.5)
        x = luma + (x - luma) * accent["contrast"] * 2.0
        c = [clamp(x + (v - luma)) for v in c]
    if "tint" in accent or "gain" in accent:
        gain, gamma = accent.get("gain", (1, 1, 1)), accent.get("tint", (1, 1, 1))
        c = [clamp(abs(v * gain[i]) ** (1.0 / gamma[i])) for i, v in enumerate(c)]
    if accent.get("vibrance"):
        luma = 0.212656 * c[0] + 0.715158 * c[1] + 0.072186 * c[2]
        sat = max(c) - min(c)
        bal = accent.get("vibrance_rgb", (1, 1, 1))
        out = []
        for i, v in enumerate(c):
            k = bal[i] * accent["vibrance"]
            sign = (k > 0) - (k < 0)
            out.append(clamp(luma + (v - luma) * (1.0 + k * (1.0 - sign * sat))))
        c = out
    return c


def to8(c):
    return [int(math.floor(v * 255.0 + 0.5)) for v in c]


ACCENTED = 'SEASON_ACCENTS = True\n'


@case
def t_each_season_s_accents_follow_sweetfx_s_lines():
    """Every season's own accents, on 512 colors across the cube, agree with SweetFX's passes
    worked one color at a time, and each season moves some color by more than a step."""
    np = season._numpy()
    colors = [((i * 37) % 256 / 255.0, (i * 91) % 256 / 255.0, (i * 53) % 256 / 255.0)
              for i in range(512)]
    worst, moved = 0.0, {}
    for s, acc in season.ACCENTS.items():
        got = season.accent_rgb(np, np.array(colors), acc)
        for i, col in enumerate(colors):
            want = sweetfx(col, acc)
            worst = max(worst, max(abs(float(got[i][j]) - want[j]) for j in range(3)))
            moved[s] = max(moved.get(s, 0.0), max(abs(want[j] - col[j]) for j in range(3)))
    assert worst < 1e-9, worst
    assert set(moved) == set(season.SEASONS) and min(moved.values()) > 1.5 / 255, moved
    return "six seasons, 512 colors, within %.0e; each moves color" % max(worst, 1e-16)


@case
def t_a_lut_takes_the_accents_on_its_colors_and_keeps_its_alpha():
    """lut_accent changes each texel's color as the accents would change that color on
    screen, in B, G, R, A order, and leaves the alpha; no accents, the same bytes."""
    np = season._numpy()
    group = lut(dds(1))
    acc = season.ACCENTS["winter_snow"]
    out = season.lut_accent(group, acc, np)
    assert out[3::4] == group[3::4], "the alpha changed"
    for t in (0, 1, 777, 65535, 200000, 262143):
        want = to8(sweetfx([x / 255.0 for x in rgb(group, t)], acc))
        assert list(rgb(out, t)) == want, (t, rgb(group, t), rgb(out, t), want)
    assert season.lut_accent(group, {}, np) == group
    return "six texels as SweetFX would color them, alpha kept; no accents, the same bytes"


@case
def t_apply_builds_accents_into_every_season_with_no_pack():
    """SEASON_ACCENTS = True and no LUT pack: each season gets the game's group with its
    accents, the ltx lists them, and status says so."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, ACCENTED)
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "built: 6 seasons on Atmospherics's LUT" in out, out
        atlas = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        got = season.lut_atlas(atlas)
        assert len(got) == 7 and got[0] == lut(dds(1)), len(got)
        for i, s in enumerate(season.SEASONS):
            assert got[1 + i] == season.lut_accent(lut(dds(1)), season.ACCENTS[s]), s
        info = ltx(d)
        for i, s in enumerate(season.SEASONS):
            assert "%s = 0:%d" % (s, 1 + i) in info and "\n%s = true" % s in info, (s, info)
        rc, out = tc.run(d, "status", tool="season.py")
        row = [l for l in out.splitlines() if l.startswith("  LUTs")]
        assert row and "spring accents" in row[0] and "(to be built)" not in row[0], out
        return "six seasons with their accents, listed, and said"


@case
def t_a_season_s_pack_and_its_accents_stack():
    """A season with a pack and accents gets the accents on its mix; one with accents only,
    on the game's group; one with a pack only, the mix as before."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS + 'SEASON_ACCENTS = {"summer": {"contrast": 0.1}, '
                          '"autumn": {"vibrance": 0.2, "vibrance_rgb": (1.3, 1.0, 0.6)}}\n')
        packs(d)
        rc, out = tc.run(d, "apply", tool="season.py")
        assert rc == 0 and "built: 3 seasons" in out, out
        got = season.lut_atlas(open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read())
        base = lut(dds(1))
        assert got[1] == season.lut_accent(base, {"contrast": 0.1}), "summer"
        assert got[2] == season.lut_accent(season.lut_mix(base, lut(dds(1, BGRA, flat(200))), 0.3),
                                           {"vibrance": 0.2, "vibrance_rgb": (1.3, 1.0, 0.6)}), \
            "autumn"
        assert got[3] == season.lut_mix(base, lut(dds(1, RGBA, inverted)), 0.6), "winter"
        info = ltx(d)
        assert "autumn = EASTMAN 30%" in info and "\nsummer = true" in info \
            and "\nautumn = true" in info and "\nwinter = true" not in info, info
        rc, out = tc.run(d, "status", tool="season.py")
        assert "summer accents, autumn EASTMAN 30% + accents, winter Iris 60%" in out, out
        return "summer on the game's group, autumn on EASTMAN's mix, winter as before"


@case
def t_a_changed_accent_rebuilds_and_the_same_one_keeps_the_build():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, 'SEASON_ACCENTS = {"winter": {"saturation": -0.1}}\n')
        rc, out = tc.run(d, "apply", tool="season.py")
        first = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc == 0 and "(to be built)" not in out, out
        io.open(os.path.join(d, "_tools", "seasons_config.py"), "w", encoding="utf-8").write(
            'SEASON_ACCENTS = {"winter": {"saturation": -0.2}}\n')
        rc, out = tc.run(d, "status", tool="season.py")
        assert "(to be built)" in out, out
        rc, out = tc.run(d, "apply", tool="season.py")
        again = open(built(d, "textures", "shaders", "lut_atlas.dds"), "rb").read()
        assert rc == 0 and again != first and season.lut_atlas(again)[1] == \
            season.lut_accent(lut(dds(1)), {"saturation": -0.2}), out
        return "kept while the same; a new value said, then built"


@case
def t_without_numpy_the_packs_build_and_the_accents_wait():
    """numpy missing: with packs the LUTs build without accents, and status says how to get
    numpy; with accents only, nothing is built and status says why."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, LUTS + ACCENTED)
        packs(d)
        rc, out = tc.run(d, "apply", tool="season.py", env=no_numpy(d))
        assert rc == 0 and "built: 2 seasons" in out and "need numpy" in out \
            and "-m pip install numpy" in out, out
        assert "\nautumn = true" not in ltx(d), ltx(d)
    with tempfile.TemporaryDirectory() as d:
        scratch(d, ACCENTED)
        rc, out = tc.run(d, "apply", tool="season.py", env=no_numpy(d))
        assert "not built" in out and "need numpy" in out, out
        assert not os.path.exists(built(d, "textures", "shaders", "lut_atlas.dds"))
        return "packs built without accents, said; accents alone wait, said"


def no_numpy(d):
    """An environment in which numpy won't import, as on a machine without it."""
    block = os.path.join(d, "block", "numpy")
    os.makedirs(block, exist_ok=True)
    io.open(os.path.join(block, "__init__.py"), "w").write("raise ImportError('blocked')\n")
    return dict(os.environ, PYTHONPATH=os.path.join(d, "block"))


def accents_in(d):
    """SEASON_ACCENTS as the scratch config has it; "none" when it has no such line."""
    ns = {}
    exec(tc.config(d), ns)
    return ns.get("SEASON_ACCENTS", "none")


OWN_ACCENTS = ('SEASON_ACCENTS = {\n'
               '    "autumn": {"vibrance": 0.2},        # a little more than the pack\n'
               '}\n')


@case
def t_configure_switches_seasons_own_accents_on_and_off():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, "")
        rc, out = tc.run(d, "accents")
        assert rc == 0 and "accents are off" in out and "accents on" in out, out
        rc, out = tc.run(d, "accents", "off")
        assert "Nothing changed" in out and accents_in(d) == "none", out
        rc, out = tc.run(d, "accents", "on")
        assert rc == 0 and "Seasons' own accents are on" in out and accents_in(d) is True, out
        assert "\n# Seasonal accents: True for Seasons' own" in tc.config(d), tc.config(d)
        tc.accepted(d)
        rc, out = tc.run(d, "accents")
        assert rc == 0 and "vibrance 0.83" in out and "deep winter" in out \
            and "contrast 0.28" in out and "numpy" not in out, out
        rc, out = tc.run(d, "accents", "on")
        assert "Nothing changed" in out, out
        rc, out = tc.run(d, "accents", "off")
        assert rc == 0 and "turns Seasonal LUT off" in out and accents_in(d) is False, out
        tc.accepted(d)
        rc, out = tc.run(d, "accents", "on", env=no_numpy(d))
        assert rc == 0 and accents_in(d) is True and "needs numpy" in out \
            and "-m pip install numpy" in out, out
    return "off by default; on, listed, off; numpy's install said when it is missing"


@case
def t_configure_keeps_accents_of_your_own_and_replaces_a_bad_value():
    with tempfile.TemporaryDirectory() as d:
        scratch(d, OWN_ACCENTS)
        rc, out = tc.run(d, "accents")
        assert rc == 0 and "of your own" in out and "autumn" in out \
            and "vibrance 0.2" in out and "spring" not in out, out
        rc, out = tc.run(d, "accents", "on")
        assert "Nothing changed" in out and tc.config(d) == OWN_ACCENTS, out
        rc, out = tc.run(d, "accents", "off")
        assert rc == 0 and accents_in(d) is False, out
        tools = os.path.join(d, "_tools")
        kept = [io.open(os.path.join(tools, f), encoding="utf-8").read()
                for f in os.listdir(tools) if f.startswith("seasons_config.py.")]
        assert kept.count(OWN_ACCENTS) == 2, kept      # the .bak, and the dated copy
    for bad in ('SEASON_ACCENTS = "yes"\n', "SEASON_ACCENTS = 1\n"):
        with tempfile.TemporaryDirectory() as d:
            scratch(d, bad)
            cal = ce.Calendar(os.path.join(d, "_tools", "seasons_config.py"))
            assert [p for p in cal.problems if "SEASON_ACCENTS" in p] and \
                [p for p in cal.check(cal.render()[0]) if "SEASON_ACCENTS" in p], cal.problems
            rc, out = tc.run(d, "accents")
            assert rc == 0 and "! SEASON_ACCENTS must be True" in out, out
            rc, out = tc.run(d, "accents", "on")
            assert rc == 0 and accents_in(d) is True, out
            tc.accepted(d)
    return "a table of your own kept by on, off copied aside; \"yes\" and 1 replaced by True"


WINDOW = r'''
import sys
sys.path.insert(0, sys.argv[1])
import tkinter as tk
import config_edit as ce
import configure
root = tk.Tk()
root.withdraw()
cal = ce.Calendar()
app = configure.App(root, cal, ce.Install())
print("box", app.accents_on.get(), repr(str(app.accent_note.cget("text"))))
app.accents_on.set(False)
app.accents_edited()
print("dirty off", cal.dirty())
app.accents_on.set(True)
app.accents_edited()
print("dirty on", cal.dirty())
print("status", str(app.status.cget("text")))
print("note on", repr(str(app.accent_note.cget("text"))))
print("saved", app.save(quiet=True))
print("box after", app.accents_on.get())
root.destroy()
'''


@case
def t_the_window_s_box_switches_the_accents():
    """The box in the window, ticked and unticked the way a click would."""
    def drive(d, env=None):
        p = os.path.join(d, "drive.py")
        io.open(p, "w", encoding="utf-8").write(WINDOW)
        r = subprocess.run([sys.executable, p, os.path.join(d, "_tools")], cwd=d, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        assert r.returncode == 0 and "Traceback" not in out, out
        return out
    with tempfile.TemporaryDirectory() as d:
        scratch(d, "")
        out = drive(d, no_numpy(d))
        for line in ("box False ''", "dirty off False", "dirty on True", "saved True",
                     "box after True"):
            assert "\n%s\n" % line in "\n" + out, (line, out)
        assert re.search(r"status .*season accents", out) \
            and re.search(r"note on .Building them needs numpy", out), out
        assert accents_in(d) is True, tc.config(d)
        tc.accepted(d)
    with tempfile.TemporaryDirectory() as d:
        scratch(d, OWN_ACCENTS)
        out = drive(d)
        assert "box True 'On with accents of your own, from seasons_config.py, for autumn.'" \
            in out and "dirty off True" in out and "dirty on False" in out, out
        assert "numpy" not in out and tc.config(d) == OWN_ACCENTS, out
    return "ticked and saved, numpy's lack said; a table of your own unticked and kept"


LOOK = r'''
import sys
sys.path.insert(0, sys.argv[1])
import tkinter as tk
import config_edit as ce
import configure
root = tk.Tk()
app = configure.App(root, ce.Calendar(), ce.Install())
root.update()
box, scroll = app.look_box, app.season_scroll
print("box height", box.winfo_height() > 200)
app.show_look()
root.update()
total = float(scroll.inner.winfo_reqheight())
top, bottom = scroll.canvas.yview()
print("tab", app.tabs.index("current"), "box seen", top <= box.winfo_y() / total <= bottom)
pick, cb, share, sp = app.lut_rows["autumn"]
cb.current(1)
share.set("40")
app.luts_edited()
scroll.canvas.yview_moveto(0)
root.update()
before = (cb.get(), share.get(), scroll.canvas.yview()[0])
for w in (cb, sp):
    w.event_generate("<MouseWheel>", delta=-120)
    root.update()
after = (cb.get(), share.get(), scroll.canvas.yview()[0])
print("values kept", before[:2] == after[:2], "page moved", after[2] > before[2])
print("luts", app.cal.luts)
root.destroy()
'''


@case
def t_the_look_of_each_season_is_in_reach_and_the_wheel_leaves_its_boxes_alone():
    """At the window's own size the Seasons tab is twice as tall as its room: it scrolls, so
    the LUTs and the accents, last on it, are there to see, and show_look scrolls to them.
    The wheel over a dropdown or a spin box scrolls the page and never steps the value."""
    with tempfile.TemporaryDirectory() as d:
        scratch(d, "")
        packs(d)
        p = os.path.join(d, "drive.py")
        io.open(p, "w", encoding="utf-8").write(LOOK)
        r = subprocess.run([sys.executable, p, os.path.join(d, "_tools")], cwd=d,
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = r.stdout + r.stderr
        assert r.returncode == 0 and "Traceback" not in out, out
        for line in ("box height True", "tab 1 box seen True",
                     "values kept True page moved True"):
            assert line in out, (line, out)
        assert re.search(r"luts \{'autumn': \('[^']+', [^)]*, 40\)\}", out), out
    return "the box laid out and scrolled to; two wheel turns move the page, not the picks"


@case
def t_the_config_check_names_each_bad_accent():
    bad = {"neutral": {"vibrance": 0.1}, "spring": "lots", "summer": {"glow": 1},
           "autumn": {"vibrance": 2}, "winter": {"tint": (1, 1)},
           "winter_snow": {"gain": (1, 1, 3)}, "late_winter": {"contrast": True}}
    got = season.accent_problems(bad)
    joined = "\n".join(got)
    for key, words in (("'neutral'", "six seasons"), ("'spring'", "table of accents"),
                       ("'glow'", "not an accent"), ("'vibrance'", "from -1 to 1"),
                       ("'tint'", "three numbers"), ("'gain'", "from 0.5 to 2"),
                       ("'contrast'", "a number from -1 to 1")):
        assert any(key in g and words in g for g in got), (key, words, joined)
    assert len(got) == 7, joined
    assert season.accent_problems("yes") and season.accent_problems(True) == [] \
        and season.accent_problems(False) == [] and season.accent_problems({}) == []
    assert season.accent_problems(season.ACCENTS) == [], season.accent_problems(season.ACCENTS)
    with tempfile.TemporaryDirectory() as d:
        scratch(d, 'SEASON_ACCENTS = "yes"\n')
        rc, out = tc.run(d, "status", tool="season.py")
        assert rc != 0 and "SEASON_ACCENTS must be True" in out, out
    return "7 problems, each naming its entry; Seasons' own pass; a bad file refused"


# --- the game script ---------------------------------------------------------------------

STUBS = r"""
calls, logged, CB = {}, {}, {}
sizes = {}
ltx = nil
lut_now = "(1.000000, 0.000000, 0.000000, 0.000000)"
mcm_lut = true
mix = nil
now_ms = 0
function printf(fmt, s) logged[#logged + 1] = s end
function time_global() return now_ms end
function RegisterScriptCallback(name, fn) CB[name] = fn end
function getFS()
    return {exist = function(self, alias, path)
        local n = sizes[alias .. "|" .. path]
        if n then return {size_real = n} end
        return nil
    end}
end
function ini_file(name)
    if not ltx then return nil end
    local t = ltx
    return {section_exist = function(self, s) return t[s] ~= nil end,
            line_exist = function(self, s, k) return t[s] ~= nil and t[s][k] ~= nil end,
            r_float_ex = function(self, s, k) return t[s] and tonumber(t[s][k]) end,
            r_string_ex = function(self, s, k) return t[s] and t[s][k] end}
end
function get_console()
    return {get_string = function(self, k) return lut_now end,
            execute = function(self, cmd)
                calls[#calls + 1] = cmd
                local a, b, c, e = cmd:match("%(([^,]+),([^,]+),([^,]+),([^%)]+)%)")
                lut_now = string.format("(%s, %s, %s, %s)", a, b, c, e)
            end}
end
ui_mcm = {get = function(path) if path == "seasons_zone/main/do_lut" then return mcm_lut end end}
zzz_seasons_of_the_zone = {season_mix = function() return mix end}
"""


def lua_world(with_ltx=True, atlas=7340160, header=362, sizes_match=True, groups=1,
              seasons='autumn = "0:3", winter = "0:4", winter_snow = "0:5", '
                      'late_winter = "0:6"', more=""):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(STUBS)
    g = lua.globals()
    if with_ltx:
        g.ltx = lua.eval('{seasons_lut = {atlas_bytes = "%d", header_bytes = "%d", '
                         'base_groups = "%d", %s}, labels = {autumn = "EASTMAN 30%%"}%s}'
                         % (atlas, header, groups, seasons, more))
    g.sizes = lua.eval('{["$game_config$|seasons_lut.ltx"] = 100, '
                       '["$game_textures$|shaders\\\\lut_atlas.dds"] = %d, '
                       '["$game_shaders$|r3\\\\settings_screenspace_LUT.h"] = %d}'
                       % (atlas if sizes_match else 1048704, header))
    lua.execute(io.open(SCRIPT, encoding="latin-1").read())
    g.on_game_start()
    return lua, g


def step(lua, g, mix):
    g.mix = lua.eval(mix)
    g.now_ms = g.now_ms + 6000
    g.CB["actor_on_update"]()
    return list(g.calls.values())


@case
def t_the_script_crossfades_the_two_heaviest_seasons():
    lua, g = lua_world()
    got = step(lua, g, "{autumn = 1}")
    assert got[-1:] == ["ssfx_lut (1,3,3,0.0000)"], got
    got = step(lua, g, "{autumn = 0.7, winter = 0.3, spring = 0}")
    assert got[-1] == "ssfx_lut (1,3,4,0.3000)", got
    n = len(got)
    assert len(step(lua, g, "{autumn = 0.7, winter = 0.3}")) == n, "it set the same again"
    got = step(lua, g, "{summer = 0.6, autumn = 0.4}")
    assert got[-1] == "ssfx_lut (1,0,3,0.4000)", got
    g.mcm_lut = False
    got = step(lua, g, "{autumn = 1}")
    assert got[-1] == "ssfx_lut (1,0,0,0.0000)", got
    assert g.label("autumn") == "EASTMAN 30%" and g.label("summer") is None
    return "autumn alone, autumn into winter, summer with no LUT, MCM off (%s)" % LUA_NAME


@case
def t_the_script_swaps_each_level_s_own_group_for_its_mix():
    """G.A.M.M.A.'s Atmospherics gives each level a group: the season's mix of that group is
    used, the level's own where the season has none, and a mix in place maps back to the
    level's group."""
    lua, g = lua_world(groups=17, seasons='winter = "2:17, 16:18", autumn = "2:19, 16:20"')
    g.lut_now = "(1.000000, 16.000000, 0.000000, 0.000000)"     # Atmospherics, outdoors
    got = step(lua, g, "{winter = 1}")
    assert got[-1] == "ssfx_lut (1,18,18,0.0000)", got
    got = step(lua, g, "{winter = 0.7, autumn = 0.3}")
    assert got[-1] == "ssfx_lut (1,18,20,0.3000)", got
    g.lut_now = "(1.000000, 2.000000, 0.000000, 0.000000)"      # a lab
    got = step(lua, g, "{winter = 1}")
    assert got[-1] == "ssfx_lut (1,17,17,0.0000)", got
    g.lut_now = "(1.000000, 3.000000, 0.000000, 0.000000)"      # a level no mix is of
    got = step(lua, g, "{winter = 1}")
    assert got[-1] == "ssfx_lut (1,3,3,0.0000)", got
    g.lut_now = "(1.000000, 18.000000, 18.000000, 0.000000)"    # ours, from the last session
    g.mcm_lut = False
    got = step(lua, g, "{winter = 1}")
    assert got[-1] == "ssfx_lut (1,16,16,0.0000)", got
    assert any("on the level's group 16" in str(s) for s in g.logged.values()), \
        list(g.logged.values())
    return "outdoors 16 -> 18, into autumn's 20; a lab's 2 -> 17; 3 kept; MCM off: 16"


@case
def t_the_script_keeps_the_game_s_intensity():
    lua, g = lua_world()
    g.lut_now = "(0.700000, 0.000000, 0.000000, 0.000000)"
    got = step(lua, g, "{winter = 1}")
    assert got[-1] == "ssfx_lut (0.7,4,4,0.0000)", got
    return "intensity 0.7 kept"


@case
def t_the_script_stands_down_for_another_lut_and_without_its_ltx():
    lua, g = lua_world(sizes_match=False)
    assert step(lua, g, "{autumn = 1}") == [], "it drove another mod's atlas"
    assert any("another LUT mod" in str(s) for s in g.logged.values()), list(g.logged.values())
    lua, g = lua_world(with_ltx=False)
    assert step(lua, g, "{autumn = 1}") == [], "it ran with no Seasonal LUT"
    return "another atlas wins: nothing set, and said; no ltx: nothing"


@case
def t_the_script_knows_which_seasons_carry_accents():
    """The ltx's [accents] marks the seasons whose groups have them, for the MCM read-out;
    an ltx from before accents has none."""
    lua, g = lua_world(more=', accents = {winter = "true", winter_snow = "true"}')
    assert g.accented("winter") is True and g.accented("winter_snow") is True
    assert g.accented("autumn") is False and g.label("autumn") == "EASTMAN 30%"
    lua, g = lua_world()
    assert g.accented("winter") is False
    lua, g = lua_world(with_ltx=False)
    assert g.accented("winter") is False
    return "winter and deep winter marked, autumn not; none without the section (%s)" % LUA_NAME


def main():
    bad = 0
    for fn in CASES:
        try:
            said = fn()
            print("  PASS  %-62s %s" % (fn.__name__[2:], said))
        except Exception as e:
            bad += 1
            print("  FAIL  %-62s %s" % (fn.__name__[2:], (str(e) if isinstance(e, AssertionError)
                                                          else repr(e))[:600]))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
