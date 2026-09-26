"""Installing a seasonal mod from its archive: a .7z, .zip or .rar the player downloaded.

The guided setup offers the archives in the GAMMA folder and in MO2's downloads folder whose
names say a season. Package reads one without unpacking it: its files, and its FOMOD
installer when it has one, whose options the window shows as checkboxes. install() then
makes it a mod folder in mods\\ the way MO2's own installer would, meta.ini included, and a
fix the author ships as a loose file goes in over the archive's copy.

Only FOMODs that ask plain questions are followed: steps of options, each installing files
and folders. One whose steps or options depend on flags, files or other mods is left to
MO2's installer. MO2's mod list is not touched: MO2 lists a new folder in mods\\ by itself,
and play.bat puts a seasonal mod in the list.
"""
import contextlib
import io
import os
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

import season
from lang import _, N_, ngettext, pgettext

ARCHIVES = (".7z", ".zip", ".rar")
GROUP_TYPES = ("SelectExactlyOne", "SelectAtMostOne", "SelectAtLeastOne", "SelectAny",
               "SelectAll")
PLUGIN_TYPES = ("Required", "Optional", "Recommended", "NotUsable", "CouldBeUsable")
# translators: "Install a new mod from archive" is an item of MO2's menu
FOLLOW = N_("Its installer asks questions this tool can't follow. Install it with MO2 - "
            "Install a new mod from archive - then add it here.")
LOCKED = N_("%s is locked with a password, which this tool can't open.")
TAKEN = N_("A mod called %s is installed already. Pick another name.")
BAD_NAME = N_("A mod's name can't start or end with a space, end with a dot, or hold any of "
              "/ \\ : * ? \" < > |. Pick another name.")
CHUNK = 1 << 20
TICK = 0.25                 # seconds between calls to install()'s progress, at the least

WINTER = ("winter", "winter_snow", "late_winter")
SEASON_WORDS = {"spring": ("spring",), "summer": ("summer",), "autumn": ("autumn",),
                "fall": ("autumn",), "winter": WINTER, "snow": WINTER, "snowy": WINTER,
                "frost": WINTER, "thaw": ("late_winter",)}
