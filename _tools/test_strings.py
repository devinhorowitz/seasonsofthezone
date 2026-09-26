"""Every word the player reads in game comes from the string table.

A translation is a second copy of configs/text/eng - rus/ beside it, the same ids, other
words. That only works if the scripts put nothing on screen that is not in the table. An
English literal handed to a widget stays English in every language, and a sentence glued
together from pieces cannot be translated at all, because another language puts the pieces
in another order. So this checks, in order:

  the tables    every eng XML reads in the encoding it declares, no id is there twice,
                and no text leans on spaces X-Ray's XML parser may collapse
  the ids       every id the scripts ask for is in the eng table: read off the scripts,
                and asked for by the scripts as they run
  the literals  no English literal reaches a widget, a PDA message or an MCM row
  plurals       plural() picks the right form for English and Russian counts, and a
                translation can move the words around a value

The other suites take game.translate_string from here. It reads the real English table
and, like the engine, hands back an unknown id as itself, so a check there on English text
is also a check that its ids resolve.

  python _tools/test_strings.py
"""
import atexit
import datetime
import glob
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

from lua_runtime import LuaRuntime, NAME as LUA_NAME
import test_mcm_strings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GD = os.path.join(ROOT, "mods", "Seasons of the Zone", "gamedata")
SCRIPTS = os.path.join(GD, "scripts")
TEXT = os.path.join(GD, "configs", "text")

# calendars of the player's own are written here, to be read by the script's own reader
TMP = tempfile.mkdtemp(prefix="sotz_strings_")
atexit.register(shutil.rmtree, TMP, True)

SEASONS = ("spring", "summer", "autumn", "winter", "winter_snow", "late_winter")


# --- the tables --------------------------------------------------------------------------

def declared_encoding(raw):
    m = re.match(rb'<\?xml[^>]*encoding="([^"]+)"', raw)
    return m.group(1).decode("ascii") if m else "utf-8"


def read_table(raw, name="<memory>"):
    """([(id, text)], [problem]) for one string table, read the way the engine reads it."""
    problems = []
    enc = declared_encoding(raw)
    try:
        raw.decode(enc)
    except (LookupError, UnicodeDecodeError) as e:
        return [], ["%s: not %s: %s" % (name, enc, e)]
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        return [], ["%s: not well-formed XML: %s" % (name, e)]
    if root.tag != "string_table":
        problems.append("%s: the root is <%s>, not <string_table>" % (name, root.tag))
    out = []
    for s in root.iter("string"):
        sid, texts = s.get("id"), s.findall("text")
        if not sid:
            problems.append("%s: a <string> with no id" % name)
            continue
        if len(texts) != 1 or not (texts[0].text or "").strip():
            problems.append("%s: %s needs one <text> with something in it" % (name, sid))
            continue
        t = texts[0].text
        # TinyXML, which X-Ray reads these with, collapses whitespace by default
        if t != t.strip() or re.search(r"\s\s", t) or "\n" in t:
            problems.append("%s: %s has a run of spaces, a line break or a space at an "
                            "end, which the engine's parser may collapse" % (name, sid))
        out.append((sid, t))
    return out, problems


def table_files(lang="eng"):
    return sorted(glob.glob(os.path.join(TEXT, lang, "*.xml")))


def table(lang="eng"):
    """{id: text} from every string table the mod ships for one language."""
    out = {}
    for p in table_files(lang):
        for sid, t in read_table(open(p, "rb").read(), os.path.basename(p))[0]:
            out[sid] = t
    return out


def translator(strings=None, asked=None):
    """game.translate_string over `strings`, the real English table unless given. An id it
    does not have comes back as itself, as the engine's does; every id asked for is added
    to `asked`, when there is one."""
    strings = table() if strings is None else strings

    def translate_string(s):
        s = str(s)
        if asked is not None:
            asked.append(s)
        return strings.get(s, s)
    return translate_string


def install(lua, g, strings=None, asked=None):
    """The engine's string table and the mod's sotz_text in a sandbox: translate_string is
    added to whatever `game` the suite has built, and sotz_text is loaded under its file's
    name, where every other script looks for it."""
    if g.game is None:
        g.game = lua.table_from({})
    g.game["translate_string"] = translator(strings, asked)
    load = lua.eval("""function(src, env)
        local e = setmetatable({}, {__index = env})
        assert(load(src, "sotz_text", "t", e))()
        return e
    end""")
    src = io.open(os.path.join(SCRIPTS, "sotz_text.script"), encoding="utf-8").read()
    g.sotz_text = load(src, g)
    return g.sotz_text


# --- reading the scripts -------------------------------------------------------------------

TOKEN = re.compile(r"""
    (?P<comment>--\[(?P<ceq>=*)\[.*?\](?P=ceq)\]|--[^\n]*)
  | (?P<long>\[(?P<leq>=*)\[.*?\](?P=leq)\])
  | (?P<str>"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*')
  | (?P<num>0[xX][0-9a-fA-F]+|\d+\.?\d*(?:[eE][+-]?\d+)?|\.\d+)
  | (?P<name>[A-Za-z_]\w*)
  | (?P<op>\.\.\.|\.\.|==|~=|<=|>=|[-+*/%^\#<>=(){}\[\];:,.])
  | (?P<ws>\s+)
""", re.S | re.X)

KEYWORDS = {"and", "break", "do", "else", "elseif", "end", "false", "for", "function",
            "if", "in", "local", "nil", "not", "or", "repeat", "return", "then", "true",
            "until", "while"}


class Tok(object):
    __slots__ = ("kind", "text", "line")

    def __init__(self, kind, text, line):
        self.kind, self.text, self.line = kind, text, line


def tokens(src):
    """Lua's tokens, comments dropped, each with its line."""
    out, pos, line = [], 0, 1
    while pos < len(src):
        m = TOKEN.match(src, pos)
        if not m:
            raise ValueError("cannot read line %d: %r" % (line, src[pos:pos + 30]))
        kind = m.lastgroup
        if kind in ("ceq", "leq"):
            kind = "comment" if m.group("comment") else "long"
        if kind not in ("ws", "comment"):
            out.append(Tok(kind, m.group(0), line))
        line += m.group(0).count("\n")
        pos = m.end()
    return out


def is_name(t, text=None):
    return t is not None and t.kind == "name" and (text is None or t.text == text)


def is_op(t, text):
    return t is not None and t.kind == "op" and t.text == text


