"""Run the SHIPPED PDA wiring under a real Lua runtime: one app, two faces, one router.

The Year and Forecast are one app now. Mod App Creator shows a single tile, a switch at the top
of each page moves between the two faces, and sotz_pda.script routes both PDA sections itself.
It has to: only one of the two is a MAC tile, so MAC's own wrapper has never heard of the other,
and without the router the switch would lead nowhere.

That router sits in the path of EVERY PDA tab, which is why it gets its own suite. A mistake in
it does not break this mod's pages - it breaks the player's whole PDA. So these cases pin that it
claims only its own two sections, hands every other one down with all its arguments, contains
a page that fails to build, never wraps twice, and works whichever order it and MAC install in.

Then the tab bar hook (modxml_seasons_pda): only ui/pda.xml and ui/pda_16.xml, only the <tab>
of the PDA's own sections, and a parked Launcher when MAC is installed but another mod's bar
won. And the app key: the shipped page scripts opened flat, switched, and closed.

And the tab of its own, against stand-ins for Modded Exes' tab registry, MAC, MCM and the PDA:
it comes only in play, a second after the first update (one added during a load crashed the
game, 2026-10-11); with MAC when MCM asks for it or the bar has no Launcher, in place of the
tile; without MAC always; without the registry never. The option adds or takes away the tab
once the game runs again, and the tile the other way round; a tab taken away while it was the
PDA's last section sends the PDA to Tasks. Back and Escape lead to the launcher only while
the tile is there, and Forecast's switch comes back to the tab.

  python _tools/test_pda.py
"""
import io
import os
import re
import sys

from lua_runtime import LuaRuntime, NAME as LUA_NAME
from test_strings import install as install_strings

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
    # the switch labels are string ids, read through sotz_text
    install_strings(lua, g)

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
    got = attempt(route, "eptForecast")
    assert got is None, "a failing page escaped the router: %s" % got
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
        # both halves say what they are, the same words on both pages, from the table
        assert p["toggle_year_label"].text == "The Year"
        assert p["toggle_fc_label"].text == "Forecast"
    return "each page lights its own half and sends the other to the other face"


def rgb(col):
    return (col.r, col.g, col.b)


@case
def t_the_foot_of_each_page():
    """Silence is MCM's "PDA notifications" seen on the page: it writes the option, lit with an
    amber label while the messages are off, and shows a change made in MCM at the next open.
    Under it, the mod's name, version and author."""
    lua, g, _, opened, _ = build()
    lua.execute("class = function(n) return function(b) local t = {}; t.__index = t; "
                "_G[n] = t; return t end end; super = function() end")
    g.CUIScriptWnd = lua.table_from({})
    options = {}
    g.ui_mcm = lua.table_from({"get": lambda path: options.get(str(path)),
                               "set": lambda path, v: options.__setitem__(str(path), v)})
    path = str(g.sotz_pda.NEWS_PATH)
    assert path == "seasons_zone/main/pda_news", path
    credit = "Seasons of the Zone v%s by %s" % (g.sotz_pda.VERSION, g.sotz_pda.AUTHOR)
    gray = (200, 200, 200)
    for page_file, cls in (("ui_seasons_pda.script", "SeasonsPDA"),
                           ("ui_seasons_forecast.script", "SeasonsForecast")):
        options.clear()
        load(page_file, g, lua)
        p = g.mkpage(g[cls])
        g[cls].InitFooter(p)
        btn, lbl = p.silence, p.silence_label
        assert lbl.text == "Silence", "%s: %r" % (cls, lbl.text)
        assert p.credit.text == credit, "%s: %r" % (cls, p.credit.text)
        # on as it ships: the plain plate and a gray label
        assert btn.tex == "sotz_btn" and rgb(lbl.col) == gray, (cls, btn.tex, rgb(lbl.col))
        cb = p.callbacks["silence"]
        cb.fn(cb.obj)
        assert options.get(path) is False, "%s: Silence wrote %r" % (cls, options)
        assert btn.tex == "sotz_btn_on" and rgb(lbl.col) == AMBER, (cls, btn.tex, rgb(lbl.col))
        cb.fn(cb.obj)
        assert options.get(path) is True, "%s: a second click wrote %r" % (cls, options)
        assert btn.tex == "sotz_btn" and rgb(lbl.col) == gray, (cls, btn.tex, rgb(lbl.col))
        # turned off in MCM: the page shows it the next time it opens
        options[path] = False
        g[cls].Reset(p)
        assert btn.tex == "sotz_btn_on" and rgb(lbl.col) == AMBER, (cls, btn.tex, rgb(lbl.col))
    assert list(opened) == [], "the footer went through the PDA: %s" % list(opened)
    return "Silence writes and shows MCM's option on both pages; the credit names %s" \
        % g.sotz_pda.VERSION


@case
def t_the_pages_name_the_release():
    """The credit's version is sotz_pda's VERSION, and season.py's VERSION names the release:
    they have to agree, or a screenshot names the wrong one. build_release.py refuses too."""
    src = io.open(os.path.join(ROOT, "_tools", "season.py"), encoding="utf-8").read()
    want = re.search(r'(?m)^VERSION\s*=\s*"([^"]+)"', src).group(1)
    lua, g, _, _, _ = build()
    assert g.sotz_pda.VERSION == want, "the pages show %s, season.py says %s" % (
        g.sotz_pda.VERSION, want)
    assert g.sotz_pda.AUTHOR == "Windwalker", g.sotz_pda.AUTHOR
    return "the pages show %s, season.py's VERSION, by %s" % (want, g.sotz_pda.AUTHOR)


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


