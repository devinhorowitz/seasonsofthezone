"""The translation layer: lang.py reading a translator's .po file, build_messages.py keeping
the files in step with the tools, and the language switch in configure.bat's window.

Nothing is translated yet, so each case brings its own small Russian file.

  python _tools/test_lang.py
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import build_messages as bm                                     # noqa: E402
import lang                                                     # noqa: E402
import test_guide as tg                                         # noqa: E402

CASES = []
RU_HEAD = r'''msgid ""
msgstr ""
"Language: ru\n"
"X-Language-Name: Русский\n"
"Plural-Forms: nplurals=3; plural=(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
"(n%100<10 || n%100>=20) ? 1 : 2);\n"
'''


def case(fn):
    CASES.append(fn)
    return fn


class Folder(object):
    """lang.py pointed at a scratch folder of .po files for the length of a case."""

    def __init__(self, files):
        self.files = files

    def __enter__(self):
        self.dir = tempfile.TemporaryDirectory()
        self.was = (lang.FOLDER, lang.CHOICE, os.environ.pop("SEASONS_LANG", None))
        lang.FOLDER = self.dir.name
        lang.CHOICE = os.path.join(self.dir.name, "language.txt")
        for name, text in self.files.items():
            io.open(os.path.join(self.dir.name, name), "w", encoding="utf-8").write(text)
        return self.dir.name

    def __exit__(self, *a):
        lang.FOLDER, lang.CHOICE, env = self.was
        if env is not None:
            os.environ["SEASONS_LANG"] = env
        lang.use("en")
        self.dir.cleanup()


def russian_rule(n):
    """Russian's plural forms by the book, to check the one read from the file against."""
    if n % 10 == 1 and n % 100 != 11:
        return 0
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return 1
    return 2


@case
def t_a_po_file_is_read_as_a_translator_writes_it():
    """Contexts, plurals, strings over several lines, escapes; a fuzzy entry, an empty one
    and an obsolete one don't count."""
    ru = RU_HEAD + r'''
msgid "Save"
msgstr "Сохранить"

#, python-format
msgid "%d mod"
msgid_plural "%d mods"
msgstr[0] "%d мод"
msgstr[1] "%d мода"
msgstr[2] "%d модов"

msgctxt "month, short"
msgid "May"
msgstr "мая"

msgid ""
"Two lines\n"
"and a \"quote\""
msgstr ""
"Две строки\n"
"и \"кавычки\""

#, fuzzy
msgid "Close"
msgstr "Закрыть?"

msgid "Untranslated"
msgstr ""

#~ msgid "Gone"
#~ msgstr "Ушло"
'''
    with Folder({"ru.po": ru}):
        assert lang.use("ru") == "ru"
        got = [lang._("Save"), lang._("Close"), lang._("Untranslated"), lang._("Gone"),
               lang.pgettext("month, short", "May"), lang._("May"),
               lang._('Two lines\nand a "quote"')]
        assert got == ["Сохранить", "Close", "Untranslated", "Gone", "мая", "May",
                       'Две строки\nи "кавычки"'], got
        counts = [lang.ngettext("%d mod", "%d mods", n) % n for n in (1, 2, 5, 11, 21, 22)]
        assert counts == ["1 мод", "2 мода", "5 модов", "11 модов", "21 мод", "22 мода"], counts
        assert lang.available() == [("en", "English", None), ("ru", "Русский", 4)], \
            lang.available()
    return "4 translations used; fuzzy, empty and obsolete ones fall back to English"


@case
def t_the_plural_rule_is_run_as_written_and_nothing_else():
    """The rule the file carries gives Russian's forms for 0 to 1000, and anything that
    isn't n, numbers and C's operators is refused."""
    rule = lang.plural_rule("(n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && "
                            "(n%100<10 || n%100>=20) ? 1 : 2)")
    wrong = [n for n in range(1001) if rule(n) != russian_rule(n)]
    assert not wrong, wrong[:10]
    assert [lang.plural_rule("n != 1")(n) for n in (0, 1, 2)] == [1, 0, 1]
    assert [lang.plural_rule("n==1 ? 0 : n==2 ? 1 : 2")(n) for n in (1, 2, 3)] == [0, 1, 2]
    refused = []
    for bad in ("__import__('os')", "n ? ", "n + 1", "n %", "(n", "n == 1)", ""):
        try:
            lang.plural_rule(bad)
        except ValueError:
            refused.append(bad)
    assert len(refused) == 7, refused
    return "Russian's rule right for 0 to 1000; 7 bad rules refused"


