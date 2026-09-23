"""Run the SHIPPED calendar page under a real Lua runtime.

The year grid is the only real arithmetic on that page, and the traps in it are quiet
ones. One season runs December into March, so it owns cells at both ends of the grid.
Months are 28, 29, 30 or 31 days, and a month drawn 31 wide regardless still renders - it
just gives February three days it does not have. Each month row is filled by season runs,
and a run that stops one day short leaves a gap nobody notices in a screenshot.

So this loads both shipped files - the data layer and the page - into a sandbox, stubs
the X-Ray bindings they reach for, and runs DrawGrid for real. The assertions are made
against the rectangles the page actually produced, not against a re-implementation.

The date is pinned, so a case cannot start passing or failing because of the day it was
run on. Where a case depends on the date it says which one and why.

  python _tools/test_calendar.py
"""
import io
import os
import re
import sys

from lupa import LuaRuntime

from check_layout import CALENDAR, read as read_layout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

# the page's own constants, read from the source rather than copied, so the test cannot
# drift away from the thing it is testing
_, GEO = read_layout(CALENDAR)
GRID_X, GRID_Y, GRID_W = GEO["GRID_X"], GEO["GRID_Y"], GEO["GRID_W"]
GUT, CELL_W, CELL_H = GEO["GUT"], GEO["CELL_W"], GEO["CELL_H"]
PITCH, ROW_Y0 = GEO["PITCH"], GEO["ROW_Y0"]

SRC = io.open(os.path.join(SCRIPTS, "ui_seasons_pda.script"), encoding="utf-8").read()
BAR_POOL = int(re.search(r"local BAR_POOL\s*=\s*(\d+)", SRC).group(1))
MARK_H = int(re.search(r"local MARK_H\s*=\s*(\d+)", SRC).group(1))
MARK_RGB = tuple(int(v) for v in re.search(
    r"local MARK_RGB\s*=\s*\{([^}]+)\}", SRC).group(1).split(","))

MONTH_LEN = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]


def cell_x(day):
    return GUT + (day - 1) * CELL_W


def row_y(m):
    return ROW_Y0 + (m - 1) * PITCH


def mlen(m, year_len):
    return MONTH_LEN[m - 1] + (1 if (m == 2 and year_len >= 366) else 0)


PRELUDE = """
-- os with a pinned today. The two-argument form still converts whatever timestamp it is
-- handed, because doy_of() builds its own for arbitrary dates.
function fixed_os(y, m, d)
    local rd, rt, rc = os.date, os.time, os.clock
    local fixed = rt({year = y, month = m, day = d, hour = 12})
    return {date = function(fmt, t) return rd(fmt, t or fixed) end,
            time = rt, clock = rc}
end

-- A CUIStatic / CUITextWnd that records what was done to it instead of drawing.
function mkwidget()
    local s = {vis = false}
    function s:SetWndPos(v)      self.x, self.y = v.x, v.y end
    function s:SetWndSize(v)     self.w, self.h = v.x, v.y end
    function s:SetTextureColor(c) self.col = c end
    function s:SetTextColor(c)   self.col = c end
    function s:SetText(t)        self.text = t end
    function s:InitTexture(t)    self.tex = t end
    function s:Show(on)          self.vis = on and true or false end
    function s:GetHeight()       return self.h or 0 end
    function s:GetWidth()        return self.w or 0 end
    return s
end

function load_in(src, name, shared)
    local env = setmetatable({}, {__index = shared})
    local f, err = load(src, name, "t", env)
    if not f then error(name .. ": " .. tostring(err)) end
    f()
    return env
end

-- A page object that is not built by InitControls - the widget pools are handed in - so
-- the drawing code can be run without an engine behind it. The metatable is the class
-- itself, which is what makes self:Bar resolve exactly as it does in game.
function make_page(cls, bars, axis, months)
    local p = setmetatable({}, {__index = cls})
    p.grid, p.bars, p.axis_x, p.months, p.bar_n = mkwidget(), bars, axis, months, 0
    return p
end
"""