# --- the tab bar: which file, which <tab>, and MAC's Launcher -----------------------------------
#
# The bar is ui/pda_16.xml (and ui/pda.xml, which includes it), and several mods ship it
# whole. These run the shipped modxml_seasons_pda.script over bars shaped like MAC's and like
# a mod's that adds tabs of its own and has no Launcher (INTERFECTOR's PDA Trading), through a
# stand-in for DXML that does what DXML does: query hands back the <tab> elements, and
# insertFromXMLString appends the button the string describes.

DXML = r"""
function mktab(ids)
    local el = {name = "tab", kids = {}}
    for _, id in ipairs(ids) do
        if id == "caption" then
            el.kids[#el.kids + 1] = {name = "caption", attribs = {}}
        else
            el.kids[#el.kids + 1] = {name = "button", attribs = {id = id}}
        end
    end
    return el
end

function mkdxml(tabs)
    local o = {tabs = tabs, inserted = {}}
    function o:query(q)
        if q ~= "tab" then error("unexpected query " .. tostring(q)) end
        return self.tabs
    end
    function o:insertFromXMLString(s, where)
        local id = s:match('id="([^"]+)"')
        local parked = s:match('x="1000"') ~= nil and s:match('width="0"') ~= nil
        where.kids[#where.kids + 1] = {name = "button", attribs = {id = id}, parked = parked}
        self.inserted[#self.inserted + 1] = id
    end
    return o
end

function ids_of(el)
    local t = {}
    for _, k in ipairs(el.kids) do
        t[#t + 1] = (k.name == "button") and k.attribs.id or k.name
    end
    return t
end
"""

MAC_BAR = ["eptTasks", "eptLauncher", "eptRanking", "eptRelations", "eptContacts",
           "eptEncyclopedia", "eptRadio", "eptLogs", "eptTaskboard", "eptInteractive"]
OTHER_BAR = ["eptTasks", "eptTaskboard", "eptRanking", "eptRelations", "eptContacts",
             "eptEncyclopedia", "eptRadio", "eptTrading", "eptLogs"]


def load_modxml(mac):
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    lua.execute(PRELUDE)
    lua.execute(DXML)
    logs = []
    g.printf = lambda fmt, *a: logs.append(str(a[0]) if a else str(fmt))
    g.dxml_core = lua.table_from({})
    g.mac_mcm = lua.table_from({"add_app": lambda *a: None}) if mac else None
    hooks = {}
    g.RegisterScriptCallback = lambda name, fn: hooks.setdefault(name, []).append(fn)
    mod = load("modxml_seasons_pda.script", g, lua)
    mod.on_game_start()
    return lua, g, mod, hooks["on_xml_read"][0], logs


def lseq(t):
    return [t[i] for i in range(1, len(t) + 1)]


@case
def t_the_tab_bar_files_and_no_others():
    lua, g, mod, read_xml, _ = load_modxml(mac=True)
    for name in ("ui\\pda.xml", "ui\\pda_16.xml", "ui/pda_16.xml", "UI\\PDA_16.XML"):
        assert mod.is_bar_file(name) is True, "%s is the tab bar and was refused" % name
    for name in ("ui\\pda_relations_16.xml", "ui\\pda_taskboard_16.xml", "ui\\pda_apps_16.xml",
                 "ui\\pda_xcvb.xml", "ui\\pda_trading_16.xml", "ui\\pda_relations_f10.xml",
                 "gameplay\\pda_16.xml", "ui\\pda_16.xml.bak"):
        assert mod.is_bar_file(name) is False, "%s is not the tab bar and was taken" % name
    # through the callback: another PDA page, even one with sections in a <tab>, is left alone
    tab = g.mktab(lua.table_from(["eptTasks", "eptTrading"]))
    x = g.mkdxml(lua.table_from([tab]))
    read_xml("ui\\pda_trading_16.xml", x)
    assert lseq(x.inserted) == [], "a page other than the bar got %s" % lseq(x.inserted)
    assert mod.tab_bar() is None, "a page other than the bar was recorded as the bar"
    return "ui/pda.xml and ui/pda_16.xml only; pda_relations_16.xml and the rest untouched"


@case
def t_both_faces_parked_in_macs_bar():
    lua, g, mod, read_xml, logs = load_modxml(mac=True)
    bar = g.mktab(lua.table_from(MAC_BAR))
    read_xml("ui\\pda_16.xml", g.mkdxml(lua.table_from([bar])))
    ids = lseq(g.ids_of(bar))
    assert ids == MAC_BAR + ["eptSeasons", "eptForecast"], ids
    kids = lseq(bar.kids)
    assert all(k.parked for k in kids[-2:]), "a face was added visible"
    st = mod.tab_bar()
    assert st.launcher is True and st.parked_launcher is False, (st.launcher, st.parked_launcher)
    # read again, as on the next level: nothing twice
    again = g.mkdxml(lua.table_from([bar]))
    read_xml("ui\\pda_16.xml", again)
    assert lseq(again.inserted) == [], "a second read added %s again" % lseq(again.inserted)
    return "two parked sections after MAC's own; the Launcher left as it is; no duplicates"


