# Translating

Seasons of the Zone has two sets of words: the **tools'** - `configure.bat`'s window, the
commands, the lines `play.bat` prints - and the **game's** - the PDA's Seasons app and
Forecast page, MCM, and the messages in game. Both come from translation files, so a
translation needs no code. Nothing is translated yet. A Russian file for the tools comes
with every string ready to fill in.

A translation can be done a piece at a time: anything not translated yet shows in English.

---

## The tools

The words are in `_tools\lang\`:

| File | What it is |
|---|---|
| `messages.pot` | Every string the tools show, made from the code. Don't edit it. |
| `ru.po` | The Russian translation: every string, each with an empty translation to fill in. |
| `language.txt` | The language picked in the window's switch. Not shipped; yours. |

A `.po` file is plain text, UTF-8, in the format of gettext, so any text editor works, and
so do tools made for it, like [Poedit](https://poedit.net/) (free). Each string looks like
this:

```
#: guide.py
#, python-format
msgid "%d seasonal mod checked."
msgid_plural "%d seasonal mods checked."
msgstr[0] ""
msgstr[1] ""
msgstr[2] ""
```

Fill in `msgstr`. What to keep:

- **Placeholders.** `%s` and `%d` are filled in by the tools in the order they come, so a
  translation keeps every one, in the same order. `%(name)s` is filled in by name: move it
  anywhere, or leave it out. A translation whose placeholders don't fit its English is not
  used - the English shows instead - and `build_messages.py --check` lists it.
- **Counts.** A string with `msgid_plural` has one `msgstr[n]` per form the language has.
  Russian has three - the header's `Plural-Forms` says which numbers take which: `[0]` for
  1, 21, 31..., `[1]` for 2-4, 22-24..., `[2]` for 0, 5-20, 25-30...
- **Context.** `msgctxt` says where a string is used when the same English means two
  things: `"month, short"` for "May" in a date picker, `"season"` for "summer".
- **Commands and names.** A command inside a sentence - `py _tools\season.py apply` - stays
  as it is, and so do file names, `seasons_config.py`'s table names and the seasons as the
  config spells them (`winter_snow`).
- **`#, fuzzy`** marks a guess, which is not used until the mark is taken off.

**Trying it.** Once `ru.po` has any string in it, `configure.bat` shows a language switch at
the bottom of the window; pick Русский, and the window redraws in it and remembers. The
commands and `play.bat` follow the same choice. The tools also start in the game's
language, when there is a translation for it. `SEASONS_LANG=ru` in the environment picks it
for one run:

```
set SEASONS_LANG=ru
py _tools\configure.py list
```

`SEASONS_LANG=qps` is a test language: it marks every string that can be translated as
`‹...›` and changes its letters, so text that can't be translated yet stands out.

**After a new version** of the tools, bring the file up to date:

```
py _tools\build_messages.py
```

New strings come in empty, and strings the tools no longer have move to the end, marked
`#~`, with their translations, to reuse. `py _tools\build_messages.py --check` says
whether everything is in step, and lists any translation that doesn't fit its English.

**Another language.** Copy `ru.po` to the language's code - `uk.po`, `pl.po` - and set its
header: `Language`, `X-Language-Name` (the language's name in itself, which the switch
shows) and `Plural-Forms` (the
[gettext manual](https://www.gnu.org/software/gettext/manual/html_node/Plural-forms.html)
has them), then clear the translations. The codes that follow the game's languages are in
`GAME_CODES` in `_tools\lang.py`.

A few things stay English: the lines `play.bat` and `configure.bat` print before Python
runs, for when the tools are missing or in the wrong folder, and what is written into files
- `seasons_config.py`'s comments, logs.

---

## The game

<!-- the game's half is written from the in-game work -->