def build(year=2026, month=9, day=22):
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    lua.execute(PRELUDE)

    g.printf = lambda *a: None
    g.os = g.fixed_os(year, month, day)
    g.device = lambda: lua.table_from({"width": 1920, "height": 1080})
    g.time_global = lambda: 0
    g.alife = lambda: None
    g.level = lua.table_from({"name": lambda: "l01_escape"})
    g.db = lua.table_from({"actor": lua.table_from({"id": lambda self: 0})})
    g.axr_main = lua.table_from({})
    g.RegisterScriptCallback = lambda *a: None
    g.relation_registry = lua.table_from({"community_goodwill": lambda f, a: 0})
    g.ui_options = lua.table_from({"get": lambda k: None})
    g.ui_mcm = lua.table_from({"get": lambda p: None})
    g.level_weathers = lua.table_from({})
    g.surge_manager = lua.table_from({})
    g.psi_storm_manager = lua.table_from({})
    g.game = lua.table_from({"get_game_time": lambda: lua.table_from({
        "diffSec": lambda self, other: 0, "get": lambda self, *a: year})})
    g.ini_file = lambda name: lua.table_from({
        "section_exist": lambda self, s: False,
        "r_float_ex": lambda self, s, k: None,
        "r_string_ex": lambda self, s, k: None})
    # the page's own engine bindings
    g.GetARGB = lambda a, r, gg, b: lua.table_from({"a": a, "r": r, "g": gg, "b": b})
    g.vector2 = lua.eval("function() local v = {}"
                         " function v:set(a, b) self.x, self.y = a, b; return self end"
                         " return v end")
    # Update() chains to the base class first, so it has to exist to be called
    g.CUIScriptWnd = lua.table_from({"Update": lambda self: None})
    g.ui_events = lua.table_from({"BUTTON_CLICKED": 1, "WINDOW_KEY_PRESSED": 2})
    g.DIK_keys = lua.table_from({"DIK_ESCAPE": 1})
    g.ActorMenu = lua.table_from({})
    # X-Ray's class(): class "X" (Base) creates the global X, which the method
    # definitions below it then fill in.
    lua.execute("""
        class = function(name)
            return function(base)
                local t = {}
                t.__index = t
                _G[name] = t
                return t
            end
        end
        super = function() end
    """)

    for fname in ("zzz_seasons_of_the_zone",):
        src = io.open(os.path.join(SCRIPTS, fname + ".script"), encoding="utf-8").read()
        g[fname] = g.load_in(src, fname, g)
    # the page goes into the globals, because `class` writes SeasonsPDA there
    lua.execute(SRC)
    return lua, g


def draw(lua, g, pool=None):
    """Run the real DrawGrid against the real calendar_page() and hand back the cells."""
    n = pool or BAR_POOL
    bars = lua.table_from([g.mkwidget() for _ in range(n)])
    axis = lua.table_from([g.mkwidget() for _ in range(5)])
    months = lua.table_from([g.mkwidget() for _ in range(12)])
    page = g.make_page(g.SeasonsPDA, bars, axis, months)
    data = g.zzz_seasons_of_the_zone.calendar_page()
    g.SeasonsPDA.DrawGrid(page, data)
    out = []
    for i in range(1, n + 1):
        w = bars[i]
        if w.vis:
            out.append({"i": i, "x": int(w.x), "y": int(w.y), "w": int(w.w),
                        "h": int(w.h), "rgb": (w.col["r"], w.col["g"], w.col["b"]),
                        "a": w.col["a"]})
    scale = [{"x": int(axis[i].x), "text": axis[i].text}
             for i in range(1, 6) if axis[i].vis]
    names = [{"y": int(months[i].y), "text": months[i].text}
             for i in range(1, 13) if months[i].vis]
    return out, scale, names, page, data


def runs_in(bars, m, today):
    """The season blocks on month m's row, with the lit today cell excluded.

    Today is drawn last and on top of the run it sits in, so counting it as a run would
    double-count that day.
    """
    y = row_y(m)
    out = [b for b in bars if b["y"] == y and b["h"] == CELL_H]
    if today is not None:
        out = [b for b in out
               if not (b["x"] == today["x"] and b["y"] == today["y"]
                       and b["w"] == today["w"])]
    return sorted(out, key=lambda b: b["x"])


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_every_month_is_filled_exactly():
    """Each row covers its own days: no gap, no overlap, and no day it does not have."""
    bars, _, _, page, data = draw(*build()[:2])
    today = {"x": int(page.today_bar.x), "y": int(page.today_bar.y),
             "w": int(page.today_bar.w)}
    ylen = data["year_len"]
    for m in range(1, 13):
        rs = runs_in(bars, m, today)
        assert rs, "month %d drew nothing" % m
        assert rs[0]["x"] == cell_x(1), \
            "month %d starts at x=%d, not %d" % (m, rs[0]["x"], cell_x(1))
        days = 0
        for a, b in zip(rs, rs[1:]):
            seam = b["x"] - (a["x"] + a["w"])
            assert 0 <= seam <= 1, "month %d has a %dpx seam at x=%d" % (m, seam, b["x"])
        for r in rs:
            days += (r["w"] + 1) // CELL_W
        assert days == mlen(m, ylen), \
            "month %d drew %d days, it has %d" % (m, days, mlen(m, ylen))
    return "twelve months drawn to their own lengths, no seams"