@case
def t_a_bar_without_the_launcher():
    """Another mod's pda_16.xml won over MAC's: its own tabs, no Launcher. With MAC, a parked
    Launcher keeps MAC's key and this app's Back working; without MAC, none is added."""
    for mac in (True, False):
        lua, g, mod, read_xml, logs = load_modxml(mac=mac)
        bar = g.mktab(lua.table_from(OTHER_BAR))
        x = g.mkdxml(lua.table_from([bar]))
        read_xml("ui\\pda_16.xml", x)
        want = ["eptSeasons", "eptForecast"] + (["eptLauncher"] if mac else [])
        assert lseq(x.inserted) == want, (mac, lseq(x.inserted))
        assert lseq(g.ids_of(bar))[:len(OTHER_BAR)] == OTHER_BAR, "the bar's own tabs moved"
        assert all(k.parked for k in lseq(bar.kids)[len(OTHER_BAR):]), "an addition shows"
        st = mod.tab_bar()
        assert st.launcher is False, "a bar without the Launcher recorded as having it"
        assert st.parked_launcher is mac, (mac, st.parked_launcher)
        said = [l for l in logs if "no Launcher tab" in l]
        assert len(said) == (1 if mac else 0), (mac, logs)
    return "with MAC a Launcher is parked and logged once; without MAC, nothing of MAC's"


@case
def t_the_sections_tab_not_the_first_tab():
    """A <tab> that is a plain container (pda_relations_16.xml has one) must never get the
    sections; the bar is the <tab> holding ept... buttons, wherever it sits."""
    lua, g, mod, read_xml, _ = load_modxml(mac=False)
    box = g.mktab(lua.table_from(["caption"]))
    bar = g.mktab(lua.table_from(["eptTasks", "eptLauncher", "eptLogs"]))
    read_xml("ui\\pda_16.xml", g.mkdxml(lua.table_from([box, bar])))
    assert lseq(g.ids_of(box)) == ["caption"], "the container got %s" % lseq(g.ids_of(box))
    assert lseq(g.ids_of(bar))[-2:] == ["eptSeasons", "eptForecast"], lseq(g.ids_of(bar))
    # a bar file with no section tab at all (a mod's odd copy): no error, nothing recorded
    lua, g, mod, read_xml, logs = load_modxml(mac=True)
    x = g.mkdxml(lua.table_from([g.mktab(lua.table_from(["caption"]))]))
    read_xml("ui\\pda_16.xml", x)
    assert lseq(x.inserted) == [] and mod.tab_bar() is None, lseq(x.inserted)
    assert not [l for l in logs if "failed" in l], logs
    return "the sections go to the tab of sections, not the first <tab> in the file"


# --- the app key and the flat windows -----------------------------------------------------------
#
# The shipped sotz_pda.script and both page scripts, with the engine reduced to what the flat
# path touches: a window that is shown or not, MCM's stored key, and an actor alive or not.

FLAT = r"""
class = function(n) return function(b) local t = {}; t.__index = t; _G[n] = t; return t end end
super = function() end
made = {}
function make_window(cls, flat)
    local w = setmetatable({flat = flat, shown = false, fills = 0, hides = 0}, cls)
    function w:IsShown() return self.shown end
    function w:ShowDialog() self.shown = true end
    function w:HideDialog() self.shown = false; self.hides = self.hides + 1 end
    function w:Fill() self.fills = self.fills + 1 end
    made[#made + 1] = w
    return w
end
function constructible(cls)
    setmetatable(cls, {__call = function(c, flat) return make_window(c, flat) end})
end
"""

KEY = 59           # DIK_F1, as a player might bind it
ESC = 1


def build_flat(key=KEY, alive=True, mcm_raises=False, saved=None):
    lua, g, seen, opened, hooks = build()
    lua.execute(FLAT)
    # the app's tile in MAC's launcher, as it is with MAC and no tab of its own
    g.z_seasons_pda_mac = lua.table_from({"has_tile": lambda: True})
    g.CUIScriptWnd = lua.table_from({"OnKeyboard": lambda *a: False})
    g.ui_events = lua.table_from({"BUTTON_CLICKED": 17, "WINDOW_KEY_PRESSED": 6})
    g.DIK_keys = lua.table_from({"DIK_ESCAPE": ESC})

    def get(path):
        if mcm_raises:
            raise RuntimeError("ui_mcm.get asserts while MCM builds its page")
        return key if str(path) == "seasons_zone/main/app_key" else None
    g.ui_mcm = lua.table_from({"get": get})
    stored = key if saved is None else saved
    g.axr_main = lua.table_from({"config": lua.table_from({
        "r_value": lambda self, sec, k, typ, d: stored if str(k) == "seasons_zone/main/app_key"
        else d})})
    actor = lua.table_from({"alive": lambda self: alive})
    g.db = lua.table_from({"actor": actor})
    # _g.script's time events: kept here, run by tick(); one that returns true is done
    timers = {}

    def create_time_event(ev, act, delay, fn, *args):
        timers[(str(ev), str(act))] = (fn, args)

    def tick():
        for k, (fn, args) in list(timers.items()):
            if fn(*args):
                timers.pop(k, None)
    g.CreateTimeEvent = create_time_event
    hooks["tick"] = tick
    g.ui_seasons_pda = load("ui_seasons_pda.script", g, lua)
    g.ui_seasons_forecast = load("ui_seasons_forecast.script", g, lua)
    g.constructible(g.SeasonsPDA)
    g.constructible(g.SeasonsForecast)
    return lua, g, opened, hooks


def shown(g):
    out = []
    if g.ui_seasons_pda.flat_window():
        out.append("year")
    if g.ui_seasons_forecast.flat_window():
        out.append("forecast")
    return out


