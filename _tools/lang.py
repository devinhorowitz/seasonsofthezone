"""The tools' words in the player's language.

English is written in the code. A translation is a gettext file, _tools/lang/<code>.po, read
as it is: nothing to compile. A string it doesn't have stays English, so a translation can be
done a piece at a time, and a new release with new strings still works with an older one.

    from lang import _, N_, ngettext, pgettext
    _("Save")                                  a whole label or sentence, never a piece of one
    _("%s is on today.") % name                values go in after, never inside _()
    ngettext("%d mod", "%d mods", n) % n       a count: the form the language needs for n
    pgettext("month, short", "May")            the same English, said differently in context
    N_("Spring")                               marked for translation where it is written, at
                                               import time; translated with _() where shown

The language is SEASONS_LANG in the environment, else the one chosen in the window (saved
in _tools/lang/language.txt), else the game's, when there is a translation for it, else
English. SEASONS_LANG=qps is a test language that marks every string that went through
here, so one that didn't stands out.

build_messages.py collects the strings into lang/messages.pot and brings each .po up to
date with it; docs/TRANSLATING.md is how to translate.
"""
import argparse
import codecs
import io
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = os.path.join(HERE, "lang")
CHOICE = os.path.join(FOLDER, "language.txt")
ENGLISH = "en"
PSEUDO = "qps"
# a language's name in itself, for a translation whose header doesn't give it
NAMES = {"ru": "\u0420\u0443\u0441\u0441\u043a\u0438\u0439",
         "uk": "\u0423\u043a\u0440\u0430\u0457\u043d\u0441\u044c\u043a\u0430",
         "pl": "Polski", "fr": "Fran\u00e7ais", "de": "Deutsch", "es": "Espa\u00f1ol",
         "it": "Italiano", "cs": "\u010ce\u0161tina",
         "pt_BR": "Portugu\u00eas (Brasil)", "tr": "T\u00fcrk\u00e7e"}
# the game's names for its languages (configs/localization.ltx), and ours
GAME_CODES = {"eng": "en", "rus": "ru", "ukr": "uk", "pol": "pl", "fra": "fr", "ger": "de",
              "deu": "de", "spa": "es", "ita": "it", "cze": "cs", "ptb": "pt_BR",
              "chn": "zh", "cht": "zh_TW", "jpn": "ja", "kor": "ko", "tur": "tr"}


# --- reading a .po file ------------------------------------------------------------------

_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "a": "\a", "b": "\b",
            "f": "\f", "v": "\v"}


def _unquote(text):
    """The string a .po line holds between its quotes, escapes undone."""
    body = text.strip()
    if len(body) < 2 or body[0] != '"' or body[-1] != '"':
        raise ValueError("a string in quotes was expected: %s" % text.strip()[:60])
    body = body[1:-1]
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), "\\" + m.group(1)), body)


def read_po(path):
    """[(context, msgid, msgid_plural, [msgstr, ...], flags, obsolete)] for every entry of a
    .po file, the header (msgid "") included. Comments other than flags are left out."""
    return read_po_lines(po_text_of(path).splitlines(), os.path.basename(path))


def po_text_of(path):
    """A .po file's text, in the charset its header names - UTF-8 when it names none, or
    one Python doesn't know. A letter that isn't in it is a ValueError."""
    with io.open(path, "rb") as f:
        data = f.read()
    if data.startswith(codecs.BOM_UTF8):
        return data[3:].decode("utf-8")
    m = re.search(br"charset=([A-Za-z0-9_.:-]+)", data[:4096])
    enc = m.group(1).decode("ascii") if m else "utf-8"
    try:
        codecs.lookup(enc)
    except LookupError:
        enc = "utf-8"
    return data.decode(enc)


