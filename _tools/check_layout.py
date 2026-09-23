"""Check the forecast page's geometry against its own frame.

Every element on this page is placed by absolute coordinate, half of them in the xml and
half in the script, and the two have to agree. Nothing in the game complains when they do
not: a label that hangs past a rule, a panel that overruns the frame, or a row list that
only fits because today happens to be quiet all render perfectly happily and look wrong
only to someone standing in front of the screen.

That is the gap this closes. It has already caught two things a person would have had to
spot by eye: the header rule drawn straight across the barometer, and a row list with room
for seven rows when a full day needs nine.

  python _tools/check_layout.py
  python _tools/check_layout.py --selftest
"""
import io
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata")
XML = os.path.join(MOD, "configs", "ui", "ui_seasons_forecast.xml")
SCRIPT = os.path.join(MOD, "scripts", "ui_seasons_forecast.script")

# the page background, from <background> in the xml
FR_L, FR_T, FR_R, FR_B = 38, 112, 782, 700
EDGE = 6            # how close to a frame edge counts as touching it
GUTTER = 6          # how close to the split counts as crossing it

LEFT = {"header", "bar", "subheader", "src", "live_dot", "wx_now", "wx_arrow",
        "wx_next", "wx_now_label", "wx_next_label", "now", "frost", "chart",
        "chart_cap_l", "chart_cap_r"}
RIGHT = {"gauge", "needle", "gauge_caption", "eco_logo", "eco_class", "eco_l1",
         "eco_l2", "eco_l3", "units", "units_label"}

# a full day: six planned changes, a blank, the Tomorrow heading and its row
ROWS_NEEDED = 9


def boxes(path):
    out = {}
    for c in ET.parse(path).getroot():
        try:
            out[c.tag] = (int(c.get("x")), int(c.get("y")),
                          int(c.get("width")), int(c.get("height")))
        except (TypeError, ValueError):
            pass
    return out


def consts(src):
    def one(name):
        m = re.search(r"local %s\s*=\s*(-?\d+)" % name, src)
        return int(m.group(1)) if m else None
    out = {n: one(n) for n in ("SPLIT_X", "FR_HEAD_Y", "CHART_X", "CHART_Y",
                               "CHART_W", "ROW_H", "CURVE_Y", "CURVE_H")}
    m = re.search(r"local ROW_Y0\s*=\s*\{(\d+),\s*(\d+)\}", src)
    out["ROW_Y0"] = int(m.group(1)) if m else None
    m = re.search(r"local HEAD_Y\s*=\s*\{(\d+),\s*(\d+)\}", src)
    out["HEAD_Y"] = int(m.group(1)) if m else None
    m = re.search(r"ECO_W, ECO_H = (\d+), (\d+), (\d+), (\d+)", src)
    if m:
        out["ECO"] = tuple(int(g) for g in m.groups())
    # whether the header rule is drawn the full width of the frame or stops at the split
    m = re.search(r"line\(FR_L \+ CHAMFER, FR_HEAD_Y,\s*([^,]+),", src)
    out["RULE_FULL_WIDTH"] = bool(m and "FR_R" in m.group(1))
    return out


