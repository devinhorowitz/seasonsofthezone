"""Fill test_pda.py's copy of the game's DXML from an install: Modded Exes' slaxml.script and
dxml_core.script, unpacked from its gamedata db0 with Anomaly's own tools/converter.exe, and Mod
App Creator's ui/pda_16.xml, the bar most players have. They are those mods' files, not this
repository's: the copy goes to _tools/_staging/dxml, which git ignores and no release ships.
test_pda.py runs its tab bar case under them when they are there, or in the folder SOTZ_DXML
names, and skips it, saying so, when they are not.

    python _tools/fetch_dxml.py <MO2 folder>                  # into _tools/_staging/dxml
    python _tools/fetch_dxml.py <MO2 folder> --out <folder>   # anywhere else
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

import lang

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "_staging", "dxml")
SCRIPTS = ("slaxml.script", "dxml_core.script")
BAR = os.path.join("Mod App Creator", "gamedata", "configs", "ui", "pda_16.xml")


def db0_of(mo2, game):
    """Modded Exes' gamedata db0: in one of MO2's mods, else in the game's own db\\mods"""
    found = glob.glob(os.path.join(mo2, "mods", "*", "db", "mods", "*modded_exes*.db0"))
    if game:
        found += glob.glob(os.path.join(game, "db", "mods", "*modded_exes*.db0"))
    return sorted(found)[0] if found else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("mo2", help="the MO2 folder of an install with Modded Exes and Mod App Creator")
    ap.add_argument("--out", default=CACHE, help="where the three files go (default: %(default)s)")
    a = ap.parse_args()
    game = lang.mo2_setting(a.mo2, "gamePath", None, None)
    converter = os.path.join(game, "tools", "converter.exe") if game else None
    db0 = db0_of(a.mo2, game)
    bar = os.path.join(a.mo2, "mods", BAR)
    missing = [what for what, path in (("Anomaly's tools\\converter.exe", converter),
                                       ("Modded Exes' gamedata .db0", db0),
                                       ("Mod App Creator's pda_16.xml", bar))
               if not (path and os.path.isfile(path))]
    if missing:
        raise SystemExit("  not found under %s: %s" % (a.mo2, ", ".join(missing)))
    os.makedirs(a.out, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="unpack_", dir=a.out)
    try:
        r = subprocess.run([converter, "-unpack", "-xdb", db0, "-dir", tmp, "-flt", "scripts\\"],
                           capture_output=True, text=True, cwd=os.path.dirname(converter))
        for f in SCRIPTS:
            got = os.path.join(tmp, "scripts", f)
            if not os.path.isfile(got):
                raise SystemExit("  %s is not in %s:\n%s" % (f, db0, r.stdout + r.stderr))
            shutil.copyfile(got, os.path.join(a.out, f))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    shutil.copyfile(bar, os.path.join(a.out, "pda_16.xml"))
    print("  from %s\n   and %s:" % (db0, bar))
    for f in SCRIPTS + ("pda_16.xml",):
        print("    %s" % os.path.join(a.out, f))
    return 0


if __name__ == "__main__":
    sys.exit(main())