class Script(object):
    """One script's tokens, with which function each sits in and whether a `name =` is a
    table's key or an assignment."""

    def __init__(self, name, src):
        self.name, self.t = name, tokens(src)
        self.funcs, self.owner, self.in_table = [], [None] * len(self.t), [False] * len(self.t)
        stack = []
        for i, tok in enumerate(self.t):
            fn = next((s for s in reversed(stack) if s[0] == "function"), None)
            self.owner[i] = fn[1] if fn else None
            self.in_table[i] = bool(stack) and stack[-1][0] == "{"
            if tok.kind == "op" and tok.text in "({[":
                stack.append((tok.text, i))
            elif tok.kind == "op" and tok.text in ")}]":
                stack.pop()
            elif tok.text == "function" and tok.kind == "name":
                parts, j = [], i + 1
                while self.at(j) is not None and (self.at(j).kind == "name"
                                                  or self.at(j).text in (".", ":")):
                    if self.at(j).kind == "name":
                        parts.append(self.at(j).text)
                    j += 1
                stack.append(("function", i, parts[-1] if parts else None))
            elif tok.kind == "name" and tok.text in ("if", "do", "repeat"):
                stack.append((tok.text, i))
            elif tok.kind == "name" and tok.text in ("end", "until"):
                s = stack.pop()
                if s[0] == "function":
                    self.funcs.append((s[1], i, s[2]))
        self.own = {name for _, _, name in self.funcs if name}

    def at(self, i):
        return self.t[i] if 0 <= i < len(self.t) else None

    def scope(self, i):
        """The token span of the function token i sits in, or the whole file."""
        for a, b, _ in self.funcs:
            if a == self.owner[i]:
                return (a, b)
        return (0, len(self.t) - 1)

    def closing(self, i):
        depth = 0
        for j in range(i, len(self.t)):
            tok = self.t[j]
            if tok.kind == "op" and tok.text in "({[":
                depth += 1
            elif tok.kind == "op" and tok.text in ")}]":
                depth -= 1
                if depth == 0:
                    return j
        return len(self.t)

    def expr_end(self, i):
        """Just past the expression that starts at token i: it runs on while a bracket is
        open or a line ends or begins with an operator."""
        joins = {"..", "and", "or", "+", "-", "*", "/", ",", "=", "(", "{", "[", "==", "~=",
                 "not", "<", ">", "<=", ">="}
        stops = {"end", "else", "elseif", "then", "do", "local", "return", "if", "for",
                 "while", "until", "repeat"}
        depth, j = 0, i
        while j < len(self.t):
            tok = self.t[j]
            if tok.kind == "op" and tok.text in "({[":
                depth += 1
            elif tok.kind == "op" and tok.text in ")}]":
                if depth == 0:
                    return j
                depth -= 1
            elif depth == 0 and ((tok.kind == "op" and tok.text in (",", ";"))
                                 or (tok.kind == "name" and tok.text in stops)):
                return j
            nxt = self.at(j + 1)
            if depth == 0 and nxt is not None and nxt.line != tok.line and not (
                    tok.text in joins or nxt.text in ("..", "and", "or", ")", "}", "]")):
                return j + 1
            j += 1
        return j

    def args(self, open_i):
        """[(first, last)] for the arguments of the call whose `(` is at open_i."""
        out, depth, start = [], 0, open_i + 1
        for j in range(open_i, len(self.t)):
            tok = self.t[j]
            if tok.kind == "op" and tok.text in "({[":
                depth += 1
            elif tok.kind == "op" and tok.text in ")}]":
                depth -= 1
                if depth == 0:
                    if j > start:
                        out.append((start, j))
                    return out
            elif depth == 1 and is_op(tok, ","):
                out.append((start, j))
                start = j + 1
        return out


def shipped_scripts():
    return [Script(os.path.basename(p), io.open(p, encoding="utf-8").read())
            for p in sorted(glob.glob(os.path.join(SCRIPTS, "*.script")))]


# --- the literals --------------------------------------------------------------------------
#
# Two ways in, because one is not enough. (1) Whatever is handed to a widget, a PDA message
# or an MCM row is followed back through the names it is built from - a local, a function's
# returns, a table - to the literals that give it its value; that finds "settled" and
# "today", single words that look like any key. (2) Prose anywhere outside a log line is
# English written to be read; that finds the sentences a table hands to another file.

# where a string meets the player: (name, called as a method, which argument is the text)
SINKS = [("put", False, 2), ("SetText", True, 1), ("Head", True, 2), ("Section", True, 2),
         ("Put", True, 2), ("send_tip", False, 2), ("set_msg", False, 2), ("desc", False, 3),
         ("row", False, 2)]

LOGS = {"say", "printf", "print", "error"}

LIBS = KEYWORDS | {"string", "math", "table", "tostring", "tonumber", "ipairs", "pairs",
                   "type", "pcall", "os", "self", "select", "unpack", "rawget", "rawset",
                   "setmetatable", "getmetatable", "next", "io", "_G"}

# English that is not for the player, by file. The emission brackets are the API's own
# values, which sotz_api and the devices reading it key on - the page shows
# st_sotz_fc_band_* instead - and the rest only ever reach the log.
NOT_SHOWN = {
    "zzz_seasons_of_the_zone.script": {
        "WITHIN 2 HOURS", "2 to 8 hours", "8 to 16 hours", "ALL CLEAR",
        # hold_cycle(), anniversary_artefacts() and reach(), each only ever logged
        "Atmospherics not present", "Dynamic Anomalies Overhaul not present", "no level",
        "seeded %s on %s over %s passes (artefacts %s -> %s)", "seeded artefacts on ",
        " (count unavailable)", "no-getter(n=%d %s)"},
}

FORMAT = re.compile(r"%[-+ #0]*\d*(?:\.\d+)?[sdifgGeExXcq%]|%[aAcCdDgGlLpPsSuUwWxX]")


def body(tok):
    return tok.text[1:-1]


def readable(tok):
    """A word of two letters or more once format codes are out, or a unit's capital. An
    underscore marks an id, a key or a file name: no player reads one."""
    b = body(tok)
    if "_" in b:
        return False
    rest = FORMAT.sub("", b)
    return bool(re.search(r"[A-Za-z]{2}", rest) or re.match(r"^[A-Z]$", rest.strip()))


def prose(tok):
    """A sentence, or a capitalized word: written to be read wherever it sits."""
    b = body(tok)
    if "_" in b or re.match(r"^[A-Z][a-z]+[A-Z]\w*$", b):   # an id, or a class's name
        return False
    return bool(re.search(r"[A-Za-z]{2}", FORMAT.sub("", b))
                and (" " in b or re.match(r"[A-Z]", b)))


def sinks(s):
    """Token spans that end up on screen."""
    out = []
    for i, tok in enumerate(s.t):
        if tok.kind != "name":
            continue
        for name, method, arg in SINKS:
            if tok.text != name or not is_op(s.at(i + 1), "("):
                continue
            if method != is_op(s.at(i - 1), ":"):
                continue
            if is_name(s.at(i - 1), "function") or (method and is_name(s.at(i - 3),
                                                                       "function")):
                continue                                   # a definition, not a call
            if not method and is_op(s.at(i - 1), ".") and name not in ("send_tip",
                                                                       "set_msg"):
                continue
            a = s.args(i + 1)
            if len(a) >= arg:
                out.append(a[arg - 1])
        # {text = ...}: an MCM row, or a row handed to MCM
        if tok.text == "text" and is_op(s.at(i + 1), "=") and s.in_table[i] \
                and not is_op(s.at(i - 1), "."):
            out.append((i + 2, s.expr_end(i + 2)))
    return out