@case
def t_a_translation_that_cant_be_filled_in_is_not_used():
    """A placeholder lost, added or of another kind would make the tool fail as it fills
    the string in; such a translation is left out, English is shown, and --check says so.
    Named ones may move, and a form may leave one out."""
    ru = RU_HEAD + r'''
msgid "%s is on today."
msgstr "Сегодня включён %s."

msgid "%s wins over %s."
msgstr "%s побеждает."

msgid "%d days"
msgstr "%s дней"

msgid "%(mod)s wins over %(other)s."
msgstr "%(other)s уступает %(mod)s."

msgid "%(mod)s is on in %(season)s."
msgstr "%(mod)s включён."

msgid "%(mod)s is on."
msgstr "%(mod)s включён в %(season)s."

msgid "%d%% done"
msgstr "%d%% готово, на 100%."

msgid "%(place)s is %(n)d km away."
msgstr "%(place)s в %(n)d км - 5%"

msgid "100%% sure"
msgstr "на 100%% уверен"
'''
    with Folder({"ru.po": ru}) as d:
        lang.use("ru")
        shown = [lang._("%s is on today.") % "X", lang._("%s wins over %s.") % ("A", "B"),
                 lang._("%d days") % 3,
                 lang._("%(mod)s wins over %(other)s.") % {"mod": "A", "other": "B"},
                 lang._("%(mod)s is on in %(season)s.") % {"mod": "A", "season": "S"},
                 lang._("%(mod)s is on.") % {"mod": "A"},
                 lang._("%d%% done") % 5,
                 lang._("%(place)s is %(n)d km away.") % {"place": "Kyiv", "n": 3},
                 lang._("100%% sure") % ()]
        assert shown == ["Сегодня включён X.", "A wins over B.", "3 days", "B уступает A.",
                         "A включён.", "A is on.", "5% done", "Kyiv is 3 km away.",
                         "на 100% уверен"], shown
        said = bm.fit_problems(os.path.join(d, "ru.po"))
        assert len(said) == 5 and all("can't be filled in" in s for s in said), said
    return ("5 unfit translations - 3 with lost or added placeholders, 2 with a stray % - "
            "left out and reported; reordered and dropped names, and %% as written, kept")


@case
def t_the_language_is_the_one_asked_for_else_the_game_s():
    """SEASONS_LANG first, then the choice saved from the window, then the game's language
    when there is a translation for it, then English; an unknown language is English."""
    ru = RU_HEAD + '\nmsgid "Save"\nmsgstr "Сохранить"\n'
    with Folder({"ru.po": ru}) as d, tempfile.TemporaryDirectory() as g:
        # a GAMMA folder whose winning localization.ltx says rus
        io.open(os.path.join(g, "ModOrganizer.ini"), "w", encoding="utf-8").write(
            "[General]\nselected_profile=@ByteArray(Default)\n")
        os.makedirs(os.path.join(g, "profiles", "Default"))
        io.open(os.path.join(g, "profiles", "Default", "modlist.txt"), "w",
                encoding="utf-8").write("+Russian Text\n-English Text\n")
        for mod, code in (("Russian Text", "rus"), ("English Text", "eng")):
            p = os.path.join(g, "mods", mod, "gamedata", "configs")
            os.makedirs(p)
            io.open(os.path.join(p, "localization.ltx"), "w", encoding="cp1251").write(
                "[string_table]\nlanguage = %s\nfont_prefix = _west\n" % code)
        assert lang.game_language(g) == "ru"
        real = lang.game_language
        lang.game_language = lambda root=None: real(g)
        try:
            got = [lang.pick()]
            lang.save_choice("en")
            got.append(lang.pick())
            os.environ["SEASONS_LANG"] = "ru"
            got.append(lang.pick())
            os.environ["SEASONS_LANG"] = "xx"
            got.append(lang.use())
            del os.environ["SEASONS_LANG"]
            os.remove(os.path.join(d, "language.txt"))
            os.remove(os.path.join(d, "ru.po"))
            got.append(lang.pick())             # the game's is Russian, but there's no file
        finally:
            lang.game_language = real
        assert got == ["ru", "en", "ru", "en", "en"], got
    return "game's Russian, saved English, SEASONS_LANG, unknown and missing, each as it should"


@case
def t_the_test_language_marks_strings_and_keeps_them_working():
    lang.use("qps")
    try:
        filled = lang._("%s is on, %d of %d.") % ("Mod", 2, 3)
        day = lang.day(8, 1)
    finally:
        lang.use("en")
    assert filled.startswith("‹") and filled.endswith("›") and "Mod" in filled, filled
    assert "2" in filled and "3" in filled, filled
    assert day.count("‹") == 2, day            # the month is marked inside the date
    return "marked, placeholders kept: %s" % filled


def sources(d, files):
    for name, text in files.items():
        io.open(os.path.join(d, name), "w", encoding="utf-8").write(text)


