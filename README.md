# Seasons of the Zone

The Zone follows the real-world calendar. Boot the game in late October, and it is autumn,
because Chornobyl is in autumn.

Light, color, fog, wind, wetness, snowfall, and ambient sound change with the date and
blend across each season boundary. Nothing to download beyond this mod, nothing to
configure.

![The Seasons of the Zone page in MCM, showing the year dial](docs/images/mcm-year-dial.png)

*More of the interface: [docs/INTERFACE.md](docs/INTERFACE.md)*

---

## What it does

Twenty console values are set per season and blended across a 14-day window centered on
each boundary:

| Layer | What changes |
|---|---|
| Color and light | grade, saturation, gamma, exposure, sun lumscale, tonemap, sunshafts |
| Foliage | specular and sun-through-leaf (`ssfx_florafixes_1/2`) |
| Fog | `ssfx_fog`, `ssfx_fog_scattering` |
| Wind | `ssfx_wind_grass`, `ssfx_wind_trees` |
| Wetness | `ssfx_wetness_multiplier` — spring stays wet after the thaw, summer dries fast |

There is a year dial on the MCM page and a PDA message when you load in.

**Five seasons.** Winter is split in two: in Polesia snow starts falling in November but
only settles from December to early March.

```
spring       Mar 05 - May 19    76 d   thaw, then green-up
summer       May 20 - Sep 14   118 d   full foliage
autumn       Sep 15 - Oct 31    47 d   leaves turn; October is the peak
winter       Nov 01 - Nov 30    30 d   first snowfall, bare ground
winter_snow  Dec 01 - Mar 04    94 d   snow on the ground
```

These are the dates the landscape changes, not the equinoxes. `--mapping met` uses
Ukraine's meteorological convention (round month starts) instead.

---

## Requirements

- S.T.A.L.K.E.R. Anomaly with **G.A.M.M.A.**, through **Mod Organizer 2** (portable)
- **Screen Space Shaders** and the **Modded Exes** DX11 build GAMMA ships with it. Nine of
  the twenty values are SSS's own; an older exe does not have them, and the mod says so in
  the log.
- **MCM**
- **Python 3**, for the launcher only. The python.org installer is enough.
- For the optional `LAYOUT` texture layer only: `python -m pip install py7zr` (and
  `rarfile` plus WinRAR or 7-Zip for `.rar` archives)

---

## Install

1. Copy the inner `mods/Seasons of the Zone` folder into your `mods/` (so that
   `mods/Seasons of the Zone/gamedata` exists) and enable it in MO2. Do not use MO2's
   *Install from archive* on the zip.
2. Copy `_tools/` and `play.bat` into your GAMMA root, next to `ModOrganizer.exe`.
3. Open `play.bat` and check that `SHORTCUT=` names the Anomaly entry you launch from MO2
   (default `Anomaly (DX11-AVX)`).
4. Launch with `play.bat` from now on.

`play.bat` checks the date, stages anything that needs staging, and starts the game. Most
days it changes nothing. Paths come from `ModOrganizer.ini`, so the drive, game folder and
profile are read rather than assumed.

**Removing it:** switch it off in MCM first (this restores the color grade to neutral),
then disable the mod. If you applied the snowfall patch, `--revert` it too; without the
mod, the addon snows whenever the weather says so.

**While a layer is on**, SSS's own MCM sliders for that layer, and the vanilla sunshafts
and gamma sliders, are overridden within five seconds. Switch the layer off to tune them
yourself.

---

## Why a launcher

Everything above changes in-engine, immediately. Terrain and grass textures cannot: X-Ray
loads them from MO2's virtual file system when a level loads and keeps them for the
session. So the texture layer has to be decided before the game starts, and that is what
`play.bat` does.

If you never use the texture layer, launch however you like.

---

## The MCM page

**Mod Configuration Menu → Seasons of the Zone**:

- **Season** — automatic, or pin one
- **Transition length** — 0 for a hard switch on the boundary date; 14 by default
- **Intensity** — 0 is GAMMA's stock look, 1 the full season
- One switch per layer: color, foliage, fog, wind, and wetness
- The year dial, today's date, and the PDA message

---

## Making other mods seasonal

Any installed mod can follow the calendar. You do not modify it; you name it in
`_tools/seasons_config.py`.

```python
TOGGLE_MODS = {
    "INVERNO Winter Textures": {                  # folder name, exactly as MO2 shows it
        "seasons": ("winter", "winter_snow"),
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
}
```

Relaunch. The mod is enabled in November and disabled in March, and appears on the MCM
page under a WINTER heading with its file count and size. Nothing is copied — MO2 just
stops mounting the folder — so an 11 GB texture set costs nothing to switch.

![Season-scoped mods grouped under colored headings in the MCM page](docs/images/mcm-seasonal-mods.png)

*The packs shown are third-party texture mods, not included here.*

### Choosing `above`

`above` is the mod yours must outrank. MO2 gives a shared file to the highest enabled mod
that ships it; if a mod above yours ships the same file, yours loses and nothing tells you.
Pick a file your mod ships and ask:

```
python _tools/season.py whowins textures/map/map_escape.dds
```

```
  line   522  [-]  Winter PDA Maps (seasonal)                    2097280 B
  line   523  [+]  358- Global Map Rework - DeadEnvoy            8388736 B   <-- WINS
  line   840  [+]  26- High Res PDA Maps - Bazingarrey           8388736 B

  Put your seasonal mod ABOVE:  358- Global Map Rework - DeadEnvoy
```