@case
def t_cover_owns_both_ends_of_the_year():
    """Cover runs December into March, so it has to appear in both rows.

    season_map walks each span modulo the year, which is what makes the wrap need no
    special case. Break that and December or January loses its colour.
    """
    bars, _, _, page, _ = draw(*build()[:2])
    today = {"x": int(page.today_bar.x), "y": int(page.today_bar.y),
             "w": int(page.today_bar.w)}
    dec = runs_in(bars, 12, today)
    jan = runs_in(bars, 1, today)
    assert len(dec) == 1, "December is drawn in %d pieces" % len(dec)
    assert len(jan) == 1, "January is drawn in %d pieces" % len(jan)
    assert dec[0]["rgb"] == jan[0]["rgb"], \
        "December is %s and January is %s" % (dec[0]["rgb"], jan[0]["rgb"])
    # and the control: a month in the middle of the year must NOT wear that colour
    jul = runs_in(bars, 7, today)
    assert jul[0]["rgb"] != dec[0]["rgb"], "July reads as deep winter"
    return "deep winter owns both December and January, and July is something else"


@case
def t_a_split_month_is_two_runs():
    """March turns on the 5th, so its row is four days of cover then the rest spring."""
    bars, _, _, page, _ = draw(*build()[:2])
    today = {"x": int(page.today_bar.x), "y": int(page.today_bar.y),
             "w": int(page.today_bar.w)}
    mar = runs_in(bars, 3, today)
    assert len(mar) == 2, "March is drawn in %d pieces, expected 2" % len(mar)
    first = (mar[0]["w"] + 1) // CELL_W
    assert first == 4, "cover holds %d days of March, expected 4" % first
    assert mar[0]["rgb"] != mar[1]["rgb"], "both halves of March are the same colour"
    # a month with no boundary in it is one piece
    assert len(runs_in(bars, 6, today)) == 1, "June is split"
    return "March splits 4 + 27 on the turn, June stays whole"


@case
def t_today_is_lit_in_the_right_cell():
    """22 September 2026."""
    lua, g = build(2026, 9, 22)
    bars, _, _, page, data = draw(lua, g)
    assert data["season"] == "autumn", data["season"]
    t = page.today_bar
    assert t is not None, "no today cell drawn"
    assert int(t.y) == row_y(9), "today is on row y=%d, September is %d" % (
        int(t.y), row_y(9))
    assert int(t.x) == cell_x(22), "today is at x=%d, the 22nd is %d" % (
        int(t.x), cell_x(22))
    assert (t.col["r"], t.col["g"], t.col["b"]) == MARK_RGB, "today is not the mark red"
    assert int(t.h) == CELL_H, "today is %dpx tall, not a filled cell" % int(t.h)
    # negative control: a different date must light a different cell
    _, _, _, p2, _ = draw(*build(2027, 1, 15)[:2])
    assert int(p2.today_bar.y) == row_y(1) and int(p2.today_bar.x) == cell_x(15), \
        "15 January did not move the lit cell"
    return "22 Sep lights September 22; 15 Jan lights January 15"


@case
def t_marked_days_are_underlined_on_their_own_cells():
    bars, _, _, _, data = draw(*build()[:2])
    marks = [b for b in bars if b["h"] == MARK_H]
    assert len(marks) == len(data["days"]), \
        "%d underlines for %d marked days" % (len(marks), len(data["days"]))
    want = set()
    for day in data["days"].values():
        want.add((cell_x(day["day"]), row_y(day["month"]) + CELL_H - MARK_H))
    got = set((b["x"], b["y"]) for b in marks)
    assert got == want, "underlines at %s, expected %s" % (sorted(got), sorted(want))
    # one red for every kind, and it must be a colour no season wears - an amber mark on
    # autumn and a slate mark on deep winter were both invisible, which is what this
    # replaced
    seasons = set()
    for m in re.findall(r"\w+\s*=\s*\{([^}]+)\}",
                        re.search(r"local SEASON_RGB = \{(.*?)\n\}", SRC, re.S).group(1)):
        seasons.add(tuple(int(v) for v in m.split(",")))
    for b in marks:
        assert b["rgb"] == MARK_RGB, "an underline is %s, not %s" % (b["rgb"], MARK_RGB)
    assert MARK_RGB not in seasons, "the mark colour is one of the season colours"
    return "%d marked days underlined in %s, a colour no season wears" % (
        len(marks), MARK_RGB)


