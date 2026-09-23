"""Catch invented engine API before it reaches a player.

Written after a crash I caused twice over. ui_seasons_forecast.script called
`widget:GetWndRect()`. There is no such method in this engine - it appears nowhere in
~16,000 lines of working scripts - but it reads exactly like something that should exist,
it passed a Lua syntax check, and it passed a Lua-runtime test because the harness stubs
the widget layer. The first player click was a hard FATAL.

A missing method is indistinguishable from a real one until it runs, so the check is a
corpus check: every method this mod calls on an engine object must be a method some OTHER
installed mod also calls. Modders collectively exercise the whole binding; a name that
appears in our files and nowhere else is a name I made up.

This wants the live GAMMA install, which is where the corpus is. Point INSTALL at it, or
pass --install.

  python _tools/check_engine_api.py --install "D:/GAMMA"
  python _tools/check_engine_api.py --selftest
"""
import argparse
import collections
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OURS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

# Methods called on `something:Name(`. Lua's own string/table methods are not engine
# API, and neither is anything we define on our own classes.
CALL = re.compile(r"[\w\)\]]\s*:\s*([A-Z]\w+)\s*\(")

# defined on our own classes: `function SeasonsPDA:Row(` etc.
OWN = re.compile(r"function\s+\w+\s*:\s*(\w+)\s*\(")


def methods_in(text):
    return set(CALL.findall(text))


def scan_ours():
    used, defined = collections.defaultdict(set), set()
    for p in sorted(glob.glob(os.path.join(OURS, "*.script"))):
        t = io.open(p, encoding="utf-8").read()
        t = re.sub(r"--\[\[.*?\]\]", "", t, flags=re.S)
        t = re.sub(r"(?m)^\s*--.*$", "", t)          # comments are not calls
        defined |= set(OWN.findall(t))
        for m in methods_in(t):
            used[m].add(os.path.basename(p))
    return used, defined


def scan_corpus(install):
    """Every method name called anywhere else in the install."""
    seen = collections.Counter()
    pat = os.path.join(install, "mods", "*", "gamedata", "scripts", "*.script")
    files = 0
    for p in glob.glob(pat):
        if "Seasons of the Zone" in p:
            continue
        try:
            t = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        files += 1
        for m in methods_in(t):
            seen[m] += 1
    return seen, files


def selftest():
    """The matcher must see a call, and must not see a comment or a definition."""
    cases = [
        ("a plain call", "local r = self.gauge:GetWndRect()", "GetWndRect", True),
        ("chained call", "x = foo():GetHeight()", "GetHeight", True),
        ("indexed call", "t[1]:SetText('a')", "SetText", True),
        # the matcher DOES see this one - "SeasonsPDA:Row(" is a colon call as far as
        # the regex is concerned. It is the OWN filter in main() that excludes it, so
        # that is what the next case actually tests.
        ("our own method", "function SeasonsPDA:Row(style)", "Row", True),
    ]
    bad = 0
    for label, src, name, want in cases:
        got = name in methods_in(src)
        ok = got == want
        bad += 0 if ok else 1
        print("  %s  %-18s %s" % ("PASS" if ok else "FAIL", label,
                                  "seen" if got else "not seen"))
    # a method we define on our own class must be excluded by the OWN filter
    src = "function SeasonsPDA:Row(style)\n  self.scroll:Row()\n"
    ok = "Row" in OWN.findall(src)
    bad += 0 if ok else 1
    print("  %s  %-18s %s" % ("PASS" if ok else "FAIL", "own filter",
                              "excluded" if ok else "NOT excluded"))

    # and a comment must be stripped before matching
    t = re.sub(r"(?m)^\s*--.*$", "", "-- self.x:MadeUpThing()\nlocal a = 1\n")
    ok = "MadeUpThing" not in methods_in(t)
    bad += 0 if ok else 1
    print("  %s  %-18s %s" % ("PASS" if ok else "FAIL", "comment ignored",
                              "stripped" if ok else "still matched"))
    return bad


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=os.environ.get("GAMMA_INSTALL", "D:/GAMMA"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        print("  self-test: the matcher must find calls and ignore the rest")
        sys.exit(1 if selftest() else 0)

    if not os.path.isdir(os.path.join(a.install, "mods")):
        print("  SKIP  no GAMMA install at %s - pass --install" % a.install)
        return 0

    used, own = scan_ours()
    corpus, files = scan_corpus(a.install)
    print("  corpus: %d method names across %d scripts" % (len(corpus), files))

    lonely = []
    for m in sorted(used):
        if m in own:                       # our own class methods
            continue
        if corpus.get(m, 0) == 0:
            lonely.append((m, sorted(used[m])))

    if lonely:
        for m, where in lonely:
            print("  FAIL  %s() is called in %s and NOWHERE else in the install"
                  % (m, ", ".join(where)))
        print("\n  %d name(s) no other mod uses - check each against the real bindings"
              % len(lonely))
        return 1

    print("  every engine method this mod calls is used by other mods too")
    return 0


if __name__ == "__main__":
    sys.exit(main())