def read_po_lines(lines, name="<lines>"):
    """read_po() for the lines of a .po file already read."""
    entries = []
    state = {"cur": None, "key": None, "flags": []}

    def done():
        cur = state["cur"]
        if cur and "msgid" in cur:
            # msgstr[n] by its number: a form not written yet is empty, not skipped
            forms = [k for k in cur if isinstance(k, int)]
            strs = ([cur["msgstr"]] if "msgstr" in cur else
                    [cur.get(i, "") for i in range(max(forms) + 1)] if forms else [])
            entries.append((cur.get("msgctxt"), cur["msgid"], cur.get("msgid_plural"), strs,
                            cur["flags"], cur["obsolete"]))
        state["cur"], state["key"] = None, None

    for raw in lines:
        line = raw.rstrip("\r\n").lstrip()
        obsolete = line.startswith("#~")
        if obsolete:
            line = line[2:].lstrip()
            if line.startswith(("|", "#")):
                continue                # msgmerge's previous msgid, or a comment, kept old
        if not line.strip():
            done()
            continue
        if line.startswith("#,"):
            state["flags"] += [f.strip() for f in line[2:].split(",") if f.strip()]
            continue
        if line.startswith("#"):
            continue
        m = re.match(r"^(msgctxt|msgid_plural|msgid|msgstr)(?:\[(\d+)\])?\s+(.*)$", line)
        cur = state["cur"]
        if m:
            word, index, rest = m.groups()
            # a msgctxt or msgid after an entry's msgstr starts the next entry
            if word in ("msgctxt", "msgid") and cur is not None and any(
                    k == "msgstr" or isinstance(k, int) for k in cur):
                done()
            if state["cur"] is None:
                state["cur"] = {"flags": state["flags"], "obsolete": obsolete}
                state["flags"] = []
            state["key"] = int(index) if index is not None else word
            state["cur"][state["key"]] = _unquote(rest)
            continue
        if line.startswith('"') and cur is not None and state["key"] is not None:
            cur[state["key"]] += _unquote(line)
            continue
        raise ValueError("%s: can't read this line: %s" % (name, line[:60]))
    done()
    return entries


def headers(entries):
    """{name: value} from a .po file's header entry."""
    for ctx, msgid, _p, strs, _f, obsolete in entries:
        if msgid == "" and ctx is None and not obsolete:
            out = {}
            for line in (strs[0] if strs else "").split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    out[k.strip()] = v.strip()
            return out
    return {}


# --- plural rules: the C expression a .po file carries, run safely ----------------------

_TOKEN = re.compile(r"\s*(?:(\d+)|(n)|(==|!=|<=|>=|&&|\|\||[<>!%?:()]))")


def plural_rule(expr):
    """A function of n from a Plural-Forms `plural=` expression, such as Russian's
    n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2.
    Only numbers, n and C's operators are allowed; anything else raises ValueError."""
    tokens, pos = [], 0
    expr = expr.strip().rstrip(";")
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m or m.end() == pos:
            raise ValueError("can't read the plural rule at: %s" % expr[pos:pos + 20])
        tokens.append(m.group(1) or m.group(2) or m.group(3))
        pos = m.end()
    at = [0]

    def peek():
        return tokens[at[0]] if at[0] < len(tokens) else None

    def take(want=None):
        t = peek()
        if t is None:
            raise ValueError("the plural rule ends too early")
        if want and t != want:
            raise ValueError("the plural rule has %r where %r goes" % (t, want))
        at[0] += 1
        return t

    def ternary():
        cond = orr()
        if peek() == "?":
            take("?")
            a = ternary()
            take(":")
            b = ternary()
            return lambda n: a(n) if cond(n) else b(n)
        return cond

    def binary(sub, ops):
        def parse():
            left = sub()
            while peek() in ops:
                op, right = take(), sub()
                left = ops[op](left, right)
            return left
        return parse

    def unary():
        if peek() == "!":
            take()
            f = unary()
            return lambda n: int(not f(n))
        if peek() == "(":
            take("(")
            f = ternary()
            take(")")
            return f
        t = take()
        if t == "n":
            return lambda n: n
        if t.isdigit():
            v = int(t)
            return lambda n: v
        raise ValueError("the plural rule has %r where a number goes" % t)

    mod = binary(unary, {"%": lambda a, b: lambda n: a(n) % b(n) if b(n) else 0})
    cmp_ = binary(mod, {"<": lambda a, b: lambda n: int(a(n) < b(n)),
                        ">": lambda a, b: lambda n: int(a(n) > b(n)),
                        "<=": lambda a, b: lambda n: int(a(n) <= b(n)),
                        ">=": lambda a, b: lambda n: int(a(n) >= b(n))})
    eq = binary(cmp_, {"==": lambda a, b: lambda n: int(a(n) == b(n)),
                       "!=": lambda a, b: lambda n: int(a(n) != b(n))})
    andd = binary(eq, {"&&": lambda a, b: lambda n: int(bool(a(n)) and bool(b(n)))})
    orr = binary(andd, {"||": lambda a, b: lambda n: int(bool(a(n)) or bool(b(n)))})
    rule = ternary()
    if at[0] != len(tokens):
        raise ValueError("the plural rule has more after its end: %s" % " ".join(tokens[at[0]:]))
    return lambda n: int(rule(int(n)))


