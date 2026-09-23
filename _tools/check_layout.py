"""Check each PDA page's geometry against its own frame.

Every element on these pages is placed by absolute coordinate, half of them in the xml and
half in the script, and the two have to agree. Nothing in the game complains when they do
not: a label that hangs past a rule, a panel that overruns the frame, or a row list that
only fits because today happens to be quiet all render perfectly happily and look wrong
only to someone standing in front of the screen.

That is the gap this closes. It has already caught three things a person would have had to
spot by eye: the header rule drawn straight across the barometer, a row list with room for
seven rows when a full day needs nine, and the back button drifting inside the ecologist
panel.

Both pages are checked, because they share a grid on purpose - the forecast and the
calendar sit side by side in the launcher and are meant to read as one device seen twice.
The calendar places its rows from a moving cursor rather than a fixed first-row y, so its
rows are reconstructed here from the same constants the script uses; a rule drawn through
one of them is invisible to a check that only reads the xml.

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

# the page background, from <background> in either xml
FR_L, FR_T, FR_R, FR_B = 38, 112, 782, 700
EDGE = 6            # how close to a frame edge counts as touching it
GUTTER = 6          # how close to the split counts as crossing it
CLEAR = 5           # how much air a rule needs on each side of it


def path(kind, name):
    if kind == "xml":
        return os.path.join(MOD, "configs", "ui", name + ".xml")
    return os.path.join(MOD, "scripts", name + ".script")


# --------------------------------------------------------------------------- the pages
#
# LEFT / RIGHT are which column each xml element belongs to. Anything not named in either
# is ignored: <px>, <row_line> and friends are templates cloned at runtime and carry no
# position of their own.
FORECAST = {
    "name": "forecast",
    "file": "ui_seasons_forecast",
    "LEFT": {"header", "bar", "subheader", "src", "live_dot", "wx_now", "wx_arrow",
             "wx_next", "wx_now_label", "wx_next_label", "wx_chance", "now", "frost",
             "chart", "chart_cap_l", "chart_cap_r"},
    "RIGHT": {"gauge", "needle", "gauge_caption", "eco_logo", "eco_class", "eco_l1",
              "eco_l2", "eco_l3", "units", "units_label", "back",
              "toggle_year", "toggle_fc", "toggle_year_label", "toggle_fc_label"},
    # Elements that belong to the ecologist panel. Anything ELSE overlapping the panel is
    # a mistake - the back button drifted inside it when the panel grew, and a control
    # sitting in the middle of a CLASSIFIED box reads as part of the classified thing.
    "ECO_MEMBERS": {"eco_logo", "eco_class", "eco_l1", "eco_l2", "eco_l3"},
    # a full day: six planned changes, a blank, the Tomorrow heading and its row
    "ROWS_NEEDED": 9,
}

CALENDAR = {
    "name": "calendar",
    "file": "ui_seasons_pda",
    "LEFT": {"header", "bar", "subheader", "turning", "marked", "grid",
             "grid_cap_l", "grid_cap_r"},
    "RIGHT": {"dial", "dial_caption", "back",
              "toggle_year", "toggle_fc", "toggle_year_label", "toggle_fc_label"},
    # one list per column now: the six marked days under the grid, the six seasons
    # beside the dial that draws them.
    "SECTIONS": [(1, 6), (2, 6)],
}


def boxes(p):
    out = {}
    for c in ET.parse(p).getroot():
        try:
            out[c.tag] = (int(c.get("x")), int(c.get("y")),
                          int(c.get("width")), int(c.get("height")))
        except (TypeError, ValueError):
            pass
    return out


def num(src, name):
    m = re.search(r"local %s\s*=\s*(-?\d+)" % name, src)
    return int(m.group(1)) if m else None


def pair(src, name):
    m = re.search(r"local %s\s*=\s*\{(-?\d+),\s*(-?\d+)\}" % name, src)
    return (int(m.group(1)), int(m.group(2))) if m else None


def consts(src, spec):
    out = {n: num(src, n) for n in ("SPLIT_X", "FR_HEAD_Y", "CHAMFER")}
    if spec is FORECAST:
        for n in ("CHART_X", "CHART_Y", "CHART_W", "ROW_H", "CURVE_Y", "CURVE_H"):
            out[n] = num(src, n)
        out["ROW_Y0"] = (pair(src, "ROW_Y0") or (None, None))[0]
        out["HEAD_Y"] = (pair(src, "HEAD_Y") or (None, None))[0]
        m = re.search(r"ECO_W, ECO_H = (\d+), (\d+), (\d+), (\d+)", src)
        if m:
            out["ECO"] = tuple(int(g) for g in m.groups())
        out["ECO_LOCKED"] = num(src, "ECO_H_LOCKED")
        # whether the header rule is drawn the full width of the frame or stops at the
        # split. Testing `x < split` instead was right only by accident: it passed
        # because the rule happens to stop at the split today, and would have gone on
        # passing if someone widened it.
        m = re.search(r"line\(FR_L \+ CHAMFER, FR_HEAD_Y,\s*([^,]+),", src)
        out["RULE_FULL_WIDTH"] = bool(m and "FR_R" in m.group(1))
    else:
        for n in ("FR_DIAL_Y", "FR_GRID_Y", "HEAD_H", "ROW_H", "GRID_W", "GUT",
                  "CELL_W", "CELL_H", "PITCH", "ROW_Y0"):
            out[n] = num(src, n)
        out["COL_X"] = pair(src, "COL_X")
        out["COL_W"] = pair(src, "COL_W")
        out["FIELD_MIN"] = num(src, "FIELD_MIN")
        out["COL_Y0"] = pair(src, "COL_Y0")
        out["COL_Y1"] = pair(src, "COL_Y1")
        out["ROWS"] = pair(src, "ROWS")
        m = re.search(r"local GRID_X, GRID_Y = (\d+), (\d+)", src)
        out["GRID_X"] = int(m.group(1)) if m else None
        out["GRID_Y"] = int(m.group(2)) if m else None
        m = re.search(r"self:Gap\(1,\s*(\d+)\)", src)
        out["GAP"] = int(m.group(1)) if m else 20
        out["RULE_FULL_WIDTH"] = False
        # the x offset of the last field in each column's rows, so a three-column row
        # cannot quietly outgrow the cell it is drawn in
        out["FIELD_MAX"] = {1: 0, 2: 0}
        for col, body in re.findall(r"self:Put\((\d),\s*\{\{(.*?)\}\}", src, re.S):
            offs = [int(v) for v in re.findall(r"\{(\d+),", "{" + body)]
            if offs:
                out["FIELD_MAX"][int(col)] = max(out["FIELD_MAX"][int(col)], max(offs))
    return out


def rules(c, spec):
    """The horizontal rules the page draws, as (y, x0, x1)."""
    split, ch = c["SPLIT_X"], c["CHAMFER"]
    out = [(c["FR_HEAD_Y"], FR_L, FR_R if c.get("RULE_FULL_WIDTH") else split)]
    if spec is CALENDAR:
        out.append((c["FR_DIAL_Y"], split + ch, FR_R - ch))
        out.append((c["FR_GRID_Y"], FR_L + ch, split - ch))
    return out


def synth_rows(c):
    """Rebuild the calendar's headings and rows from the cursor the script walks.

    Returns the boxes, where each column's cursor ended, and which column each box
    belongs to - the column cannot be inferred from the name, because the sections do
    not alternate.
    """
    out, col_of, cursor = {}, {}, {1: c["COL_Y0"][0], 2: c["COL_Y0"][1]}
    n = 0
    for i, (col, rows) in enumerate(CALENDAR["SECTIONS"]):
        if i and col == CALENDAR["SECTIONS"][i - 1][0]:
            cursor[col] += c["GAP"]
        for kind, height in [("head", c["HEAD_H"])] + [("row", c["ROW_H"])] * rows:
            n += 1
            key = "%s%d" % (kind, n)
            out[key] = (c["COL_X"][col - 1], cursor[col], width_of(c, col), height)
            col_of[key] = col
            cursor[col] += height
    return out, cursor, col_of


def check(box, c, spec):
    bad = []
    split = c["SPLIT_X"]
    left, right = spec["LEFT"], spec["RIGHT"]
    placed = dict(box)

    # the calendar's rows exist only at runtime, so they are rebuilt here and checked
    # alongside everything the xml places
    if spec is CALENDAR:
        rows, cursor, col_of = synth_rows(c)
        placed.update(rows)
        left = left | set(k for k, v in col_of.items() if v == 1)
        right = right | set(k for k, v in col_of.items() if v == 2)
        for col in (1, 2):
            if cursor[col] > c["COL_Y1"][col - 1]:
                bad.append("column %d needs %dpx but its cell stops at %d"
                           % (col, cursor[col], c["COL_Y1"][col - 1]))
            if c["COL_Y1"][col - 1] > FR_B - EDGE:
                bad.append("column %d runs to %d, past the frame at %d"
                           % (col, c["COL_Y1"][col - 1], FR_B))
        # rows must not need more slots than the pool holds
        need = {1: 0, 2: 0}
        for col, rows_n in CALENDAR["SECTIONS"]:
            need[col] += rows_n
        for col in (1, 2):
            if need[col] > c["ROWS"][col - 1]:
                bad.append("column %d needs %d rows, the pool holds %d"
                           % (col, need[col], c["ROWS"][col - 1]))
        # And a three-field row must fit the width of the cell it is drawn in. The script
        # floors each field at FIELD_MIN, so a last field starting nearer the edge than
        # that is one the page has silently widened past its own cell.
        for col in (1, 2):
            reach = c["FIELD_MAX"][col] + c["FIELD_MIN"]
            if reach > width_of(c, col):
                bad.append("column %d's last field starts at %d and needs %d of %dpx"
                           % (col, c["FIELD_MAX"][col], reach, width_of(c, col)))
        # the cells themselves have to sit inside the frame they claim
        if c["COL_X"][0] + c["COL_W"][0] > c["SPLIT_X"] - GUTTER:
            bad.append("the left cell runs to %d, past the split at %d"
                       % (c["COL_X"][0] + c["COL_W"][0], c["SPLIT_X"]))
        if c["COL_X"][1] + c["COL_W"][1] > FR_R - EDGE:
            bad.append("the right cell runs to %d, past the frame at %d"
                       % (c["COL_X"][1] + c["COL_W"][1], FR_R))

    for tag, (x, y, w, h) in sorted(placed.items()):
        if tag not in left and tag not in right:
            continue
        if tag in left and x + w > split - GUTTER:
            bad.append("%s runs to x=%d, past the column split at %d" % (tag, x + w, split))
        if tag in right and x < split + GUTTER:
            bad.append("%s starts at x=%d, left of the split at %d" % (tag, x, split))
        if y < FR_T + EDGE - 2:
            bad.append("%s top %d is above the frame at %d" % (tag, y, FR_T))
        if y + h > FR_B - 2:
            bad.append("%s bottom %d is below the frame at %d" % (tag, y + h, FR_B))

    # nothing may be drawn across a rule, and a rule sitting hard against a row reads as
    # an underline rather than as a divider
    for ry, rx0, rx1 in rules(c, spec):
        for tag, (x, y, w, h) in sorted(placed.items()):
            if tag not in left and tag not in right:
                continue
            if not (x < rx1 and x + w > rx0):
                continue
            if y < ry < y + h:
                bad.append("the rule at y=%d is drawn across %s (y %d..%d, x %d..%d)"
                           % (ry, tag, y, y + h, x, x + w))
            elif 0 <= ry - (y + h) < CLEAR or 0 <= y - ry < CLEAR:
                bad.append("the rule at y=%d has no air around %s (y %d..%d)"
                           % (ry, tag, y, y + h))

    # No two controls may overlap: where they do, a click lands on whichever the engine
    # drew last, which is not something a player can see. Labels are exempt - each sits
    # over its own plate by design - so only the plates are compared.
    ctl = sorted(t for t in placed if t in CONTROLS)
    for i, a in enumerate(ctl):
        ax, ay, aw, ah = placed[a]
        for b in ctl[i + 1:]:
            bx, by, bw, bh = placed[b]
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah:
                bad.append("controls %s and %s overlap, so a click on either is a guess"
                           % (a, b))

    if spec is FORECAST:
        bad += forecast_extra(box, c)
    else:
        bad += calendar_extra(box, c)
    return bad


# Everything a player can click, on either page.
CONTROLS = {"back", "units", "toggle_year", "toggle_fc"}


def width_of(c, col):
    """The cell a column's rows are drawn in, as the script itself declares it."""
    return c["COL_W"][col - 1]