def engine_press(g, hooks, key):
    """A key press in the order Level_input.cpp handles it: the scripts' on_key_press first,
    then the UI's top window, which by then may be one the scripts just opened; time events
    run on a later update."""
    hooks["on_key_press"][0](key)
    for mod, cls in (("ui_seasons_pda", "SeasonsPDA"), ("ui_seasons_forecast", "SeasonsForecast")):
        w = g[mod].flat_window()
        if w:
            g[cls].OnKeyboard(w, key, g.ui_events.WINDOW_KEY_PRESSED)
            break
    hooks["tick"]()


@case
def t_the_key_opens_the_year_flat():
    """In game the window opened and closed on one press (2026-10-06): the press that opened
    it reached it next, and the app key closes a flat face."""
    lua, g, opened, hooks = build_flat()
    engine_press(g, hooks, KEY + 1)
    assert shown(g) == [], "another key opened %s" % shown(g)
    engine_press(g, hooks, KEY)
    assert shown(g) == ["year"], "after one press of the key: %s" % shown(g)
    w = g.ui_seasons_pda.flat_window()
    assert w.flat is True and w.fills == 1, (w.flat, w.fills)
    assert list(opened) == [], "the key went through the PDA: %s" % list(opened)
    # the key again closes it, and does not open it again behind its own back
    engine_press(g, hooks, KEY)
    assert shown(g) == [], "after a second press: %s" % shown(g)
    engine_press(g, hooks, KEY)
    assert shown(g) == ["year"], "after a third press: %s" % shown(g)
    # unbound (how it ships), or the actor dead: nothing
    for kw in (dict(key=-1), dict(alive=False)):
        lua2, g2, _, hooks2 = build_flat(**kw)
        engine_press(g2, hooks2, KEY)
        assert shown(g2) == [], (kw, shown(g2))
    return "the key opens The Year, the key again closes it; unbound or dead, nothing"


@case
def t_the_switch_trades_one_window_for_the_other():
    lua, g, opened, hooks = build_flat()
    engine_press(g, hooks, KEY)
    year = g.ui_seasons_pda.flat_window()
    g.SeasonsPDA.OnToggle(year)
    assert shown(g) == ["forecast"], "after the switch on The Year: %s" % shown(g)
    fc = g.ui_seasons_forecast.flat_window()
    assert fc.flat is True, "Forecast opened in the PDA's place, not flat"
    # identity compared inside Lua: two lupa proxies of one table need not be == in Python
    lua.execute("FIRST_FORECAST = ui_seasons_forecast.flat_window()")
    g.SeasonsForecast.OnToggle(fc)
    assert shown(g) == ["year"], "after the switch on Forecast: %s" % shown(g)
    assert list(opened) == [], "a flat switch went through the PDA: %s" % list(opened)
    # one window per face, however often: the same one comes back, filled afresh, and asking
    # for a face already open leaves it as it is
    hooks["on_key_press"][0](KEY)
    g.ui_seasons_pda.open_flat()
    assert g.ui_seasons_pda.flat_window().fills == 2, g.ui_seasons_pda.flat_window().fills
    g.SeasonsPDA.OnToggle(g.ui_seasons_pda.flat_window())
    assert shown(g) == ["forecast"], shown(g)
    assert lua.eval("ui_seasons_forecast.flat_window() == FIRST_FORECAST"), \
        "Forecast came back as a new window"
    assert len(g.made) == 2, "%d windows made for two faces" % len(g.made)
    # and in the PDA the switch still goes through the PDA's sections
    page = g.make_window(g.SeasonsPDA, False)
    g.SeasonsPDA.OnToggle(page)
    assert list(opened) == ["eptForecast"], list(opened)
    return "flat, each switch closes one window and opens the other; in the PDA, sections"


@case
def t_what_closes_a_flat_face():
    lua, g, opened, hooks = build_flat()
    pressed = g.ui_events.WINDOW_KEY_PRESSED
    for cls, mod in (("SeasonsPDA", "ui_seasons_pda"), ("SeasonsForecast", "ui_seasons_forecast")):
        for how in ("escape", "key", "back"):
            g[mod].open_flat()
            w = g[mod].flat_window()
            if how == "back":
                g[cls].OnBack(w)
            else:
                took = g[cls].OnKeyboard(w, ESC if how == "escape" else KEY, pressed)
                assert took is True, "%s: %s not taken" % (cls, how)
            assert g[mod].flat_window() is None, "%s: %s left the window open" % (cls, how)
        assert list(opened) == [], "%s: closing went through the PDA: %s" % (cls, list(opened))
        # in the PDA the app key is not the page's to take, and Escape goes to the launcher
        page = g.make_window(g[cls], False)
        assert g[cls].OnKeyboard(page, KEY, pressed) is False, "%s took the key in the PDA" % cls
        g[cls].OnKeyboard(page, ESC, pressed)
        assert list(opened)[-1:] == ["eptLauncher"], list(opened)
        del opened[:]
    return "Escape, the key and Back close either flat face; in the PDA, Escape goes back"