def definitions(s, name, scope):
    """Spans that give `name` its value: its assignments in `scope` or at file scope, and
    the returns of a function of that name."""
    spans = []
    for i, tok in enumerate(s.t):
        if not is_name(tok, name) or is_op(s.at(i - 1), ".") or is_op(s.at(i - 1), ":"):
            continue
        if not (s.owner[i] is None or s.scope(i) == scope):
            continue
        j = i + 1
        while is_op(s.at(j), ",") and is_name(s.at(j + 1)):
            j += 2
        if is_op(s.at(j), "=") and not s.in_table[i]:
            spans.append((j + 1, s.expr_end(j + 1)))
    for a, b, fname in s.funcs:
        if fname == name:
            spans += [(i + 1, s.expr_end(i + 1)) for i in range(a, b)
                      if is_name(s.t[i], "return")]
    return spans


def flow(s, span, scope, seen, depth=0):
    """Literal tokens that can reach the screen through `span`. An index is a key, not the
    thing shown, and a comparison's operand is not shown at all; the arguments of a
    function of this file go in rather than out, so its returns are followed instead."""
    found, (a, b), i = [], span, span[0]
    while i < min(b, len(s.t)):
        tok = s.t[i]
        if is_op(tok, "[") and i > a and (s.t[i - 1].kind == "name"
                                          or s.t[i - 1].text in ")]"):
            i = s.closing(i) + 1
            continue
        if tok.kind == "str":
            compared = any(is_op(s.at(k), op) for k in (i - 1, i + 1) for op in ("==", "~="))
            key = is_op(s.at(i - 1), "[") and is_op(s.at(i + 1), "]")
            if not (compared or key):
                found.append(i)
        elif tok.kind == "name" and tok.text not in LIBS and depth < 8:
            if is_op(s.at(i - 1), ".") or is_op(s.at(i - 1), ":") or (
                    is_op(s.at(i + 1), "=") and s.in_table[i]):
                i += 1
                continue
            if (tok.text, scope) not in seen:
                seen.add((tok.text, scope))
                for d in definitions(s, tok.text, scope):
                    found += flow(s, d, s.scope(d[0]), seen, depth + 1)
            if tok.text in s.own and is_op(s.at(i + 1), "("):
                i = s.closing(i + 1) + 1
                continue
        i += 1
    return found


def logged(s):
    """Spans only a log line reads, and a class's name."""
    out = []
    for i, tok in enumerate(s.t):
        if tok.kind == "name" and tok.text in LOGS and is_op(s.at(i + 1), "(") \
                and not is_name(s.at(i - 1), "function"):
            a = s.args(i + 1)
            if a:
                out.append((a[0][0], a[-1][1]))
        if is_name(tok, "class"):
            out.append((i + 1, i + 2))
    return out


def english_on_screen(s, allowed=None):
    """[(file, line, literal)] for every English literal that can reach the player."""
    allowed = NOT_SHOWN.get(s.name, set()) if allowed is None else allowed
    hits = set()
    for span in sinks(s):
        hits |= {i for i in flow(s, span, s.scope(span[0]), set()) if readable(s.t[i])}
    logs = logged(s)
    for i, tok in enumerate(s.t):
        key = is_op(s.at(i - 1), "[") and is_op(s.at(i + 1), "]")
        if tok.kind == "str" and prose(tok) and not key \
                and not any(a <= i < b for a, b in logs):
            hits.add(i)
    return [(s.name, s.t[i].line, body(s.t[i])) for i in sorted(hits)
            if body(s.t[i]) not in allowed]


# --- the ids ------------------------------------------------------------------------------

ID = re.compile(r"^(?:st_sotz_|ui_mcm_seasons_zone_|pda_btn_|pda_app_)[a-z0-9_]*$"
                r"|^seasons_zone_[a-z0-9_]*_lst_[a-z0-9_]*$")

CALLS = ("text", "plural")


def calls(s):
    """(index, helper) for each call of the string helpers, direct or through a local
    alias, and of game.translate_string."""
    alias = {}
    for i, tok in enumerate(s.t):
        if is_name(tok, "local") and is_name(s.at(i + 1)) and is_op(s.at(i + 2), "=") \
                and is_name(s.at(i + 3), "sotz_text") and is_op(s.at(i + 4), ".") \
                and s.at(i + 5) is not None and s.at(i + 5).text in CALLS:
            alias[s.at(i + 1).text] = s.at(i + 5).text
    out = []
    for i, tok in enumerate(s.t):
        if not (tok.kind == "name" and is_op(s.at(i + 1), "(")):
            continue
        if tok.text in CALLS and is_op(s.at(i - 1), ".") and is_name(s.at(i - 2),
                                                                       "sotz_text"):
            out.append((i + 1, tok.text))
        elif tok.text == "translate_string" and is_name(s.at(i - 2), "game"):
            out.append((i + 1, "text"))
        elif tok.text in alias and not is_op(s.at(i - 1), ".") and not is_name(
                s.at(i - 1), "function"):
            out.append((i + 1, alias[tok.text]))
    return out


def resolves(sid, have):
    """An id the table has, or a count's id whose forms it has."""
    return sid in have or (sid + "_one" in have and sid + "_many" in have)


def families():
    """The ids the scripts build at run time, by the literal they start with: the names of
    every season, every month's four forms, the speakers and each transmission."""
    rem = remembrance_ids()
    return {
        "st_sotz_season_": ["st_sotz_season_%s%s" % (s, f) for s in SEASONS
                            for f in ("", "_mid")],
        "st_sotz_month_": ["st_sotz_month_%d%s" % (m, f) for m in range(1, 13)
                           for f in ("", "_date", "_short", "_short_date")],
        "st_sotz_speaker_": ["st_sotz_speaker_" + w for w in rem["speakers"]],
        "st_sotz_rem_": rem["ids"],
        "ui_mcm_seasons_zone_page_": ["ui_mcm_seasons_zone_page_" + s for s in SEASONS],
        "seasons_zone_main_mode_lst_": ["seasons_zone_main_mode_lst_" + s for s in SEASONS],
    }