def forecast_extra(box, c):
    bad = []
    # the row list has to hold a full day, not merely a quiet one
    fits = (FR_B - EDGE - c["ROW_Y0"]) // c["ROW_H"]
    if fits < FORECAST["ROWS_NEEDED"]:
        bad.append("only %d rows fit below y=%d at %dpx; a full day needs %d"
                   % (fits, c["ROW_Y0"], c["ROW_H"], FORECAST["ROWS_NEEDED"]))
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
        if ex < c["SPLIT_X"]:
            bad.append("the ecologist panel starts left of the split")
        if ey + eh > FR_B - EDGE:
            bad.append("the ecologist panel bottom %d overruns the frame" % (ey + eh))
        for tag in sorted(FORECAST["ECO_MEMBERS"]):
            if tag not in box:
                continue
            x, y, w, h = box[tag]
            if not (ey < y and y + h < ey + eh):
                bad.append("%s at y=%d..%d sits outside the panel %d..%d"
                           % (tag, y, y + h, ey, ey + eh))

        # and nothing that is not part of the panel may sit inside it
        for tag, (x, y, w, h) in sorted(box.items()):
            if tag in FORECAST["ECO_MEMBERS"]:
                continue
            if tag not in (FORECAST["LEFT"] | FORECAST["RIGHT"]):
                continue
            if x < ex + ew and x + w > ex and y < ey + eh and y + h > ey:
                bad.append("%s overlaps the ecologist panel (%d..%d, %d..%d)"
                           % (tag, ex, ex + ew, ey, ey + eh))

        # the panel should be close to the size of what it holds, not a void with a
        # heading floating at the top of it
        used = [box[m] for m in FORECAST["ECO_MEMBERS"] if m in box]
        if used:
            content = max(y + h for _, y, _, h in used) - min(y for _, y, _, _ in used)
            if eh > content * 2.2:
                bad.append("the ecologist panel is %dpx tall around %dpx of content"
                           % (eh, content))

        # The rule above measures DECLARED boxes, and eco_l1..l3 are declared whether or
        # not they hold text - so a panel that is empty only at the locked tier sailed
        # through it, and shipped as a 162px border around an emblem and one word. The
        # locked height is checked against what that tier actually draws.
        lh = c.get("ECO_LOCKED")
        if lh:
            for tag in ("eco_logo", "eco_class"):
                if tag not in box:
                    continue
                _, y, _, h = box[tag]
                if not (ey < y and y + h < ey + lh):
                    bad.append("%s at y=%d..%d falls outside the locked panel %d..%d"
                               % (tag, y, y + h, ey, ey + lh))
            for tag in ("eco_l1", "eco_l2", "eco_l3"):
                if tag not in box:
                    continue
                _, y, _, h = box[tag]
                if y < ey + lh:
                    bad.append("%s sits inside the locked panel, which draws no lines"
                               % tag)
    return bad


