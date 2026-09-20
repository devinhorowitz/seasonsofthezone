# Configuring the launch-time layers

Everything here is optional. With no configuration you get the whole in-engine layer:
light, color, foliage, fog, wind, wetness, the dial, the MCM pages and the PDA message.

Configuration adds what cannot change at runtime: swapping texture mods, switching
season-scoped mods, and gating ambient sound. `_tools/season.py` does that before the game
starts; `play.bat` runs it for you.

```bash
cp _tools/seasons_config.example.py _tools/seasons_config.py
```

That is the only file you edit. The example is a complete working configuration.

---

## Commands

```bash
python _tools/season.py status                 # today's season, what is staged, what is installed
python _tools/season.py apply                  # stage it (what play.bat runs)
python _tools/season.py apply --dry-run        # report what would change
python _tools/season.py apply --season winter  # stage a season other than today's
python _tools/season.py apply --no-textures    # in-engine only, this run
python _tools/season.py whowins <gamedata path>
```

`status` changes nothing. `apply` does nothing when the staged season already matches the
date. `--mapping met` uses Ukraine's meteorological calendar (round month starts).

---

## `TOGGLE_MODS`

Switches a whole mod on and off per season. Nothing is copied; MO2 stops mounting the
folder. Prefer this.

```python
TOGGLE_MODS = {
    "INVERNO Winter Textures (seasonal)": {        # folder name, exactly as MO2 shows it
        "seasons": ("winter", "winter_snow"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
}
```

| Field | Meaning |
|---|---|
| *key* | The mod folder name under `mods/`. A folder that is not installed is skipped. |
| `seasons` | Seasons in which the mod is enabled: `spring`, `summer`, `autumn`, `winter`, `winter_snow`. Note the trailing comma in a one-element tuple: `("winter",)`. |
| `above` | The mod this one must outrank. |

Each mod listed here gets its own tick on the page of every season it serves, with its
file count and size. Unticking it there means "never mount this in that season"; the
same mod can stay on for another season.

### Choosing `above`

MO2 gives a shared file to the highest enabled mod that ships it. If a mod above yours
ships the same file, yours loses and nothing tells you. Pick a file your mod ships and ask:

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
| spring, summer | nothing |
| autumn | swamp birds |
| winter | insects, swamp birds |
| deep winter | insects, swamp birds, daytime birds |

Wind, storms, thunder and interiors are never touched. Crows and owls stay all year.

The generated mod is placed directly above `SOUND_SRC` and follows the MCM switch; you do
not touch it in MO2. If you disable the source mod, the generated presets are removed at
the next launch. Leave `SOUND_SRC = None` to skip the layer.

---

## Presets

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

**`seasons_config.py needs fixing`.** The message names the entry and the field. The
usual mistake is `"seasons": ("winter")`, a string, not a tuple; it needs the trailing
comma: `("winter",)`.

**Textures are wrong for the season.** The mod says so on load: *"TEXTURES ARE STAGED FOR
X but the season running is Y"*. Run `season.py apply` or `play.bat` and restart.

**MO2 undid my modlist edit.** MO2 rewrites `modlist.txt` when it closes. Close it before
running the tools, or use `play.bat`.

**Nothing happens.** Check MCM → Seasons of the Zone → *Enable seasonal atmosphere*, and
that the log has `[seasons] armed` followed by `[seasons] <season> applied`.
