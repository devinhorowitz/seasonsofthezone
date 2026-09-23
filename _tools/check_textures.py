"""Every texture this mod names must actually resolve.

Written after the launcher tiles shipped empty. The name was right, the .dds was on disk,
and nothing drew: Init3tButton is a four-state button, so the engine appends _e/_h/_t/_d
and looks THOSE up as declared ids. A loose file satisfies none of them and the engine
draws nothing rather than complaining in a way anyone would notice.

So a texture name resolves only if it is either

  * declared as an <texture id="..."> in one of this mod's textures_descr files, or
  * present as textures/<name>.dds, which is the path fallback InitTexture uses.

and a name used by a 3t BUTTON needs all four suffixed ids declared, not the bare name.

Names built by concatenation (`"sotz_gauge_" .. cycle`) cannot be read off the source, so
the families are listed here explicitly and checked for completeness. That list is the
thing to update when a new family appears.

  python _tools/check_textures.py
  python _tools/check_textures.py --selftest
"""
import argparse
import glob
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata")
TEX = os.path.join(MOD, "textures")
DESCR = os.path.join(MOD, "configs", "ui", "textures_descr")
UI = os.path.join(MOD, "configs", "ui")
SCRIPTS = os.path.join(MOD, "scripts")

# Names the scripts build at runtime, so no regex can see them. Each entry is
# (prefix, [suffixes], is_button).
FAMILIES = [
    ("sotz_needle_", ["clear", "partly", "cloudy", "foggy", "rain", "storm"], False),
    ("sotz_wx_", ["clear", "partly", "cloudy", "foggy", "rain", "storm",
                  "frost", "arrow"], False),
    ("sotz_app_year_", ["spring", "summer", "autumn", "winter", "winter_snow",
                        "late_winter"], True),
    ("ui_season_hdr_", ["spring", "summer", "autumn", "winter", "winter_snow",
                        "late_winter"], False),
    ("ui_seasons_dial_", ["%02d" % i for i in range(32)], False),
]

BUTTON_SUFFIXES = ("_e", "_h", "_t", "_d")

# Functions that pick a texture name for InitTexture to use, so the call itself carries a
# variable. Every name they return is checked. eco_emblem() picks GAMMA's shield when GAMMA
# UI's faction sheet is installed and base Anomaly's icon when it is not.
PICKERS = ["eco_emblem"]

# Declared by base Anomaly itself, inside its packed configs, where this check cannot look.
BASE_GAME = {
    "ui_inGame2_PD_Ecologist": "configs/ui/textures_descr/ui_actor_newsmanager_icons.xml",
}


def declared_ids():
    ids = set()
    for p in glob.glob(os.path.join(DESCR, "*.xml")):
        ids |= set(re.findall(r'<texture[^>]*id="([^"]+)"',
                              io.open(p, encoding="utf-8").read()))
    return ids


def foreign_ids(install):
    """id -> the mod that declares it, for every OTHER mod in the install.

    Borrowing is legitimate - the ecologists' own faction banner is theirs to lend - but
    it is a dependency, so it gets named. If a GAMMA update ever drops the id, this says
    so here rather than leaving a blank panel in the game.
    """
    out = {}
    if not install:
        return out
    pat = os.path.join(install, "mods", "*", "gamedata", "configs", "ui",
                       "textures_descr", "*.xml")
    for p in glob.glob(pat):
        p = p.replace("\\", "/")
        if "Seasons of the Zone" in p:
            continue
        owner = p.split("/mods/")[-1].split("/")[0]
        try:
            body = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for i in re.findall(r'<texture[^>]*id="([^"]+)"', body):
            out.setdefault(i, owner)
    return out


def on_disk():
    if not os.path.isdir(TEX):
        return set()
    return {f[:-4] for f in os.listdir(TEX) if f.lower().endswith(".dds")}


def literal_uses():
    """(name, is_button) for every texture named literally in a script or ui xml.

    Two things this has to get right, because getting either wrong makes the check cry
    wolf and a check nobody trusts is worse than no check:

      * InitTexture on a widget that came from Init3tButton is a FOUR-STATE use, even
        though the call looks identical to the one on a plain static. The widget the call
        is made on is what decides, so the Init3tButton assignments are collected first.
      * a literal that is immediately concatenated - "sotz_gauge_" .. cycle - is a prefix,
        not a name. Only the family list can say what those expand to.
    """
    out = set()
    for p in glob.glob(os.path.join(SCRIPTS, "*.script")):
        t = io.open(p, encoding="utf-8").read()
        t = re.sub(r"(?m)^\s*--.*$", "", t)
        buttons = set(re.findall(r"self\.(\w+)\s*=\s*\w+:Init3tButton\(", t))
        for m in re.finditer(r'(?:self\.(\w+))?:InitTexture\(\s*"([^"]+)"\s*(\.\.)?', t):
            widget, name, concat = m.group(1), m.group(2), m.group(3)
            if concat:
                continue                       # a prefix, covered by FAMILIES
            out.add((name, widget in buttons))
    for p in glob.glob(os.path.join(UI, "*.xml")):
        t = io.open(p, encoding="utf-8").read()
        for n in re.findall(r"<texture>([^<]+)</texture>", t):
            out.add((n.strip(), False))
    return out


