"""Static checks on this mod's configs/ui XML, in the shape X-Ray actually needs.

Written after a crash. Both pages shipped with an explanatory comment above the root
element. That is valid XML - ElementTree parsed it happily, and a check that only asked
"does every element the script inits exist?" passed - but X-Ray's parser takes the FIRST
element as the root, so a leading comment makes ParseFile fail. ParseFile does not raise;
it returns, and every Init* afterwards hands back nil. The first method call on one of
those nils is a hard engine FATAL that pcall cannot catch.

Every working ui xml in a stock install starts with its root element and keeps comments
inside it. So that is what this asserts, alongside the element coverage.

  python _tools/check_ui_xml.py            check
  python _tools/check_ui_xml.py --selftest prove the checks can fail
"""
import glob
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata")
UI = os.path.join(MOD, "configs", "ui")
SCRIPTS = os.path.join(MOD, "scripts")

# which script drives which xml
PAGES = {
    "ui_seasons_pda.xml": "ui_seasons_pda.script",
    "ui_seasons_forecast.xml": "ui_seasons_forecast.script",
}


def check_preamble(path, text):
    """The root element must be the very first thing in the file."""
    bad = []
    if text.startswith("﻿"):
        bad.append("starts with a UTF-8 BOM")
    stripped = text.lstrip("﻿ \t\r\n")
    if stripped.startswith("<!--"):
        bad.append("a comment sits above the root element - X-Ray will treat that "
                   "comment as the document and ParseFile will fail")
    elif stripped.startswith("<?"):
        bad.append("an XML declaration or processing instruction sits above the root")
    elif not stripped.startswith("<w>"):
        first = stripped[:40].replace("\n", " ")
        bad.append("root element is not <w>: %r" % first)
    return bad


def elements_used(script_text):
    """Element names the script hands to Init*, including ones passed by variable."""
    used = set(re.findall(r'Init(?:TextWnd|Static|ScrollView|3tButton)\s*\(\s*"([^"]+)"',
                          script_text))
    used |= set(re.findall(r'Row\s*\(\s*"([^"]+)"', script_text))
    for a, b in re.findall(r'"(row_[a-z]+)"\s+or\s+"(row_[a-z]+)"', script_text):
        used |= {a, b}
    return used


def check_file(xml_path, script_path):
    problems = []
    name = os.path.basename(xml_path)
    text = io.open(xml_path, encoding="utf-8").read()

    for p in check_preamble(xml_path, text):
        problems.append("%s: %s" % (name, p))

    try:
        root = ET.parse(xml_path).getroot()
    except ET.ParseError as e:
        problems.append("%s: not well-formed XML: %s" % (name, e))
        return problems

    defined = {c.tag for c in root}
    if script_path and os.path.exists(script_path):
        used = elements_used(io.open(script_path, encoding="utf-8").read())
        for miss in sorted(used - defined):
            problems.append("%s: <%s> is initialised by %s but not defined here"
                            % (name, miss, os.path.basename(script_path)))
    return problems


def run():
    problems, checked = [], 0
    for xml_path in sorted(glob.glob(os.path.join(UI, "*.xml"))):
        name = os.path.basename(xml_path)
        script = PAGES.get(name)
        problems += check_file(xml_path,
                               os.path.join(SCRIPTS, script) if script else None)
        checked += 1
    return checked, problems


def selftest():
    """Break a copy of each rule and confirm the checker notices."""
    cases = [
        ("comment above the root",
         "<!-- hello -->\n<w>\n  <a x=\"0\"/>\n</w>\n", True),
        ("xml declaration above the root",
         "<?xml version=\"1.0\"?>\n<w>\n  <a x=\"0\"/>\n</w>\n", True),
        ("BOM", "﻿<w>\n  <a x=\"0\"/>\n</w>\n", True),
        ("wrong root", "<window>\n  <a x=\"0\"/>\n</window>\n", True),
        ("correct file", "<w>\n<!-- fine here -->\n  <a x=\"0\"/>\n</w>\n", False),
    ]
    bad = 0
    for label, text, should_fail in cases:
        found = bool(check_preamble("<memory>", text))
        ok = (found == should_fail)
        if not ok:
            bad += 1
        print("  %s  %-30s %s" % ("PASS" if ok else "FAIL", label,
                                  "flagged" if found else "accepted"))
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("  self-test: the checks must reject what X-Ray rejects")
        sys.exit(1 if selftest() else 0)

    checked, problems = run()
    if problems:
        for p in problems:
            print("  FAIL  %s" % p)
        print("\n  %d file(s) checked, %d problem(s)" % (checked, len(problems)))
        sys.exit(1)
    print("  %d ui xml file(s) checked, all sound" % checked)