@case
def t_the_key_as_saved_skips_ui_mcm():
    """MCM's page reads the key with app_key(true): ui_mcm.get asserts while MCM builds it."""
    lua, g, opened, hooks = build_flat(mcm_raises=True)
    assert g.sotz_pda.app_key(True) == KEY, g.sotz_pda.app_key(True)
    # in play, ui_mcm first; when it cannot answer, the saved value
    assert g.sotz_pda.app_key() == KEY, g.sotz_pda.app_key()
    lua, g, opened, hooks = build_flat(key=-1, saved=-1)
    assert g.sotz_pda.app_key() is None and g.sotz_pda.app_key(True) is None
    # the saved value never overrides what MCM answers in play
    lua, g, opened, hooks = build_flat(key=KEY, saved=-1)
    assert g.sotz_pda.app_key() == KEY and g.sotz_pda.app_key(True) is None
    return "app_key(true) reads only the saved options; in play MCM answers first"


@case
def t_a_load_closes_the_flat_faces():
    """A quickload with The Year open flat crashed the game as the save came up (2026-10-11):
    the load restarts the scripts and frees the window the engine still shows, and the next
    frame draws it (AnomalyDX11AVX.exe+0x215C52, where Immersive Identification's tag dialog
    crashed). Both faces close when the level goes."""
    lua, g, opened, hooks = build_flat()
    unload = hooks.get("actor_on_net_destroy")
    assert unload, "nothing closes a flat face when the level goes"
    for face in ("year", "forecast"):
        g.sotz_pda.open_flat(face)
        assert shown(g) == [face], "opening %s flat: %s" % (face, shown(g))
        unload[0]()
        assert shown(g) == [], "a load left %s open flat" % shown(g)
    unload[0]()
    assert shown(g) == [], shown(g)
    return "a load closes whichever face is open flat, and with none open does nothing"


# --- a tab of its own ---------------------------------------------------------------------------
#
# The shipped sotz_pda.script and z_seasons_pda_mac.script over stand-ins for Modded Exes' tab
# registry (pda_dynamic_tabs), the tab control's AddTab, MAC, MCM's option (in play and as
# saved), the tab bar modxml_seasons_pda read, the PDA, and _g.script's time events.

TABS = r"""
NOW = 0
timers = {}
function CreateTimeEvent(ev_id, act_id, delay, fn, ...)
    local id = ev_id .. "/" .. act_id
    if not timers[id] then timers[id] = {at = NOW + delay, fn = fn, args = {...}} end
end
function play(seconds)
    NOW = NOW + seconds
    for id, ev in pairs(timers) do
        if NOW >= ev.at and ev.fn(unpack(ev.args)) then timers[id] = nil end
    end
end
function pending()
    local n = 0
    for _ in pairs(timers) do n = n + 1 end
    return n
end
CUITabControl = {AddTab = function() end}
calls = {}
getters = {}
SEQ = 0
REFUSE = false
pda_dynamic_tabs = {
    register = function(caption, getter, after)
        if REFUSE then error("no tab bar") end
        SEQ = SEQ + 1
        local id = "ept_dynamic_" .. SEQ
        calls[#calls + 1] = "register " .. tostring(caption) .. (after and (" after " .. tostring(after)) or "")
        getters[id] = getter
        return id
    end,
    unregister = function(id)
        calls[#calls + 1] = "unregister " .. id
        getters[id] = nil
        return true
    end,
}
tiles = {}
adds, removed = 0, 0
ADD_FAILS, REMOVE_FAILS = false, false
mac_mcm = {
    add_app = function(id, data)
        if ADD_FAILS then error("MAC refused the app") end
        adds = adds + 1
        tiles[id] = data
    end,
    remove_app = function(id)
        if REMOVE_FAILS then error("MAC kept the app") end
        removed = removed + 1
        tiles[id] = nil
    end,
}
OPTION = false
SAVED = nil
MCM_BUILDING = false
asked_while_building = 0
OFFERED = true
bad_paths = 0
ui_mcm = {get = function(path)
    if MCM_BUILDING then
        asked_while_building = asked_while_building + 1
        error("ui_mcm.get asserts while MCM builds its page")
    end
    if path == "seasons_zone/main/pda_tab" then
        -- MCM answers only for an option a page defines, and logs the rest
        if not OFFERED then bad_paths = bad_paths + 1; return nil end
        return OPTION
    end
end}
axr_main = {config = {r_value = function(self, sec, key, typ, def)
    if key == "seasons_zone/main/pda_tab" and SAVED ~= nil then return SAVED end
    return def
end}}
BAR = nil
modxml_seasons_pda = {tab_bar = function() return BAR end}
ACTIVE = "eptTasks"
opened = {}
PDA_FAILS = false
PDA = {
    GetActiveSection = function(self) if PDA_FAILS then error("no PDA yet") end return ACTIVE end,
    SetActiveSubdialog = function(self, s) opened[#opened + 1] = s; ACTIVE = s end,
}
ActorMenu = {get_pda_menu = function() return PDA end}
YEAR_FAILS = false
ui_seasons_pda = {get_ui = function() if YEAR_FAILS then error("boom") end return "YEAR_PAGE" end}
ui_seasons_forecast = {get_ui = function() return "FORECAST_PAGE" end}
pda = {set_active_subdialog = function(section) return "BASE:" .. tostring(section) end}
function mkback()
    local b = {}
    function b:Show(on) self.shown = on end
    return b
end
"""

NO_LAUNCHER = {"file": "ui\\pda_16.xml", "launcher": False, "parked_launcher": True}


def attempt(fn, *args):
    """a call's result, or the error it raised, as text"""
    try:
        return fn(*args)
    except Exception as e:
        return "error: %s" % str(e).splitlines()[0]