def ids_in(scripts, have, known=None):
    """[problem] for every id the scripts name that the table does not have."""
    known = families() if known is None else known
    bad = []
    for s in scripts:
        for i, tok in enumerate(s.t):
            if tok.kind != "str" or not ID.match(body(tok)):
                continue
            where = "%s:%d" % (s.name, tok.line)
            if is_op(s.at(i + 1), ".."):                    # the start of a built id
                if body(tok) not in known:
                    bad.append("%s builds ids from %r, which this test cannot list - add it "
                               "to families()" % (where, body(tok)))
                    continue
                bad += ["%s: %s" % (where, x) for x in known[body(tok)]
                        if not resolves(x, have)]
            elif not resolves(body(tok), have):
                bad.append("%s: %s" % (where, body(tok)))
        # a helper asked for a whole literal id, whatever it looks like
        for open_i, helper in calls(s):
            first = s.args(open_i)[:1]
            if not first:
                continue
            a, b = first[0]
            if b - a == 1 and s.t[a].kind == "str" and not ID.match(body(s.t[a])):
                sid = body(s.t[a])
                if not (resolves(sid, have) if helper == "plural" else sid in have):
                    bad.append("%s:%d: %s" % (s.name, s.t[a].line, sid))
    return sorted(set(bad))


# --- the scripts, running -------------------------------------------------------------------

PRELUDE = r"""
function fixed_os(y, m, d)
    local rd, rt, rc = os.date, os.time, os.clock
    local fixed = rt({year = y, month = m, day = d, hour = 12})
    return {date = function(fmt, t) return rd(fmt, t or fixed) end, time = rt, clock = rc}
end

function load_in(src, name, shared)
    local env = setmetatable({}, {__index = shared})
    local f = assert(load(src, name, "t", env))
    local exposed = f()
    return env, exposed
end

-- the widgets a page builds, each keeping the last text it was given
WIDGETS = {}
function mkwidget(name)
    local s = {name = name}
    function s:SetWndPos(v) end
    function s:SetWndSize(v) self.h = v.y end
    function s:GetWndPos() return {x = 0, y = 0} end
    function s:GetHeight() return self.h or 20 end
    function s:GetWidth() return 20 end
    function s:SetTextureColor() end
    function s:SetTextColor() end
    function s:SetText(t) self.text = t end
    function s:InitTexture() end
    function s:Show() end
    function s:Enable() end
    WIDGETS[#WIDGETS + 1] = s
    return s
end

function CScriptXmlInit()
    local x = {}
    function x:ParseFile() end
    function x:InitStatic(n) return mkwidget(n) end
    function x:InitTextWnd(n) return mkwidget(n) end
    function x:Init3tButton(n) return mkwidget(n) end
    return x
end

function vector2()
    local v = {}
    function v:set(a, b) self.x, self.y = a, b; return self end
    return v
end

function Frect() return {set = function(self) return self end} end

class = function(name)
    return function(base) local t = {}; t.__index = t; _G[name] = t; return t end
end
super = function() end

-- a page as the engine builds it, filled once
function open_page(cls)
    WIDGETS = {}
    local p = setmetatable({}, {__index = cls})
    function p:SetWndRect() end
    function p:Register() end
    function p:AddCallback() end
    p:InitControls()
    p:Reset()
    local out = {}
    for _, w in ipairs(WIDGETS) do out[#out + 1] = w.text end
    return out
end
"""

# each file's locals a case drives, handed back by one `return` appended to the file
EXPOSE = {"zzz_seasons_of_the_zone": "return {pda_announce = pda_announce, apply = apply, "
                                     "rem_send = rem_send, REMEMBRANCE = REMEMBRANCE, "
                                     "actor_on_first_update = actor_on_first_update}",
          "ui_seasons_forecast": "return {countdown = countdown, lead = lead, "
                                 "window_text = window_text}"}

HOUR = 3600
CYCLES = ("clear", "partly", "cloudy", "rain", "storm", "foggy")


class World(object):
    """A sandbox: the runtime, its globals, the messages sent, the log, and the locals each
    file handed back."""