def english_plural(n):
    return 0 if n == 1 else 1


_HOLDER = re.compile(r"%(?:\(([^)]*)\))?[-#0 +]*\d*(?:\.\d+)?([sdifgxXr%])")


def holders(text):
    """The % placeholders in a string, as the code fills them: (the names of the named ones,
    the kinds of the others in order). %% is not one."""
    found = [(m.group(1), m.group(2)) for m in _HOLDER.finditer(text) if m.group(2) != "%"]
    return (frozenset(n for n, _ in found if n is not None),
            tuple(c for n, c in found if n is None))


def fits(text, *english):
    """Can `text` stand in for the English strings given, when the code fills it in? Its
    unnamed placeholders must come as theirs do - one more or less and filling it fails -
    and its named ones must be among theirs; a name can be left out. And it must fill in
    as they do: a stray % - "50%." - is a crash, not a percent sign."""
    named, order = holders(text)
    want = [holders(e) for e in english]
    if not (named <= frozenset().union(*(w[0] for w in want))
            and order in {w[1] for w in want}):
        return False
    return fills(text, *english)


_STAND_IN = {"d": 1, "i": 1, "x": 1, "X": 1, "f": 1.0, "g": 1.0}


def fills(text, *english):
    """Does `text` fill in with values like those the code gives the English: a tuple of
    their kinds, or a dict of their names? The code leaves a string with no placeholder
    and no %% alone, so any text fills in for that."""
    found = []
    for e in english:
        found = [(m.group(1), m.group(2)) for m in _HOLDER.finditer(e)]
        if found:
            break
    if not found:
        return True
    names = {n: _STAND_IN.get(c, "x") for n, c in found if n is not None}
    values = names or tuple(_STAND_IN.get(c, "x") for n, c in found if c != "%")
    try:
        text % values
    except (TypeError, ValueError, KeyError):
        return False
    return True


# --- a catalog ----------------------------------------------------------------------------

class Catalog(object):
    """One language's translations: {(context, msgid): [msgstr, ...]}, and its plural rule."""

    def __init__(self, code, entries=()):
        self.code, self.table, self.plural, self.nplurals = code, {}, english_plural, 2
        self.name = code
        head = headers(entries)
        forms = head.get("Plural-Forms", "")
        m = re.search(r"nplurals\s*=\s*(\d+)\s*;\s*plural\s*=\s*([^;]+);?", forms)
        if m:
            self.nplurals, self.plural = int(m.group(1)), plural_rule(m.group(2))
        self.name = head.get("X-Language-Name") or NAMES.get(code) or code
        self.dropped = []           # translations whose placeholders don't match the English
        for ctx, msgid, plural, strs, flags, obsolete in entries:
            if not msgid or obsolete or "fuzzy" in flags or not any(strs):
                continue
            refs = (msgid,) if plural is None else (msgid, plural)
            if any(s and not fits(s, *refs) for s in strs):
                self.dropped.append((ctx, msgid))
                continue
            self.table[(ctx, msgid)] = strs

    def __len__(self):
        return len(self.table)

    def get(self, ctx, msgid):
        strs = self.table.get((ctx, msgid))
        return strs[0] if strs and strs[0] else None

    def nget(self, ctx, msgid, plural, n):
        strs = self.table.get((ctx, msgid))
        if strs:
            i = self.plural(n)
            if 0 <= i < len(strs) and strs[i]:
                return strs[i]
        return None


_ACCENTS = dict(zip("aceinorsuyAEINOSUY", "àçéîñöŕšûýÀÉÎÑÖŠÛÝ"))
_HOLDERS = re.compile(r"%(?:\([^)]*\))?[-#0 +]*\d*(?:\.\d+)?[sdifgxXr%]|\{[^{}]*\}|\\n|\n")