def check(box, c):
    bad = []
    split, rule = c["SPLIT_X"], c["FR_HEAD_Y"]

    for tag, (x, y, w, h) in sorted(box.items()):
        if tag not in LEFT and tag not in RIGHT:
            continue
        if tag in LEFT and x + w > split - GUTTER:
            bad.append("%s runs to x=%d, past the column split at %d" % (tag, x + w, split))
        if tag in RIGHT and x < split + GUTTER:
            bad.append("%s starts at x=%d, left of the split at %d" % (tag, x, split))
        if y < FR_T + EDGE - 2:
            bad.append("%s top %d is above the frame at %d" % (tag, y, FR_T))
        if y + h > FR_B - 2:
            bad.append("%s bottom %d is below the frame at %d" % (tag, y + h, FR_B))

    # How far the header rule actually runs, read from the call that draws it. Testing
    # `x < split` instead was right only by accident: it passed because the rule happens
    # to stop at the split today, and would have gone on passing if someone widened it.
    rule_x0 = FR_L
    rule_x1 = FR_R if c.get("RULE_FULL_WIDTH") else split
    for tag, (x, y, w, h) in sorted(box.items()):
        if tag not in LEFT and tag not in RIGHT:
            continue
        crosses_y = y < rule < y + h
        overlaps_x = x < rule_x1 and x + w > rule_x0
        if crosses_y and overlaps_x:
            bad.append("the header rule at y=%d is drawn across %s (y %d..%d, x %d..%d)"
                       % (rule, tag, y, y + h, x, x + w))

    # the row list has to hold a full day, not merely a quiet one
    fits = (FR_B - EDGE - c["ROW_Y0"]) // c["ROW_H"]
    if fits < ROWS_NEEDED:
        bad.append("only %d rows fit below y=%d at %dpx; a full day needs %d"
                   % (fits, c["ROW_Y0"], c["ROW_H"], ROWS_NEEDED))
    if c["HEAD_Y"] >= c["ROW_Y0"]:
        bad.append("the column heading at %d is not above its rows at %d"
                   % (c["HEAD_Y"], c["ROW_Y0"]))

    # the chart's own contents have to fit the element the xml declares
    if "chart" in box:
        cx, cy, cw, ch = box["chart"]
        if (cx, cy, cw) != (c["CHART_X"], c["CHART_Y"], c["CHART_W"]):
            bad.append("chart xml (%d,%d,%d) disagrees with the script (%d,%d,%d)"
                       % (cx, cy, cw, c["CHART_X"], c["CHART_Y"], c["CHART_W"]))
        need = c["CURVE_Y"] + c["CURVE_H"] + 18      # + the hour labels under it
        if need > ch:
            bad.append("the curve needs %dpx but <chart> is %dpx tall" % (need, ch))

    # the ecologist panel's lines have to sit inside its border
    if "ECO" in c:
        ex, ey, ew, eh = c["ECO"]
        if ex < split:
            bad.append("the ecologist panel starts left of the split")
        if ey + eh > FR_B - EDGE:
            bad.append("the ecologist panel bottom %d overruns the frame" % (ey + eh))
        for tag in ("eco_logo", "eco_class", "eco_l1", "eco_l2", "eco_l3"):
            if tag not in box:
                continue
            x, y, w, h = box[tag]
            if not (ey < y and y + h < ey + eh):
                bad.append("%s at y=%d..%d sits outside the panel %d..%d"
                           % (tag, y, y + h, ey, ey + eh))
    return bad


def selftest():
    box = boxes(XML)
    c = consts(io.open(SCRIPT, encoding="utf-8").read())
    cases = []

    bent = dict(c); bent["ROW_H"] = 19
    cases.append(("rows too tall to fit a full day", box, bent, True))

    # a full-width rule at 200 would be drawn straight through the barometer, which is
    # exactly what shipped once
    bent = dict(c); bent["FR_HEAD_Y"] = 200; bent["RULE_FULL_WIDTH"] = True
    cases.append(("full-width rule across the barometer", box, bent, True))

    # and the same rule stopping at the split must NOT be flagged
    bent = dict(c); bent["FR_HEAD_Y"] = 200; bent["RULE_FULL_WIDTH"] = False
    cases.append(("left-column rule clears it", box, bent, False))

    b2 = dict(box); b2["eco_l3"] = (556, 690, 206, 18)
    cases.append(("a panel line outside its border", b2, c, True))

    b3 = dict(box); b3["chart"] = (c["CHART_X"], c["CHART_Y"], c["CHART_W"], 60)
    cases.append(("curve taller than its element", b3, c, True))

    cases.append(("the page as it stands", box, c, False))

    bad = 0
    for label, bb, cc, want in cases:
        got = bool(check(bb, cc))
        ok = got == want
        bad += 0 if ok else 1
        print("  %s  %-34s %s" % ("PASS" if ok else "FAIL", label,
                                  "flagged" if got else "accepted"))
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("  self-test: each way the layout can drift must be caught")
        sys.exit(1 if selftest() else 0)

    problems = check(boxes(XML), consts(io.open(SCRIPT, encoding="utf-8").read()))
    if problems:
        for p in problems:
            print("  FAIL  %s" % p)
        print("\n  %d layout problem(s)" % len(problems))
        sys.exit(1)
    print("  every element sits inside its cell, and the rule crosses nothing")