def world(date=(2026, 9, 22), mcm=None, standing=0, surge_left=4 * HOUR, weather="plan",
          cycle="storm", plan=None, period=6, elapsed_h=1.0, observed=False, calendar=None,
          mods=None, mac=True, units=None, asked=None, strings=None, year=2026):
    """Every script the mod ships, loaded as X-Ray loads them, over stubs for what they
    reach for."""
    w = World()
    # latin-1 hands every byte through as it is: the pages draw the degree sign as \176
    w.lua = lua = LuaRuntime(unpack_returned_tuples=True, encoding="latin-1")
    w.g = g = lua.globals()
    lua.execute(PRELUDE)
    w.sent, w.log = sent, log = [], []
    g.printf = lambda fmt, *a: log.append(str(fmt) % tuple(a) if a else str(fmt))
    g.os = g.fixed_os(*date)
    g.time_global = lambda: 0
    g.device = lambda: lua.table_from({"width": 1920, "height": 1080})
    g.GetARGB = lambda *a: 0
    g.ui_events = lua.table_from({"BUTTON_CLICKED": 1})
    g.CUIScriptWnd = lua.table_from({})
    g.ActorMenu = lua.table_from({})
    g.RegisterScriptCallback = lambda *a: None
    g.CreateTimeEvent = lambda *a: None
    g.level = lua.table_from({"name": lambda: "l01_escape", "get_time_hours": lambda: 12,
                              "get_time_minutes": lambda: 0})
    g.db = lua.table_from({"actor": lua.table_from({"id": lambda self: 0})})
    g.relation_registry = lua.table_from({"community_goodwill": lambda f, a: standing})
    g.game = lua.table_from({"get_game_time": lambda: lua.table_from({
        "diffSec": lambda self, other: other["elapsed"] if other is not None else 0,
        "get": lambda self, *a: year})})
    stamp = lambda left, period: lua.table_from({"elapsed": period - left})  # noqa: E731
    g.surge_manager = lua.table_from({"SurgeManager": lua.table_from({
        "_delta": 24 * HOUR, "last_surge_time": stamp(surge_left, 24 * HOUR)})})
    g.psi_storm_manager = lua.table_from({"PsiStormManager": lua.table_from({
        "_delta": 48 * HOUR, "last_psi_storm_time": stamp(30 * HOUR, 48 * HOUR)})})
    opts = {"video/weather/%s_period" % cycle: period}
    g.ui_options = lua.table_from({"get": lambda k: opts.get(k)})
    vals = {"seasons_zone/main/units": units}
    vals.update(mcm or {})
    g.ui_mcm = lua.table_from({"get": lambda p: vals.get(p)})
    g.axr_main = lua.table_from({"config": lua.table_from({
        "r_value": lambda self, sec, path, t, default: {
            "seasons_zone/winter_snow/preset": "seasons_deepwinter"}.get(path, default)})})
    if weather == "stock":
        wm = lua.table_from({"cycle": cycle, "weather_storage": lua.table_from([]),
                             "last_period_change_date": lua.table_from(
                                 {"elapsed": elapsed_h * HOUR})})
        g.level_weathers = lua.table_from({"get_weather_manager": lambda: wm})
    elif weather == "plan":
        segs = plan if plan is not None else [(690, "rain"), (1000, "cloudy")]
        wm = lua.table_from({
            "cycle": cycle, "day_plan_index": 1, "abs_schedule_minute": lambda self: 600,
            "day_plan": lua.table_from([lua.table_from({"minute": m, "cycle": c})
                                        for m, c in segs])})
        g.level_weathers = lua.table_from({"get_weather_manager": lambda: wm})
    else:
        g.level_weathers = lua.table_from({})
    g.utils_data = lua.table_from({"collect_section": lambda ini, sec: lua.table_from(
        list(CYCLES) if sec == "weather_cycles" else [])})

    files = {("$game_config$", "seasons_presets\\%s.ltx" % n):
             os.path.join(GD, "configs", "seasons_presets", n + ".ltx")
             for n in ("Seasons_DeepWinter", "Seasons_Neutral")}
    if calendar is not None:
        path = os.path.join(TMP, "calendar_%d.ltx" % len(os.listdir(TMP)))
        io.open(path, "w", encoding="cp1251").write(
            "[calendar]\n" + "".join("%s = %s\n" % kv for kv in calendar.items()))
        files[("$game_config$", "season_calendar.ltx")] = path
    g.getFS = lambda: lua.table_from({
        "exist": lambda self, alias, name: (alias, name) in files,
        "update_path": lambda self, alias, name: files.get((alias, name), name),
        "file_list_open_ex": lambda self, *a: lua.table_from({"Size": lambda self: 0})})
    g.FS = lua.table_from({"FS_ListFiles": 1, "FS_RootOnly": 2})
    g.bit_or = lambda a, b: int(a) | int(b)

    today = "%04d-%02d-%02d" % date
    tomorrow = (datetime.date(*date) + datetime.timedelta(days=1)).isoformat()
    weather_ltx = {"weather": {"high": 14.5, "low": -1.5, "cycle": "rain", "date": today},
                   "weather_next": {"high": 2, "low": -4, "cycle": "snow",
                                    "date": tomorrow}} if observed else {}
    table_ltx = read_ltx(os.path.join(GD, "configs", "seasons_of_the_zone.ltx"))

    def ini_file(name):
        secs = {"seasons_of_the_zone.ltx": table_ltx, "season_weather.ltx": weather_ltx,
                "season_mods.ltx": mods or {}}.get(str(name), {})

        def num(self, s, k):
            v = secs.get(s, {}).get(k)
            return None if v is None else float(v)
        return lua.table_from({
            "section_exist": lambda self, s: s in secs,
            "r_float_ex": num,
            "r_string_ex": lambda self, s, k: (None if secs.get(s, {}).get(k) is None
                                               else str(secs[s][k]))})
    g.ini_file = ini_file
    g.news_manager = lua.table_from({
        "send_tip": lambda actor, msg, t, icon, *a: sent.append((msg, icon))})
    g.actor_menu = lua.table_from({"set_msg": lambda n, msg, *a: sent.append((msg, None))})
    g.mac_mcm = lua.table_from({"add_app": lambda *a: None}) if mac else None
    store = {}
    con = lua.table_from({"execute": lambda self, c: store.__setitem__(*str(c).split(" ", 1)),
                          "get_string": lambda self, n: store.get(n)})
    g.get_console = lambda: con

    install(lua, g, strings, asked)
    w.got = {}
    for name in ("zzz_seasons_of_the_zone", "sotz_api", "sotz_pda", "ui_seasons_forecast",
                 "ui_seasons_pda", "zzz_seasons_of_the_zone_mcm"):
        # bytes, as the engine reads them: a comment may hold a character latin-1 lacks
        src = open(os.path.join(SCRIPTS, name + ".script"), "rb").read()
        env, exposed = g.load_in(src + b"\n" + EXPOSE.get(name, "").encode("ascii"), name, g)
        g[name] = env
        w.got[name] = exposed
    w.z = w.got["zzz_seasons_of_the_zone"]
    return w


def page(w, cls):
    """The texts a page shows once filled; a page that failed to fill fails the case."""
    rows = list(w.g.open_page(w.g[cls]).values())
    broken = [line for line in w.log if "failed" in line]
    assert not broken, broken
    return rows


def read_ltx(path):
    out, cur = {}, None
    for line in io.open(path, encoding="cp1251", errors="replace"):
        line = line.split(";")[0].strip()
        m = re.match(r"^\[([^\]]+)\]", line)
        if m:
            cur = out.setdefault(m.group(1).strip(), {})
        elif cur is not None and "=" in line:
            k, v = (x.strip() for x in line.split("=", 1))
            cur[k] = v
    return out


def remembrance_ids():
    """Every transmission's id, and every speaker, as the running script builds them."""
    days = world().z["REMEMBRANCE"]
    ids, speakers = [], set()
    for key in days.keys():
        day = days[key]
        for pool in ("opens", "lines"):
            for i in range(1, len(day[pool]) + 1):
                sid = "st_sotz_rem_%s_%s_%d" % (day["key"], pool, i)
                years = day["years"] is not None and day["years"]["%s_%d" % (pool, i)]
                ids += [sid + "_one", sid + "_many"] if years else [sid]
                speakers.add(day[pool][i])
    return {"ids": ids, "speakers": sorted(speakers)}


def mcm_rows(g):
    """What on_mcm_load() hands MCM to show: each page title, desc row and list label.
    ui_mcm.script runs each through translate_string, so a string id is right here."""
    op = g.zzz_seasons_of_the_zone_mcm.on_mcm_load()
    out = []
    for i in range(1, len(op.gr) + 1):
        page = op.gr[i]
        out.append(page.text)
        for j in range(1, len(page.gr) + 1):
            o = page.gr[j]
            if o.type == "desc":
                out.append(o.text)
            elif o.type == "list" and o.no_str:
                out += [o.content[k][2] for k in range(1, len(o.content) + 1)]
    return out


OWN = {"custom": "true", "dial": "none", "summer": "5, 1", "winter_snow": "11, 15"}
ONE = {"custom": "true", "dial": "none", "winter_snow": "1, 1"}


