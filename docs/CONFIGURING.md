# Configuring the launch-time layers

Everything here is optional. With no configuration you get the whole in-engine layer:
light, color, foliage, fog, wind, wetness, the dial, the MCM pages and the PDA message.

Configuration adds what cannot change at runtime: swapping texture mods, switching
season-scoped mods, and gating ambient sound. `_tools/season.py` does that before the game
starts; `play.bat` runs it for you.

The quickest way in is `configure.bat` in your GAMMA folder. It lists your MO2 mods;
tick the seasons each one belongs to, and it writes `_tools/seasons_config.py` for you,
with the `above` for each mod worked out from the files the mods share. Its Seasons tab
moves the season dates, turns seasons off and names them; see [`CALENDAR`](#calendar) and
[`NAMES`](#names). Its presets keep a whole setup under a name, to load again here or on
another install; the GAMMA example preset is a full working setup to start from. Between
the window and the presets, the file needs no editing by hand.

`seasons_config.py` is still the one file all of it lives in, and yours to edit by hand if
you would rather. `_tools/seasons_config.example.py` is the GAMMA example as a file.

Scoping a mod to a season is the common case, but the calendar is open: you can add your
own base periods and overlapping events, and scope mods to those instead. That is
**[docs/SCHEDULING.md](SCHEDULING.md)**; this page is the field reference.

---

## Commands

```bash
python _tools/season.py status                 # today's season, what is staged, what is installed
python _tools/season.py apply                  # stage it (what play.bat runs)
python _tools/season.py apply --dry-run        # report what would change
python _tools/season.py apply --season winter  # stage a period other than today's
python _tools/season.py apply --no-textures    # in-engine only, this run
python _tools/season.py whowins <gamedata path> --for "<your mod>"
python _tools/season.py dial                   # hand CALENDAR to the game, draw its dial
```

`status` changes nothing. `apply` does nothing when the staged season already matches the
date. `--mapping met` uses Ukraine's meteorological calendar (round month starts) for one
run; `CALENDAR` is the lasting way to change the dates.

The configure tool, as commands:

```bash
python _tools/configure.py                    # the window (what configure.bat opens)
python _tools/configure.py list               # what is on the calendar
python _tools/configure.py add "<mod>" --when winter "deep winter" [--above "<mod>"]
python _tools/configure.py remove "<mod>"
python _tools/configure.py event christmas 12-24 12-26
python _tools/configure.py event weekend --weekdays weekends     # a rule; see SCHEDULING.md
python _tools/configure.py event christmas --remove
python _tools/configure.py calendar           # when each season starts, and which are off
python _tools/configure.py calendar summer=5-1 "deep winter=11-15" [--only]
python _tools/configure.py calendar --off late_winter
python _tools/configure.py calendar --on late_winter      # back on, at Polesia's date
python _tools/configure.py calendar --preset met          # the meteorological dates
python _tools/configure.py calendar --reset               # Polesia's again
python _tools/configure.py name                           # what each season is called
python _tools/configure.py name "deep winter" "The Long Cold"
python _tools/configure.py name "deep winter" --reset
python _tools/configure.py preset                         # the presets there are
python _tools/configure.py preset show "Two seasons"
python _tools/configure.py preset load "Two seasons" [--parts calendar]
python _tools/configure.py preset save "Mine" [--about "..."] [--parts calendar mods]
```

`add` puts a mod on the calendar, or replaces its seasons if it is already there. The
name is checked against MO2's list, with suggestions for a near miss. `--when` takes
season names as MCM shows them or as the config spells them, and any event or period.
Without `--above`, the anchor is the highest enabled mod that ships any of the same
files; when another seasonal mod on in the same season shares files, `add` names it and
leaves the choice to you.

Every save checks the result with `season.py`'s own rules first, keeps the previous file
as `seasons_config.py.bak`, and rewrites only the entries that changed, so comments and
anything written by hand stay as they were. A save that can't keep every comment - one
inside a table written on a single line, say - also keeps a dated copy that no later save
touches, and says where. The tool refuses rather than guess: a file saved in an encoding it
would have to mangle, a table sharing its line with another statement, a table the lines
below it change again, or a file that changed since it was opened is left as it is, with a
message saying what to do.

---

## `TOGGLE_MODS`

Switches a whole mod on and off per season. Nothing is copied; MO2 stops mounting the
folder. Prefer this.

```python
TOGGLE_MODS = {
    "INVERNO Winter Textures (seasonal)": {        # folder name, exactly as MO2 shows it
        "seasons": ("winter", "winter_snow", "late_winter"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
}
```

| Field | Meaning |
|---|---|
| *key* | The mod folder name under `mods/`. A folder that is not installed is skipped. |
| `seasons` | Seasons in which the mod is enabled: `spring`, `summer`, `autumn`, `winter`, `winter_snow`, `late_winter`. Note the trailing comma in a one-element tuple: `("winter",)`. |
| `above` | The mod this one must outrank. |

Each mod listed here gets its own tick on the page of every season it serves, with its
file count and size. Unticking it there means "never mount this in that season"; the
same mod can stay on for another season.

### Choosing `above`

MO2 gives a shared file to the highest enabled mod that ships it. If a mod above yours
ships the same file, yours loses and nothing tells you. Pick a file your mod ships and ask,
naming your mod with `--for`:

```bash
python _tools/season.py whowins textures/map/map_escape.dds --for "Winter PDA Maps (seasonal)"
```

```
  file: gamedata/textures/map/map_escape.dds

    line   190  [-]  Winter PDA Maps (seasonal)                   2097280 B   <-- yours
    line   539  [+]  358- Global Map Rework - DeadEnvoy           8388736 B   <-- to outrank
    line   862  [+]  26- High Res PDA Maps - Bazingarrey          8388736 B

  Put Winter PDA Maps (seasonal) ABOVE:  358- Global Map Rework - DeadEnvoy
  i.e.  "above": "358- Global Map Rework - DeadEnvoy"
```

`--for` keeps your mod out of the answer. Without it, the top enabled mod is named, and
the one under it too, in case the top one is yours: MO2 puts a fresh install at the top.

Use that name. If no mod ships the file, any position works.

Placement is checked on every run. An anchor that no longer exists skips that entry with a
warning; the others still run.

`above` only puts the mod directly above that one anchor. `season.py status` also checks
every file of every season-scoped mod against every mod above it and reports: `SHADOWED`
when an enabled mod would win, how many disabled mods above would win if enabled, and a
note when two season-scoped mods overlap in a shared season. `play.bat` runs the same
check whenever the modlist has changed.

---

## `LAYOUT`

For mods that ship one folder per season inside one archive, such as Aydin's Grass
Tweaks.

```python
LAYOUT = {
    "289- Grass Tweaks (reinstall for different options) - Aydin": {
        "archive": "Aydins_Grass_Tweaks_4.0.7z",     # filename in MO2's downloads folder
        "options": {
            "spring": ["Aydin's Grass Tweaks - SPRING 4.0",
                       "Aydin's Grass Tweaks - SPRING TREES 4.0"],
            "summer": ["Aydin's Grass Tweaks - SUMMER 3.0", ...],
            ...
        },
    },
}
```

| Field | Meaning |
|---|---|
| *key* | The installed mod folder whose contents are replaced. |
| `archive` | Filename in `downloads/`. `.7z` needs `python -m pip install py7zr`; `.rar` needs `rarfile` plus WinRAR or 7-Zip. |
| `options` | Season → folder names inside the archive, applied in order (later ones win). |

Gigabytes are copied on a season change, so use `TOGGLE_MODS` wherever a mod can simply
be switched off. A season with no entry keeps whatever is already staged.

What is installed is identified by hashing the folder against the archive's options, so a
correct season is never re-copied. The archive-side hashes are cached after the first run.

---

## `SOUND_SRC`

```python
SOUND_SRC = "304- Dark Signal Weather and Ambiance Audio - Shrike"
```

Name the mod that wins your `configs/environment/ambients/presets/` files (several
soundscape mods ship the same presets; use `whowins`). `season.py` generates a
`Seasonal Soundscape` mod from that mod's files with these channels removed:

| Season | Silenced |
|---|---|
| spring | night crickets |
| summer | nothing |
| autumn | daytime insects, swamp birds |
| winter | all insects, swamp birds |
| deep winter | all insects, swamp birds, daytime birds |
| late winter | all insects |

Wind, storms, thunder and interiors are never touched. Crows and owls stay all year.
Crickets belong to summer and autumn nights, so spring is carried by the dawn chorus
alone; autumn keeps them calling until the first frost but loses the daytime insects.
The thaw brings the marsh birds back before any insect stirs.

The generated files record which channels they were cut with, so editing this table
rebuilds them at the next launch rather than waiting for the season to turn.

The generated mod is placed directly above `SOUND_SRC` and follows the MCM switch; you do
not touch it in MO2. If you disable the source mod, the generated presets are removed at
the next launch. Leave `SOUND_SRC = None` to skip the layer.

---

## `CALENDAR`

```python
CALENDAR = {
    "summer": (5, 1),            # (month, day) the season starts
    "winter_snow": (11, 15),
}
```

The seasons that are on and the day each starts. `configure.bat`'s Seasons tab writes it,
and `configure.py calendar` does from a command prompt. Each season runs until the next one
that is on, so a season left out gives its days to the one before it; the example is
summer from May 1 and deep winter from November 15, and nothing else. `None`, or no
`CALENDAR` at all, is Polesia's six.

Every season needs at least 14 days, no two can start on the same day, and none can start
on February 29, which three years in four do not have. At least one has to be on.

A mod scoped only to seasons that are off is never switched on; `season.py status` names
it. An MCM pin on a season that is off counts as automatic.

`play.bat` hands the calendar to the game in `configs/season_calendar.ltx`, and saving from
the tool does too, so the in-engine layer follows it from the next start even without
`play.bat`. MCM shows a page and a pin for each season that is on.

The year dial is redrawn for your dates, 32 images in the mod's `textures/` folder. That
needs Pillow, a Python package: `python -m pip install pillow`, which the tool offers to
run. Without Pillow the dial is hidden, since the shipped one shows Polesia's dates.
`season.py dial` draws it by hand, and a return to Polesia's calendar deletes it.

---

## `NAMES`

```python
NAMES = {
    "winter_snow": "The Long Cold",
    "late_winter": "Rasputitsa",
}
```

Names of your own for the seasons. The game shows them wherever it names a season: the PDA,
the messages when a season turns, MCM's page titles and the Season list, and the year
dial, which is redrawn with them as for a calendar of your own. The config keeps the
usual keys, so `when`, `LAYOUT` and everything else still say `winter_snow`.

A name is up to 20 letters, English or Cyrillic, which is what the game can show; two
seasons can't share one. `None`, or a name left as the usual one, keeps the usual name.

---

## Presets

A preset keeps a setup under a name, in `_tools/presets/`, as a JSON file: plain data, so
one posted by someone else can be loaded without running anything they wrote. It holds any
of four parts:

| Part | What it is |
|---|---|
| calendar | `CALENDAR` and `NAMES` |
| events | `EVENTS` and `PERIODS` |
| mods | `TOGGLE_MODS` |
| textures | `LAYOUT` and `SOUND_SRC` |

**Save preset...** in the window, or `configure.py preset save`, keeps the parts that have
something in them, unless you pick others. **Load preset...** sets the parts you choose in
place of yours, and like any change in the window it is written only when you save. A
preset made on another install loads here: a mod you don't have is left out, a mod whose
anchor you don't have is placed again for your list, a texture set whose archive is not in
your `downloads/` is left out, and loading says which. Every part goes through the same
rules as a save, and a preset that would break the config is refused whole.

Four calendars come with the tool: Polesia, Meteorological, Two seasons and Southern
hemisphere. The GAMMA example holds the mods, events, texture sets and sound source these
tools were made on. A preset of the same name as one that comes with the tool can't be
saved over it.

---

## Color grade presets

The mod ships its season grades as `cfg_load` presets, `Seasons_*.ltx`, in
`gamedata/configs/seasons_presets/`. `play.bat` copies them into the game's `appdata/`
if they are not there, beside Atmospherics' `Atmos_*.ltx`; an existing copy is never
overwritten, so you can tune them in place. Which preset a season uses is chosen on that
season's MCM page, not here.

---

## Troubleshooting

**The mod toggled but nothing changed on screen.** Almost always `above`. Run `whowins`
on a file the mod ships and re-anchor.

**`anchor '...' is not in the modlist - SKIPPED`.** The `above` name has a typo, or that
mod is not installed. It must match the folder name exactly.

**`seasons_config.py is not saved as UTF-8`.** Notepad saves as ANSI or UTF-16 when asked
to; the tools read UTF-8. File, Save as, Encoding: UTF-8.

**`seasons_config.py needs fixing`.** The message names the line, or the entry and the
field. The usual mistakes:

- `("winter")` is a string, not a tuple. One season needs the trailing comma:
  `("winter",)`.
- A comma in the wrong place, or missing between two entries. Python can only say
  roughly where, so a missing comma is reported as a range of lines; it goes after the
  `}` that closes an entry.
- A name without quotes: `winter_snow` instead of `"winter_snow"`.
- The same table set twice, often an entry added above the template's empty
  `TOGGLE_MODS = {}`. Python keeps the last one, so the entry would be thrown away.

`whowins` still runs while the file has a mistake in it.

**The year dial is gone.** A calendar of your own needs a dial drawn for it, and drawing
one needs Pillow: `python -m pip install pillow`, then `python _tools/season.py dial`.

**Textures are wrong for the season.** The mod says so on load: *"TEXTURES ARE STAGED FOR
X but the season running is Y"*. Run `season.py apply` or `play.bat` and restart.

**MO2 undid my modlist edit.** MO2 rewrites `modlist.txt` when it closes. Close it before
running the tools, or use `play.bat`.

**Nothing happens.** Check MCM → Seasons of the Zone → *Enable seasonal atmosphere*, and
that the log has `[seasons] armed` followed by `[seasons] <season> applied`.