def picked_uses():
    """{picker: {names}} read off each picker's `return "name", ...` lines."""
    out = {}
    for p in glob.glob(os.path.join(SCRIPTS, "*.script")):
        t = io.open(p, encoding="utf-8").read()
        t = re.sub(r"(?m)^\s*--.*$", "", t)
        for fn in PICKERS:
            m = re.search(r"local function %s\(\)(.*?)\nend" % fn, t, re.S)
            if m:
                out[fn] = set(re.findall(r'return\s+"([^"]+)"', m.group(1)))
    return out


def button_uses():
    """Names handed to MAC's add_app, which builds a 3t button from them."""
    out = set()
    for p in glob.glob(os.path.join(SCRIPTS, "*.script")):
        t = io.open(p, encoding="utf-8").read()
        for n in re.findall(r'texture\s*=\s*"([^"]+)"', t):
            out.add(n)
    return out


def resolve(name, is_button, ids, files, foreign=None):
    """Why this name would not draw, or None."""
    foreign = foreign or {}
    if not is_button and name in foreign:
        return None                      # borrowed, and present in this install
    if is_button:
        missing = [s for s in BUTTON_SUFFIXES if (name + s) not in ids]
        if missing:
            return ("used as a 3t button but %s %s not declared - a loose .dds does not "
                    "satisfy a four-state button" % (", ".join(name + m for m in missing),
                                                     "is" if len(missing) == 1 else "are"))
        return None
    if name in ids or name in files:
        return None
    return "neither declared in a textures_descr nor present as textures/%s.dds" % name


def run(install=None):
    ids, files = declared_ids(), on_disk()
    foreign = foreign_ids(install)
    problems = []
    borrowed = []
    checked = 0

    for name, is_btn in sorted(literal_uses()):
        checked += 1
        if not is_btn and name not in ids and name not in files and name in foreign:
            borrowed.append((name, foreign[name]))
        why = resolve(name, is_btn, ids, files, foreign)
        if why:
            problems.append("%s: %s" % (name, why))

    for name in sorted(button_uses()):
        checked += 1
        why = resolve(name, True, ids, files, foreign)
        if why:
            problems.append("%s: %s" % (name, why))

    picked = picked_uses()
    for fn in PICKERS:
        if not picked.get(fn):
            problems.append("%s(): not found, or returns no literal name - update PICKERS"
                            % fn)
        for name in sorted(picked.get(fn, ())):
            checked += 1
            if name in BASE_GAME:
                continue                     # base Anomaly declares it; see BASE_GAME
            why = resolve(name, False, ids, files, foreign)
            if why:
                problems.append("%s (from %s()): %s" % (name, fn, why))

    for prefix, suffixes, is_button in FAMILIES:
        for s in suffixes:
            checked += 1
            why = resolve(prefix + s, is_button, ids, files, foreign)
            if why:
                problems.append("%s: %s" % (prefix + s, why))

    return checked, problems, len(ids), len(files), borrowed


def selftest():
    ids = {"good_e", "good_h", "good_t", "good_d", "plain"}
    files = {"loose"}
    cases = [
        ("declared id", "plain", False, None),
        ("loose file", "loose", False, None),
        ("missing entirely", "nope", False, "flag"),
        ("button fully declared", "good", True, None),
        ("button with only a loose file", "loose", True, "flag"),
    ]
    bad = 0
    for label, name, btn, want in cases:
        got = resolve(name, btn, ids, files)
        ok = (got is None) == (want is None)
        bad += 0 if ok else 1
        print("  %s  %-30s %s" % ("PASS" if ok else "FAIL", label,
                                  "flagged" if got else "accepted"))
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("  self-test: a loose .dds must NOT satisfy a four-state button")
        sys.exit(1 if selftest() else 0)

    ap = argparse.ArgumentParser()
    ap.add_argument("--install", default=os.environ.get("GAMMA_INSTALL", "D:/GAMMA"))
    a = ap.parse_args([x for x in sys.argv[1:] if x != "--selftest"])

    checked, problems, n_ids, n_files, borrowed = run(a.install)
    print("  %d declared ids, %d .dds on disk" % (n_ids, n_files))
    for name, owner in borrowed:
        print("  borrowed  %s  (declared by %s)" % (name, owner[:46]))
    if problems:
        for p in problems:
            print("  FAIL  %s" % p)
        print("\n  %d name(s) checked, %d would not draw" % (checked, len(problems)))
        sys.exit(1)
    print("  %d texture name(s) checked, every one resolves" % checked)