def play(asked, strings=None):
    """Every path that puts text on screen, run over `strings` (the English table unless
    given), with each id asked for added to `asked`. Returns the text the player reads."""
    rows = []
    # the Forecast page: each kind of weather, each tier, real weather, both units
    for kw in (dict(), dict(mcm={"seasons_zone/main/wx_exact": True}),
               dict(plan=[(700, "storm"), (900, "storm")]), dict(plan=[(690, "rain")]),
               dict(weather="stock"), dict(weather="stock", elapsed_h=5),
               dict(weather="stock", elapsed_h=7), dict(weather="stock", period=3, elapsed_h=0),
               dict(weather="none"), dict(standing=250, surge_left=HOUR),
               dict(standing=250, surge_left=5 * HOUR), dict(standing=250, surge_left=12 * HOUR),
               dict(standing=250, surge_left=20 * HOUR), dict(standing=900),
               dict(standing=900, surge_left=100), dict(standing=900, surge_left=1800),
               dict(observed=True), dict(observed=True, units="fahrenheit")):
        rows += page(world(asked=asked, strings=strings, **kw), "SeasonsForecast")
    # The Year: a day each kind marks, the day before a turn, calendars of the player's own
    for date, cal in (((2026, 10, 2), None), ((2026, 4, 26), None), ((2026, 9, 14), None),
                      ((2026, 7, 1), OWN), ((2026, 12, 20), dict(OWN, name_winter_snow="Long")),
                      ((2026, 7, 1), ONE)):
        rows += page(world(date=date, calendar=cal, asked=asked, strings=strings),
                     "SeasonsPDA")
    # both, when their data cannot be read
    w = world(asked=asked, strings=strings)
    w.g.zzz_seasons_of_the_zone.forecast_page = None
    w.g.zzz_seasons_of_the_zone.calendar_page = None
    rows += page(w, "SeasonsForecast") + page(w, "SeasonsPDA")
    # the page's helpers over their ranges, whichever branch the states above missed
    fc = w.got["ui_seasons_forecast"]
    for v in range(0, 30000, 100):
        rows += [fc["countdown"](v), fc["lead"](v / 10.0),
                 fc["window_text"](w.lua.table_from({"lo": v / 20.0, "hi": v / 10.0}))]
    # the report on loading in: tomorrow, in some days, all three phases, pinned, one season
    for date, blend, pin, cal in (((2026, 9, 14), 0, None, None), ((2026, 9, 22), 0, None, None),
                                  ((2026, 9, 12), 14, None, None), ((2026, 9, 15), 14, None, None),
                                  ((2026, 9, 19), 14, None, None), ((2026, 7, 1), 0, "autumn", None),
                                  ((2026, 7, 1), 0, None, ONE)):
        w = world(date=date, calendar=cal, asked=asked, strings=strings,
                  mcm={"seasons_zone/main/blend_days": blend, "seasons_zone/main/mode": pin})
        w.z["pda_announce"]()
        rows += [m for m, _ in w.sent]
    # the season change notice across a turn, the ecologists' news, every transmission
    for blend in (0, 14):
        w = world(date=(2026, 9, 1), standing=250, asked=asked, strings=strings,
                  mcm={"seasons_zone/main/blend_days": blend})
        w.z["actor_on_first_update"]()
        for day in range(2, 30):
            w.g.os = w.g.fixed_os(2026, 9, day)
            w.z["apply"](False)
        w.g.zzz_seasons_of_the_zone.eco_access_tick()
        days = w.z["REMEMBRANCE"]
        for key in days.keys():
            for pool in ("opens", "lines"):
                for i in range(1, len(days[key][pool]) + 1):
                    w.z["rem_send"](days[key], pool, i)
        rows += [m for m, _ in w.sent]
    # MCM: a pin the calendar disagrees with, no Mod App Creator, a mod listed, no mods yet
    tr = translator(strings)
    for kw in (dict(mcm={"seasons_zone/main/mode": "summer"}, weather="stock",
                    mods={"mods": {"staged_for": "none", "list": ""}}),
               dict(mac=False, weather="none", mods={
                   "mods": {"staged_for": "autumn", "list": "pack"},
                   "pack": {"name": "Pack", "seasons": "winter"}}),
               dict(calendar=OWN)):
        w = world(asked=asked, strings=strings, **kw)
        w.z["actor_on_first_update"]()
        for r in mcm_rows(w.g):
            if re.match(r"^[a-z0-9_]+$", str(r)) and "_" in str(r):
                asked.append(r)              # an id MCM will look up
            rows.append(tr(r))
    return rows


# --- the cases ------------------------------------------------------------------------------

CASES = []


def case(fn):
    CASES.append(fn)
    return fn


@case
def t_the_tables_read_as_the_engine_reads_them():
    files = table_files()
    assert len(files) >= 3, "found %d string tables in %s" % (len(files), TEXT)
    seen, problems, n = {}, [], 0
    for p in files:
        raw = open(p, "rb").read()
        assert declared_encoding(raw) == "windows-1251", \
            "%s declares %s" % (os.path.basename(p), declared_encoding(raw))
        entries, bad = read_table(raw, os.path.basename(p))
        problems += bad
        for sid, _ in entries:
            here = os.path.basename(p)
            if sid in seen:
                problems.append("%s is in %s" % (sid, "%s twice" % here if seen[sid] == here
                                                 else "both %s and %s" % (seen[sid], here)))
            seen[sid] = here
            n += 1
    assert not problems, "; ".join(problems[:10])
    assert table()["st_sotz_plural_rule"] == "en", "the English table names no plural rule"
    return "%d ids in %d files, each once, all windows-1251" % (n, len(files))


HOLDER = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)")


def translation_problems(folder, eng):
    """What is wrong with one language's tables beside the English ones, `eng` {id: text}:
    an id English doesn't have, a $placeholder its English doesn't fill, and, under the
    Russian plural rule, a count without its _few form. A table may leave ids out: the game
    shows the English for those."""
    out, have = [], {}
    for p in sorted(glob.glob(os.path.join(folder, "*.xml"))):
        entries, bad = read_table(open(p, "rb").read(), os.path.basename(p))
        out += bad
        have.update(entries)
    lang = os.path.basename(folder)
    for sid, t in sorted(have.items()):
        if sid not in eng:
            if not (sid.endswith("_few") and sid[:-4] + "_many" in eng):
                out.append("%s: %s is not in the English table" % (lang, sid))
            continue
        extra = set(HOLDER.findall(t)) - set(HOLDER.findall(eng[sid]))
        if extra:
            out.append("%s: %s has $%s, which the game doesn't fill there"
                       % (lang, sid, ", $".join(sorted(extra))))
    if have.get("st_sotz_plural_rule", eng.get("st_sotz_plural_rule")) == "ru":
        for sid in sorted(eng):
            if sid.endswith("_many") and sid[:-5] + "_one" in eng \
                    and sid[:-5] + "_few" not in have:
                out.append("%s: %s_few is missing, which the Russian rule needs for 2 to 4"
                           % (lang, sid[:-5]))
    return out


