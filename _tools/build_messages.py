#!/usr/bin/env python3
"""Collect the tools' strings for translators, and keep the translations in step with them.

  python _tools/build_messages.py              write lang/messages.pot, and bring every
                                               lang/<code>.po up to date with it
  python _tools/build_messages.py --check      fail when messages.pot or a .po is out of
                                               date, a translation doesn't fit its English,
                                               or a string given to _() isn't written out
  python _tools/build_messages.py --unmarked [file.py ...]
                                               words a player may see that no _() marks: a
                                               list to look through, not a rule

The strings are what the tools pass to _(), N_(), ngettext(), pgettext() and npgettext()
(lang.py). A .po keeps what is translated in it; a string that is new comes in empty, and one
the tools no longer have moves to the end as obsolete (#~), for the translator to reuse. A
comment starting "# translators:" on the line above a call goes to the translator with it.
docs/TRANSLATING.md says how to translate.
"""
import ast
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import lang                                                     # noqa: E402

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# the tools a player runs, in the order their strings go in the file
SOURCES = ("lang.py", "season.py", "config_edit.py", "configure.py", "guide.py",
           "installer.py", "mod_install.py", "fetch_weather.py")
POT = os.path.join(lang.FOLDER, "messages.pot")
CALLS = {"_": ("msgid",), "N_": ("msgid",), "pgettext": ("ctx", "msgid"),
         "ngettext": ("msgid", "plural"), "npgettext": ("ctx", "msgid", "plural")}
HEADER = ("Project-Id-Version: Seasons of the Zone\n"
          "MIME-Version: 1.0\n"
          "Content-Type: text/plain; charset=UTF-8\n"
          "Content-Transfer-Encoding: 8bit\n")
PLURALS = {"en": "nplurals=2; plural=(n != 1);",
           "ru": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
                 "(n%100<10 || n%100>=20) ? 1 : 2);",
           "uk": "nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
                 "(n%100<10 || n%100>=20) ? 1 : 2);"}


def called(node):
    """The name of the lang call a node makes - _, pgettext and so on - or None."""
    f = node.func
    if isinstance(f, ast.Name) and f.id in CALLS:
        return f.id
    if (isinstance(f, ast.Attribute) and f.attr in CALLS and isinstance(f.value, ast.Name)
            and f.value.id == "lang"):
        return f.attr
    return None


def extract(names=SOURCES):
    """(entries, problems). entries: {(ctx, msgid): {"plural", "files", "notes"}}, in the
    order they come; problems: sentences for calls that can't be collected."""
    entries, problems = {}, []
    for name in names:
        path = os.path.join(HERE, name)
        text = io.open(path, encoding="utf-8").read()
        lines = text.split("\n")
        tree = ast.parse(text, name)
        found = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kind = called(node)
            if not kind:
                continue
            want = CALLS[kind]
            args = node.args[:len(want)]
            if len(args) < len(want) or not all(
                    isinstance(a, ast.Constant) and isinstance(a.value, str) for a in args):
                problems.append("%s:%d: %s() takes its strings written out in quotes, whole - "
                                "values go in after, with %%" % (name, node.lineno, kind))
                continue
            found.append((node.lineno, node.col_offset, dict(zip(want, (a.value for a in args)))))
        for lineno, _col, v in sorted(found, key=lambda t: (t[0], t[1])):
            key = (v.get("ctx"), v["msgid"])
            if not v["msgid"]:
                problems.append("%s:%d: an empty string can't be translated" % (name, lineno))
                continue
            e = entries.setdefault(key, {"plural": v.get("plural"), "files": [],
                                         "notes": []})
            if e["plural"] != v.get("plural"):
                problems.append("%s:%d: %r is used with two different plurals, or with one and "
                                "without" % (name, lineno, v["msgid"]))
            if name not in e["files"]:
                e["files"].append(name)
            above = lines[lineno - 2].strip() if lineno >= 2 else ""
            if above.lower().startswith("# translators:"):
                note = above[len("# translators:"):].strip()
                if note not in e["notes"]:
                    e["notes"].append(note)
    return entries, problems


