"""Catch a local read before it is declared.

The forecast page picked its barometer image from `w.now` nine lines above the
`local w = d.weather` that creates it. Lua does not complain: an undeclared name is a
global read, X-Ray gives each script its own globals table, so `w` was simply nil. The
gauge silently fell through to its default and drew the wrong weather. Nothing failed,
nothing logged, and the only way to notice was to look at the needle and know it was
wrong.

The check is deliberately narrow, because a full scope analysis of Lua is not worth
writing here: within one top-level function body, flag a name that is READ on a line
above the `local <name>` that declares it. That is the exact shape of the bug, and it has
no false positives on straight-line code.

  python _tools/check_locals.py
  python _tools/check_locals.py --selftest
"""
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

FUNC = re.compile(r"^function\s+[\w:.]+\s*\(")
LOCAL = re.compile(r"^\s*local\s+(?!function\b)([\w\s,]+?)\s*(?:=|$)")
WORD = re.compile(r"[A-Za-z_]\w*")
# Parameters of a nested function are declarations too, scoped to that function. Missing
# this made the check flag `local function band(left, full)` against a `local full`
# declared later in the enclosing body - two different names that never meet.
PARAMS = re.compile(r"\bfunction\b[^(]*\(([^)]*)\)")
# `for i, b in ipairs(t)` and `for i = 1, n` declare their variables too. Without this,
# every loop variable read as an undeclared use of whatever was declared later under the
# same name - which is most short names in most files.
FORVARS = re.compile(r"^\s*for\s+([\w\s,]+?)\s+in\s|^\s*for\s+(\w+)\s*=")


def strip_code(line):
    """Whittle a line down to the names it actually READS.

    Comments and string literals are not reads. Neither are field or method names:
    `md(b.m, b.d)` reads `b`, not `m` and `d`, and mistaking those for variables is what
    the first version of this check did on every table it saw.
    """
    line = re.sub(r"--.*$", "", line)
    line = re.sub(r'"[^"]*"', '""', line)
    line = re.sub(r"'[^']*'", "''", line)
    line = re.sub(r"[.:]\s*\w+", "", line)          # b.m, obj:Method
    # A table-constructor key is not a read: in `key = b.season,` only `b` is read. The
    # trailing comma is what separates an entry from an assignment, and it is the only
    # signal available without parsing - `local a, z = f()` has no trailing comma and
    # keeps its names, which an earlier and broader version of this rule destroyed.
    if line.rstrip().endswith(","):
        line = re.sub(r"^\s*\w+\s*=", "", line)
    return line


def functions(lines):
    """(start, end) for each top-level `function ... end`, by column-0 anchoring."""
    out, start = [], None
    for i, raw in enumerate(lines):
        if FUNC.match(raw):
            start = i
        elif start is not None and raw.rstrip() == "end":
            out.append((start, i))
            start = None
    return out


def scan_file(path):
    lines = io.open(path, encoding="utf-8").read().split("\n")
    problems = []

    for a, b in functions(lines):
        body = lines[a:b + 1]
        declared = {}                       # name -> offset of its `local`
        for off, raw in enumerate(body):
            code = strip_code(raw)
            m = LOCAL.match(code)
            if m:
                for name in m.group(1).split(","):
                    name = name.strip()
                    if name and name not in declared:
                        declared[name] = off
            fm = FORVARS.match(code)
            if fm:
                for name in (fm.group(1) or fm.group(2) or "").split(","):
                    name = name.strip()
                    if name and name not in declared:
                        declared[name] = off
            pm = PARAMS.search(raw)
            if pm:
                for name in pm.group(1).split(","):
                    name = name.strip()
                    if name and name != "..." and name not in declared:
                        declared[name] = off

        for name, decl_off in declared.items():
            for off in range(decl_off):
                code = strip_code(body[off])
                # A declaration line is exactly where this bug lives - `local head = w`
                # above `local w` - so the line is not skipped. Only the names being
                # declared on the left are; the right-hand side is a read like any other.
                m2 = LOCAL.match(code)
                if m2:
                    code = code.split("=", 1)[1] if "=" in code else ""
                if name in WORD.findall(code):
                    problems.append(
                        "%s:%d: reads `%s` %d line(s) before `local %s` on line %d - "
                        "that read is a nil global, not the local"
                        % (os.path.basename(path), a + off + 1, name,
                           decl_off - off, name, a + decl_off + 1))
                    break
    return problems


SELFTEST_BAD = """function Page:Fill()
    local head = w and w.now
    local w = d.weather
    return head
end
"""

SELFTEST_OK = """function Page:Fill()
    local w = d.weather
    local head = w and w.now
    -- w mentioned in a comment above would not count
    return head
end
"""

SELFTEST_SHADOW = """function Page:A()
    local w = 1
    return w
end

function Page:B()
    local head = 2
    local w = 3
    return head + w
end
"""


def selftest():
    import tempfile
    bad = 0
    for label, src, want in (("use before local", SELFTEST_BAD, True),
                             ("declared first", SELFTEST_OK, False),
                             ("separate functions", SELFTEST_SHADOW, False)):
        fd, p = tempfile.mkstemp(suffix=".script")
        os.close(fd)
        io.open(p, "w", encoding="utf-8").write(src)
        got = bool(scan_file(p))
        os.unlink(p)
        ok = got == want
        bad += 0 if ok else 1
        print("  %s  %-22s %s" % ("PASS" if ok else "FAIL", label,
                                  "flagged" if got else "accepted"))
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("  self-test: a read above its own `local` must be flagged")
        sys.exit(1 if selftest() else 0)

    problems, n = [], 0
    for p in sorted(glob.glob(os.path.join(SCRIPTS, "*.script"))):
        n += 1
        problems += scan_file(p)
    if problems:
        for pr in problems:
            print("  FAIL  %s" % pr)
        print("\n  %d script(s) checked, %d problem(s)" % (n, len(problems)))
        sys.exit(1)
    print("  %d script(s) checked, no local is read before it exists" % n)
