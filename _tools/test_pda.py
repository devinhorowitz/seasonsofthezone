"""Run the SHIPPED PDA wiring under a real Lua runtime: one app, two faces, one router.

The Year and Forecast are one app now. Mod App Creator shows a single tile, a switch at the top
of each page moves between the two faces, and sotz_pda.script routes both PDA sections itself.
It has to: only one of the two is a MAC tile, so MAC's own wrapper has never heard of the other,
and without the router the switch would lead nowhere.

That router sits in the path of EVERY PDA tab, which is why it gets its own suite. A mistake in
it does not break this mod's pages - it breaks the player's whole PDA. So these cases pin that it
claims only its own two sections, hands every other one down with all its arguments, contains
a page that fails to build, never wraps twice, and works whichever order it and MAC install in.

  python _tools/test_pda.py
"""
import io
import os
import re
import sys

from lua_runtime import LuaRuntime, NAME as LUA_NAME

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata", "scripts")

AMBER = (238, 196, 112)

PRELUDE = """
function load_in(src, name, shared)
    local env = setmetatable({}, {__index = shared})
    local f, err = load(src, name, "t", env)
    if not f then error(name .. ": " .. tostring(err)) end
    f()
    return env
end

function mkwidget(id)
    local s = {id = id, enabled = true}
    function s:InitTexture(t)   self.tex = t end
    function s:Enable(on)       self.enabled = on and true or false end
    function s:SetTextColor(c)  self.col = c end
    function s:SetText(t)       self.text = t end
    return s
end

function mkxml()
    local x = {}
    function x:Init3tButton(id)  return mkwidget(id) end
    function x:InitTextWnd(id)   return mkwidget(id) end
    return x
end

-- A page object as the engine would hand InitToggle one: its own xml, and Register /
-- AddCallback recording what was wired rather than wiring it.
function mkpage(cls)
    local p = setmetatable({xml = mkxml(), registered = {}, callbacks = {}}, {__index = cls})
    function p:Register(w, name) self.registered[name] = w end
    function p:AddCallback(name, ev, fn, obj) self.callbacks[name] = {fn = fn, obj = obj} end
    return p
end

-- Mod App Creator's own wrapper, verbatim in shape from mac_mcm.mac_handle_tabs: it claims
-- the launcher and every REGISTERED app's tab, and hands the rest to what it wrapped.
function mac_wrap(apps)
    local mac_main = pda.set_active_subdialog
    pda.set_active_subdialog = function(section)
        if section == "eptLauncher" then return "MAC_LAUNCHER" end
        for _, app in pairs(apps) do
            if app.tab == section and app.func then return app.func() end
        end
        return mac_main(section)
    end
end
"""


def load(fname, g, lua):
    src = io.open(os.path.join(SCRIPTS, fname), encoding="utf-8").read()
    return g.load_in(src, fname, g)