@case
def t_the_pool_holds_a_full_year():
    """A short pool does not error - Bar() just stops - so the count has to be asserted."""
    lua, g = build()
    bars, _, _, page, _ = draw(lua, g)
    used = int(page.bar_n)
    assert used <= BAR_POOL, "%d cells drawn, the pool holds %d" % (used, BAR_POOL)
    assert used >= 45, "only %d cells drawn; the grid is not being filled" % used
    # the control: squeeze the pool and the grid must come up short, which is exactly
    # the silent failure this guards against
    short, _, _, _, _ = draw(*build()[:2], pool=8)
    assert len(short) == 8, "a squeezed pool drew %d" % len(short)
    return "%d of %d cells used; a squeezed pool is caught" % (used, BAR_POOL)


@case
def t_the_scales_label_the_grid():
    _, scale, names, _, _ = draw(*build()[:2])
    assert [s["text"] for s in scale] == ["1", "8", "15", "22", "29"], \
        [s["text"] for s in scale]
    assert [n["text"] for n in names] == \
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
         "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], [n["text"] for n in names]
    for i, n in enumerate(names):
        assert n["y"] == GRID_Y + row_y(i + 1), \
            "%s sits at y=%d, its row is %d" % (n["text"], n["y"], GRID_Y + row_y(i + 1))
    # the label is 54 wide, so this is the real bound: past it and it hangs off the grid
    # and into the dial column, which is exactly what the forecast's 24-hour label did
    for s in scale:
        assert GRID_X <= s["x"] <= GRID_X + GRID_W - 54, \
            "day %s hangs off the grid at x=%d" % (s["text"], s["x"])
    xs = [s["x"] for s in scale]
    assert xs == sorted(xs) and len(set(xs)) == len(xs), \
        "the day marks are out of order or piled up: %s" % xs
    return "twelve month names on their rows, five day marks across the top"