class Game(object):
    """One load: the Lua state anew, the scripts started, the level loaded (the tab bar read as
    the PDA is built) and the first update; `seen` is what reached the registry by each step."""

    def __init__(self, mac=True, registry=True, addtab=True, option=False, bar=None,
                 pages=False):
        lua = self.lua = LuaRuntime(unpack_returned_tuples=True)
        g = self.g = lua.globals()
        lua.execute(PRELUDE)
        lua.execute(TABS)
        self.logs = []
        g.printf = lambda fmt, *a: self.logs.append(str(a[0]) if a else str(fmt))
        self.hooks = {}
        g.RegisterScriptCallback = lambda name, fn: self.hooks.setdefault(str(name), []).append(fn)
        if not mac:
            lua.execute("mac_mcm = nil")
        if not registry:
            lua.execute("pda_dynamic_tabs = nil")
        if not addtab:
            lua.execute("CUITabControl = {}")
        g.OPTION = option
        # MCM's page defines the option where a tile and a tab can both be
        g.OFFERED = mac and registry and addtab
        g.sotz_pda = load("sotz_pda.script", g, lua)
        g.z_seasons_pda_mac = load("z_seasons_pda_mac.script", g, lua)
        if pages:
            lua.execute(FLAT)
            g.CUIScriptWnd = lua.table_from({"OnKeyboard": lambda *a: False})
            g.ui_events = lua.table_from({"BUTTON_CLICKED": 17, "WINDOW_KEY_PRESSED": 6})
            g.DIK_keys = lua.table_from({"DIK_ESCAPE": ESC})
            install_strings(lua, g)
            g.ui_seasons_pda = load("ui_seasons_pda.script", g, lua)
            g.ui_seasons_forecast = load("ui_seasons_forecast.script", g, lua)
            g.constructible(g.SeasonsPDA)
            g.constructible(g.SeasonsForecast)
        self.seen = []
        g.sotz_pda.on_game_start()
        g.z_seasons_pda_mac.on_game_start()
        self.seen.append(self.calls())
        self.fire("on_game_load")
        if bar is not None:
            g.BAR = lua.table_from(bar)
        self.seen.append(self.calls())
        self.fire("actor_on_first_update")
        self.seen.append(self.calls())

    def fire(self, name):
        for fn in self.hooks.get(name, []):
            fn()

    def calls(self):
        return lseq(self.g.calls)

    def opened(self):
        return lseq(self.g.opened)

    def tile(self):
        return self.g.tiles.app_seasons is not None

    def option(self, on):
        """MCM's option set and applied: the callbacks hear it; the game runs on later"""
        self.g.OPTION = on
        assert self.hooks.get("on_option_change"), "nothing hears MCM's options change"
        self.fire("on_option_change")


@case
def t_the_tile_until_a_tab_is_asked_for():
    gm = Game()
    gm.g.play(5)
    pda, g = gm.g.sotz_pda, gm.g
    assert gm.seen == [[], [], []] and gm.calls() == [], (gm.seen, gm.calls())
    assert gm.tile() and g.z_seasons_pda_mac.has_tile() is True, "no tile"
    assert pda.year_section() == "eptSeasons" and pda.back_to_launcher() is True, \
        (pda.year_section(), pda.back_to_launcher())
    return "MAC, the option off: the tile, no tab, The Year in its parked section"


@case
def t_the_tab_when_asked_comes_in_play():
    gm = Game(option=True)
    g = gm.g
    g.play(0.5)
    half = gm.calls()
    g.play(0.5)
    assert gm.seen == [[], [], []], "a tab while the scripts start or the game loads: %s" % gm.seen
    assert half == [], "the tab came before a second of play: %s" % half
    assert gm.calls() == ["register pda_app_seasons"], gm.calls()
    assert g.pending() == 0, "the time event stayed"
    g.play(5)
    assert gm.calls() == ["register pda_app_seasons"], "registered again: %s" % gm.calls()
    assert not gm.tile() and g.removed == 0, "a tile: none to add as the game started"
    pda = g.sotz_pda
    sec = pda.year_section()
    assert sec == "ept_dynamic_1" and pda.back_to_launcher() is False, (sec, pda.back_to_launcher())
    # the tab shows The Year; one that fails to build shows nothing, logged, and the PDA stays up
    getter = g.getters[sec]
    assert getter() == "YEAR_PAGE", getter()
    g.YEAR_FAILS = True
    n = len(gm.logs)
    failed = attempt(getter)
    assert failed is None and len(gm.logs) == n + 1, "a page that fails to build: %s" % failed
    g.YEAR_FAILS = False
    # the router: the parked sections still the app's, every other down
    gm.fire("on_game_load")
    route = g.pda.set_active_subdialog
    got = (route("eptSeasons"), route("eptForecast"), route("eptMap"))
    assert got == ("YEAR_PAGE", "FORECAST_PAGE", "BASE:eptMap"), got
    return "nothing while loading; the tab a second into play, once, after the others; no tile"