def pseudo(text):
    """A string as the test language shows it: marked at both ends, its letters changed,
    its % and {} placeholders and line breaks kept, so it still formats."""
    out, last = [], 0
    for m in _HOLDERS.finditer(text):
        out.append("".join(_ACCENTS.get(c, c) for c in text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append("".join(_ACCENTS.get(c, c) for c in text[last:]))
    return "‹" + "".join(out) + "›"


class PseudoCatalog(Catalog):
    def __init__(self):
        Catalog.__init__(self, PSEUDO)
        self.name = "Test language"

    def get(self, ctx, msgid):
        return pseudo(msgid)

    def nget(self, ctx, msgid, plural, n):
        return pseudo(msgid if n == 1 else plural)


# --- which language -----------------------------------------------------------------------

def po_path(code):
    return os.path.join(FOLDER, "%s.po" % code)


def load(code):
    """The catalog for `code`, or None when there is no file for it or it can't be read."""
    if code == PSEUDO:
        return PseudoCatalog()
    path = po_path(code)
    if not os.path.isfile(path):
        return None
    try:
        return Catalog(code, read_po(path))
    except (OSError, ValueError) as e:
        # said once, and in English, since the translation is what can't be read
        if path not in _unread:
            _unread.add(path)
            sys.stderr.write("  lang/%s can't be read (%s), so the tools show English. "
                             "py _tools\\build_messages.py --check says more.\n"
                             % (os.path.basename(path), e))
        return None


_unread = set()


def available():
    """[(code, name, strings translated)] for English and every language with a
    translation that has any strings in it, English first."""
    out = [(ENGLISH, "English", None)]
    try:
        names = sorted(f[:-3] for f in os.listdir(FOLDER) if f.endswith(".po"))
    except OSError:
        names = []
    for code in names:
        cat = load(code)
        if cat is not None and len(cat):
            out.append((code, cat.name, len(cat)))
    return out


def gamma_root():
    """The GAMMA folder these tools belong to: the one above _tools, or, for the copy in a
    mod's own folder (mods\\<mod>\\_tools, where the installer runs), two further up."""
    above = os.path.dirname(HERE)
    for root in (above, os.path.dirname(os.path.dirname(above))):
        if os.path.isfile(os.path.join(root, "ModOrganizer.ini")):
            return root
    return above


def saved_choice():
    """The language picked in the window: in this _tools, or, when these are the mod
    folder's own tools, in the GAMMA folder's."""
    theirs = os.path.join(gamma_root(), "_tools", "lang", "language.txt")
    for path in (CHOICE, theirs):
        try:
            got = io.open(path, encoding="utf-8-sig", errors="replace").read().strip()
        except (OSError, ValueError):
            continue
        # a file saved in another encoding, or with other words in it, is no choice
        if re.match(r"^[A-Za-z]{2,3}(?:_[A-Za-z]{2,4})?$", got):
            return got
    return None


def save_choice(code):
    """Keep the language picked in the window, for the window and play.bat alike."""
    os.makedirs(FOLDER, exist_ok=True)
    io.open(CHOICE, "w", encoding="utf-8").write(code + "\n")


def _mo2(root):
    """(mods folder, [enabled mods, highest priority first]) of the MO2 this is in."""
    ini = os.path.join(root, "ModOrganizer.ini")
    try:
        text = io.open(ini, encoding="utf-8", errors="replace").read()
    except OSError:
        return None, []
    m = re.search(r"(?m)^selected_profile\s*=\s*(?:@ByteArray\()?([^)\r\n]*)\)?\s*$", text)
    profile = m.group(1).strip() if m else "Default"
    try:
        lines = io.open(os.path.join(root, "profiles", profile, "modlist.txt"),
                        encoding="utf-8", errors="replace").read().splitlines()
    except OSError:
        return None, []
    return os.path.join(root, "mods"), [l[1:].strip() for l in lines if l.startswith("+")]


def game_language(root=None):
    """The language the game shows, as our code, from the configs/localization.ltx that
    wins: in MO2's overwrite folder, where the game's own Options menu saves it, else among
    MO2's enabled mods, where a translation mod sets it; or None when none has one, which
    is English: the game's own is packed, and English."""
    root = root or gamma_root()
    mods, enabled = _mo2(root)
    places = [os.path.join(root, "overwrite", "gamedata", "configs", "localization.ltx")]
    places += [os.path.join(mods, m, "gamedata", "configs", "localization.ltx")
               for m in enabled] if mods else []
    for p in places:
        if os.path.isfile(p):
            break
    else:
        p = None
    if p is None:
        return None
    try:
        text = io.open(p, encoding="cp1251", errors="replace").read()
    except OSError:
        return None
    m = re.search(r"(?mi)^\s*language\s*=\s*([A-Za-z_]+)", text)
    return GAME_CODES.get(m.group(1).lower()) if m else None


def pick():
    """The language to use now: see the top of this file."""
    env = os.environ.get("SEASONS_LANG", "").strip()
    if env:
        return env
    choice = saved_choice()
    if choice:
        return choice
    game = game_language()
    if game and game != ENGLISH:
        cat = load(game)
        if cat is not None and len(cat):
            return game
    return ENGLISH


_catalog = None
_code = None


def use(code=None):
    """Switch to `code`, or to the language pick() says; English when there is no catalog
    for it. Returns the code in use."""
    global _catalog, _code
    code = code or pick()
    _catalog = None if code == ENGLISH else load(code)
    _code = code if _catalog is not None else ENGLISH
    return _code


def language():
    if _code is None:
        use()
    return _code


def _cat():
    if _code is None:
        use()
    return _catalog


# --- the calls the tools make -------------------------------------------------------------

def _(msgid):
    cat = _cat()
    return (cat.get(None, msgid) if cat is not None else None) or msgid


def N_(msgid):
    """Marks a string for translation where it can't be translated yet, at import time."""
    return msgid


def pgettext(context, msgid):
    cat = _cat()
    return (cat.get(context, msgid) if cat is not None else None) or msgid


def ngettext(singular, plural, n):
    cat = _cat()
    got = cat.nget(None, singular, plural, n) if cat is not None else None
    return got or (singular if english_plural(n) == 0 else plural)


def npgettext(context, singular, plural, n):
    cat = _cat()
    got = cat.nget(context, singular, plural, n) if cat is not None else None
    return got or (singular if english_plural(n) == 0 else plural)


class HelpAsWritten(argparse.HelpFormatter):
    """--help with each help as written. argparse fills %(default)s and the like into every
    help itself, so a percent sign in a translation would stop --help; none of ours uses
    that, and each is filled in before argparse sees it."""

    def _expand_help(self, action):
        return self._get_help_string(action)


class RawHelpAsWritten(HelpAsWritten, argparse.RawDescriptionHelpFormatter):
    pass


def parser(**kw):
    """An ArgumentParser that shows each help as written, its commands' too."""
    kw.setdefault("formatter_class", HelpAsWritten)
    return argparse.ArgumentParser(**kw)


# --- words every tool needs ---------------------------------------------------------------

def months():
    """The months' short names, as the date pickers list them: "Jan" to "Dec"."""
    return (pgettext("month, short", "Jan"), pgettext("month, short", "Feb"),
            pgettext("month, short", "Mar"), pgettext("month, short", "Apr"),
            pgettext("month, short", "May"), pgettext("month, short", "Jun"),
            pgettext("month, short", "Jul"), pgettext("month, short", "Aug"),
            pgettext("month, short", "Sep"), pgettext("month, short", "Oct"),
            pgettext("month, short", "Nov"), pgettext("month, short", "Dec"))


def month(m):
    """A month's short name, 1 to 12: "Aug"."""
    return months()[m - 1]


def month_long(m):
    """A month's name in full, as it goes in a date: "August"."""
    return (pgettext("month, in a date", "January"), pgettext("month, in a date", "February"),
            pgettext("month, in a date", "March"), pgettext("month, in a date", "April"),
            pgettext("month, in a date", "May"), pgettext("month, in a date", "June"),
            pgettext("month, in a date", "July"), pgettext("month, in a date", "August"),
            pgettext("month, in a date", "September"),
            pgettext("month, in a date", "October"),
            pgettext("month, in a date", "November"),
            pgettext("month, in a date", "December"))[m - 1]


def day(m, d):
    """A day of the year in short: "Aug 1"."""
    return pgettext("a day of the year, short: Aug 1",
                    "%(month)s %(day)d") % {"month": month(m), "day": d}


def and_list(words):
    """Words in a list the way a sentence runs them: "a", "a and b", "a, b and c"."""
    return _join(list(words), pgettext("the last two in a list", "%(rest)s and %(last)s"))


def or_list(words):
    """"a", "a or b", "a, b or c"."""
    return _join(list(words), pgettext("the last two in a list of choices",
                                       "%(rest)s or %(last)s"))


def _join(words, last_two):
    if len(words) < 2:
        return "".join(words)
    comma = pgettext("between words in a list", ", ")
    return last_two % {"rest": comma.join(words[:-1]), "last": words[-1]}


def date_long(when):
    """A date in full: "September 26, 2026"."""
    return pgettext("a date in full: September 26, 2026",
                    "%(month)s %(day)d, %(year)d") % {
        "month": month_long(when.month), "day": when.day, "year": when.year}