Use that name. If no mod ships the file, any position works.

### Mods that work well this way

| Mod | Seasons | Notes |
|---|---|---|
| Project I.N.V.E.R.N.O — winter textures | `winter`, `winter_snow` | Terrain, flora and levels. Must outrank your grass mod and Atmospherics/SSS; it carries its own shader headers. |
| I.N.V.E.R.N.O — "Partly snowy" ground detail | `winter` | Patchy ground while the snow arrives. Above the base INVERNO. |
| Grass and Trees by PanceRide | `summer` / `autumn` | Matching Summer and Autumn editions; two entries, one per season. |
| Winter loading screens | `winter`, `winter_snow` | Above your loading-screen mod. |
| Winter PDA maps | `winter`, `winter_snow` | Above every mod that ships map textures, INVERNO included. |
| Swamp / ground fog | `spring`, `autumn` | |

If MO2 can mount it as a folder, it can be seasonal: footstep audio, menu art, a flower pack.

### `LAYOUT`

Some mods ship one folder per season inside a single archive (Aydin's Grass Tweaks).
`LAYOUT` restages the mod's contents from the archive when the season changes. Gigabytes
move, so use `TOGGLE_MODS` wherever a mod can simply be switched off.

`seasons_config.example.py` is a complete working configuration;
[docs/CONFIGURING.md](docs/CONFIGURING.md) is the field reference.

---

## Optional: seasonal ambient sound

Point `SOUND_SRC` at the ambience mod that wins your
`configs/environment/ambients/presets/` files. Its sound channels are then gated per
season: insects and daytime birds silenced in deep winter, marsh birds from autumn on, wind
and storms untouched. Crows and owls stay all year.

The gated presets are generated from your own files at launch. Switchable on the MCM page.

---

## Optional: seasonal snowfall

Project I.N.V.E.R.N.O's snowfall addon plays its particles off the weather alone, so it
snows in September. `patches/apply_seasonal_snowfall.py` adds a seasonal layer: snow only
in the two winters and lighter in the first, seeds in spring, leaves in autumn, dust in the
dry months.

It edits your own copy of the addon; none of INVERNO's code is shipped here. Install the
standalone "Snowfall (light + Dynamic Fog)" addon, then:

```
python patches/apply_seasonal_snowfall.py
```

It finds the script under `mods/`, backs it up to `yawm_snowfall.script.orig`, and inserts
the layer. `--revert` restores the backup. Running it twice does nothing, and it refuses a
file that does not look like INVERNO's script.

The addon also ships an old `level_weathers.script`. Remove it: the patcher warns, and
`--disable-weathers` renames it. See [docs/LOAD-ORDER.md](docs/LOAD-ORDER.md).

---

## Optional: color grade presets

Each season's color grade can come from a `cfg_load` preset instead of the mod's season
table: pick one per season on the MCM page. The dropdown lists every preset in the game's
`appdata/` — Atmospherics' `Atmos_Cold`, `Atmos_Neutral` and `Atmos_Warm`, and any you
have tuned yourself — plus the mod's own `Seasons_Spring`, `Seasons_Summer`,
`Seasons_Autumn`, `Seasons_Winter`, `Seasons_DeepWinter` and `Seasons_Neutral`. `play.bat`
copies those six into `appdata/` beside the others, so you can `cfg_load` or edit them
too. Only the grade changes; fog, wind and wetness stay with the season table.

---

## Load order

Seasons of the Zone can go anywhere in MO2. No other mod ships any of its files, and
script order comes from the engine's directory listing (hence the `zzz_` name), not from
priority. It only has to be enabled. What does need placing:

- the mods in `TOGGLE_MODS` — `play.bat` puts each directly above its `above` anchor at
  every launch, and `season.py status` reports anything higher up that would override it;
- INVERNO's snowfall addon — remove `level_weathers.script` from it;
- never enable the old Season Flora prototype alongside this.

A GAMMA launcher **Update** drops this mod and its companions from the load order.
Details and recovery: [docs/LOAD-ORDER.md](docs/LOAD-ORDER.md).

---

## Documentation

| | |
|---|---|
| [docs/INTERFACE.md](docs/INTERFACE.md) | The MCM page, option by option |
| [docs/CONFIGURING.md](docs/CONFIGURING.md) | Making other mods seasonal: fields, commands, troubleshooting |
| [docs/HOW-IT-WORKS.md](docs/HOW-IT-WORKS.md) | The calendar, the blend, the values, the MO2 rule |
| [docs/LOAD-ORDER.md](docs/LOAD-ORDER.md) | Where everything sits, what must not be enabled together, recovering from a GAMMA update |
| [CHANGELOG.md](CHANGELOG.md) | Version history |

---

## Credits

Seasons of the Zone is by **Devin Horowitz**, MIT license.

No third-party assets are included. The texture, snowfall and soundscape layers read mods
you install yourself, and the configuration ships empty. INVERNO's `yawm_snowfall.script`
(Yet Another Winter Mod by Daedalus-Prime, refactored by demonized, edited by Fabio Conte;
particles by S.e.m.i.t.o.n.e.) is not shipped in any form; the patcher carries only the
seasonal layer.

Built on **Screen Space Shaders** by Ascii1457 and **G.A.M.M.A.** by Grokitach. Seasonal
texture sets by the I.N.V.E.R.N.O, PanceRide and Aydin authors.