@case
def t_a_translation_fits_the_english_table():
    """Every language folder beside eng is checked against it, and a Russian table with a
    fault of each kind is caught; a partial one that is right passes."""
    eng = table()
    langs = [d for d in sorted(os.listdir(TEXT)) if d != "eng"
             and os.path.isdir(os.path.join(TEXT, d))]
    problems = [p for d in langs for p in translation_problems(os.path.join(TEXT, d), eng)]
    assert not problems, "; ".join(problems[:10])
    d = os.path.join(TMP, "rus")
    os.makedirs(d, exist_ok=True)
    head = '<?xml version="1.0" encoding="windows-1251"?>\n<string_table>\n'
    good = ('<string id="st_sotz_plural_rule"><text>ru</text></string>\n'
            '<string id="st_sotz_date"><text>$day $month $year</text></string>\n')
    for sid in sorted(eng):
        if sid.endswith("_many") and sid[:-5] + "_one" in eng:
            good += '<string id="%s_few"><text>%s</text></string>\n' % (sid[:-5], eng[sid])
    with open(os.path.join(d, "st_seasons_of_the_zone.xml"), "wb") as f:
        f.write((head + good + "</string_table>\n").encode("cp1251"))
    ok = translation_problems(d, eng)
    assert not ok, ok
    bad = (good.replace("$day $month $year", "$day $month $year $moon")
           + '<string id="st_sotz_no_such_id"><text>х</text></string>\n')
    few = [l for l in good.split("\n") if "_few" in l]
    bad = bad.replace(few[0] + "\n", "")
    with open(os.path.join(d, "st_seasons_of_the_zone.xml"), "wb") as f:
        f.write((head + bad + "</string_table>\n").encode("cp1251"))
    got = translation_problems(d, eng)
    assert len(got) == 3 and any("$moon" in g for g in got) and any(
        "no_such_id" in g for g in got) and any("_few is missing" in g for g in got), got
    return ("%d language folder(s) beside eng, all fit; a partial Russian table passes, and "
            "an unknown id, a stray $placeholder and a missing _few are each caught"
            % len(langs))


@case
def t_a_broken_table_is_caught():
    head = b'<?xml version="1.0" encoding="windows-1251"?>\n<string_table>\n'
    for label, xml, says in (
            ("a duplicate", b'<string id="a"><text>x</text></string>'
                            b'<string id="a"><text>y</text></string>', None),
            ("bad XML", b'<string id="a"><text>x</text>', "well-formed"),
            ("two spaces", b'<string id="a"><text>x  y</text></string>', "run of spaces"),
            ("an empty text", b'<string id="a"><text></text></string>', "something in it"),
            ("a byte cp1251 lacks", b'<string id="a"><text>\x98</text></string>', "not")):
        entries, bad = read_table(head + xml + b"\n</string_table>")
        if says is None:
            ids = [sid for sid, _ in entries]
            assert len(ids) != len(set(ids)), "%s went unseen" % label
        else:
            assert any(says in b for b in bad), "%s: %s" % (label, bad)
    return "a duplicate, bad XML, a run of spaces, an empty text and a stray byte"


@case
def t_every_id_in_the_scripts_is_in_the_table():
    scripts, have = shipped_scripts(), table()
    bad = ids_in(scripts, have)
    assert not bad, "ids the English table cannot answer: " + "; ".join(bad[:12])
    mcm = test_mcm_strings.keys(test_mcm_strings.read(test_mcm_strings.MCM))
    missing = [k for k, _ in mcm if k not in have]
    assert not missing, "MCM labels with no string: %s" % missing
    named = sum(1 for s in scripts for t in s.t if t.kind == "str" and ID.match(body(t)))
    assert named >= 100, "only %d ids read off the scripts - the scan is broken" % named
    return "%d ids named in the scripts and %d MCM labels, all in the table" % (named,
                                                                                len(mcm))


@case
def t_every_id_asked_for_in_play_is_in_the_table():
    asked, have = [], table()
    rows = play(asked)
    missing = sorted(set(a for a in asked if a not in have))
    assert not missing, "asked for and not in the table: %s" % missing[:12]
    # and the ids really were asked for: the transmissions alone are over a hundred
    rem = [a for a in set(asked) if a.startswith("st_sotz_rem_")]
    assert len(rem) >= 108, "only %d transmissions asked for" % len(rem)
    shown = [r for r in rows if r]
    left = [r for r in shown if ID.match(str(r))]
    assert not left, "a raw id reached the screen: %s" % left[:5]
    return "%d different ids asked for over %d lines of text, every one in the table" % (
        len(set(asked)), len(shown))


@case
def t_a_translation_reaches_every_line():
    """Every path again, over a stand-in translation that brackets each text. A line with a
    word in it and no bracket did not come through the table, and would stay English."""
    marked = {sid: (t if sid == "st_sotz_plural_rule" else "[%s]" % t)
              for sid, t in table().items()}
    rows = [str(r) for r in play([], marked) if r]
    # the player's own words: the season named in configure.bat above
    theirs = {"Long"}
    left = sorted(set(r for r in rows if re.search(r"[A-Za-z]{2}", r) and "[" not in r
                      and r not in theirs))
    assert not left, "%d line(s) no translation would change: %s" % (len(left), left[:8])
    return "%d lines on screen, every one through the table" % len(rows)


@case
def t_a_missing_id_is_caught():
    have = table()
    for label, src in (
            ("a literal id", 'put(w, sotz_text.text("st_sotz_fc_not_there"))'),
            ("an id in a table", 'local T = {a = "st_sotz_sky_not_there"}'),
            ("a helper's literal", 'local x = sotz_text.text("typo_fc_title")'),
            ("an alias's literal", 'local t = sotz_text.text\nlocal x = t("typo_fc_title")'),
            ("a count's id", 'local x = sotz_text.plural("st_sotz_year_in_weeks", 2)'),
            ("an id built from an unknown start",
             'local x = sotz_text.text("st_sotz_new_" .. k)')):
        bad = ids_in([Script("probe.script", src)], have, known={})
        assert bad, "%s went unseen" % label
    # and the control: ids the table has pass
    good = Script("probe.script", 'local x = sotz_text.plural("st_sotz_year_in_days", 2)\n'
                                  'local y = sotz_text.text("st_sotz_fc_title")')
    assert not ids_in([good], have, known={}), ids_in([good], have, known={})
    return "a literal, a table's, a helper's, an alias's, a count's and a built id"


@case
def t_no_english_reaches_the_screen():
    found = []
    for s in shipped_scripts():
        found += english_on_screen(s)
    assert not found, "%d English literal(s) on screen: %s" % (len(found), "; ".join(
        "%s:%d %r" % f for f in found[:12]))
    return "no English literal reaches a widget, a PDA message or an MCM row"


# the scripts as they were before their words moved to the string table
BEFORE = "2107444"


