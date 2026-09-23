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
    ("sotz_gauge_", ["clear", "partly", "cloudy", "foggy", "rain", "storm"], False),
    ("sotz_wx_", ["clear", "partly", "cloudy", "foggy", "rain", "storm",
                  "arrow"], False),
    ("sotz_app_year_", ["spring", "summer", "autumn", "winter", "winter_snow"], True),
    ("ui_season_hdr_", ["spring", "summer", "autumn", "winter", "winter_snow"], False),
    ("ui_seasons_dial_", ["%02d" % i for i in range(32)], False),
]

BUTTON_SUFFIXES = ("_e", "_h", "_t", "_d")


def declared_ids():
    ids = set()
    for p in glob.glob(os.path.join(DESCR, "*.xml")):
        ids |= set(re.findall(r'<texture\s+id="([^"]+)"',
                              io.open(p, encoding="utf-8").read()))
    return ids


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


def button_uses():
    """Names handed to MAC's add_app, which builds a 3t button from them."""
    out = set()
    for p in glob.glob(os.path.join(SCRIPTS, "*.script")):
        t = io.open(p, encoding="utf-8").read()
        for n in re.findall(r'texture\s*=\s*"([^"]+)"', t):
            out.add(n)
    return out


def resolve(name, is_button, ids, files):
    """Why this name would not draw, or None."""
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


def run():
    ids, files = declared_ids(), on_disk()
    problems = []
    checked = 0

    for name, is_btn in sorted(literal_uses()):
        checked += 1
        why = resolve(name, is_btn, ids, files)
        if why:
            problems.append("%s: %s" % (name, why))

    for name in sorted(button_uses()):
        checked += 1
        why = resolve(name, True, ids, files)
        if why:
            problems.append("%s: %s" % (name, why))

    for prefix, suffixes, is_button in FAMILIES:
        for s in suffixes:
            checked += 1
            why = resolve(prefix + s, is_button, ids, files)
            if why:
                problems.append("%s: %s" % (prefix + s, why))

    return checked, problems, len(ids), len(files)


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

    checked, problems, n_ids, n_files = run()
    print("  %d declared ids, %d .dds on disk" % (n_ids, n_files))
    if problems:
        for p in problems:
            print("  FAIL  %s" % p)
        print("\n  %d name(s) checked, %d would not draw" % (checked, len(problems)))
        sys.exit(1)
    print("  %d texture name(s) checked, every one resolves" % checked)