SEASON_PHRASES = {("deep", "winter"): ("winter_snow",), ("late", "winter"): ("late_winter",)}
# The words in a name, as letters: "Simple_Autumn_v1.1" is Simple Autumn v, and a name run
# together is split where its capitals start words, "AutumnNoLeavesLOD" as Autumn No Leaves
# LOD. So "frostychun" and "Falling" stay one word each and say no season.
WORD = re.compile(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+")


class ArchiveError(Exception):
    """Why an archive can't be read or installed, in words for the player."""


# --- which archives -----------------------------------------------------------------------

def seasons_in(text):
    """The seasons a name says, as season keys in season.SEASONS order: "Colorful Autumn
    1.4" -> ["autumn"]. Words, case-insensitive, whole words: spring; summer; autumn or fall;
    winter or snow or snowy or frost -> winter, winter_snow, late_winter; "deep winter" ->
    winter_snow; "late winter" or thaw -> late_winter. [] when it says none."""
    words = [w.lower() for w in WORD.findall(text or "")]
    said, i = set(), 0
    while i < len(words):
        pair = tuple(words[i:i + 2])
        if pair in SEASON_PHRASES:
            said.update(SEASON_PHRASES[pair])
            i += 2
        else:
            said.update(SEASON_WORDS.get(words[i], ()))
            i += 1
    return [s for s in season.SEASONS if s in said]


def installed_from(meta_ini):
    """The file name a mod's meta.ini says it was installed from, or None. MO2 writes the
    path as QSettings does - in quotes when it holds a comma, with \\\\, \\" and \\xHHHH
    escapes - and a path from another tool may use backslashes; only the name is kept."""
    try:
        text = io.open(meta_ini, encoding="utf-8-sig", errors="replace").read()
    except OSError:
        return None
    m = re.search(r"(?mi)^\s*installationFile\s*=(.*)$", text)
    if not m:
        return None
    v = m.group(1).strip()
    if len(v) >= 2 and v[0] == v[-1] == '"':
        v = v[1:-1]

    def unescape(e):
        s = e.group(1)
        if s[0] == "x" and len(s) > 1:
            return chr(int(s[1:], 16))
        return '"' if s == '"' else "/" + ("" if s == "\\" else s)

    v = re.sub(r'\\(x[0-9a-fA-F]{1,4}|.)', unescape, v)
    return re.split(r"[\\/]", v)[-1].strip() or None


def found(gamma, folders):
    """Archives (.7z, .zip, .rar) sitting directly in `gamma` or in gamma\\downloads whose
    names say a season, and that aren't installed: [{"path", "name", "seasons"}], name
    being the file name without its extension. Installed means a mod folder in `folders`
    (names of folders in mods/) whose meta.ini has installationFile naming that file (by
    base name, any folder), or a folder named like the archive without its extension.

    An archive in both places is listed once, from the GAMMA folder."""
    out = {}
    for where in (gamma, os.path.join(gamma, "downloads")):
        try:
            names = os.listdir(where)
        except OSError:
            continue
        for f in names:
            stem, ext = os.path.splitext(f)
            if ext.lower() not in ARCHIVES or f.casefold() in out:
                continue
            said = seasons_in(stem)
            if said and os.path.isfile(os.path.join(where, f)):
                out[f.casefold()] = {"path": os.path.join(where, f), "name": stem,
                                     "seasons": said}
    for folder in folders:
        if not out:
            break
        for key in [k for k, a in out.items() if a["name"].casefold() == folder.casefold()]:
            del out[key]
        src = installed_from(os.path.join(gamma, "mods", folder, "meta.ini"))
        if src:
            out.pop(src.casefold(), None)
    return sorted(out.values(), key=lambda a: a["name"].casefold())


def place(loose, dests):
    """Where a loose file from the mod's author - a fix - goes: the one dest in `dests`
    whose file name is the loose file's (case-insensitive), or None when there is none, or
    several different ones. `dests` may be files()'s (member, dest) pairs."""
    name = re.split(r"[\\/]", loose)[-1].casefold()
    hits = {}
    for d in dests:
        d = (d[1] if isinstance(d, (tuple, list)) else d).replace("\\", "/")
        if d.rsplit("/", 1)[-1].casefold() == name:
            hits.setdefault(d.casefold(), d)
    return next(iter(hits.values())) if len(hits) == 1 else None


def folder_name(text):
    """`text` as a mod folder's name: without the characters a folder name can't hold, its
    spaces run together, and no dot or space at the end. "" when nothing is left."""
    s = re.sub(r'[\x00-\x1f/\\:*?"<>|]', " ", text or "")
    return " ".join(s.split()).rstrip(". ")


# --- reading archives ---------------------------------------------------------------------

def kind(path):
    """".7z", ".zip" or ".rar" by the file's extension; None for any other file."""
    ext = os.path.splitext(path)[1].lower()
    return ext if ext in ARCHIVES else None


def _py7zr():
    try:
        import py7zr
    except ImportError:
        # translators: %s is the command that installs it
        raise ArchiveError(_("Opening a .7z needs py7zr, a Python package: %s")
                           % (season._python() + " -m pip install py7zr"))
    return py7zr


def _rarfile():
    """rarfile, pointed at UnRAR or 7-Zip: it reads a .rar's list of files itself, but
    needs one of the two to unpack them."""
    try:
        import rarfile
    except ImportError:
        # translators: %s is the command that installs it
        raise ArchiveError(_("Opening a .rar needs rarfile, a Python package: %s. It also "
                             "needs WinRAR or 7-Zip installed.")
                           % (season._python() + " -m pip install rarfile"))
    tool = season._find_unrar()
    if os.path.splitext(os.path.basename(tool))[0].lower() == "7z":
        rarfile.SEVENZIP_TOOL = tool
    else:
        rarfile.UNRAR_TOOL = tool
    try:
        rarfile.tool_setup()
    except rarfile.RarCannotExec:
        raise ArchiveError(_("Opening a .rar needs WinRAR or 7-Zip installed. Install either "
                             "one, then try again."))
    return rarfile


def _said(e):
    """An exception in a few words."""
    text = " ".join(str(e).split())
    return text[:200] if text else type(e).__name__


@contextlib.contextmanager
def _reading(archive):
    """What a library raises for a damaged archive, as an ArchiveError. OSError is left
    alone: the caller knows whether it was reading or writing."""
    try:
        yield
    except (ArchiveError, OSError):
        raise
    except Exception as e:
        name = os.path.basename(archive)
        if type(e).__name__ in ("PasswordRequired", "RarWrongPassword"):
            raise ArchiveError(_(LOCKED) % name)
        # translators: %(kind)s is .7z, .zip or .rar; %(error)s what the library said
        raise ArchiveError(_("%(archive)s can't be read as a %(kind)s (%(error)s). It may be "
                             "damaged or not fully downloaded; download it again.")
                           % {"archive": name, "kind": kind(archive), "error": _said(e)})


def listing(archive):
    """The files in an archive, in its order: [(member, size)], member as the archive names
    it. Folders are left out. Raises ArchiveError when it can't be read."""
    name = os.path.basename(archive)
    k = kind(archive)
    if not k:
        raise ArchiveError(_("%s isn't a .7z, .zip or .rar.") % name)
    with _reading(archive):
        if k == ".7z":
            py7zr = _py7zr()
            with open(archive, "rb") as fp, py7zr.SevenZipFile(fp) as z:
                if z.needs_password():
                    raise ArchiveError(_(LOCKED) % name)
                return [(f.filename, f.uncompressed) for f in z.list()
                        if not f.is_directory and not f.is_symlink]
        if k == ".zip":
            with zipfile.ZipFile(archive) as z:
                infos = [i for i in z.infolist() if not i.is_dir()]
                if any(i.flag_bits & 1 for i in infos):
                    raise ArchiveError(_(LOCKED) % name)
                return [(i.filename, i.file_size) for i in infos]
        rarfile = _rarfile()
        with rarfile.RarFile(archive) as z:
            if z.needs_password():
                raise ArchiveError(_(LOCKED) % name)
            return [(i.filename, i.file_size) for i in z.infolist() if i.is_file()]


def _create(path):
    os.makedirs(season.lp(os.path.dirname(path)), exist_ok=True)
    return open(season.lp(path), "wb")


def _unpack_7z(archive, targets, count):
    """unpack() for a .7z. py7zr is handed the open file, not its path: given a path it
    unpacks each block of the archive in a thread of its own, and progress has to come
    from this one."""
    py7zr = _py7zr()
    from py7zr.io import Py7zIO, WriterFactory
    wanted = {slashed(m): (m, paths) for m, paths in targets.items()}
    kept, sinks = {}, []

    class Sink(Py7zIO):
        """One member on its way to its paths, or to memory when it has none."""

        def __init__(self, member, paths, keep):
            self.member, self.n, self.files = member, 0, []
            self.memory = io.BytesIO() if keep else None
            sinks.append(self)
            for p in paths:
                self.files.append(_create(p))

        def write(self, data):
            for f in self.files:
                f.write(data)
            if self.memory is not None:
                self.memory.write(data)
            self.n += len(data)
            count(len(data) * len(self.files))
            return len(data)

        def read(self, size=None):
            return b""

        def seek(self, offset, whence=0):
            return 0

        def flush(self):
            pass

        def size(self):
            return self.n

        def close(self):
            for f in self.files:
                f.close()
            if self.memory is not None:
                kept[self.member] = self.memory.getvalue()

    class Factory(WriterFactory):
        def create(self, filename):
            member, paths = wanted.get(slashed(filename), (filename, None))
            return Sink(member, paths or [], keep=paths == [])

    try:
        with open(archive, "rb") as fp, py7zr.SevenZipFile(fp) as z:
            z.extract(targets=list(targets), factory=Factory())
    finally:
        for s in sinks:
            for f in s.files:
                f.close()
    return kept


def _unpack_each(z, targets, count):
    """unpack() for a .zip or .rar: one member at a time, read in pieces."""
    kept = {}
    for member, paths in targets.items():
        with z.open(member) as src:
            if not paths:
                kept[member] = src.read()
                continue
            files = []
            try:
                for p in paths:
                    files.append(_create(p))
                while True:
                    data = src.read(CHUNK)
                    if not data:
                        break
                    for f in files:
                        f.write(data)
                    count(len(data) * len(files))
            finally:
                for f in files:
                    f.close()
    return kept


def unpack(archive, targets, count=lambda n: None):
    """Write each member `targets` names, {member: [paths]}, to its paths - most often one,
    several when an installer puts a file in two places - calling count(bytes written) as
    it goes, in this thread. A member with no paths is read into memory instead: returns
    {member: bytes} for those. Raises ArchiveError for a damaged archive and OSError for a
    file that can't be read or written."""
    k = kind(archive)
    with _reading(archive):
        if k == ".7z":
            return _unpack_7z(archive, targets, count)
        if k == ".zip":
            with zipfile.ZipFile(archive) as z:
                return _unpack_each(z, targets, count)
        rarfile = _rarfile()
        with rarfile.RarFile(archive) as z:
            return _unpack_each(z, targets, count)


def slashed(path):
    """A path in an archive or an installer "/"-separated, without "." parts or a slash at
    either end."""
    return "/".join(p for p in path.replace("\\", "/").split("/") if p not in ("", "."))


def safe(path):
    """Does a "/"-separated path stay inside the folder it is under?"""
    parts = path.split("/")
    return bool(path) and ".." not in parts and ":" not in parts[0]


def parse_xml(data):
    """An installer's XML: UTF-8 with or without a BOM, or UTF-16. Its <?xml?> line is
    dropped unread, since the encoding it names is not always the one the file is in."""
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = data.decode("utf-16")
    elif data[:3] == b"\xef\xbb\xbf":
        text = data[3:].decode("utf-8", "replace")
    elif len(data) > 1 and b"\x00" in data[:2]:
        text = data.decode("utf-16-le" if data[1:2] == b"\x00" else "utf-16-be")
    else:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("cp1252", "replace")
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", text.lstrip(chr(0xFEFF)))
    return ET.fromstring(text)


def _tag(e):
    """An element's name without its namespace, in lower case: FOMOD tools differ in both."""
    return e.tag.rsplit("}", 1)[-1].lower() if isinstance(e.tag, str) else ""


def _kids(e, name):
    return [c for c in e if _tag(c) == name] if e is not None else []


def _kid(e, name):
    k = _kids(e, name)
    return k[0] if k else None


def _attr(e, name, default=None):
    for k, v in e.attrib.items():
        if k.rsplit("}", 1)[-1].lower() == name.lower():
            return v
    return default


def _text(e):
    """An element's text, its lines ended the same way and trimmed."""
    if e is None or not e.text:
        return ""
    lines = e.text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    return "\n".join(l.rstrip() for l in lines).strip()


def _true(v):
    return (v or "").strip().lower() in ("true", "1")


def _ordered(elements, order):
    """Elements as the installer shows them: Explicit keeps the file's order; Ascending, the
    default, and Descending sort them by name."""
    order = (order or "Ascending").strip().lower()
    if order == "explicit":
        return list(elements)
    out = sorted(elements, key=lambda e: (_attr(e, "name") or "").casefold())
    return out[::-1] if order == "descending" else out


def _canon(value, names, default):
    """`value` spelled as in `names`, whatever its case; `default` when it isn't one."""
    for n in names:
        if (value or "").strip().lower() == n.lower():
            return n
    return default


def asks_more(root):
    """Does this installer depend on something this tool doesn't track - other mods, files,
    or flags set by earlier choices? An element left empty asks nothing."""
    return any(_tag(e) in ("moduledependencies", "conditionalfileinstalls", "visible",
                           "conditionflags", "dependencytype") and len(e)
               for e in root.iter())


# --- what an archive installs -------------------------------------------------------------

class Fomod(object):
    """A FOMOD installer this tool can follow.
    .name; .steps: [{"name", "groups": [{"name", "type", "plugins":
    [{"id", "name", "description", "type", "files": [...]}]}]}], type being the group's
    SelectExactlyOne / SelectAtMostOne / SelectAtLeastOne / SelectAny / SelectAll, and a
    plugin's type Required / Optional / Recommended / NotUsable / CouldBeUsable. Plugin
    ids are unique strings stable for one archive.

    A plugin's "files" are the (member, dest) pairs it installs, and "size" their bytes. Its
    id is where it stands in the file, "step.group.plugin", counted from 1: the order it is
    shown in can differ. Sources are read from the folder that holds fomod\\, in any case."""

    def __init__(self, root, base, members):
        self.name = _text(_kid(root, "modulename"))
        self.sizes = dict(members)
        base = slashed(base).casefold()
        self.index = {}              # a path under the base, casefolded: (member, path)
        for m, _ in members:
            p = slashed(m)
            if safe(p) and (not base or p.casefold().startswith(base + "/")):
                rel = p[len(base) + 1:] if base else p
                self.index[rel.casefold()] = (m, rel)
        self.order = {e: i for i, e in enumerate(root.iter())}
        self.entries = {}            # plugin id: its (priority, order, member, dest)
        self.missing = {}            # plugin id, or None for required files: sources not there
        # (priority, order, member, dest) installed whatever is chosen
        self.required, self.missing[None], _ = self.resolve(
            _kid(root, "requiredinstallfiles"), "Required")
        self.steps = []
        steps = _kid(root, "installsteps")
        doc = _kids(steps, "installstep")
        for step in _ordered(doc, _attr(steps, "order") if steps is not None else None):
            s = doc.index(step) + 1
            groups_el = _kid(step, "optionalfilegroups")
            gdoc = _kids(groups_el, "group")
            groups = []
            for group in _ordered(gdoc, _attr(groups_el, "order")
                                  if groups_el is not None else None):
                g = gdoc.index(group) + 1
                plugins_el = _kid(group, "plugins")
                pdoc = _kids(plugins_el, "plugin")
                plugins = []
                for plugin in _ordered(pdoc, _attr(plugins_el, "order")
                                       if plugins_el is not None else None):
                    pid = "%d.%d.%d" % (s, g, pdoc.index(plugin) + 1)
                    kind_el = _kid(_kid(plugin, "typedescriptor"), "type")
                    ptype = _canon(_attr(kind_el, "name") if kind_el is not None else None,
                                   PLUGIN_TYPES, "Optional")
                    entries, self.missing[pid], always = self.resolve(
                        _kid(plugin, "files"), ptype)
                    self.entries[pid] = entries
                    self.required += always
                    files = [(m, d) for _, _, m, d in entries]
                    plugins.append({"id": pid, "name": _attr(plugin, "name") or "",
                                    "description": _text(_kid(plugin, "description")),
                                    "type": ptype, "files": files,
                                    "size": sum(self.sizes.get(m, 0) for m, _ in files)})
                if plugins:
                    groups.append({"name": _attr(group, "name") or "",
                                   "type": _canon(_attr(group, "type"), GROUP_TYPES,
                                                  "SelectAny"),
                                   "plugins": plugins})
            self.steps.append({"name": _attr(step, "name") or "", "groups": groups})

    def resolve(self, files_el, ptype):
        """The <file>s and <folder>s under `files_el` against the archive: (entries, the
        sources it doesn't have, the entries installed whatever is chosen). A folder maps
        its whole subtree; a destination left out is the source's own path, and a folder's
        empty one is the mod folder itself."""
        entries, missing, always = [], [], []
        for e in files_el if files_el is not None else ():
            what = _tag(e)
            if what not in ("file", "folder"):
                continue
            src = slashed(_attr(e, "source") or "")
            raw = _attr(e, "destination")
            dest = slashed(raw) if raw is not None else src
            try:
                prio = int(_attr(e, "priority") or 0)
            except ValueError:
                prio = 0
            at = self.order[e]
            got = []
            if what == "file":
                hit = self.index.get(src.casefold())
                if not dest:
                    dest = src
                elif raw is not None and raw.rstrip()[-1:] in ("\\", "/"):
                    dest += "/" + src.rsplit("/", 1)[-1]    # a folder to put it in
                if hit:
                    got.append((prio, at, hit[0], dest))
            else:
                under = src.casefold() + "/" if src else ""
                for key, (m, rel) in self.index.items():
                    if key.startswith(under):
                        rest = rel[len(under):]
                        got.append((prio, at, m, dest + "/" + rest if dest else rest))
            got = [x for x in got if safe(x[3])]
            if not got:
                missing.append(src)
            entries += got
            if _true(_attr(e, "alwaysInstall")) or (_true(_attr(e, "installIfUsable"))
                                                    and ptype != "NotUsable"):
                always += got
        return entries, missing, always

    def plugins(self):
        return [p for s in self.steps for g in s["groups"] for p in g["plugins"]]

    def default(self):
        """The plugin ids chosen before the player changes anything: Required, Recommended,
        every plugin of a SelectAll group, and for a SelectExactlyOne or SelectAtLeastOne
        group with none of those, its first usable plugin. For a group like Colorful
        Autumn's "Options" (SelectAtLeastOne, all Optional) choose all of them - install
        everything, which is what a player who hasn't read the options wants."""
        out = set()
        for step in self.steps:
            for g in step["groups"]:
                usable = [p for p in g["plugins"] if p["type"] != "NotUsable"]
                if g["type"] == "SelectAll":
                    picks = usable
                else:
                    picks = ([p for p in usable if p["type"] == "Required"]
                             + [p for p in usable if p["type"] == "Recommended"])
                    if g["type"] in ("SelectExactlyOne", "SelectAtMostOne"):
                        picks = picks[:1]
                    if not picks and g["type"] == "SelectAtLeastOne":
                        picks = [p for p in usable if p["type"] == "Optional"] or usable[:1]
                    elif not picks and g["type"] == "SelectExactlyOne":
                        picks = usable[:1]
                out.update(p["id"] for p in picks)
        return out

    def problems(self, chosen):
        """What the group rules refuse in `chosen`, a sentence each: "Pick one of <group>.",
        "Pick at least one of <group>.", "Pick no more than one of <group>.", a NotUsable
        plugin chosen, a Required one left out. A group whose options install nothing, like
        an introduction, asks nothing. A chosen option naming files the archive doesn't
        have is refused too."""
        chosen, out = set(chosen or ()), []
        for step in self.steps:
            for g in step["groups"]:
                if not any(p["files"] or self.missing[p["id"]] for p in g["plugins"]):
                    continue
                n = sum(1 for p in g["plugins"] if p["id"] in chosen)
                if g["type"] == "SelectExactlyOne" and n != 1:
                    # translators: %s is the name of a group of options in a mod's installer
                    out.append(_("Pick one of %s.") % g["name"])
                elif g["type"] == "SelectAtMostOne" and n > 1:
                    out.append(_("Pick no more than one of %s.") % g["name"])
                elif g["type"] == "SelectAtLeastOne" and n < 1:
                    out.append(_("Pick at least one of %s.") % g["name"])
                for p in g["plugins"]:
                    if p["type"] == "NotUsable" and p["id"] in chosen:
                        out.append(_("%s can't be used here. Uncheck it.") % p["name"])
                    elif (p["type"] == "Required" or g["type"] == "SelectAll") \
                            and p["type"] != "NotUsable" and p["id"] not in chosen:
                        out.append(_("%s is required. Check it.") % p["name"])
        for src in self.missing[None]:
            out.append(_("Its installer always installs %s, which isn't in the archive.") % src)
        for p in self.plugins():
            if p["id"] in chosen:
                for src in self.missing[p["id"]]:
                    out.append(_("%(option)s installs %(file)s, which isn't in the archive.")
                               % {"option": p["name"], "file": src})
        return out

    def files(self, chosen):
        """[(member, dest)] for the plugins in `chosen` and the files installed whatever is
        chosen. Where two go to the same dest, the higher priority wins, and at the same
        priority the one later in the installer's file."""
        pool = list(self.required)
        for pid in sorted(set(chosen or ()) & set(self.entries)):
            pool += self.entries[pid]
        best = {}
        for prio, at, member, dest in pool:
            key = dest.casefold()
            if key not in best or (prio, at) >= best[key][:2]:
                best[key] = (prio, at, member, dest)
        return sorted(((m, d) for _, _, m, d in best.values()), key=lambda x: x[1].casefold())


class Package(object):
    """What an archive would install as a mod.

    .archive  the path; .name  a mod folder name to suggest: the FOMOD's moduleName when it
    has one, else the archive's name without its extension; .version  the FOMOD info.xml's
    <Version>, or None; .about  the FOMOD's description of itself if any (first plugin
    description of an info step is fine), else ""; .fomod  a Fomod, or None for an archive
    that is just files; .problem  None, or why it can't be installed here, in a sentence:
    an installer with conditions, flags or dependencies ("Its installer asks questions this
    tool can't follow. Install it with MO2 - Install a new mod from archive - then add it
    here."), an archive with no gamedata folder anywhere, or one with gamedata in more than
    one place and no FOMOD to choose.
    Raises ArchiveError when the archive can't be read at all, including a missing package
    (.7z needs py7zr: "py -m pip install py7zr"; .rar needs rarfile and UnRAR or 7-Zip).

    Nothing is unpacked but the installer's two XML files. .members lists the archive's
    files, [(member, size)]."""

    def __init__(self, archive):
        self.archive = archive
        self.name = folder_name(os.path.splitext(os.path.basename(archive))[0])
        self.version, self.about, self.fomod, self.problem = None, "", None, None
        self.plain = []
        try:
            self.members = listing(archive)
        except OSError as e:
            raise ArchiveError(_("Can't open %(archive)s: %(error)s.")
                               % {"archive": os.path.basename(archive),
                                  "error": (e.strerror or _said(e)).rstrip(".")})
        self.sizes = dict(self.members)
        paths = [(m, slashed(m)) for m, _ in self.members]
        fomod = sorted((p.count("/"), m, p) for m, p in paths
                       if re.search(r"(^|/)fomod/moduleconfig\.xml$", p, re.I))
        base = fomod[0][2][:-len("fomod/moduleconfig.xml")] if fomod else None
        infos = sorted((p.count("/"), m) for m, p in paths
                       if re.search(r"(^|/)fomod/info\.xml$", p, re.I)
                       and (base is None
                            or p[:-len("fomod/info.xml")].casefold() == base.casefold()))
        want = [x[1] for x in fomod[:1] + infos[:1]]
        try:
            data = unpack(archive, {m: [] for m in want}) if want else {}
        except OSError as e:
            raise ArchiveError(_("Can't read %(archive)s: %(error)s.")
                               % {"archive": os.path.basename(archive),
                                  "error": (e.strerror or _said(e)).rstrip(".")})
        if infos:
            self.read_info(data.get(infos[0][1], b""))
        if fomod:
            self.read_fomod(data.get(fomod[0][1], b""), fomod[0][2], base)
        elif any(re.search(r"(^|/)fomod/script\.(cs|vb|py)$", p, re.I) for _, p in paths):
            self.problem = _(FOLLOW)
        else:
            self.read_plain(paths)

    def read_info(self, data):
        """info.xml: the version, and the mod's description of itself."""
        try:
            info = parse_xml(data)
        except (ET.ParseError, ValueError):
            return
        self.version = _text(_kid(info, "version")) or None
        self.about = _text(_kid(info, "description"))

    def read_fomod(self, data, where, base):
        try:
            root = parse_xml(data)
        except (ET.ParseError, ValueError) as e:
            self.problem = (_("Its installer, %(file)s, can't be read: %(error)s.")
                            % {"file": where, "error": _said(e)})
            return
        self.name = folder_name(_text(_kid(root, "modulename"))) or self.name
        if asks_more(root):
            self.problem = _(FOLLOW)
            return
        self.fomod = Fomod(root, base.rstrip("/"), self.members)
        if not self.about:
            # an introduction: a step whose options install nothing, but say something
            for step in self.fomod.steps:
                plugins = [p for g in step["groups"] for p in g["plugins"]]
                if plugins and not any(p["files"] for p in plugins):
                    said = [p["description"] for p in plugins if p["description"]]
                    if said:
                        self.about = said[0]
                        break

    def read_plain(self, paths):
        """An archive that is just files installs everything under the folder that holds
        gamedata, when there is one such folder."""
        roots = {}
        for m, p in paths:
            parts = p.split("/")
            low = [x.casefold() for x in parts[:-1]]
            if "gamedata" in low:
                top = "/".join(parts[:low.index("gamedata")])
                roots.setdefault(top.casefold(), top)
        if not roots:
            self.problem = _("It has no gamedata folder, so it isn't a mod this tool can "
                             "install.")
            return
        if len(roots) > 1:
            # translators: the archive's top folder, in a list of the folders gamedata is in
            where = sorted(r or _("the top") for r in roots.values())
            # translators: "Install a new mod from archive" is an item of MO2's menu
            self.problem = (ngettext("It has gamedata folders in %(n)d places (%(places)s) and "
                                     "no installer to choose between them. Install it with "
                                     "MO2 - Install a new mod from archive - then add it here.",
                                     "It has gamedata folders in %(n)d places (%(places)s) and "
                                     "no installer to choose between them. Install it with "
                                     "MO2 - Install a new mod from archive - then add it here.",
                                     len(where))
                            % {"n": len(where),
                               "places": pgettext("between words in a list", ", ").join(
                                   where[:3] + (["..."] if where[3:] else []))})
            return
        top = next(iter(roots.values()))
        under = top.casefold() + "/" if top else ""
        plain = {}                  # one file per place, whatever its case: the later wins
        for m, p in paths:
            if p.casefold().startswith(under) and safe(p[len(under):]):
                plain[p[len(under):].casefold()] = (m, p[len(under):])
        self.plain = sorted(plain.values(), key=lambda x: x[1].casefold())

    def files(self, chosen=None):
        """[(member, dest)]: each archive member to install and where, as "/"-separated
        paths under the mod folder, like "gamedata/textures/ccon/CConV1.5.dds". `chosen` is a
        set of plugin ids for a FOMOD (None: its defaults); ignored for a plain archive,
        which installs everything under the folder that holds gamedata. Directories are
        not listed."""
        if self.problem:
            return []
        if self.fomod:
            return self.fomod.files(self.fomod.default() if chosen is None else chosen)
        return list(self.plain)

    def size(self, chosen=None):
        """Bytes it would install, uncompressed."""
        return sum(self.sizes.get(m, 0) for m, _ in self.files(chosen))


# --- installing ---------------------------------------------------------------------------

def _ini_value(s):
    """`s` as QSettings writes a value, which is how MO2 reads it back: backslashes and quotes
    escaped, and in quotes when it holds , ; or = or starts or ends with a space."""
    out = s.replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % out if re.search(r"[,;=]|^ | $", s) else out


def meta_ini(pkg):
    """The meta.ini MO2 writes for a mod it installs from an archive, as bytes: its fields,
    its order, CRLF line ends. installationFile is what lets found() tell it is installed."""
    lines = ["[General]", "gameName=stalkeranomaly", "modid=0",
             "version=" + _ini_value(pkg.version or ""), "newestVersion=", 'category="-1,"',
             "nexusFileStatus=1",
             "installationFile=" + _ini_value(os.path.abspath(pkg.archive).replace("\\", "/")),
             "repository=Nexus", "comments=", "notes=", "url=", "hasCustomURL=false",
             "converted=false", "validated=false", "", "[installedFiles]", "size=0", ""]
    return "\r\n".join(lines).encode("utf-8")


def _gb(n):
    return (_("%.1f GB") % (n / 2 ** 30) if n >= 2 ** 30 / 10
            else _("%d MB") % max(1, n // 2 ** 20))


class _Stop(BaseException):
    """An exception from install()'s progress, carried out through py7zr and the other
    libraries as it was: they turn an Exception they catch into one of their own."""


class _Ticker(object):
    """progress(done, total), now and then: at the start, every TICK seconds at most while
    bytes are written, and once at the end."""

    def __init__(self, progress, total):
        self.progress, self.total, self.done, self.at = progress, total, 0, None

    def __call__(self, n):
        self.done += n
        now = time.monotonic()
        if self.progress and (self.at is None or now - self.at >= TICK):
            self.at = now
            self.end()

    def end(self):
        if self.progress:
            try:
                self.progress(self.done, self.total)
            except BaseException as e:
                raise _Stop(e)


def _remove(path):
    """Delete a folder this install made, trying again while Windows still holds a file in
    it - an indexer or a virus scanner looking at what was just written."""
    for _ in range(10):
        try:
            shutil.rmtree(season.lp(path))
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.3)
    shutil.rmtree(season.lp(path), ignore_errors=True)


def _dest(dest):
    """A dest as a path under the mod folder, or ArchiveError for one that leaves it."""
    d = slashed(dest)
    if not safe(d):
        raise ArchiveError(_("%s isn't a place inside a mod's folder.") % dest)
    return d


def install(pkg, name, chosen=None, extra=(), progress=None, mods=None):
    """Install `pkg` as the mod folder mods\\<name> (mods defaults to season.MODS) and
    return its path. The files go into a temp folder beside it first and are renamed into
    place at the end, so a failure leaves no half-made mod; `extra`, [(loose path, dest)],
    is copied over the archive's files; a meta.ini is written the way MO2 writes one
    (gameName=stalkeranomaly, modid=0, version, installationFile = the archive's path,
    [installedFiles] size=0 is fine). Refuses, with ArchiveError: a folder of that name
    already there ("A mod called X is installed already. Pick another name."), a name MO2
    can't have (season._folder_problem), no files chosen, `pkg.problem`. progress(done,
    total) in bytes is called now and then while extracting - from the thread install runs
    in; the window calls install from a worker thread. MO2's mod list is not touched: MO2
    finds new folders by itself, and play.bat puts a seasonal mod in the list.

    Also refused: choices the FOMOD's rules refuse, and too little room on the drive. Each
    file unpacked is checked against the size the archive gives it. An exception raised by
    progress stops the install, leaving nothing behind, and comes out of install as it
    was raised: a way for the window to cancel."""
    mods = os.path.abspath(mods or season.MODS)
    if not isinstance(name, str) or not name.strip():
        raise ArchiveError(_("Give the mod a name."))
    if season._folder_problem(name):
        raise ArchiveError(_(BAD_NAME))
    if pkg.problem:
        raise ArchiveError(pkg.problem)
    final = os.path.join(mods, name)
    if os.path.lexists(final):
        raise ArchiveError(_(TAKEN) % name)
    if not os.path.isdir(mods):
        raise ArchiveError(_("There is no mods folder at %s.") % mods)
    if pkg.fomod:
        chosen = pkg.fomod.default() if chosen is None else set(chosen)
        refused = pkg.fomod.problems(chosen)
        if refused:
            raise ArchiveError(" ".join(refused))
    plan = pkg.files(chosen)
    if not plan:
        raise ArchiveError(_("Nothing is chosen to install. Check at least one option.")
                           if pkg.fomod else _("Nothing is chosen to install."))
    extra = [(src, _dest(dest)) for src, dest in extra]
    for src, __ in extra:
        if not os.path.isfile(src):
            raise ArchiveError(_("%s isn't there any more.") % src)
    total = pkg.size(chosen)
    need = total + sum(os.path.getsize(src) for src, _ in extra)
    free = shutil.disk_usage(mods).free
    if free < need + (64 << 20):
        raise ArchiveError(_("It needs %(need)s of room on the drive with the mods folder, "
                             "which has %(free)s free. Make room, then try again.")
                           % {"need": _gb(need), "free": _gb(free)})

    tmp = tempfile.mkdtemp(prefix=name + ".installing-", dir=mods)
    try:
        at = {m: i for i, (m, _) in enumerate(pkg.members)}
        targets = {}                # in the archive's order, which a solid archive needs
        for member, dest in sorted(plan, key=lambda x: at.get(x[0], 0)):
            targets.setdefault(member, []).append(os.path.join(tmp, *dest.split("/")))
        tick = _Ticker(progress, total)
        tick(0)
        try:
            unpack(pkg.archive, targets, tick)
        except ArchiveError as e:
            # translators: %s is why the archive couldn't be read, in a sentence or two
            raise ArchiveError(_("%s Nothing was installed.") % e)
        tick.end()
        for member, dest in plan:
            got = os.path.getsize(season.lp(os.path.join(tmp, *dest.split("/"))))
            if got != pkg.sizes.get(member):
                raise ArchiveError(ngettext(
                    "%(file)s came out of %(archive)s at %(got)d bytes, not %(want)d. Nothing "
                    "was installed.",
                    "%(file)s came out of %(archive)s at %(got)d bytes, not %(want)d. Nothing "
                    "was installed.", got)
                    % {"file": dest, "archive": os.path.basename(pkg.archive), "got": got,
                       "want": pkg.sizes.get(member)})
        for src, dest in extra:
            to = season.lp(os.path.join(tmp, *dest.split("/")))
            os.makedirs(os.path.dirname(to), exist_ok=True)
            shutil.copyfile(src, to)
        with open(os.path.join(tmp, "meta.ini"), "wb") as f:
            f.write(meta_ini(pkg))
        for attempt in range(10):
            try:
                os.rename(tmp, final)
                break
            except FileExistsError:
                raise ArchiveError(_(TAKEN) % name)
            except PermissionError as e:
                # Windows refuses while another program has a file in the folder open
                if attempt == 9:
                    raise ArchiveError(_("Couldn't rename the new mod's folder to %(mod)s: "
                                         "%(error)s. Nothing was installed.")
                                       % {"mod": name,
                                          "error": (e.strerror or _said(e)).rstrip(".")})
                time.sleep(0.3)
    except BaseException as e:
        _remove(tmp)
        if isinstance(e, _Stop):
            raise e.args[0] from None
        if isinstance(e, ArchiveError) or not isinstance(e, Exception):
            raise
        if isinstance(e, OSError):
            what = e.filename if isinstance(e.filename, str) else ""
            what = what[4:] if what.startswith("\\\\?\\") else what
            said = {"file": what, "mod": name, "error": (e.strerror or _said(e)).rstrip(".")}
            if what.startswith(tmp):
                said["file"] = what[len(tmp) + 1:]
                raise ArchiveError(_("Couldn't write %(file)s: %(error)s. Nothing was "
                                     "installed.") % said)
            if what:
                raise ArchiveError(_("Couldn't read %(file)s: %(error)s. Nothing was "
                                     "installed.") % said)
            raise ArchiveError(_("Couldn't install %(mod)s: %(error)s. Nothing was "
                                 "installed.") % said)
        raise ArchiveError(_("Couldn't install %(mod)s: %(error)s. Nothing was installed.")
                           % {"mod": name, "error": _said(e)})
    return final