def calendar_extra(box, c):
    bad = []
    # the grid's own contents have to fit the element the xml declares
    if "grid" in box:
        gx, gy, gw, gh = box["grid"]
        if (gx, gy, gw) != (c["GRID_X"], c["GRID_Y"], c["GRID_W"]):
            bad.append("grid xml (%d,%d,%d) disagrees with the script (%d,%d,%d)"
                       % (gx, gy, gw, c["GRID_X"], c["GRID_Y"], c["GRID_W"]))
        # the longest month has to fit beside the month names
        need_w = c["GUT"] + 31 * c["CELL_W"]
        if need_w > gw:
            bad.append("31 days need %dpx beside the %dpx gutter, <grid> is %dpx wide"
                       % (need_w, c["GUT"], gw))
        # twelve month rows, plus the day scale above them
        need_h = c["ROW_Y0"] + 11 * c["PITCH"] + c["CELL_H"]
        if need_h > gh:
            bad.append("twelve months need %dpx but <grid> is %dpx tall" % (need_h, gh))
        # a row taller than the pitch would overlap the month under it
        if c["CELL_H"] > c["PITCH"]:
            bad.append("cells are %dpx tall on a %dpx pitch, so the months overlap"
                       % (c["CELL_H"], c["PITCH"]))
        # the day scale is drawn at the element's own top, so the first row has to clear it
        if c["ROW_Y0"] < 14:
            bad.append("the first month at y=%d is drawn over the day scale"
                       % c["ROW_Y0"])
    return bad