@case
def t_the_strings_are_collected_and_the_files_kept_in_step():
    """build_messages.py over two small tools: every kind of call is collected, a changed
    tool makes --check fail until it is run, a string that is gone moves to the end of the
    .po as obsolete with its translation, and translations are kept."""
    one = ('from lang import _, ngettext, pgettext\n'
           'def f(n):\n'
           '    print(_("Save"))\n'
           '    # translators: a button\n'
           '    print(pgettext("button", "Close"))\n'
           '    print(ngettext("%d mod", "%d mods", n) % n)\n')
    two = 'from lang import _\nNAME = _("Gone soon")\n'
    ru = RU_HEAD + '\nmsgid "Save"\nmsgstr "Сохранить"\n\nmsgid "Gone soon"\nmsgstr "Скоро"\n'
    with tempfile.TemporaryDirectory() as d, Folder({"ru.po": ru}) as words:
        sources(d, {"one.py": one, "two.py": two})
        old = (bm.HERE, bm.SOURCES, bm.POT)
        bm.HERE, bm.SOURCES, bm.POT = d, ("one.py", "two.py"), os.path.join(words,
                                                                              "messages.pot")
        said = []

        def check():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                code = bm.main(["--check"])
            said.append(buf.getvalue())
            return code
        try:
            before = check()
            made = bm.main([])
            after = check()
            entries, _p = bm.extract()
            sources(d, {"two.py": "from lang import _\nNAME = _('New one')\n"})
            stale = check()
            bm.main([])
            po = io.open(os.path.join(words, "ru.po"), encoding="utf-8").read()
        finally:
            bm.HERE, bm.SOURCES, bm.POT = old
    keys = sorted((c or "", m) for c, m in entries)
    assert (before, made, after, stale) == (1, 0, 0, 1), (before, made, after, stale)
    for text in (said[0], said[2]):
        assert "messages.pot is out of date" in text and "ru.po is out of date" in text, said
    assert "problem" not in said[1], said[1]
    assert keys == [("", "%d mod"), ("", "Gone soon"), ("", "Save"), ("button", "Close")], keys
    assert "#. a button" in po and 'msgid "New one"\nmsgstr ""' in po, po
    assert '#~ msgid "Gone soon"\n#~ msgstr "Скоро"' in po, po
    assert 'msgid "Save"\nmsgstr "Сохранить"' in po, po
    assert 'msgstr[2] ""' in po, po
    return "4 strings collected; stale caught twice; translation kept, gone one kept as #~"


@case
def t_the_check_refuses_what_a_translator_couldnt_translate():
    """A string built inside _(), an f-string, and _ used as a variable where _() is called
    are each refused, with the line. _() of a name - a string marked with N_() where it is
    written - is let be."""
    bad = ('from lang import _, N_\n'
           'TITLE = N_("A title")\n'
           'def f(x):\n'
           '    print(_("x is %s" % x))\n'
           '    print(_(f"{x} here"))\n'
           '    print(_(TITLE), _(x.name))\n'
           'def g(rows):\n'
           '    for _, v in rows:\n'
           '        pass\n'
           '    return _("done")\n')
    with tempfile.TemporaryDirectory() as d:
        sources(d, {"bad.py": bad})
        old = (bm.HERE, bm.SOURCES)
        bm.HERE, bm.SOURCES = d, ("bad.py",)
        try:
            _e, problems = bm.extract()
            problems += bm.shadowed()
        finally:
            bm.HERE, bm.SOURCES = old
    assert [p.split(":")[1] for p in problems] == ["4", "5", "8"], problems
    return "3 refused, _() of a marked name let be: %s" % "; ".join(
        p[:40] for p in problems)


@case
def t_the_shipped_files_are_in_step_with_the_tools():
    """What the release checks: messages.pot and every .po up to date, every translation one
    the tools can fill in, every call collectable."""
    r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "build_messages.py"),
                        "--check"], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout.strip().splitlines()[-1]


@case
def t_the_switch_shows_once_a_translation_has_text():
    """No translation with text: no switch. A Russian file with one string in it: the switch
    shows English and Русский, picking Русский redraws the page in it and keeps the choice
    for next time."""
    ru = RU_HEAD + '\nmsgid "Advanced editor..."\nmsgstr "Расширенный редактор..."\n'
    out = {}
    for label, files in (("none", {}), ("empty", {"ru.po": RU_HEAD}), ("one", {"ru.po": ru})):
        with tempfile.TemporaryDirectory() as d:
            tg.sandbox(d)
            words = os.path.join(d, "_tools", "lang")
            os.makedirs(words, exist_ok=True)
            for name, text in files.items():
                io.open(os.path.join(words, name), "w", encoding="utf-8").write(text)
            rc, text = tg.drive(d, r"""
box = getattr(g, "lang_box", None)
print("BOX", None if box is None else list(box.cget("values")))
if box is not None:
    box.set("Русский")
    box.event_generate("<<ComboboxSelected>>")
    settle()
    print("NOW", [t for t in texts(g.bar) if "editor" in t or "редактор" in t])
""")
            assert rc == 0, text
            saved = os.path.join(words, "language.txt")
            out[label] = (text, io.open(saved, encoding="utf-8").read().strip()
                          if os.path.isfile(saved) else None)
    assert "BOX None" in out["none"][0] and "BOX None" in out["empty"][0], out
    assert "BOX ['English', 'Русский']" in out["one"][0], out["one"][0]
    assert "NOW ['Расширенный редактор...']" in out["one"][0], out["one"][0]
    assert out["one"][1] == "ru" and out["none"][1] is None, out
    return "hidden with no translation and with an empty one; with one string, shown and used"


