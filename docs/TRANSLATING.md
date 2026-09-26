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
  anywhere, or leave it out. In a string with placeholders, a percent sign of its own is
  written `%%`, as the English does. A translation that can't be filled in the way its
  English is - a placeholder lost or added, or a `%` on its own - is not used: the English
  shows instead, and `build_messages.py --check` lists it.
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

**After a new version** of the tools, installing it keeps your translations: it brings
your `ru.po` up to date with the new strings and keeps the file as it was beside it, as
`ru.po.bak`. To do the same by hand, where you translate:

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

The game's words are the mod's string tables, in
`mods\Seasons of the Zone\gamedata\configs\text\eng\`:

| File | What it is |
|---|---|
| `st_seasons_of_the_zone.xml` | Everything the mod says in game: the PDA app's two pages, its messages, the transmissions on the days the Zone marks, month and season names. |
| `ui_seasons_of_the_zone.xml` | The MCM pages. |

The game picks the folder by its own language setting: a Russian game reads
`text\rus\`. A translation is a copy of both files there, with each `<text>` translated
and every `id` kept as it is. It can be done a piece at a time: for an id a language's
table doesn't have, the game shows the English. (Before this mod had any Russian table, a
Russian game showed its MCM page in English, not as ids.)

What to keep:

- **The encoding.** The files are windows-1251, as the first line says; Cyrillic fits in
  it. Save them that way, not as UTF-8.
- **`$name` placeholders** are values the game fills in - a place, a count, a date, a
  season. Put each wherever the sentence needs it, and keep its name.
- **Two forms of a season.** `$Season` starts a sentence and `$season` goes inside one
  ("Deep winter", "deep winter"); `$From`/`$from`, `$To`/`$to`, `$Next`/`$next` and
  `$Pinned`/`$pinned` work the same way. Each season has both: `st_sotz_season_<key>` and
  `st_sotz_season_<key>_mid`.
- **Counts.** An id that comes as `<id>_one` and `<id>_many` takes a count, `$n`. Russian
  needs a third form: add `<id>_few` beside each pair, and set `st_sotz_plural_rule` to
  `ru`. Then `_one` is for 1, 21, 31..., `_few` for 2-4, 22-24..., `_many` for the rest.
- **Dates.** `st_sotz_date` and `st_sotz_date_short` put the parts of a date in order:
  "$month $day, $year" becomes "$day $month $year" in Russian. Each month has four forms:
  on its own and inside a date (`_date`), full and short (`_short`). In Russian the ones
  inside a date take the genitive: "сентября".
- **One line each.** A `<text>` stays on one line, with no double spaces and no spaces at
  its ends: the game's XML reader drops them.

What stays English for now:

- Words drawn into textures: the year dial's season names, its lines under each season and
  its day counts, and the barometer's STORMY / RAIN / CHANGE / FAIR / DRY.
- `ui_mcm_seasons_mods.xml`, which `season.py` writes for your own seasonal mods, into
  `text\eng\`.
- The words other mods read from the API, like the emission warning's bands.

`_tools\test_strings.py` checks that every id the scripts use is in the English tables,
that no script puts English on the screen itself, and, for each language folder beside
`eng`, that its ids are English ones, its `$placeholders` are ones the game fills, and,
under the Russian rule, that every count has its `_few` form.