def build(forecast_fails=False):
    """A sandbox with the base PDA router, both pages stubbed, and sotz_pda loaded."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    lua.execute(PRELUDE)
    g.printf = lambda *a: None
    g.GetARGB = lambda a, r, gg, b: lua.table_from({"a": a, "r": r, "g": gg, "b": b})
    g.ui_events = lua.table_from({"BUTTON_CLICKED": 17})

    # the base game's router: records what reached it, with every argument
    seen = []

    def base(section, *rest):
        seen.append((section,) + tuple(rest))
        return "BASE:" + str(section)
    g.pda = lua.table_from({"set_active_subdialog": base})

    def year_ui():
        return "YEAR_PAGE"

    def fc_ui():
        if forecast_fails:
            raise RuntimeError("forecast page would not build")
        return "FORECAST_PAGE"
    g.ui_seasons_pda = lua.table_from({"get_ui": year_ui})
    g.ui_seasons_forecast = lua.table_from({"get_ui": fc_ui})

    # the section the PDA was last told to show
    opened = []
    menu = lua.table_from({"SetActiveSubdialog": lambda self, tab: opened.append(tab)})
    g.ActorMenu = lua.table_from({"get_pda_menu": lambda: menu})

    # on_game_start registers the router on on_game_load; capture it to call by hand
    hooks = {}
    g.RegisterScriptCallback = lambda name, fn: hooks.setdefault(name, []).append(fn)
    g.sotz_pda = load("sotz_pda.script", g, lua)
    g.sotz_pda.on_game_start()
    return lua, g, seen, opened, hooks


def install(hooks):
    for fn in hooks.get("on_game_load", []):
        fn()


CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_routes_both_faces():
    lua, g, seen, _, hooks = build()
    install(hooks)
    route = g.pda.set_active_subdialog
    assert route("eptSeasons") == "YEAR_PAGE", route("eptSeasons")
    assert route("eptForecast") == "FORECAST_PAGE", route("eptForecast")
    assert seen == [], "one of the app's own sections leaked through to the base game: %s" % seen
    return "eptSeasons -> The Year, eptForecast -> Forecast, neither reaches the base game"


@case
def t_hands_every_other_tab_down_whole():
    """Every PDA tab passes through here. The rest must arrive unchanged."""
    lua, g, seen, _, hooks = build()
    install(hooks)
    route = g.pda.set_active_subdialog
    assert route("eptRelations") == "BASE:eptRelations"
    # an argument upstream might add one day must survive the trip
    route("eptContacts", "extra", 7)
    assert seen[-1] == ("eptContacts", "extra", 7), seen[-1]
    return "other tabs reach the base game with every argument intact"


@case
def t_a_broken_page_does_not_take_the_pda_down():
    lua, g, seen, _, hooks = build(forecast_fails=True)
    install(hooks)
    route = g.pda.set_active_subdialog
    # the broken face comes back empty rather than raising through the PDA
    assert route("eptForecast") is None, "a failing page escaped the router"
    # and the rest of the PDA is untouched by it
    assert route("eptTasks") == "BASE:eptTasks"
    assert route("eptSeasons") == "YEAR_PAGE"
    return "a page that fails to build is contained; every other tab still works"


@case
def t_wraps_once():
    """on_game_load fires on every save load. A second wrap would stack the router."""
    lua, g, seen, _, hooks = build()
    install(hooks)
    # Compared inside Lua, by identity. lupa may hand Python a fresh proxy for the same
    # function on every read, so a Python `==` proves nothing either way. And counting
    # passthroughs cannot catch a double wrap at all - a stacked router still reaches the
    # base game once - so the check is on the function's identity.
    lua.execute("FIRST_ROUTER = pda.set_active_subdialog")
    install(hooks)
    install(hooks)
    same = lua.eval("pda.set_active_subdialog == FIRST_ROUTER")
    assert same, "the router wrapped itself again on a later load"
    return "three loads, and the router is the same function after all of them"


@case
def t_lives_with_mac_in_either_order():
    """MAC wraps on on_game_load too. Whichever wraps last is outer; both orders must work."""
    for order in ("mac_outer", "ours_outer"):
        lua, g, seen, _, hooks = build()
        # MAC's app list as the registration builds it: ONE tile, on The Year
        apps = lua.table_from({"app_seasons": lua.table_from({
            "tab": "eptSeasons", "func": g.ui_seasons_pda.get_ui})})
        if order == "mac_outer":
            install(hooks)
            g.mac_wrap(apps)
        else:
            g.mac_wrap(apps)
            install(hooks)
        route = g.pda.set_active_subdialog
        assert route("eptSeasons") == "YEAR_PAGE", (order, route("eptSeasons"))
        # the face with no tile: MAC has never heard of it, so this is the case that needs
        # the router at all
        assert route("eptForecast") == "FORECAST_PAGE", (order, route("eptForecast"))
        assert route("eptLauncher") == "MAC_LAUNCHER", (order, route("eptLauncher"))
        assert route("eptRadio") == "BASE:eptRadio", (order, route("eptRadio"))
    # the control: MAC alone cannot reach the face that has no tile
    lua, g, seen, _, hooks = build()
    g.mac_wrap(lua.table_from({"app_seasons": lua.table_from({
        "tab": "eptSeasons", "func": g.ui_seasons_pda.get_ui})}))
    assert g.pda.set_active_subdialog("eptForecast") != "FORECAST_PAGE", \
        "MAC reached Forecast without the router, so this test proves nothing"
    return "works MAC-outer and ours-outer; MAC alone cannot reach Forecast"


@case
def t_one_tile():
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    lua.execute(PRELUDE)
    g.printf = lambda *a: None
    tiles = []

    def add_app(app_id, data):
        tiles.append((app_id, data.name, data.tab))
    g.mac_mcm = lua.table_from({"add_app": add_app})
    g.zzz_seasons_of_the_zone = lua.table_from({
        "calendar_page": lambda: lua.table_from({"season": "autumn"})})
    g.ui_seasons_pda = lua.table_from({"get_ui": lambda: None})
    g.ui_seasons_forecast = lua.table_from({"get_ui": lambda: None})
    g.RegisterScriptCallback = lambda *a: None
    g.sotz_pda = load("sotz_pda.script", g, lua)
    reg = load("z_seasons_pda_mac.script", g, lua)
    reg.on_game_start()
    assert len(tiles) == 1, "%d tiles in the launcher: %s" % (len(tiles), tiles)
    app_id, name, tab = tiles[0]
    assert tab == "eptSeasons", tab
    # the tile's own label, so the section titles can stay "The Year" and "Forecast"
    assert name == "pda_app_seasons", name
    # the control: no MAC, no tile, and no error
    g.mac_mcm = None
    tiles.clear()
    reg.on_game_start()
    assert tiles == [], tiles
    return "one tile, on The Year, labelled Seasons; nothing and no error without MAC"


def switch(page_file, cls, lua, g, opened):
    load(page_file, g, lua)
    p = g.mkpage(g[cls])
    g[cls].InitToggle(p)
    return p


@case
def t_the_switch_on_each_page():
    lua, g, _, opened, _ = build()
    lua.execute("class = function(n) return function(b) local t = {}; t.__index = t; "
                "_G[n] = t; return t end end; super = function() end")
    g.CUIScriptWnd = lua.table_from({})

    for page_file, cls, here, away, goes_to in (
            ("ui_seasons_pda.script", "SeasonsPDA", "toggle_year", "toggle_fc",
             "eptForecast"),
            ("ui_seasons_forecast.script", "SeasonsForecast", "toggle_fc", "toggle_year",
             "eptSeasons")):
        p = switch(page_file, cls, lua, g, opened)
        mine, other = p[here], p[away]
        # this page's own half: pressed in, amber, and wired to nothing
        assert mine.enabled is False, "%s: its own half is still clickable" % cls
        lbl = p[here + "_label"]
        assert (lbl.col.r, lbl.col.g, lbl.col.b) == AMBER, "%s: own half not amber" % cls
        assert here not in p.callbacks, "%s: clicking its own half does something" % cls
        # the other half: live, and it goes to the other face
        assert other.enabled is True, "%s: the other half is disabled" % cls
        cb = p.callbacks[away]
        del opened[:]
        cb.fn(cb.obj)
        assert list(opened) == [goes_to], "%s: switch opened %s" % (cls, list(opened))
        # both halves say what they are, the same words on both pages
        assert p["toggle_year_label"].text == "The Year"
        assert p["toggle_fc_label"].text == "Forecast"
    return "each page lights its own half and sends the other to the other face"


@case
def t_one_name_for_each_section():
    """Four files name the two sections. If they disagree, a face is unreachable, silently."""
    read = lambda f: io.open(os.path.join(SCRIPTS, f), encoding="utf-8").read()
    views = dict(re.findall(r'(\w+)\s*=\s*\{tab = "(ept\w+)"', read("sotz_pda.script")))
    assert views == {"year": "eptSeasons", "forecast": "eptForecast"}, views
    injected = set(re.findall(r'id = "(ept\w+)"', read("modxml_seasons_pda.script")))
    assert injected == set(views.values()), \
        "the xml injection parks %s, the router claims %s" % (injected, set(views.values()))
    # the registration and both switches name them through sotz_pda, not by hand
    for f in ("z_seasons_pda_mac.script", "ui_seasons_pda.script",
              "ui_seasons_forecast.script"):
        src = read(f)
        code = "\n".join(line.split("--", 1)[0] for line in src.splitlines())
        stray = set(re.findall(r'"(eptSeasons|eptForecast)"', code))
        assert not stray, "%s spells %s out by hand instead of using sotz_pda.VIEWS" % (
            f, stray)
    return "sotz_pda, the xml injection and every caller agree on both section ids"


if __name__ == "__main__":
    print("  running the shipped PDA wiring under %s" % LUA_NAME)
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-40s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-40s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-40s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