def shadowed(names=SOURCES):
    """Sentences for each scope that calls _() and also sets a variable called _: there it
    is no longer the function, and the call fails or does nothing useful."""
    out = []
    for name in names:
        tree = ast.parse(io.open(os.path.join(HERE, name), encoding="utf-8").read(), name)
        scopes = [tree] + [n for n in ast.walk(tree)
                           if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        for scope in scopes:
            sets, calls = [], []
            todo = list(ast.iter_child_nodes(scope))
            while todo:
                node = todo.pop()
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef,
                                     ast.Lambda, ast.ListComp, ast.SetComp, ast.DictComp,
                                     ast.GeneratorExp)):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                                         ast.ClassDef)) and node.name == "_":
                        sets.append(node.lineno)
                    continue                    # a scope of its own
                if isinstance(node, ast.Name) and node.id == "_" and isinstance(
                        node.ctx, (ast.Store, ast.Del)):
                    sets.append(node.lineno)
                if isinstance(node, ast.arg) and node.arg == "_":
                    sets.append(node.lineno)
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == "_"):
                    calls.append(node.lineno)
                todo.extend(ast.iter_child_nodes(node))
            if isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
                a = scope.args
                for arg in a.args + a.kwonlyargs + [x for x in (a.vararg, a.kwarg) if x]:
                    if arg.arg == "_":
                        sets.append(scope.lineno)
            if sets and calls:
                out.append("%s:%d: _ is set here and _() is called in the same %s; name the "
                           "variable something else" % (
                               name, min(sets), "function" if scope is not tree else "file"))
    return out


def quoted(s):
    """A string as a .po file writes it: escaped, split after each line break."""
    esc = (s.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")
           .replace("\r", "\\r"))
    parts = esc.split("\n")
    if len(parts) == 1:
        return '"%s"' % parts[0]
    pieces = [p + "\\n" for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])
    return '""\n' + "\n".join('"%s"' % p for p in pieces)


def entry_text(ctx, msgid, plural, strs, flags=(), files=(), notes=(), obsolete=False):
    lines = ["#. " + n for n in notes]
    if files:
        lines.append("#: " + " ".join(files))
    if flags:
        lines.append("#, " + ", ".join(flags))
    body = []
    if ctx is not None:
        body.append("msgctxt " + quoted(ctx))
    body.append("msgid " + quoted(msgid))
    if plural is not None:
        body.append("msgid_plural " + quoted(plural))
        body += ["msgstr[%d] %s" % (i, quoted(s)) for i, s in enumerate(strs)]
    else:
        body.append("msgstr " + quoted(strs[0] if strs else ""))
    if obsolete:
        body = ["#~ " + l for b in body for l in b.split("\n")]
    return "\n".join(lines + body)


def flags_of(msgid, plural):
    return (["python-format"] if any(
        lang.holders(t) != (frozenset(), ()) or "%%" in t
        for t in (msgid, plural or "")) else [])


def pot_text(entries):
    out = ["# Seasons of the Zone: the words of its tools, for translators.",
           "# build_messages.py writes this file; don't edit it. A translation is lang/<code>.po;",
           "# docs/TRANSLATING.md says how.",
           entry_text(None, "", None, [HEADER + "Plural-Forms: " + PLURALS["en"] + "\n"]), ""]
    for (ctx, msgid), e in entries.items():
        out += [entry_text(ctx, msgid, e["plural"], ["", ""] if e["plural"] else [""],
                           flags_of(msgid, e["plural"]), e["files"], e["notes"]), ""]
    return "\n".join(out)


def po_text(path, entries):
    """A .po file brought up to date with `entries`: its header and what is translated in
    it kept, new strings empty, strings gone kept at the end as obsolete."""
    have = lang.read_po(path)
    head = next((e for e in have if e[1] == "" and e[0] is None and not e[5]), None)
    header = head[3][0] if head and head[3] else HEADER
    m = re.search(r"nplurals\s*=\s*(\d+)", header)
    nplurals = int(m.group(1)) if m else 2
    old = {(e[0], e[1]): e for e in have if e[1] != "" or e[0] is not None}
    top = [l.rstrip("\n") for l in io.open(path, encoding="utf-8-sig")]
    comments = []
    for l in top:
        if l.startswith("# ") or l == "#":
            comments.append(l)
        else:
            break
    out = comments + [entry_text(None, "", None, [header]), ""]
    for key, e in entries.items():
        ctx, msgid = key
        prev = old.pop(key, None)
        strs = list(prev[3]) if prev else []
        flags = flags_of(msgid, e["plural"])
        if prev and "fuzzy" in prev[4]:
            flags = ["fuzzy"] + flags
        if e["plural"] is not None:
            strs = (strs + [""] * nplurals)[:nplurals]
        else:
            strs = strs[:1] or [""]
        out += [entry_text(ctx, msgid, e["plural"], strs, flags, e["files"], e["notes"]), ""]
    for (ctx, msgid), e in old.items():
        if any(e[3]):
            out += [entry_text(ctx, msgid, e[2], e[3], obsolete=True), ""]
    return "\n".join(out)


def po_files():
    try:
        return sorted(os.path.join(lang.FOLDER, f) for f in os.listdir(lang.FOLDER)
                      if f.endswith(".po"))
    except OSError:
        return []


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def fit_problems(path):
    """Sentences for each translation in a .po that its English can't be filled into."""
    out = []
    try:
        entries = lang.read_po(path)
        cat = lang.Catalog(os.path.basename(path)[:-3], entries)
    except ValueError as e:
        return ["%s: %s" % (os.path.basename(path), e)]
    for ctx, msgid in cat.dropped:
        out.append("%s: the translation of %r has other placeholders than the English, so "
                   "it isn't used" % (os.path.basename(path), msgid))
    return out