@case
def t_a_leap_year_gives_february_its_day():
    """2028 has a 29 February; the row has to be one cell longer, and only that row."""
    a, _, _, pa, da = draw(*build(2026, 6, 1)[:2])
    b, _, _, pb, db = draw(*build(2028, 6, 1)[:2])
    assert da["year_len"] == 365 and db["year_len"] == 366, (da["year_len"], db["year_len"])
    ta = {"x": int(pa.today_bar.x), "y": int(pa.today_bar.y), "w": int(pa.today_bar.w)}
    tb = {"x": int(pb.today_bar.x), "y": int(pb.today_bar.y), "w": int(pb.today_bar.w)}
    feb_a = sum((r["w"] + 1) // CELL_W for r in runs_in(a, 2, ta))
    feb_b = sum((r["w"] + 1) // CELL_W for r in runs_in(b, 2, tb))
    assert (feb_a, feb_b) == (28, 29), (feb_a, feb_b)
    mar_a = sum((r["w"] + 1) // CELL_W for r in runs_in(a, 3, ta))
    mar_b = sum((r["w"] + 1) // CELL_W for r in runs_in(b, 3, tb))
    assert mar_a == mar_b == 31, "March changed length: %d vs %d" % (mar_a, mar_b)
    return "February goes 28 to 29 in a leap year and March does not move"


@case
def t_the_grid_wears_the_dial_s_colours():
    """The two pictures of the year have to agree.

    The grid's palette is a hand-written copy of what build_season_dial.py computes from
    the season grades, because deriving it in Lua would mean shipping the grade maths
    twice. A copy drifts the moment a grade is edited - it already had, by enough that
    the dial's spring was (175,235,175) against the page's (122,158,104) - so the copy is
    checked against its source here rather than trusted.
    """
    import build_season_dial

    dim = float(re.search(r"local SEASON_DIM\s*=\s*([0-9.]+)", SRC).group(1))
    block = re.search(r"local SEASON_RGB = \{(.*?)\n\}", SRC, re.S).group(1)
    have = {k: tuple(int(v) for v in vs.split(","))
            for k, vs in re.findall(r"(\w+)\s*=\s*\{([^}]+)\}", block)}
    want = build_season_dial.season_colors()
    assert set(have) == {"spring", "summer", "autumn", "winter", "winter_snow"}, have
    for k, got in sorted(have.items()):
        exp = tuple(int(round(c * dim)) for c in want[k])
        assert all(abs(a - b) <= 1 for a, b in zip(got, exp)), \
            "%s is %s, the dial dimmed by %.2f gives %s" % (k, got, dim, exp)
    # and the control: the factor has to be doing something, or "dimmed" is a fiction
    assert 0.5 <= dim < 1.0, dim
    return "all five seasons match the dial's arcs dimmed by %.2f" % dim


@case
def t_the_page_reports_where_today_falls():
    _, _, _, _, d = draw(*build(2026, 9, 22)[:2])
    assert d["doy"] == 265, d["doy"]
    assert d["year_len"] == 365, d["year_len"]
    spans = sum(s["span"] for s in d["seasons"].values())
    assert spans == d["year_len"], "the seasons total %d days, the year is %d" % (
        spans, d["year_len"])
    return "day 265 of 365, and the five seasons total exactly one year"


@case
def t_an_event_day_alarms_and_an_ordinary_day_breathes():
    """The rhythm is the information, so both rhythms have to be real.

    Today is not one of the six, so none of this can be seen in game until 2 October -
    which is exactly why it is pinned here instead of waited for.
    """
    assert "self.alert = (d.marked ~= nil)" in SRC, "Fill no longer arms the alarm"

    def colours(page, g, ms):
        g.time_global = lambda: ms
        g.SeasonsPDA.Update(page)
        line = page.marked.col
        cell = page.today_bar.col
        return ((line["r"], line["g"], line["b"]) if line else None,
                (cell["r"], cell["g"], cell["b"]), cell["a"])

    # --- 2 October: an anniversary, so the Zone gets loud ---------------------
    lua, g = build(2026, 10, 2)
    _, _, _, page, data = draw(lua, g)
    assert data["marked"] is not None, "2 October is not reported as marked"
    assert data["marked"]["kind"] == "anniversary", data["marked"]["kind"]
    page.marked, page.alert = g.mkwidget(), True

    # a 900ms square pulse: hot for the first 55%, cool after
    hot_line, hot_cell, hot_a = colours(page, g, 0)
    cool_line, cool_cell, cool_a = colours(page, g, 700)
    assert hot_line == MARK_RGB, hot_line
    assert hot_cell == MARK_RGB, hot_cell
    assert cool_line != MARK_RGB and cool_cell != MARK_RGB, (cool_line, cool_cell)
    assert cool_line == cool_cell, "the line and the cell are out of step"
    # it never stops being red - a pulse, not a blink
    assert cool_line[0] > cool_line[1] and cool_line[0] > cool_line[2], cool_line
    assert hot_a == cool_a == 255, (hot_a, cool_a)

    # --- an ordinary day: the slow breath, and the event line untouched -------
    lua2, g2 = build(2026, 9, 23)
    _, _, _, plain, plain_data = draw(lua2, g2)
    assert plain_data["marked"] is None, "23 September reads as a marked day"
    plain.marked, plain.alert = g2.mkwidget(), False
    alphas = set()
    for ms in (0, 600, 1200, 1800):
        g2.time_global = lambda ms=ms: ms
        g2.SeasonsPDA.Update(plain)
        alphas.add(plain.today_bar.col["a"])
    assert len(alphas) > 1, "the ordinary-day cell is not breathing: %s" % alphas
    assert max(alphas) <= 255 and min(alphas) >= 150, alphas
    assert plain.marked.col is None, "an ordinary day coloured the event line"
    return "2 Oct alarms at 900ms on both, 23 Sep breathes %s and leaves the line alone" \
        % sorted(alphas)


@case
def t_the_page_says_nothing_about_the_mod():
    """Staged mod names are an install's business, not the Zone's.

    They were on this page and read as what they are: MO2 folder strings. There is no
    reliable way to turn an author-chosen folder name into something a stalker would say,
    so the page does not try - and this fails if the wiring ever comes back.
    """
    # the field accesses, not bare words: "an extra crop of artefacts" is a sentence
    # about the Zone and matched a substring test for "extra"
    for name in ("mod_list", "d.extra", "staged_for", "m.enabled", "m.wanted",
                 "On the calendar"):
        assert name not in SRC, "the page still reaches for %s" % name
    # and the control: the data layer still publishes it, for MCM
    data = io.open(os.path.join(SCRIPTS, "zzz_seasons_of_the_zone.script"),
                   encoding="utf-8").read()
    assert "function mod_list()" in data, "mod_list() is gone from the data layer"
    mcm = io.open(os.path.join(SCRIPTS, "zzz_seasons_of_the_zone_mcm.script"),
                  encoding="utf-8").read()
    assert "mod_list()" in mcm, "MCM no longer lists the staged mods"
    return "no mod data on the page; MCM still carries it"


if __name__ == "__main__":
    print("  running the shipped calendar page under Lua")
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-36s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-36s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-36s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