@case
def t_the_option_in_play():
    gm = Game(option=True)
    g = gm.g
    g.play(1)
    # off, with the PDA last on the tab: the tab goes once the game runs again, the tile comes
    # back, and the PDA goes to Tasks rather than a section nothing answers
    g.ACTIVE = "ept_dynamic_1"
    gm.option(False)
    paused = gm.calls()
    g.play(0.01)
    assert paused == ["register pda_app_seasons"], "it changed in the menu: %s" % paused
    assert gm.calls() == ["register pda_app_seasons", "unregister ept_dynamic_1"], gm.calls()
    assert gm.tile() and g.sotz_pda.back_to_launcher() is True, "no tile after the tab went"
    assert g.sotz_pda.year_section() == "eptSeasons", g.sotz_pda.year_section()
    assert gm.opened()[-1:] == ["eptTasks"], gm.opened()
    # on again, changed twice before the game runs: one new tab, the tile taken away
    gm.option(True)
    gm.option(True)
    g.play(0.01)
    assert gm.calls()[2:] == ["register pda_app_seasons"], gm.calls()
    assert not gm.tile() and g.removed == 1, (gm.tile(), g.removed)
    assert g.sotz_pda.year_section() == "ept_dynamic_2", g.sotz_pda.year_section()
    # a change that leaves the tab as it is: nothing
    gm.option(True)
    g.play(0.01)
    assert gm.calls()[2:] == ["register pda_app_seasons"], gm.calls()
    # off while the PDA was last elsewhere: it stays there
    g.ACTIVE = "eptMap"
    n = len(gm.opened())
    gm.option(False)
    g.play(0.01)
    assert gm.calls()[-1] == "unregister ept_dynamic_2", gm.calls()
    assert len(gm.opened()) == n and g.ACTIVE == "eptMap", (gm.opened(), g.ACTIVE)
    return "off: tab gone, tile back, the PDA off the gone tab; on again: one tab, no tile"


@case
def t_the_tab_where_no_tile_can_be_reached():
    """Without MAC there is no tile; with a bar that lacks MAC's Launcher there is one only
    behind MAC's own key. Either way the tab comes whatever the option says."""
    for kw in (dict(mac=False), dict(mac=False, option=True), dict(bar=NO_LAUNCHER)):
        gm = Game(**kw)
        gm.g.play(1)
        pda = gm.g.sotz_pda
        assert gm.seen == [[], [], []], (kw, gm.seen)
        assert gm.calls() == ["register pda_app_seasons"], (kw, gm.calls())
        assert not gm.tile() and pda.back_to_launcher() is False, (kw, gm.tile())
        assert pda.year_section() == "ept_dynamic_1", (kw, pda.year_section())
        # without MAC the option is on no page: asking MCM for it would only log a bad path
        gm.option(True)
        gm.g.play(0.01)
        assert gm.g.bad_paths == 0, "%s: MCM asked for an option no page defines" % kw
    # the bar without the Launcher is read after the scripts start, so the tile came first and
    # went as the tab came
    assert gm.g.removed == 1, gm.g.removed
    return "no MAC, or a bar without its Launcher: the tab in play, the option on or off, no tile"


@case
def t_no_tab_without_the_registry():
    for what in ("registry", "addtab"):
        gm = Game(option=True, registry=(what != "registry"), addtab=(what != "addtab"))
        gm.g.play(1)
        pda = gm.g.sotz_pda
        assert gm.calls() == [] and gm.tile(), (what, gm.calls(), gm.tile())
        assert pda.tab_supported() is False and pda.wants_tab() is False, what
        assert pda.year_section() == "eptSeasons" and gm.logs == [], (what, gm.logs)
        assert gm.g.bad_paths == 0, "%s: MCM asked for an option no page defines" % what
    # nor without MAC: nothing at all, and nothing said
    gm = Game(mac=False, registry=False)
    gm.g.play(1)
    assert gm.calls() == [] and not gm.tile() and gm.logs == [], (gm.calls(), gm.logs)
    return "without the registry or AddTab: the tile though the option is on, nothing logged"


@case
def t_a_tab_refused_or_a_pda_unread():
    gm = Game(option=True)
    gm.g.REFUSE = True
    gm.g.play(1)
    assert gm.tile() and gm.g.sotz_pda.year_section() == "eptSeasons", gm.tile()
    assert len(gm.logs) == 1 and "no PDA tab" in gm.logs[0], gm.logs
    # refused where the tile came as the game started (the bar read later): one tile, not two
    gm = Game(bar=NO_LAUNCHER)
    gm.g.REFUSE = True
    gm.g.play(1)
    assert gm.tile() and gm.g.adds == 1, "the tile added %d times" % gm.g.adds
    # a PDA that cannot be read as the tab goes: the tile back all the same, logged, done
    gm = Game(option=True)
    gm.g.play(1)
    gm.g.PDA_FAILS = True
    gm.option(False)
    err = attempt(gm.g.play, 0.01)
    assert err is None, "the PDA's error reached the game: %s" % err
    assert gm.g.pending() == 0 and gm.tile(), (gm.g.pending(), gm.tile())
    assert len(gm.logs) == 1 and "PDA tab" in gm.logs[0], gm.logs
    return "a refused tab leaves one tile; a PDA that cannot be read leaves the game on"


