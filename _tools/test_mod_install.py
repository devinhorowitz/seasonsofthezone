"""Installing a seasonal mod from its archive: mod_install.py.

Each case makes its own small archives in a scratch folder - .7z and .zip, and .rar where
WinRAR is installed - some with a FOMOD modeled on the seasonal texture mods players
download, and checks what Package reads from them and what install() leaves on disk. The
last case reads the real Colorful Autumn archive when it is in the GAMMA folder, without
unpacking anything but its installer.

  python _tools/test_mod_install.py
"""
import contextlib
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import mod_install as mi                                        # noqa: E402

GAMMA = os.environ.get("GAMMA_INSTALL", r"D:\GAMMA")
REAL = os.path.join(GAMMA, "C-Con Clorful Autumn 1.4.7z")
RAR = next((p for p in (os.path.join(os.environ.get(v, ""), "WinRAR", "Rar.exe")
                        for v in ("ProgramFiles", "ProgramFiles(x86)"))
            if os.path.isfile(p)), None)
WINTER = ["winter", "winter_snow", "late_winter"]
CASES = []


def case(fn):
    CASES.append(fn)
    return fn


# --- archives to test with ----------------------------------------------------------------

def body(name, size=64):
    """A test file's bytes: its own name over and over, so a file in the wrong place shows."""
    line = (name + "\n").encode()
    return (line * (size // len(line) + 1))[:size]


def make(path, files, stored=False):
    """An archive at `path` holding `files`, {member: bytes}, in that order."""
    if path.endswith(".7z"):
        import py7zr
        with py7zr.SevenZipFile(path, "w") as z:
            for name, data in files.items():
                z.writestr(data, name)
    elif path.endswith(".zip"):
        with zipfile.ZipFile(path, "w", zipfile.ZIP_STORED if stored
                             else zipfile.ZIP_DEFLATED) as z:
            for name, data in files.items():
                z.writestr(name, data)
    else:
        stage = path + ".files"
        for name, data in files.items():
            p = os.path.join(stage, *name.split("/"))
            os.makedirs(os.path.dirname(p), exist_ok=True)
            open(p, "wb").write(data)
        subprocess.run([RAR, "a", "-r", "-idq", path, "*"], cwd=stage, check=True)
        shutil.rmtree(stage)
    return path


def on_disk(folder):
    """The files under `folder`, as "/"-separated paths."""
    out = []
    for r, _, fs in os.walk(folder):
        for f in fs:
            out.append(os.path.relpath(os.path.join(r, f), folder).replace(os.sep, "/"))
    return sorted(out)


def refused(fn, *args, **kw):
    """The ArchiveError `fn` raises, as text; fails the case when it raises none."""
    try:
        fn(*args, **kw)
    except mi.ArchiveError as e:
        return str(e)
    raise AssertionError("%s did not refuse" % fn.__name__)


TOP = "Rusty Leaves 2.1"
PARTS = {
    "Leaves": [("folder", r"gamedata\textures\leaves", r"gamedata\textures\leaves")],
    "Grass": [("folder", r"gamedata\textures\grass", r"gamedata\textures\grass")],
    "Grass fix": [("folder", r"gamedata\levels", r"gamedata\levels")],
    "Ground": [("folder", r"gamedata\textures\terrain", r"gamedata\textures\terrain"),
               ("folder", r"gamedata\textures\detail", r"gamedata\textures\detail")],
}
TEXTURES = ["gamedata/textures/leaves/oak.dds", "gamedata/textures/leaves/birch.dds",
            "gamedata/textures/grass/grass.dds", "gamedata/textures/grass/grass_swamp.dds",
            "gamedata/levels/l01_escape/level.details",
            "gamedata/textures/terrain/terrain_escape.dds",
            "gamedata/textures/detail/detail_moss.dds"]
INFO = ("<fomod>\n  <Name>Rusty Leaves</Name>\n  <Author>Tester</Author>\n"
        "  <Version>2.1</Version>\n</fomod>\n")


def plugin_xml(name, files, kind="Optional", description=""):
    out = ['<plugin name="%s">' % name, "<description>%s</description>" % description]
    if files:
        out.append("<files>")
        for what, src, dest in files:
            prio = ""
            if isinstance(dest, tuple):
                dest, prio = dest[0], ' priority="%d"' % dest[1]
            out.append('<%s source="%s"%s%s/>' % (what, src, "" if dest is None
                                                   else ' destination="%s"' % dest, prio))
        out.append("</files>")
    out.append('<typeDescriptor><type name="%s"/></typeDescriptor></plugin>' % kind)
    return "\n".join(out)


def group_xml(name, kind, plugins):
    return ('<group name="%s" type="%s"><plugins order="Explicit">%s</plugins></group>'
            % (name, kind, "\n".join(plugins)))


def fomod_xml(steps, head="", tail="", declaration=""):
    """ModuleConfig.xml for `steps`, [(step name, [group xml])], as the FOMOD Creation Tool
    lays one out: an xsi namespace, explicit order, backslashes in the paths."""
    return (declaration + '<!-- made for the tests -->\n<config xmlns:xsi="http://www.w3.org/'
            '2001/XMLSchema-instance" xsi:noNamespaceSchemaLocation="http://qconsulting.ca/'
            'fo3/ModConfig5.0.xsd">\n<moduleName>Rusty Leaves: a test palette</moduleName>\n'
            + head + '<installSteps order="Explicit">'
            + "".join('<installStep name="%s"><optionalFileGroups order="Explicit">%s'
                      '</optionalFileGroups></installStep>' % (n, "".join(gs))
                      for n, gs in steps)
            + "</installSteps>" + tail + "</config>\n")


def rusty_steps(parts=PARTS):
    """Colorful Autumn's shape: a page that only describes the mod, then one group of four
    options, each installing whole folders."""
    return [("Welcome", [group_xml("About", "SelectExactlyOne", [plugin_xml(
                "Go on", [], description="Warmer leaves and drier grass, for the tests.")])]),
            ("Parts", [group_xml("Parts", "SelectAtLeastOne",
                                 [plugin_xml(n, f) for n, f in parts.items()])])]


def rusty(path, xml=None):
    """A FOMOD archive with one top folder holding fomod\\ and gamedata\\, like Colorful
    Autumn: its installer in UTF-16, as the FOMOD Creation Tool saves it, and the author's
    own meta.ini beside them."""
    xml = fomod_xml(rusty_steps()) if xml is None else xml
    content = {TOP + "/fomod/ModuleConfig.xml": xml.encode("utf-16"),
               TOP + "/fomod/info.xml": INFO.encode("utf-16"),
               TOP + "/fomod/shot.png": body("png")}
    for rel in TEXTURES:
        content[TOP + "/" + rel] = body(rel, 300)
    content[TOP + "/meta.ini"] = b"[General]\r\nmodid=0\r\n"
    return make(path, content)


def ids(pkg, *names):
    """The plugin ids for these option names."""
    by = {p["name"]: p["id"] for p in pkg.fomod.plugins()}
    return {by[n] for n in names}


def dests(pairs):
    return sorted(d for _, d in pairs)


# --- the cases ----------------------------------------------------------------------------

@case
def t_seasons_in_reads_the_words_a_name_says():
    said = {n: mi.seasons_in(n) for n in (
        "C-Con Clorful Autumn 1.4", "INVERNO Winter Textures", "Partly Snowy",
        "Swamp Ground Fog", "frostychun", "Grok's & Bert's Casings Falling Sounds",
        "Seasonal Snowfall (INVERNO)", "Deep Winter Pack", "Late Winter", "Spring Thaw",
        "Simple_Autumn_Retexture_No_Leaves_v1.1", "AutumnNoLeavesLOD.2", "Summer and FALL",
        "FROST", "deep-winter", "")}
    want = {"C-Con Clorful Autumn 1.4": ["autumn"], "INVERNO Winter Textures": WINTER,
            "Partly Snowy": WINTER, "Swamp Ground Fog": [], "frostychun": [],
            "Grok's & Bert's Casings Falling Sounds": [], "Seasonal Snowfall (INVERNO)": [],
            "Deep Winter Pack": ["winter_snow"], "Late Winter": ["late_winter"],
            "Spring Thaw": ["spring", "late_winter"],
            "Simple_Autumn_Retexture_No_Leaves_v1.1": ["autumn"],
            "AutumnNoLeavesLOD.2": ["autumn"], "Summer and FALL": ["summer", "autumn"],
            "FROST": WINTER, "deep-winter": ["winter_snow"], "": []}
    bad = {n: (said[n], want[n]) for n in want if said[n] != want[n]}
    assert not bad, bad
    return "%d names: whole words, in any case, underscores and run-together capitals split" % (
        len(want))


@case
def t_a_plain_archive_installs_from_the_folder_that_holds_gamedata():
    with tempfile.TemporaryDirectory() as d:
        top = mi.Package(make(os.path.join(d, "Autumn Ground.zip"), {
            "gamedata/textures/terrain/t.dds": body("t"), "readme.txt": body("r")}))
        assert (top.name, top.version, top.about, top.fomod, top.problem) == (
            "Autumn Ground", None, "", None, None), vars(top)
        assert top.files() == [("gamedata/textures/terrain/t.dds",
                                "gamedata/textures/terrain/t.dds"),
                               ("readme.txt", "readme.txt")], top.files()
        down = mi.Package(make(os.path.join(d, "Winter Maps v2.7z"), {
            "About this mod.txt": body("a"),
            "Winter Maps v2/gamedata/textures/map/Map_Escape.dds": body("old", 300),
            "Winter Maps v2/gamedata/textures/map/map_escape.dds": body("m", 500),
            "Winter Maps v2/Readme.txt": body("r")}))
        assert down.problem is None, down.problem
        assert down.files() == [("Winter Maps v2/gamedata/textures/map/map_escape.dds",
                                 "gamedata/textures/map/map_escape.dds"),
                                ("Winter Maps v2/Readme.txt", "Readme.txt")], down.files()
        assert down.size() == 500 + len(body("r")), down.size()
        out = mi.install(down, "Winter Maps", mods=mods_in(d))
        assert on_disk(out) == ["Readme.txt", "gamedata/textures/map/map_escape.dds",
                                "meta.ini"], on_disk(out)
        got = open(os.path.join(out, "gamedata", "textures", "map", "map_escape.dds"),
                   "rb").read()
        assert got == body("m", 500), got[:20]
        none = mi.Package(make(os.path.join(d, "Snow Pics.zip"), {"pics/a.png": body("a")}))
        assert none.problem and "no gamedata" in none.problem and none.files() == [], \
            none.problem
        two = mi.Package(make(os.path.join(d, "Winter Choice.zip"), {
            "01 Light/gamedata/a.dds": body("a"), "02 Heavy/gamedata/a.dds": body("b")}))
        assert two.problem and "01 Light, 02 Heavy" in two.problem, two.problem
        assert two.files() == [], two.files()
    return "gamedata at the top and one folder down, a file twice in two cases; none, or two " \
           "places, is a problem"


@case
def t_an_archive_cant_place_a_file_outside_the_mod():
    """Member names that would land a file elsewhere - on another drive, "D:" or "C:x" in
    any part of the path, or in a hidden stream, "x:y" - are left out of the install, and
    install's own check refuses any path that gets past that. Nothing here is unpacked, so
    the case writes nothing outside its folder even when the guard is broken."""
    bad = ["Mod/gamedata/D:/abs.dds", "Mod/gamedata/textures/C:sneaky.dds",
           "Mod/gamedata/x.dds:stream", "Mod/gamedata/../../up.dds"]
    with tempfile.TemporaryDirectory() as d:
        files = {"Mod/gamedata/ok.dds": body("ok")}
        files.update({m: body(m) for m in bad})
        pkg = mi.Package(make(os.path.join(d, "Mod.zip"), files))
        assert pkg.files() == [("Mod/gamedata/ok.dds", "gamedata/ok.dds")], pkg.files()
        passed = [m for m in bad if mi.safe(m.split("/", 1)[1])]
        assert not passed, "let through: %s" % passed
        refused = 0
        for dest in ("gamedata/D:/abs.dds", "gamedata/../../up.dds", ".."):
            try:
                mi.inside(os.path.join(d, "tmp"), dest)
            except mi.ArchiveError:
                refused += 1
        assert refused == 3, refused
    return "4 names that leave the mod folder left out; install's own check refuses 3 more"


@case
def t_the_fomod_default_installs_every_part():
    with tempfile.TemporaryDirectory() as d:
        pkg = mi.Package(rusty(os.path.join(d, "Rusty Leaves 2.1.7z")))
        assert pkg.problem is None, pkg.problem
        assert pkg.name == "Rusty Leaves a test palette", pkg.name
        assert (pkg.version, pkg.about) == ("2.1", "Warmer leaves and drier grass, for the "
                                                   "tests."), (pkg.version, pkg.about)
        steps = pkg.fomod.steps
        assert [s["name"] for s in steps] == ["Welcome", "Parts"], steps
        parts = steps[1]["groups"][0]
        assert parts["type"] == "SelectAtLeastOne" and [p["name"] for p in parts[
            "plugins"]] == list(PARTS), parts
        assert len({p["id"] for p in pkg.fomod.plugins()}) == 5, pkg.fomod.plugins()
        default = pkg.fomod.default()
        assert default == ids(pkg, "Go on", *PARTS), default
        assert dests(pkg.files()) == sorted(TEXTURES), pkg.files()
        assert pkg.files() == pkg.files(default)
        assert pkg.size() == 300 * len(TEXTURES), pkg.size()
        assert pkg.fomod.problems(default) == [], pkg.fomod.problems(default)
    return "all four options and the intro page: every texture, not fomod\\ or meta.ini"


@case
def t_choices_change_the_files():
    with tempfile.TemporaryDirectory() as d:
        pkg = mi.Package(rusty(os.path.join(d, "Rusty Leaves 2.1.zip")))
        grass = pkg.files(ids(pkg, "Grass"))
        assert dests(grass) == ["gamedata/textures/grass/grass.dds",
                                "gamedata/textures/grass/grass_swamp.dds"], grass
        assert grass[0][0] == TOP + "/gamedata/textures/grass/grass.dds", grass
        both = pkg.files(ids(pkg, "Leaves", "Ground"))
        assert dests(both) == sorted(TEXTURES[:2] + TEXTURES[5:]), both
        assert pkg.size(ids(pkg, "Grass")) == 600, pkg.size(ids(pkg, "Grass"))
        assert pkg.files(set()) == [], pkg.files(set())
        assert pkg.fomod.problems(set()) == ["Pick at least one of Parts."], \
            pkg.fomod.problems(set())
    return "Grass alone, Leaves with Ground, and nothing, which the group refuses"


@case
def t_sources_match_the_archive_in_any_case():
    parts = {"Grass": [("folder", r"GameData\Textures\GRASS", r"gamedata\textures\grass")],
             "One leaf": [("file", r"GAMEDATA\textures\Leaves\OAK.dds",
                           r"gamedata\textures\leaves\oak.dds")],
             "Birch": [("file", r"gamedata\textures\leaves\birch.dds", None)],
             "Loose": [("file", r"gamedata\textures\leaves\birch.dds", "")],
             "Into": [("file", r"gamedata\textures\leaves\birch.dds", "gamedata\\extra\\")],
             "Top": [("folder", r"gamedata\levels", "")]}
    with tempfile.TemporaryDirectory() as d:
        pkg = mi.Package(rusty(os.path.join(d, "Case.7z"), fomod_xml(rusty_steps(parts))))
        got = {p["name"]: dests(p["files"]) for p in pkg.fomod.plugins()}
        want = {"Go on": [],
                "Grass": ["gamedata/textures/grass/grass.dds",
                          "gamedata/textures/grass/grass_swamp.dds"],
                "One leaf": ["gamedata/textures/leaves/oak.dds"],
                "Birch": ["gamedata/textures/leaves/birch.dds"],
                "Loose": ["gamedata/textures/leaves/birch.dds"],
                "Into": ["gamedata/extra/birch.dds"],
                "Top": ["l01_escape/level.details"]}
        assert got == want, got
        assert pkg.fomod.problems(pkg.fomod.default()) == [], pkg.fomod.problems(
            pkg.fomod.default())
    return "a folder and a file in other cases; no destination, an empty one, a folder one"


@case
def t_utf16_and_utf8_installers_read_alike():
    seen = {}
    with tempfile.TemporaryDirectory() as d:
        for label, xml, enc in (
                ("UTF-16", fomod_xml(rusty_steps()), "utf-16"),
                ("UTF-16 BE", fomod_xml(rusty_steps()), "utf-16-be"),
                ("UTF-8 with a BOM", fomod_xml(rusty_steps()), "utf-8-sig"),
                ("UTF-8 saying UTF-16", fomod_xml(rusty_steps(), declaration=
                                                  '<?xml version="1.0" encoding="UTF-16"?>\n'),
                 "utf-8")):
            data = xml.encode(enc)
            if enc == "utf-16-be":
                data = b"\xfe\xff" + data
            path = make(os.path.join(d, "enc%d.zip" % len(seen)), {
                TOP + "/fomod/ModuleConfig.xml": data,
                TOP + "/gamedata/textures/grass/grass.dds": body("g"),
                TOP + "/gamedata/textures/leaves/oak.dds": body("o"),
                TOP + "/gamedata/levels/l01/level.details": body("l"),
                TOP + "/gamedata/textures/detail/d.dds": body("d"),
                TOP + "/gamedata/textures/terrain/t.dds": body("t")})
            pkg = mi.Package(path)
            assert pkg.problem is None, (label, pkg.problem)
            seen[label] = (pkg.name, [[p["name"] for g in s["groups"] for p in g["plugins"]]
                                      for s in pkg.fomod.steps], pkg.files())
    first = seen["UTF-16"]
    assert first[2] and all(v == first for v in seen.values()), seen
    return ", ".join(seen)


@case
def t_the_higher_priority_wins_and_then_the_later():
    """Two options with the same file: the higher priority wins wherever it stands, and at
    the same priority the one later in the file, the required files being first."""
    head = ('<requiredInstallFiles><file source="base\\x.dds" destination="gamedata\\x.dds"/>'
            '<file source="base\\y.dds" destination="gamedata\\y.dds"/></requiredInstallFiles>')
    group = group_xml("Patches", "SelectAny", [
        plugin_xml("High", [("file", r"a\x.dds", (r"gamedata\x.dds", 5))]),
        plugin_xml("Low", [("file", r"b\x.dds", (r"gamedata\x.dds", 0))]),
        plugin_xml("Same", [("file", r"c\y.dds", r"gamedata\Y.dds")])])
    files = {"P/fomod/ModuleConfig.xml": fomod_xml([("Only", [group])], head=head).encode(),
             "P/base/x.dds": b"base x", "P/base/y.dds": b"base y", "P/a/x.dds": b"high x",
             "P/b/x.dds": b"low x", "P/c/y.dds": b"same y"}
    with tempfile.TemporaryDirectory() as d:
        pkg = mi.Package(make(os.path.join(d, "Prio.7z"), files))
        assert pkg.problem is None, pkg.problem

        def winners(*names):
            return {dst.lower(): m.split("/")[1] for m, dst in pkg.files(ids(pkg, *names))}

        assert winners() == {"gamedata/x.dds": "base", "gamedata/y.dds": "base"}, winners()
        assert winners("High", "Low")["gamedata/x.dds"] == "a", winners("High", "Low")
        assert winners("Low")["gamedata/x.dds"] == "b", winners("Low")
        assert winners("Same")["gamedata/y.dds"] == "c", winners("Same")
        mods = os.path.join(d, "mods")
        os.makedirs(mods)
        out = mi.install(pkg, "Prio", ids(pkg, "High", "Low", "Same"), mods=mods)
        assert on_disk(out) == ["gamedata/Y.dds", "gamedata/x.dds", "meta.ini"], on_disk(out)
        assert open(os.path.join(out, "gamedata", "x.dds"), "rb").read() == b"high x"
        assert open(os.path.join(out, "gamedata", "Y.dds"), "rb").read() == b"same y"
    return "priority 5 beats a later 0; at 0 the later beats the required file; one copy each"


def rules_pkg(d):
    groups = [group_xml("Color", "SelectExactlyOne", [
                  plugin_xml("Warm", [("file", "w.dds", r"gamedata\c.dds")]),
                  plugin_xml("Cold", [("file", "c.dds", r"gamedata\c.dds")])]),
              group_xml("Extras", "SelectAtMostOne", [
                  plugin_xml("Fog", [("file", "f.dds", r"gamedata\f.dds")]),
                  plugin_xml("Mist", [("file", "m.dds", r"gamedata\m.dds")])]),
              group_xml("Pieces", "SelectAtLeastOne", [
                  plugin_xml("Bark", [("file", "b.dds", r"gamedata\b.dds")]),
                  plugin_xml("Moss", [("file", "o.dds", r"gamedata\o.dds")])]),
              group_xml("Base", "SelectAll", [
                  plugin_xml("Core", [("file", "k.dds", r"gamedata\k.dds")]),
                  plugin_xml("Core too", [("file", "t.dds", r"gamedata\t.dds")])]),
              group_xml("Patches", "SelectAny", [
                  plugin_xml("Broken", [("file", "x.dds", r"gamedata\x.dds")], "NotUsable"),
                  plugin_xml("Must", [("file", "u.dds", r"gamedata\u.dds")], "Required"),
                  plugin_xml("Maybe", [("file", "y.dds", r"gamedata\y.dds")])]),
              group_xml("Tint", "SelectExactlyOne", [
                  plugin_xml("Pale", [("file", "p.dds", r"gamedata\p.dds")]),
                  plugin_xml("Deep", [("file", "e.dds", r"gamedata\e.dds")], "Recommended")])]
    # fomod\ at the top of the archive, not in a folder of its own
    files = {"fomod/ModuleConfig.xml": fomod_xml([("One", groups)]).encode()}
    for f in "wcfmbokutxype":
        files["%s.dds" % f] = body(f)
    return mi.Package(make(os.path.join(d, "Rules.zip"), files))


@case
def t_group_rules_are_said_a_sentence_each():
    with tempfile.TemporaryDirectory() as d:
        pkg = rules_pkg(d)
        default = pkg.fomod.default()
        assert default == ids(pkg, "Warm", "Bark", "Moss", "Core", "Core too", "Must",
                              "Deep"), sorted(default)
        assert pkg.fomod.problems(default) == [], pkg.fomod.problems(default)
        said = {}
        for label, drop, add in (("none of an exactly-one", {"Warm"}, set()),
                                 ("two of an exactly-one", set(), {"Cold"}),
                                 ("two of an at-most-one", set(), {"Fog", "Mist"}),
                                 ("none of an at-least-one", {"Bark", "Moss"}, set()),
                                 ("a NotUsable one", set(), {"Broken"}),
                                 ("a Required one left out", {"Must"}, set()),
                                 ("one of a SelectAll left out", {"Core too"}, set())):
            chosen = (default - ids(pkg, *drop)) | (ids(pkg, *add) if add else set())
            said[label] = pkg.fomod.problems(chosen)
        want = {"none of an exactly-one": ["Pick one of Color."],
                "two of an exactly-one": ["Pick one of Color."],
                "two of an at-most-one": ["Pick no more than one of Extras."],
                "none of an at-least-one": ["Pick at least one of Pieces."],
                "a NotUsable one": ["Broken can't be used here. Uncheck it."],
                "a Required one left out": ["Must is required. Check it."],
                "one of a SelectAll left out": ["Core too is required. Check it."]}
        assert said == want, said
        mods = os.path.join(d, "mods")
        os.makedirs(mods)
        why = refused(mi.install, pkg, "Rules", default | ids(pkg, "Fog", "Mist"), mods=mods)
        assert why == "Pick no more than one of Extras.", why
        assert os.listdir(mods) == [], os.listdir(mods)
        # Warm, Bark, Moss, Core, Core too, Must and Deep, from the top of the archive
        assert pkg.files(default) == [("%s.dds" % f, "gamedata/%s.dds" % t) for f, t in (
            ("b", "b"), ("w", "c"), ("e", "e"), ("k", "k"), ("o", "o"), ("t", "t"),
            ("u", "u"))], pkg.files(default)
    return "the defaults pass; each of seven breaks said, and install refuses one"


@case
def t_options_are_shown_in_the_installer_order():
    """Explicit keeps the file's order; Ascending, which an installer that says nothing
    gets, and Descending sort by name. Ids go by the file's order all the same."""
    def plugins(order):
        attr = ' order="%s"' % order if order else ""
        group = ('<group name="G" type="SelectAny"><plugins%s>%s</plugins></group>' % (
            attr, plugin_xml("Zeta", [("file", "z.dds", None)])
            + plugin_xml("alpha", [("file", "a.dds", None)])
            + plugin_xml("Mid", [("file", "m.dds", None)])))
        return fomod_xml([("S", [group])])

    shown = {}
    with tempfile.TemporaryDirectory() as d:
        for order in ("Explicit", None, "Ascending", "Descending"):
            pkg = mi.Package(make(os.path.join(d, "o%d.zip" % len(shown)), {
                "fomod/ModuleConfig.xml": plugins(order).encode(), "z.dds": b"z",
                "a.dds": b"a", "m.dds": b"m"}))
            shown[order] = [(p["name"], p["id"]) for p in pkg.fomod.plugins()]
    z, a, m = ("Zeta", "1.1.1"), ("alpha", "1.1.2"), ("Mid", "1.1.3")
    assert shown == {"Explicit": [z, a, m], None: [a, m, z], "Ascending": [a, m, z],
                     "Descending": [z, m, a]}, shown
    return "explicit, unsaid, ascending and descending; the ids the same in each"


@case
def t_files_an_installer_always_installs_come_with_any_choice():
    """alwaysInstall puts a file in whatever is chosen, installIfUsable whenever its option
    can be used; a source the archive doesn't have is refused once it is chosen."""
    group = group_xml("Parts", "SelectAny", [
        plugin_xml("Trees", [("file", "t.dds", r"gamedata\t.dds")]).replace(
            'source="t.dds"', 'alwaysInstall="true" source="t.dds"'),
        plugin_xml("Bushes", [("file", "b.dds", r"gamedata\b.dds")]).replace(
            'source="b.dds"', 'installIfUsable="true" source="b.dds"'),
        plugin_xml("Broken", [("file", "x.dds", r"gamedata\x.dds")], "NotUsable").replace(
            'source="x.dds"', 'installIfUsable="true" source="x.dds"'),
        plugin_xml("Ghost", [("folder", r"gamedata\ghost", r"gamedata\ghost")])])
    head = '<requiredInstallFiles><file source="gone.dds"/></requiredInstallFiles>'
    with tempfile.TemporaryDirectory() as d:
        files = {"fomod/ModuleConfig.xml": fomod_xml([("S", [group])]).encode(),
                 "t.dds": b"t", "b.dds": b"b", "x.dds": b"x"}
        pkg = mi.Package(make(os.path.join(d, "Always.zip"), files))
        assert dests(pkg.files(set())) == ["gamedata/b.dds", "gamedata/t.dds"], pkg.files(set())
        assert pkg.fomod.problems(set()) == [], pkg.fomod.problems(set())
        said = pkg.fomod.problems(ids(pkg, "Ghost"))
        assert said == ["Ghost installs gamedata/ghost, which isn't in the archive."], said
        files["fomod/ModuleConfig.xml"] = fomod_xml([("S", [group])], head=head).encode()
        pkg = mi.Package(make(os.path.join(d, "Gone.zip"), files))
        said = pkg.fomod.problems(set())
        assert said == ["Its installer always installs gone.dds, which isn't in the archive."], \
            said
        assert refused(mi.install, pkg, "Gone", mods=mods_in(d)) == said[0]
    return "two files with no option chosen, a NotUsable one's left out; missing ones said"


@case
def t_an_installer_with_conditions_is_left_to_mo2():
    plain = plugin_xml("Grass", PARTS["Grass"])
    flagged = plain.replace("<typeDescriptor>", '<conditionFlags><flag name="grass">On'
                            '</flag></conditionFlags><typeDescriptor>')
    typed = plain.replace('<typeDescriptor><type name="Optional"/></typeDescriptor>',
                          '<typeDescriptor><dependencyType><defaultType name="Optional"/>'
                          '<patterns><pattern><dependencies><flagDependency flag="a" '
                          'value="On"/></dependencies><type name="Required"/></pattern>'
                          '</patterns></dependencyType></typeDescriptor>')
    grass = [("Parts", [group_xml("Parts", "SelectAny", [plain])])]
    variants = {
        "condition flags": fomod_xml([("Parts", [group_xml("Parts", "SelectAny",
                                                           [flagged])])]),
        "a type that depends": fomod_xml([("Parts", [group_xml("Parts", "SelectAny",
                                                               [typed])])]),
        "module dependencies": fomod_xml(grass, head='<moduleDependencies operator="And">'
                                         '<fileDependency file="ccon.ltx" state="Active"/>'
                                         '</moduleDependencies>'),
        "conditional installs": fomod_xml(grass, tail='<conditionalFileInstalls><patterns>'
                                          '<pattern><dependencies><flagDependency flag="a" '
                                          'value="On"/></dependencies><files><folder source='
                                          '"gamedata" destination="gamedata"/></files>'
                                          '</pattern></patterns></conditionalFileInstalls>'),
        "a step shown on a condition": fomod_xml(grass).replace(
            '<installStep name="Parts">', '<installStep name="Parts"><visible><flagDependency '
            'flag="a" value="On"/></visible>')}
    with tempfile.TemporaryDirectory() as d:
        mods = os.path.join(d, "mods")
        os.makedirs(mods)
        for i, (label, xml) in enumerate(variants.items()):
            pkg = mi.Package(rusty(os.path.join(d, "c%d.7z" % i), xml))
            assert (pkg.problem, pkg.fomod, pkg.files()) == (mi.FOLLOW, None, []), (
                label, pkg.problem)
            assert pkg.name == "Rusty Leaves a test palette", (label, pkg.name)
            assert refused(mi.install, pkg, "C%d" % i, mods=mods) == mi.FOLLOW, label
        empty = mi.Package(rusty(os.path.join(d, "empty.7z"), fomod_xml(grass).replace(
            "<typeDescriptor>", "<conditionFlags/><typeDescriptor>")))
        assert empty.problem is None and empty.fomod, empty.problem
        assert dests(empty.files(ids(empty, "Grass"))) == TEXTURES[2:4], empty.files()
        assert os.listdir(mods) == [], os.listdir(mods)
    return "%d kinds refused with MO2's way named; an empty conditionFlags asks nothing" % (
        len(variants))


@case
def t_place_finds_where_a_fix_goes():
    pairs = [("M/gamedata/textures/grass/Grass.dds", "gamedata/textures/grass/Grass.dds"),
             ("M/gamedata/textures/grass/grass_swamp.dds",
              "gamedata/textures/grass/grass_swamp.dds"),
             ("M/gamedata/textures/leaves/oak.dds", "gamedata/textures/leaves/oak.dds"),
             ("M/gamedata/textures/trees/oak.dds", "gamedata/textures/trees/oak.dds")]
    one = mi.place(r"D:\GAMMA\grass.DDS", pairs)
    assert one == "gamedata/textures/grass/Grass.dds", one
    assert mi.place("grass_swamp.dds", [d for _, d in pairs]) == pairs[1][1]
    assert mi.place("birch.dds", pairs) is None
    assert mi.place("oak.dds", pairs) is None
    assert mi.place("oak.dds", ["gamedata/a/oak.dds", "GAMEDATA/A/OAK.dds"]) \
        == "gamedata/a/oak.dds"
    return "one match, from a path or a name; none; two different is None; one twice is one"


def mods_in(d):
    mods = os.path.join(d, "mods")
    os.makedirs(mods, exist_ok=True)
    return mods


@case
def t_install_makes_the_mod_folder_and_its_meta_ini():
    with tempfile.TemporaryDirectory() as d:
        archive = rusty(os.path.join(d, "Rusty, Leaves 2.1.7z"))
        pkg = mi.Package(archive)
        mods = mods_in(d)
        out = mi.install(pkg, pkg.name, mods=mods)
        assert out == os.path.join(mods, "Rusty Leaves a test palette"), out
        assert os.listdir(mods) == ["Rusty Leaves a test palette"], os.listdir(mods)
        assert on_disk(out) == sorted(TEXTURES + ["meta.ini"]), on_disk(out)
        for rel in TEXTURES:
            assert open(os.path.join(out, *rel.split("/")), "rb").read() == body(rel, 300), rel
        raw = open(os.path.join(out, "meta.ini"), "rb").read()
        assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b""), raw
        lines = raw.decode("utf-8").split("\r\n")
        path = os.path.abspath(archive).replace("\\", "/")
        for want in ("[General]", "gameName=stalkeranomaly", "modid=0", "version=2.1",
                     'installationFile="%s"' % path, "[installedFiles]", "size=0"):
            assert want in lines, (want, lines)
        assert lines.index("[installedFiles]") > lines.index("[General]"), lines
        assert mi.installed_from(os.path.join(out, "meta.ini")) == "Rusty, Leaves 2.1.7z"
        plain = mi.Package(make(os.path.join(d, "Autumn Ground.7z"), {
            "Autumn Ground/gamedata/textures/terrain/t.dds": body("t"),
            "Autumn Ground/gamedata/configs/empty.ltx": b""}))
        out = mi.install(plain, "Autumn Ground", mods=mods)
        assert on_disk(out) == ["gamedata/configs/empty.ltx", "gamedata/textures/terrain/t.dds",
                                "meta.ini"], on_disk(out)
        assert os.path.getsize(os.path.join(out, "gamedata", "configs", "empty.ltx")) == 0
        assert "version=" in open(os.path.join(out, "meta.ini")).read().splitlines()
    return "every texture, MO2's meta.ini (a comma in the path quoted), an empty file too"


@case
def t_the_fix_file_goes_in_over_the_archive_copy():
    with tempfile.TemporaryDirectory() as d:
        pkg = mi.Package(rusty(os.path.join(d, "Rusty Leaves 2.1.zip")))
        fix = os.path.join(d, "grass.dds")
        open(fix, "wb").write(b"the author's fixed grass")
        where = mi.place(fix, pkg.files())
        assert where == "gamedata/textures/grass/grass.dds", where
        out = mi.install(pkg, "Rusty", extra=[(fix, where)], mods=mods_in(d))
        got = open(os.path.join(out, *where.split("/")), "rb").read()
        assert got == b"the author's fixed grass", got
        other = "gamedata/textures/grass/grass_swamp.dds"
        assert open(os.path.join(out, *other.split("/")), "rb").read() == body(other, 300)
        assert on_disk(out) == sorted(TEXTURES + ["meta.ini"]), on_disk(out)
        new = mi.install(pkg, "Rusty 2", extra=[(fix, "gamedata/textures/fix/grass.dds")],
                         mods=mods_in(d))
        assert "gamedata/textures/fix/grass.dds" in on_disk(new), on_disk(new)
        why = refused(mi.install, pkg, "Rusty 3", extra=[(fix, "../outside.dds")],
                      mods=mods_in(d))
        assert "inside" in why, why
    return "the loose file replaces the archive's grass.dds; a new place is made; ../ refused"


@case
def t_install_refuses_what_it_cant_do():
    with tempfile.TemporaryDirectory() as d:
        mods = mods_in(d)
        os.makedirs(os.path.join(mods, "Rusty", "gamedata"))
        open(os.path.join(mods, "Rusty", "gamedata", "mine.txt"), "w").write("keep")
        pkg = mi.Package(rusty(os.path.join(d, "Rusty Leaves 2.1.7z")))
        calls = []
        said = [refused(mi.install, pkg, "Rusty", mods=mods,
                        progress=lambda done, total: calls.append(done)),
                refused(mi.install, pkg, "rusty", mods=mods),
                refused(mi.install, pkg, "Rusty: autumn", mods=mods),
                refused(mi.install, pkg, "Rusty.", mods=mods),
                refused(mi.install, pkg, "  ", mods=mods)]
        assert said[0] == "A mod called Rusty is installed already. Pick another name.", said
        assert calls == [], "it unpacked before refusing: %s" % calls
        assert said[1] == "A mod called rusty is installed already. Pick another name.", said
        assert said[2] == said[3] == mi.BAD_NAME and said[4] == "Give the mod a name.", said
        any_group = group_xml("Extras", "SelectAny", [plugin_xml("Grass", PARTS["Grass"])])
        loose = mi.Package(rusty(os.path.join(d, "Loose.7z"),
                                 fomod_xml([("Extras", [any_group])])))
        assert loose.fomod.default() == set(), loose.fomod.default()
        said.append(refused(mi.install, loose, "Loose", mods=mods))
        assert said[-1] == "Nothing is chosen to install. Check at least one option.", said
        nothing = mi.Package(make(os.path.join(d, "Winter Pics.zip"), {"a.png": b"a"}))
        said.append(refused(mi.install, nothing, "Pics", mods=mods))
        assert said[-1] == nothing.problem, said
        assert os.listdir(mods) == ["Rusty"], os.listdir(mods)
        assert on_disk(os.path.join(mods, "Rusty")) == ["gamedata/mine.txt"]
    return "%d refusals, the folder already there untouched, nothing new in mods" % len(said)


def damaged_zip(path):
    """A zip whose second file's bytes are changed, after its first is whole: it lists,
    and unpacking stops partway."""
    make(path, {"D/gamedata/a.dds": body("a", 5000), "D/gamedata/b.dds": body("b", 5000)},
         stored=True)
    with zipfile.ZipFile(path) as z:
        info = z.getinfo("D/gamedata/b.dds")
    raw = bytearray(open(path, "rb").read())
    raw[info.header_offset + 30 + len(info.filename) + 2500] ^= 0xFF
    open(path, "wb").write(bytes(raw))
    return path


def damaged_7z(path):
    """A .7z whose packed stream is changed partway, its header left whole."""
    import py7zr
    import random
    rnd = random.Random(7)
    make(path, {"D/gamedata/a.dds": bytes(rnd.getrandbits(8) for _ in range(60000)),
                "D/gamedata/b.dds": bytes(rnd.getrandbits(8) for _ in range(60000))})
    with py7zr.SevenZipFile(path) as z:
        start = z.afterheader
    raw = bytearray(open(path, "rb").read())
    for i in range(90000, 90400):
        raw[start + i] ^= 0x5A
    open(path, "wb").write(bytes(raw))
    return path


@case
def t_a_failure_leaves_nothing_behind():
    """A damaged archive stops the install partway, with a file already written: the temp
    folder goes, and no mod folder is made."""
    with tempfile.TemporaryDirectory() as d, ticking():
        mods = mods_in(d)
        for archive in (damaged_zip(os.path.join(d, "Winter Damaged.zip")),
                        damaged_7z(os.path.join(d, "Winter Damaged.7z"))):
            pkg = mi.Package(archive)
            assert pkg.problem is None and len(pkg.files()) == 2, pkg.problem
            calls = []
            why = refused(mi.install, pkg, "Damaged", mods=mods,
                          progress=lambda done, total: calls.append(done))
            assert "Nothing was installed" in why, why
            assert max(calls) > 0, "%s failed before writing anything" % archive
            assert os.listdir(mods) == [], os.listdir(mods)

        class Cancel(Exception):
            pass

        pkg = mi.Package(rusty(os.path.join(d, "Rusty Leaves 2.1.7z")))
        for stop in (Cancel, KeyboardInterrupt):
            def progress(done, total, stop=stop):
                if done:
                    raise stop("the window was closed")
            try:
                mi.install(pkg, "Stopped", progress=progress, mods=mods)
                raise AssertionError("an exception from progress did not stop it")
            except stop as e:
                assert str(e) == "the window was closed", e
            assert os.listdir(mods) == [], os.listdir(mods)
    return "a damaged .zip and .7z; progress raising, as it raised: no mod or temp folder"


def multi_7z(path, parts):
    """A .7z with each file in a block of its own - the kind py7zr unpacks in threads when
    given the archive's path."""
    import py7zr
    for i, (name, data) in enumerate(parts.items()):
        with py7zr.SevenZipFile(path, "a" if i else "w") as z:
            z.writestr(data, name)
    with py7zr.SevenZipFile(path) as z:
        assert len(z.header.main_streams.unpackinfo.folders) == len(parts), "one block"
    return path


@case
def t_progress_comes_from_the_install_thread_with_the_whole_total():
    """Called for every piece written, not only at the start and the end, which install
    calls itself: the pieces are where another thread would show."""
    with tempfile.TemporaryDirectory() as d, ticking():
        mods = mods_in(d)
        seen = []
        for archive in (multi_7z(os.path.join(d, "Summer Blocks.7z"), {
                            "S/gamedata/a.dds": body("a", 3 << 20),
                            "S/gamedata/b.dds": body("b", 3 << 20),
                            "S/gamedata/c.dds": body("c", 1000)}),
                        make(os.path.join(d, "Summer Blocks.zip"), {
                            "S/gamedata/a.dds": body("a", 3 << 20),
                            "S/gamedata/c.dds": body("c", 1000)})):
            pkg = mi.Package(archive)
            calls, box = [], {}

            def progress(done, total):
                calls.append((threading.get_ident(), done, total))

            def work():
                box["ident"] = threading.get_ident()
                box["out"] = mi.install(pkg, os.path.basename(archive) + " mod",
                                        progress=progress, mods=mods)

            t = threading.Thread(target=work)
            t.start()
            t.join()
            size = pkg.size()
            assert "out" in box, "install failed"
            assert calls and calls[0][1:] == (0, size) and calls[-1][1:] == (size, size), calls
            assert all(c[2] == size for c in calls), calls
            assert len(calls) >= 5, calls
            assert {c[0] for c in calls} == {box["ident"]}, (calls, box["ident"])
            assert [c[1] for c in calls] == sorted(c[1] for c in calls), calls
            seen.append("%d calls" % len(calls))
    return "a .7z in three blocks (%s) and a .zip (%s): one thread, total = size()" % tuple(
        seen)


@contextlib.contextmanager
def ticking():
    """install()'s progress called for every piece written."""
    was, mi.TICK = mi.TICK, 0
    try:
        yield
    finally:
        mi.TICK = was


@case
def t_found_lists_seasonal_archives_not_installed():
    with tempfile.TemporaryDirectory() as g:
        down = os.path.join(g, "downloads")
        os.makedirs(down)
        for where, name in ((g, "Rusty Autumn 2.1.7z"), (down, "Rusty Autumn 2.1.7z"),
                            (down, "Deep Winter Pack.zip"), (down, "Snowy Maps.7z"),
                            (down, "Spring, Greener.rar"), (down, "Summer Grass.zip"),
                            (down, "Weapons Pack.zip"), (down, "Autumn notes.txt"),
                            (g, "Frosty Weapons.7z")):
            open(os.path.join(where, name), "wb").write(b"not read")
        os.makedirs(os.path.join(down, "Summer Folder.zip"))
        meta = {"Maps (seasonal)": "installationFile=C:/elsewhere/Snowy Maps.7z",
                "Spring": 'installationFile="D:/GAMMA/downloads/Spring, Greener.rar"',
                "Summer Grass": "installationFile=",
                "No meta": None}
        for folder, line in meta.items():
            os.makedirs(os.path.join(g, "mods", folder))
            if line:
                open(os.path.join(g, "mods", folder, "meta.ini"), "w").write(
                    "[General]\nmodid=0\n%s\n" % line)
        got = mi.found(g, list(meta))
        assert got == [
            {"path": os.path.join(down, "Deep Winter Pack.zip"), "name": "Deep Winter Pack",
             "seasons": ["winter_snow"]},
            {"path": os.path.join(g, "Rusty Autumn 2.1.7z"), "name": "Rusty Autumn 2.1",
             "seasons": ["autumn"]}], got
        assert mi.found(os.path.join(g, "nowhere"), []) == []
    with tempfile.TemporaryDirectory() as g:
        archive = rusty(os.path.join(g, "Rusty Autumn 2.1.7z"))
        assert [a["name"] for a in mi.found(g, [])] == ["Rusty Autumn 2.1"]
        pkg = mi.Package(archive)
        mi.install(pkg, pkg.name, mods=mods_in(g))
        assert mi.found(g, os.listdir(os.path.join(g, "mods"))) == []
    return "one from the GAMMA folder, one from downloads; installed, or no season, left out"


@case
def t_a_rar_installs_like_the_others():
    if not RAR:
        return "WinRAR's Rar.exe isn't here - skipped"
    with tempfile.TemporaryDirectory() as d:
        pkg = mi.Package(rusty(os.path.join(d, "Rusty Leaves 2.1.rar")))
        assert pkg.problem is None and pkg.version == "2.1", pkg.problem
        grass = ids(pkg, "Grass")
        out = mi.install(pkg, "Rusty", grass, mods=mods_in(d))
        assert on_disk(out) == ["gamedata/textures/grass/grass.dds",
                                "gamedata/textures/grass/grass_swamp.dds",
                                "meta.ini"], on_disk(out)
        rel = "gamedata/textures/grass/grass_swamp.dds"
        assert open(os.path.join(out, *rel.split("/")), "rb").read() == body(rel, 300)
    return "its installer read through UnRAR, and the Grass option installed"


@case
def t_an_archive_that_cant_be_read_is_said():
    with tempfile.TemporaryDirectory() as d:
        said = []
        fake = os.path.join(d, "Winter Fake.7z")
        open(fake, "wb").write(b"this is not an archive")
        said.append(refused(mi.Package, fake))
        assert "can't be read as a .7z" in said[-1], said
        said.append(refused(mi.Package, os.path.join(d, "Gone Winter.zip")))
        assert said[-1].startswith("Can't open Gone Winter.zip:"), said
        said.append(refused(mi.Package, os.path.join(d, "Winter.txt")))
        assert said[-1] == "Winter.txt isn't a .7z, .zip or .rar.", said
        real = make(os.path.join(d, "Winter Real.7z"), {"gamedata/a.dds": b"a"})
        saved = sys.modules.get("py7zr")
        sys.modules["py7zr"] = None                # as if it were not installed
        try:
            said.append(refused(mi.Package, real))
        finally:
            if saved is None:
                del sys.modules["py7zr"]
            else:
                sys.modules["py7zr"] = saved
        assert said[-1].startswith("Opening a .7z needs py7zr") and "-m pip install py7zr" \
            in said[-1], said
    return "not an archive, gone, the wrong kind, and py7zr missing"


@case
def t_the_real_colorful_autumn_archive():
    """The archive this was made for, read where the player put it. Nothing is unpacked
    but its installer."""
    if not os.path.isfile(REAL):
        return "%s isn't here - skipped" % REAL
    pkg = mi.Package(REAL)
    assert pkg.problem is None, pkg.problem
    assert pkg.name == "Colorful Autumn (C-Consciousness and Boreals Forest Ground recolor)", \
        pkg.name
    assert pkg.version == "1.4", pkg.version
    assert pkg.about.startswith("A recolor of"), pkg.about
    options = [g for s in pkg.fomod.steps for g in s["groups"] if g["name"] == "Options"]
    assert len(options) == 1 and options[0]["type"] == "SelectAtLeastOne", options
    names = [p["name"] for p in options[0]["plugins"]]
    assert len(names) == 4 and [n.split()[0] for n in names] == ["Trees", "Grass", "No",
                                                                   "Grounds"], names
    four = {p["id"] for p in options[0]["plugins"]}
    assert four <= pkg.fomod.default(), (four, pkg.fomod.default())
    grass = pkg.files({p["id"] for p in options[0]["plugins"]
                       if p["name"].startswith("Grass")})
    assert grass and all(d.startswith("gamedata/textures/ccon/") for _, d in grass), grass
    where = mi.place("CConV1.5.dds", pkg.files())
    assert where == "gamedata/textures/ccon/CConV1.5.dds", where
    return "%s %s: %d files by default, %.1f GB" % (pkg.name.split(" (")[0], pkg.version,
                                                     len(pkg.files()), pkg.size() / 2 ** 30)


if __name__ == "__main__":
    print("  installing a seasonal mod from its archive")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-58s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-58s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-58s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