@case
def t_the_scan_finds_what_the_old_scripts_showed():
    found, read = [], 0
    for p in sorted(glob.glob(os.path.join(SCRIPTS, "*.script"))):
        rel = os.path.relpath(p, ROOT).replace(os.sep, "/")
        r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (BEFORE, rel)],
                           capture_output=True)
        if r.returncode != 0:
            continue                                # a script that came later
        read += 1
        found += english_on_screen(Script(os.path.basename(p), r.stdout.decode("utf-8")))
    assert read >= 8, "git produced %d of the scripts as they were at %s" % (read, BEFORE)
    got = {(f, lit) for f, _, lit in found}
    want = [("ui_seasons_forecast.script", "No readings right now."),
            ("ui_seasons_forecast.script", "Partly cloudy"),
            ("ui_seasons_forecast.script", "turns in %d to %d hours"),
            ("ui_seasons_forecast.script", "settled"),
            ("ui_seasons_forecast.script", "planned"),
            ("ui_seasons_forecast.script", "C"),
            ("ui_seasons_forecast.script", "CLASSIFIED"),
            ("ui_seasons_forecast.script", "Rain or storm"),
            ("ui_seasons_pda.script", "The calendar can't be read right now."),
            ("ui_seasons_pda.script", "today"),
            ("ui_seasons_pda.script", "in %d days"),
            ("ui_seasons_pda.script", "Jan"),
            ("ui_seasons_pda.script", "from "),
            ("zzz_seasons_of_the_zone.script", "deep winter"),
            ("zzz_seasons_of_the_zone.script", "September"),
            ("zzz_seasons_of_the_zone.script", "Seasons: Deep winter"),
            ("zzz_seasons_of_the_zone.script", "saturation "),
            ("zzz_seasons_of_the_zone.script", "Today is "),
            ("zzz_seasons_of_the_zone.script", "%s in the Zone. %s. %s begins in %s days."),
            ("zzz_seasons_of_the_zone.script",
             "Owl: No traffic on any channel. Nobody is working today."),
            ("zzz_seasons_of_the_zone_mcm.script", "No seasonal mods are set for this season."),
            ("zzz_seasons_of_the_zone_mcm.script", "Built-in"),
            ("sotz_pda.script", "The Year")]
    missed = [w for w in want if w not in got]
    assert not missed, "the scan missed, in the old scripts: %s" % missed
    assert len(found) >= 250, "only %d found in the old scripts" % len(found)
    return "%d English literals in the scripts as of %s, every sample among them" % (
        len(found), BEFORE)


@case
def t_the_scan_follows_a_name_back_to_its_words():
    def scan(src):
        return [lit for _, _, lit in english_on_screen(Script("probe.script", src), set())]
    for label, src, want in (
            ("handed straight over", 'function P:F()\n    put(self.a, "Forecast")\nend', "Forecast"),
            ("through a local", 'function P:F()\n    local s = "settled"\n'
                                '    put(self.a, s)\nend', "settled"),
            ("through a function", 'local function f() return "soon" end\n'
                                   'function P:F()\n    put(self.a, f())\nend', "soon"),
            ("through a table", 'local T = {a = "fair"}\n'
                                'function P:F(k)\n    put(self.a, T[k])\nend', "fair"),
            ("into a message", 'news_manager.send_tip(db.actor, "Hold on", nil)', "Hold on"),
            ("into an MCM row", 'local r = {text = "calm"}', "calm")):
        assert want in scan(src), "%s: %s" % (label, scan(src))
    for label, src in (
            ("a log line", 'say("the page failed to build")'),
            ("a string id", 'put(self.a, sotz_text.text("st_sotz_fc_title"))'),
            ("a key compared", 'if d.kind == "memorial" then put(self.a, "") end'),
            ("an index", 'put(self.a, T["Clear sky"])')):
        assert not scan(src), "%s was taken for English: %s" % (label, scan(src))
    return "straight, through a local, a function and a table; logs, ids and keys left be"


def sandbox(strings):
    """sotz_text over a string table of the case's own."""
    lua = LuaRuntime(unpack_returned_tuples=True)
    return lua, install(lua, lua.globals(), strings)


FORMS = {"en": {0: "many", 1: "one", 2: "many", 5: "many", 11: "many", 21: "many",
                22: "many", 25: "many", 111: "many"},
         "ru": {0: "many", 1: "one", 2: "few", 5: "many", 11: "many", 21: "one",
                22: "few", 25: "many", 111: "many"}}


@case
def t_plural_picks_the_form():
    for rule, want in FORMS.items():
        _, tx = sandbox({"st_sotz_plural_rule": rule, "x_one": "one $n", "x_few": "few $n",
                         "x_many": "many $n"})
        got = {n: tx.plural("x", n) for n in want}
        assert got == {n: "%s %d" % (f, n) for n, f in want.items()}, (rule, got)
    # a table with no _few, as English has none: few falls back to many
    _, tx = sandbox({"st_sotz_plural_rule": "ru", "x_one": "one $n", "x_many": "many $n"})
    assert (tx.plural("x", 22), tx.plural("x", 21)) == ("many 22", "one 21")
    # and a table that names no rule counts as English
    _, tx = sandbox({"x_one": "one $n", "x_few": "few $n", "x_many": "many $n"})
    assert tx.plural("x", 22) == "many 22", tx.plural("x", 22)
    # the real English table
    _, tx = sandbox(table())
    got = [tx.plural("st_sotz_year_in_days", n) for n in (1, 2, 21)]
    assert got == ["in 1 day", "in 2 days", "in 21 days"], got
    return "0 1 2 5 11 21 22 25 111 under en and ru; a missing few reads as many"


@case
def t_a_translation_can_move_the_words():
    lua, tx = sandbox({"st_sotz_date": "$day $month $year",
                       "st_sotz_month_9_date": "sentyabrya",
                       "st_sotz_date_short": "$day $month", "st_sotz_month_4_short_date": "apr",
                       "x": "$b before $a, $a again, $c untouched", "p_many": "100% $n"})
    assert tx.date(9, 25, 2026) == "25 sentyabrya 2026", tx.date(9, 25, 2026)
    assert tx.date_short(4, 15) == "15 apr", tx.date_short(4, 15)
    got = tx.text("x", lua.table_from({"a": "A", "b": "%1 B"}))
    assert got == "%1 B before A, A again, $c untouched", got
    assert tx.plural("p", 3) == "100% 3", tx.plural("p", 3)
    # and English, from the table as shipped
    _, en = sandbox(table())
    assert en.date(9, 25, 2026) == "September 25, 2026", en.date(9, 25, 2026)
    return "the day before the month, a value used twice, a % left alone"


if __name__ == "__main__":
    print("  checking the words on screen under %s" % LUA_NAME)
    bad = 0
    for fn in CASES:
        try:
            print("  PASS  %-44s %s" % (fn.__name__[2:], fn()))
        except AssertionError as e:
            bad += 1
            print("  FAIL  %-44s %s" % (fn.__name__[2:], e))
        except Exception as e:
            bad += 1
            print("  ERROR %-44s %s: %s" % (fn.__name__[2:], type(e).__name__, e))
    print("\n  %d/%d passed" % (len(CASES) - bad, len(CASES)))
    sys.exit(1 if bad else 0)