@case
def t_a_mac_that_refuses():
    """MAC asserts on what it is given, and the game starts every script in one pass that
    catches nothing: a tile MAC refuses is logged and the rest starts. One MAC cannot take
    away stays, and Back still leads to it."""
    # a second start (scripts reloaded by hand) asks MAC for no second tile
    gm = Game()
    gm.g.z_seasons_pda_mac.on_game_start()
    assert gm.g.adds == 1 and gm.g.z_seasons_pda_mac.has_tile() is True, gm.g.adds
    lua = LuaRuntime(unpack_returned_tuples=True)
    g = lua.globals()
    lua.execute(PRELUDE)
    lua.execute(TABS)
    lua.execute("ADD_FAILS = true")
    logs = []
    g.printf = lambda fmt, *a: logs.append(str(a[0]) if a else str(fmt))
    g.RegisterScriptCallback = lambda *a: None
    g.sotz_pda = load("sotz_pda.script", g, lua)
    g.z_seasons_pda_mac = load("z_seasons_pda_mac.script", g, lua)
    err = attempt(g.z_seasons_pda_mac.on_game_start)
    assert err is None, "MAC's refusal stopped the scripts starting: %s" % err
    assert g.z_seasons_pda_mac.has_tile() is False and len(logs) == 1, logs
    assert "MAC registration failed" in logs[0], logs
    # the tab comes, and MAC keeps the tile: it stays, said once, and Back still has it
    gm = Game()
    gm.g.play(1)
    gm.g.REMOVE_FAILS = True
    gm.option(True)
    gm.g.play(0.01)
    assert gm.calls() == ["register pda_app_seasons"], gm.calls()
    assert gm.g.z_seasons_pda_mac.has_tile() is True and gm.g.sotz_pda.back_to_launcher() is True
    assert len(gm.logs) == 1 and "stays" in gm.logs[0], gm.logs
    return "a refused tile is logged and the scripts start; a tile MAC keeps stays reachable"


@case
def t_back_escape_and_the_switch_follow_the_tile():
    pressed = 6
    for option in (False, True):
        gm = Game(option=option, pages=True)
        g = gm.g
        g.play(1)
        tile = not option
        for cls in ("SeasonsPDA", "SeasonsForecast"):
            page = g.make_window(g[cls], False)
            page.back = g.mkback()
            g[cls].Reset(page)
            assert page.back.shown is tile, "%s, option %s: Back shown %s" % (
                cls, option, page.back.shown)
            n = len(gm.opened())
            took = g[cls].OnKeyboard(page, ESC, pressed)
            if tile:
                assert took is True and gm.opened()[n:] == ["eptLauncher"], (cls, gm.opened())
            else:
                assert took is False and gm.opened()[n:] == [], (cls, took, gm.opened())
            # flat, Back is there and Escape closes the window, tile or tab
            flat = g.make_window(g[cls], True)
            flat.back = g.mkback()
            flat.shown = True
            g[cls].Reset(flat)
            assert flat.back.shown is True, (cls, option)
            assert g[cls].OnKeyboard(flat, ESC, pressed) is True and flat.shown is False, cls
        # the switch: The Year to Forecast's section, Forecast back to The Year's, the tab's
        year = g.make_window(g.SeasonsPDA, False)
        fc = g.make_window(g.SeasonsForecast, False)
        g.SeasonsPDA.OnToggle(year)
        g.SeasonsForecast.OnToggle(fc)
        want = ["eptForecast", "eptSeasons" if tile else "ept_dynamic_1"]
        assert gm.opened()[-2:] == want, (option, gm.opened()[-2:])
    return "Back and Escape to the launcher with the tile; with the tab, the PDA's; Forecast to the tab"


MCM = r"""
function mcm_main(op)
    for _, page in ipairs(op.gr) do
        if page.id == "main" then return page.gr end
    end
end
function mcm_ids(gr)
    local t = {}
    for i, o in ipairs(gr) do t[i] = o.id end
    return t
end
function mcm_status(gr)
    for _, o in ipairs(gr) do
        if o.id == "status_mac" then return o.text end
    end
end
function mcm_option(gr, id)
    for _, o in ipairs(gr) do
        if o.id == id then return o end
    end
end
"""


@case
def t_mcm_offers_the_tab_and_says_where_the_app_is():
    """The option is on the Main page under the app key where a tile and a tab can both be,
    and the status line says which way in the app has: by the options as saved, since
    ui_mcm.get asserts while MCM builds the page."""
    def main_page(mac=True, registry=True, saved=None, bar=None):
        gm = Game(mac=mac, registry=registry, bar=bar)
        gm.lua.execute(MCM)
        gm.g.SAVED = saved
        gm.g.MCM_BUILDING = True
        mcm = load("zzz_seasons_of_the_zone_mcm.script", gm.g, gm.lua)
        gr = gm.g.mcm_main(mcm.on_mcm_load())
        assert gm.g.asked_while_building == 0, "ui_mcm.get asked while MCM built its page"
        ids = lseq(gm.g.mcm_ids(gr))
        return ids, str(gm.g.mcm_status(gr)), gm.g.mcm_option(gr, "pda_tab")
    s = "ui_mcm_seasons_zone_status_"
    for kw, offered, status in (
            (dict(), True, s + "mac"),
            (dict(saved=True), True, s + "tab"),
            (dict(bar=NO_LAUNCHER), True, s + "tab"),
            (dict(mac=False), False, s + "tab"),
            (dict(mac=False, registry=False), False, s + "no_mac"),
            (dict(registry=False, saved=True), False, s + "mac"),
            (dict(registry=False, bar=NO_LAUNCHER), False, s + "no_tab")):
        ids, said, opt = main_page(**kw)
        assert ("pda_tab" in ids) is offered, (kw, ids)
        if offered:
            assert ids[ids.index("app_key") + 1] == "pda_tab", (kw, ids)
            # a check, off as it ships
            assert (opt.type, opt.val, opt["def"]) == ("check", 1, False), \
                (opt.type, opt.val, opt["def"])
        assert said == status, (kw, said)
    gm = Game()
    path = str(gm.g.sotz_pda.TAB_PATH)
    assert path == "seasons_zone/main/pda_tab", path
    return "offered with MAC and the registry, under the app key; the status line names the tab"


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
