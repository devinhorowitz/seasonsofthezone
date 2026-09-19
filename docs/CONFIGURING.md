# Configuring the launch-time layers

Everything in this file is **optional**. With no configuration at all you still get the
complete in-engine layer — light, colour, foliage, fog, wind, wetness, the calendar dial,
the MCM page and the PDA report — and it needs no downloads beyond the mod itself.

What configuration adds is the layer that *cannot* change at runtime: swapping texture
mods, toggling season-scoped mods, and gating ambient sound. Those are decided before the
game starts, by `_tools/season.py`, which `play.bat` runs for you.

```bash
cp _tools/seasons_config.example.py _tools/seasons_config.py
```

That file is the only one you edit. `season.py` is the engine and knows nothing about
your folder names. The example is a complete, working configuration from a real install —
read it alongside this page.

---

## The commands

```bash
python _tools/season.py status                 # what season is it, what is staged, what is installed
python _tools/season.py apply                  # stage it (this is what play.bat runs)
python _tools/season.py apply --dry-run        # say what would change, change nothing
python _tools/season.py apply --season winter  # stage a season other than today's
python _tools/season.py apply --no-textures    # in-engine only, this run
python _tools/season.py whowins <gamedata path>
```

`status` is read-only. `apply` is a no-op when the staged season already matches the
date, so running it on every launch costs nothing — it does real work about five times a
year.

`--mapping met` swaps the phenological calendar for Ukraine's hydrometeorological one
(round month starts) if you prefer tidy dates to accurate ones.

---

## `TOGGLE_MODS` — switch a whole mod on and off

The cheap mechanism, and the one to prefer. Nothing is copied: MO2 simply stops mounting
the folder, so an 11 GB winter texture set costs nothing to swap.

```python
TOGGLE_MODS = {
    "INVERNO Winter Textures (seasonal)": {        # folder name, exactly as MO2 shows it
        "seasons": ("winter", "winter_snow"),      # any of the five
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
}
```

| Field | Required | Meaning |
|---|---|---|
| *key* | yes | The mod folder name under `mods/`, character for character. A folder that is not installed is skipped silently, so you can ship a config for mods you have not downloaded yet. |
| `seasons` | yes | Tuple of seasons in which the mod is enabled. Valid: `spring`, `summer`, `autumn`, `winter`, `winter_snow`. |
| `above` | yes | The mod this one must outrank. See below — this is the field that goes wrong. |

Every mod listed here appears on the MCM page by itself, under a coloured heading for its
first season, with its file count and size, and its own tick box. Ticking it off means
"never mount this, even in season", and it survives restarts.

### Getting `above` right, which is the only hard part

MO2 gives a shared file to the **highest enabled mod that ships it**. If something above
yours also ships that file, your mod loses and *nothing tells you*: the flag flips exactly
as asked, `season.py` reports success, and the screen does not change.

So ask instead of guessing. Pick a file your mod ships, and run:

```bash
python _tools/season.py whowins textures/map/map_escape.dds
```

```
  file: gamedata/textures/map/map_escape.dds

    line   522  [-]  Winter PDA Maps (seasonal)                    2097280 B
    line   523  [+]  358- Global Map Rework - DeadEnvoy            8388736 B   <-- WINS
    line   840  [+]  26- High Res PDA Maps - Bazingarrey           8388736 B

  Put your seasonal mod ABOVE:  358- Global Map Rework - DeadEnvoy
```

Copy that name into `above`. If it reports that no mod ships the file, the base game `.db`
provides it, any placement wins, and you can anchor on anything stable.

Placement is re-checked on **every** run, not only when the mod is first inserted, so
correcting an `above` afterwards actually moves the mod.

---

## `LAYOUT` — restage a mod's contents per season

For mods that ship **one folder per season inside a single archive**. Aydin's Grass Tweaks
is the usual example: four seasonal variants, one download, meant to be reinstalled by
hand when you want a different one.

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
| *key* | The installed mod folder whose contents get replaced. |
| `archive` | Filename inside `downloads/` (MO2's own download folder). `.7z` needs `python -m pip install py7zr`; `.rar` needs `python -m pip install rarfile` plus WinRAR or 7-Zip. A missing package is reported with the command to run. |
| `options` | Season → list of folder names **inside the archive**, applied in overlay order (later entries win). |

This is the expensive mechanism — gigabytes are genuinely copied on a season change — so
use `TOGGLE_MODS` whenever a mod can simply be switched off instead. A season with no
entry keeps whatever is already staged.

Staged contents are identified by hashing the folder against every option in the archive,
so a season change is skipped when the correct set is already in place. The archive-side
hashes are cached after the first run (keyed on the archive's size and date), so a launch
costs a hash of the live folder rather than a re-extraction.

---

## `SOUND_SRC` — seasonal ambient gating

```python
SOUND_SRC = "304- Dark Signal Weather and Ambiance Audio - Shrike"
```

Name the mod that **wins** your `configs/environment/ambients/presets/` files — several
soundscape mods ship the same presets and only the highest enabled one is read, so use
`whowins` here too. `season.py` then generates a `Seasonal Soundscape` mod from *your*
files with the out-of-season channels removed:

| Season | Silenced |
|---|---|
| spring, summer | nothing |
| autumn | swamp birds |
| winter | all insects, swamp birds |
| deep winter | all insects, swamp birds, daytime birds |

Wind, storms, thunder and interiors are never touched, and crows and owls stay year-round
on purpose — a silent winter is wrong, a buzzing one is worse. Nothing of the source mod
is redistributed; the generated mod is built from what is already on your disk.

Leave it as `None` to skip the layer entirely.

The generated mod is placed in the modlist directly above `SOUND_SRC` and enabled or
disabled with the MCM switch — you never touch it in MO2.

---

## Troubleshooting

**The mod toggled but nothing changed on screen.** Almost always `above`. Run `whowins` on
a file the mod ships and re-anchor. This is silent by design in MO2, so suspect it first.

**`cannot place <mod>: <name> not in modlist`.** The `above` name has a typo, or that mod
is not installed. It must match the folder name exactly.

**`seasons_config.py needs fixing`.** The message names the entry and the field. The
usual one is `"seasons": ("winter")`, which is a string in Python, not a tuple — it
needs the trailing comma: `("winter",)`.

**Textures are wrong for the season.** The mod says so on load: *"TEXTURES ARE STAGED FOR
X but the season running is Y"*. Run `season.py apply` (or launch with `play.bat`) and
restart. Textures bind at level load and cannot follow the calendar mid-session.

**MO2 undid my modlist edit.** MO2 rewrites `modlist.txt` when it closes. Close it before
running the tools, and use `play.bat` rather than launching MO2 first.

**Nothing at all happens.** Check MCM → Seasons of the Zone → *Enable seasonal
atmosphere*, and that the log has `[seasons] armed` followed by `[seasons] <season>
applied`.