def read(spec):
    box = boxes(path("xml", spec["file"]))
    c = consts(io.open(path("lua", spec["file"]), encoding="utf-8").read(), spec)
    return box, c


def selftest():
    cases = []

    fbox, fc = read(FORECAST)
    bent = dict(fc); bent["ROW_H"] = 19
    cases.append(("rows too tall to fit a full day", fbox, bent, FORECAST, True))

    # a full-width rule at 200 would be drawn straight through the barometer, which is
    # exactly what shipped once
    bent = dict(fc); bent["FR_HEAD_Y"] = 206; bent["RULE_FULL_WIDTH"] = True
    cases.append(("full-width rule across the barometer", fbox, bent, FORECAST, True))

    # and the same rule stopping at the split must NOT be flagged. 206 rather than 200:
    # at 200 it clears the barometer but sits 4px under the source line, so the pair
    # stopped isolating the thing being tested.
    bent = dict(fc); bent["FR_HEAD_Y"] = 206; bent["RULE_FULL_WIDTH"] = False
    cases.append(("left-column rule clears it", fbox, bent, FORECAST, False))

    b2 = dict(fbox); b2["back"] = (740, 480, 34, 34)
    cases.append(("a control inside the panel", b2, fc, FORECAST, True))

    b2 = dict(fbox); b2["eco_l3"] = (556, 690, 206, 18)
    cases.append(("a panel line outside its border", b2, fc, FORECAST, True))

    # the locked border left at the full height is the void that shipped
    bent = dict(fc); bent["ECO_LOCKED"] = fc["ECO"][3]
    cases.append(("locked panel sized for lines it hides", fbox, bent, FORECAST, True))

    # and too short to hold the emblem is the other way to get it wrong
    bent = dict(fc); bent["ECO_LOCKED"] = 30
    cases.append(("locked panel clipping its emblem", fbox, bent, FORECAST, True))

    # the Forecast half of the switch slid right onto the units button
    b5 = dict(fbox); b5["toggle_fc"] = (690, 126, 64, 24)
    cases.append(("switch sitting on the units button", b5, fc, FORECAST, True))

    b3 = dict(fbox); b3["chart"] = (fc["CHART_X"], fc["CHART_Y"], fc["CHART_W"], 60)
    cases.append(("curve taller than its element", b3, fc, FORECAST, True))

    cases.append(("the forecast as it stands", fbox, fc, FORECAST, False))

    cbox, cc = read(CALENDAR)
    bent = dict(cc); bent["ROW_H"] = 26
    cases.append(("calendar rows overrun their cell", cbox, bent, CALENDAR, True))

    # the divider under the grid, nudged down into the first row of the list
    bent = dict(cc); bent["FR_GRID_Y"] = cc["FR_GRID_Y"] + 24
    cases.append(("divider drawn through a row", cbox, bent, CALENDAR, True))

    bent = dict(cc); bent["ROWS"] = (4, 8)
    cases.append(("row pool too small for the lists", cbox, bent, CALENDAR, True))

    bent = dict(cc); bent["FIELD_MAX"] = {1: 270, 2: 190}
    cases.append(("a field starting past the cell", cbox, bent, CALENDAR, True))

    b4 = dict(cbox); b4["grid"] = (cc["GRID_X"], cc["GRID_Y"], cc["GRID_W"], 120)
    cases.append(("grid taller than its element", b4, cc, CALENDAR, True))

    bent = dict(cc); bent["CELL_W"] = 15
    cases.append(("31 days wider than the grid", cbox, bent, CALENDAR, True))

    bent = dict(cc); bent["CELL_H"] = 22
    cases.append(("months overlapping on the pitch", cbox, bent, CALENDAR, True))

    cases.append(("the calendar as it stands", cbox, cc, CALENDAR, False))

    bad = 0
    for label, bb, ccc, spec, want in cases:
        got = bool(check(bb, ccc, spec))
        ok = got == want
        bad += 0 if ok else 1
        print("  %s  %-36s %s" % ("PASS" if ok else "FAIL", label,
                                  "flagged" if got else "accepted"))
    return bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        print("  self-test: each way a layout can drift must be caught")
        sys.exit(1 if selftest() else 0)

    problems = 0
    for spec in (FORECAST, CALENDAR):
        box, c = read(spec)
        found = check(box, c, spec)
        for p in found:
            print("  FAIL  %-9s %s" % (spec["name"], p))
        problems += len(found)
        if not found:
            print("  ok    %-9s every element sits inside its cell, and no rule "
                  "crosses one" % spec["name"])
    if problems:
        print("\n  %d layout problem(s)" % problems)
        sys.exit(1)