@case
def t_what_translators_and_their_tools_write_is_read():
    """msgmerge's #~| lines, an indented line, a file in windows-1251 that says so, a plural
    form not written yet, a language.txt saved with a BOM or as UTF-16, the language set in
    the game's own Options, and a % in a --help translation: each read as meant, where each
    once dropped the whole language, shifted the forms, crashed or went unseen. An update of
    the file keeps the translator's comments and the form's place, and writes UTF-8."""
    ru = RU_HEAD + r'''"Content-Type: text/plain; charset=CP1251\n"

# a translator's note
msgid "Save"
msgstr "Сохранить"

#, python-format
msgid "%d mod"
msgid_plural "%d mods"
msgstr[0] "%d мод"
msgstr[2] "%d модов"

msgid "Two lines"
msgstr ""
    "Две строки"

#~| msgid "Gone before"
#~ msgid "Gone"
#~ msgstr "Ушло"
'''
    with Folder({}) as d:
        io.open(os.path.join(d, "ru.po"), "wb").write(ru.encode("cp1251"))
        assert lang.use("ru") == "ru"
        got = [lang._("Save"), lang._("Two lines")] + [
            lang.ngettext("%d mod", "%d mods", n) % n for n in (1, 2, 5)]
        assert got == ["Сохранить", "Две строки", "1 мод", "2 mods", "5 модов"], got
        entries = bm.read_entries(os.path.join(HERE, "lang", "messages.pot"))
        entries[(None, "Save")] = {"plural": None, "files": [], "notes": []}
        entries[(None, "%d mod")] = {"plural": "%d mods", "files": [], "notes": []}
        text = bm.po_text(os.path.join(d, "ru.po"), entries)
        assert "charset=UTF-8" in text and "# a translator's note\nmsgid \"Save\"" in text, \
            text[:1500]
        assert 'msgstr[1] ""\nmsgstr[2] "%d модов"' in text, text
        io.open(os.path.join(d, "ru.po"), "wb").write(b"msgid \"x\"\nnonsense\n")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            assert lang.use("ru") == "en" and lang.use("ru") == "en"
        assert err.getvalue().count("lang/ru.po can't be read") == 1, err.getvalue()
        for data, want in ((b"\xef\xbb\xbfru\r\n", "ru"), ("ru".encode("utf-16"), None),
                           (b"\xff\xfe\x00", None), (b"no such thing", None)):
            io.open(os.path.join(d, "language.txt"), "wb").write(data)
            assert lang.saved_choice() == want, (data, lang.saved_choice())
    with tempfile.TemporaryDirectory() as g:
        io.open(os.path.join(g, "ModOrganizer.ini"), "w", encoding="utf-8").write(
            "[General]\nselected_profile=@ByteArray(Default)\n")
        os.makedirs(os.path.join(g, "profiles", "Default"))
        io.open(os.path.join(g, "profiles", "Default", "modlist.txt"), "w",
                encoding="utf-8").write("+English Text\n")
        for where, code in ((("mods", "English Text"), "eng"), (("overwrite",), "rus")):
            p = os.path.join(g, *where + ("gamedata", "configs"))
            os.makedirs(p)
            io.open(os.path.join(p, "localization.ltx"), "w", encoding="cp1251").write(
                "[string_table]\nlanguage = %s\n" % code)
        assert lang.game_language(g) == "ru", lang.game_language(g)
    ap = lang.parser(prog="x")
    sub = ap.add_subparsers(dest="cmd", parser_class=lang.parser)
    sub.add_parser("y").add_argument("--z", help="100% of it, at %(nothing)s")
    help_text = sub.choices["y"].format_help()
    assert "100% of it, at %(nothing)s" in help_text, help_text
    return "each read; the note and the form kept, UTF-8 written; one note for an unreadable file"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    failed = 0
    for fn in CASES:
        name = fn.__name__[2:]
        try:
            print("  PASS  %-58s %s" % (name, fn()))
        except AssertionError as e:
            failed += 1
            print("  FAIL  %-58s %s" % (name, str(e)[:1500]))
    print("%d/%d passed" % (len(CASES) - failed, len(CASES)))
    sys.exit(1 if failed else 0)