def unmarked(names):
    """(file, line, text) for string literals that read like words a player sees and that
    no lang call marks. A help for finding them; it can't know every case."""
    skip_calls = {"join", "startswith", "endswith", "split", "rsplit", "replace", "strip",
                  "rstrip", "lstrip", "get", "pop", "setdefault", "getattr", "setattr",
                  "hasattr", "isinstance", "open", "compile", "match", "search", "sub",
                  "findall", "finditer", "fullmatch", "encode", "decode", "index", "count",
                  "add_argument", "add_parser", "bind", "register", "configure_style",
                  "Style", "run", "Popen", "check_output", "environ", "trace_add",
                  "event_generate", "after", "attributes", "geometry", "cget"}
    skip_kw = {"anchor", "side", "sticky", "fill", "style", "state", "foreground",
               "background", "cursor", "orient", "mode", "justify", "relief", "font",
               "textvariable", "variable", "value", "values", "default", "encoding",
               "errors", "newline", "metavar", "dest", "choices", "action", "compound",
               "selectmode", "show", "takefocus", "exportselection", "padding"}
    out = []
    for name in names:
        path = os.path.join(HERE, name) if not os.path.isabs(name) else name
        text = io.open(path, encoding="utf-8").read()
        tree = ast.parse(text, name)
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        docs = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef,
                                 ast.AsyncFunctionDef)) and node.body:
                first = node.body[0]
                if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                    docs.add(first.value)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
                continue
            s = node.value
            if node in docs or not re.search(r"[A-Za-z]{2,}", s):
                continue
            words = re.findall(r"[A-Za-z']+", s)
            if not (len(words) >= 2 and " " in s.strip()) and not re.search(r"[.?!:]\s*$", s):
                continue
            if re.match(r"^\s*[\w.\\/:-]+\s*$", s) or s.startswith(("#", "%s", "http")):
                continue
            p, marked, ignored = parents.get(node), False, False
            while p is not None:
                if isinstance(p, ast.Call):
                    if called(p):
                        marked = True
                        break
                    f = p.func
                    fname = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    if fname in skip_calls:
                        ignored = True
                        break
                if isinstance(p, ast.keyword) and p.arg in skip_kw:
                    ignored = True
                    break
                if isinstance(p, (ast.Subscript, ast.Compare)):
                    ignored = True
                    break
                if isinstance(p, ast.Dict) and node in p.keys:
                    ignored = True
                    break
                if isinstance(p, (ast.FunctionDef, ast.ClassDef, ast.Module)):
                    break
                p = parents.get(p)
            if not marked and not ignored:
                out.append((name, node.lineno, s))
    return out


def main(argv):
    if argv[:1] == ["--unmarked"]:
        hits = unmarked(argv[1:] or SOURCES)
        for f, line, s in hits:
            print("%s:%d: %s" % (f, line, s.replace("\n", "\\n")[:110]))
        print("%d string(s) that read like words a player sees and aren't marked" % len(hits))
        return 0
    entries, problems = extract()
    problems += shadowed()
    pot = pot_text(entries)
    if argv[:1] == ["--check"]:
        try:
            on_disk = io.open(POT, encoding="utf-8").read()
        except OSError:
            on_disk = None
        if on_disk != pot:
            problems.append("lang/messages.pot is out of date with the tools. Run "
                            "python _tools/build_messages.py")
        for path in po_files():
            try:
                if io.open(path, encoding="utf-8-sig").read() != po_text(path, entries):
                    problems.append("lang/%s is out of date with the tools. Run python "
                                    "_tools/build_messages.py" % os.path.basename(path))
            except ValueError as e:
                problems.append("lang/%s: %s" % (os.path.basename(path), e))
            problems += fit_problems(path)
        for p in problems:
            print("  " + p)
        print("%d string(s) for translators; %s" % (
            len(entries), "%d problem(s)" % len(problems) if problems else "everything in step"))
        return 1 if problems else 0
    for p in problems:
        print("  " + p)
    if problems:
        print("Nothing written: fix those first.")
        return 1
    os.makedirs(lang.FOLDER, exist_ok=True)
    write(POT, pot)
    for path in po_files():
        write(path, po_text(path, entries))
        cat = lang.Catalog(os.path.basename(path)[:-3], lang.read_po(path))
        print("  %-10s %d of %d translated" % (os.path.basename(path), len(cat), len(entries)))
    print("%d string(s) in lang/messages.pot" % len(entries))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
