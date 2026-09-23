# Seasons of the Zone

**Point a mod at a stretch of the real calendar. It loads itself when that time of year
comes round, and unloads when it passes.**

The Zone follows the real-world calendar. Boot the game in late October, and it is autumn,
because Chornobyl is in autumn.

Light, color, fog, wind, wetness, snowfall, and ambient sound change with the date and
blend across each season boundary. Nothing to download beyond this mod, nothing to
configure.

That is the part that works out of the box. Underneath it is a scheduler, and the four
seasons are simply the calendar it ships with — see
**[the calendar underneath](#the-calendar-underneath)**.

![The Main page in MCM, showing the year dial](docs/images/mcm-main.png)

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

There is a year dial on the Main page and a PDA message when you load in.

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

## The calendar underneath

Seasons of the Zone is two independent halves, and you can use either on its own.

| | What it is | Configurable? |
|---|---|---|
| **In-engine** | Twenty console values blended across the date. Color, fog, wind, wetness. | No — it just runs |
| **Launch-time** | A scheduler that decides which mods MO2 mounts today | Yes — this is the open half |

The launch-time half has nothing seasonal about it. It maps a date to a set of names, and
mods declare which names they belong to. The five seasons are the default set. You can add
your own.

**Base periods** partition the year — exactly one is active on any date. **Events** overlay
whatever period they land in, so they add without displacing:

```python
# _tools/seasons_config.py
EVENTS = {
    "christmas": ((12, 24), (12, 26)),    # start, end - inclusive
    "halloween": ((10, 31), (10, 31)),    # a single day is fine
    "twelvetide": ((12, 26), (1, 6)),     # a window may wrap the year end
}

TOGGLE_MODS = {
    "Christmas Lights": {"when": ("christmas",), "above": "..."},
}
```

On December 25th the game stages deep winter **and** Christmas. The snow does not go
anywhere — that is what "overlay" means, and it is the difference between a mod that
does seasons and one that can do occasions.

Nothing about a period has to be a texture. If MO2 can mount it as a folder, it can be put
on the calendar: a gameplay patch, an audio set, a spawn table, a loading screen. The
texture packs are just the obvious first use.

```python
PERIODS = {                    # extra base periods, alongside the seasons
    "mud_season": (3, 20),     # runs until the next period starts
}
```

Full reference: **[docs/SCHEDULING.md](docs/SCHEDULING.md)**.

---

## Six days the Zone marks

Six fixed dates ship with the mod, each laid over whatever season is running rather than
replacing it. April 26 is still spring underneath; December 14 is still deep winter.

Two are **remembrance days** and the Zone goes quiet:

| | |
|---|---|
| **April 26** | International Chernobyl Disaster Remembrance Day |
| **December 14** | Liquidators' Day |

The weather is held clear and the PDA carries the day. No reward, no drop, no map marker.

Four are **anniversaries** — the release dates of the mainline games — and they pull the
other way. The weather is pushed to storm and a few extra artifacts are seeded on each
level you visit, roughly zero to five, once per level per day.

| | |
|---|---|
| **March 20** | Shadow of Chernobyl |
| **August 22** | Clear Sky |
| **October 2** | Call of Pripyat |
| **November 20** | Heart of Chornobyl |

Each day carries its own PDA traffic — an opening transmission shortly after you load in,
then more at intervals of eight to twenty minutes, drawn from that day's pool. 108 lines
in all, across eight voices, each signed and carrying that speaker's portrait: Barman,
Sidorovich, Owl, Beard, Sakharov, Forester, Nimble, and an unnamed guide.

The anniversary lines count the years **in-world**, from the in-game clock against the
year each game is set in — Shadow of Chernobyl in May 2012, Clear Sky in 2011, Call of
Pripyat in August 2012. A fresh save hears *"6 years since Operation Fairway"*, and the
count advances as the save ages. Heart of Chornobyl is set in 2021-22, still ahead of
Anomaly's own calendar, so it carries no count at all.

Five switches on the MCM Main page turn any of it off. The artifact seed is the only part
of the mod that writes to your save.

---

## Requirements

- S.T.A.L.K.E.R. Anomaly with **G.A.M.M.A.**, through **Mod Organizer 2** (portable)
- **Screen Space Shaders** and the **Modded Exes** DX11 build GAMMA ships with it. Nine of
  the twenty values are SSS's own; an older exe does not have them, and the mod says so in
  the log.
- **MCM**
- **Mod App Creator**, for the PDA app. MCM's Main page shows in red if it's missing.
- **Python 3**, for the launcher only. The python.org installer is enough.
- For the optional `LAYOUT` texture layer only: `python -m pip install py7zr` (and
  `rarfile` plus WinRAR or 7-Zip for `.rar` archives)

### Outside GAMMA

| | Plain Anomaly | Anomaly + Modded Exes |
|---|---|---|
| Color and light | yes | yes |
| Foliage, fog, wind, wetness | no | with Screen Space Shaders |
| The six marked days | yes | yes |
| The read API for other mods | yes | yes |
| The Seasons PDA app | no | with Mod App Creator |
| Texture and sound staging | with MO2 portable and Python | same |

- Foliage, fog, wind, and wetness use Screen Space Shaders' engine commands, which only exist
  in Modded Exes. Without them the mod logs it once and skips those layers.
- The PDA app needs Mod App Creator, which requires Modded Exes.
- Staging works with any MO2 portable install. It reads the game path and profile from
  `ModOrganizer.ini`.
- The anniversary artifacts need Dynamic Anomalies Overhaul.

Tested on Anomaly 1.5.3 with Modded Exes, MCM and Mod App Creator, and nothing else from
GAMMA: the in-engine layers, the marked days, the PDA app and MCM all work, and the forecast
reads the base game's weather. Plain Anomaly without Modded Exes hasn't been run; its column
follows from what its engine lacks.

---

## Install

1. In MO2, use **Install a new mod from archive** on the release zip, then enable the mod.
   That's everything in game: the light and weather, the marked days, the PDA app and MCM.
2. For real-world temperatures and the texture and sound layers, copy `_tools/` and
   `play.bat` from the mod's folder into your GAMMA folder, next to `ModOrganizer.exe`. (In
   MO2, right-click the mod and choose **Open in Explorer**.)
3. Open `play.bat` and check that `SHORTCUT=` names the Anomaly entry you launch from MO2
   (default `Anomaly (DX11-AVX)`).
4. Launch with `play.bat` from now on.

`play.bat` fetches Chornobyl's weather, checks the date, stages anything that needs staging,
and starts the game. Most days it changes nothing. Paths come from `ModOrganizer.ini`, so
the drive, game folder and profile are read rather than assumed.

**Updating:** install the new zip over the old one and choose **Replace**, then copy
`_tools/` and `play.bat` again. Your `seasons_config.py` isn't in the zip, so copying
`_tools/` leaves it alone. Versions before 1.7.0 were installed by copying the
`mods/Seasons of the Zone` folder: name the new install `Seasons of the Zone` so it
replaces that copy.

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

## The MCM pages

**Mod Configuration Menu → Seasons of the Zone** has six pages: Main, then one for
each season.

- **Main** — the year dial and today's date; the master switch; season (automatic, or
  pin one — a pin also decides what is staged at the next launch); transition length (0 for a hard switch on the boundary date, 14 by default);
  intensity (0 is GAMMA's stock look, 1 the full season); one switch per layer: color,
  foliage, fog, wind, and wetness; the two launch-time switches, for textures and
  ambient sound; the PDA message.
- **Spring, Summer, Autumn, Winter, Deep winter** — that season's color grade preset,
  a read-out of the values it resolves to, and a tick for each texture mod scoped to it.

---

## Putting a mod on the calendar

Any installed mod can follow the calendar. You do not modify it; you name it in
`_tools/seasons_config.py`.

```python
TOGGLE_MODS = {
    "INVERNO Winter Textures": {                  # folder name, exactly as MO2 shows it
        "when": ("winter", "winter_snow"),        # any period or event name
        "above": "388- Aydins Grass Tweaks SSS Terrain LOD Compatibility - aytabag",
    },
}
```

`when` takes any mix of base periods and events. `seasons` is the original spelling of the
same key and still works, so nothing written for an earlier version needs editing.

Relaunch. The mod is enabled in November and disabled in March, and appears on the Winter
and Deep winter pages with its file count and size. Nothing is copied — MO2 just
stops mounting the folder — so an 11 GB texture set costs nothing to switch.

![The Winter page, with a tick for each mod winter uses](docs/images/mcm-season-winter.png)

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
| C Consciousness Grass & Trees | `spring` / `summer` / `autumn` / `winter` | Four sets, one entry each; the Dead set covers both winters under the snow. Its grass placement does not change with the season, so that part stays mounted year-round and is not a seasonal entry. |
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
season, so each of the five sounds different: spring keeps the dawn chorus and loses the
crickets, summer has everything, autumn loses the daytime insects but keeps crickets
calling until the frost, and the winters lose the insects entirely. Wind and storms are
untouched. Crows and owls stay all year.

The gated presets are generated from your own files at launch. Switchable on the Main page.

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
table: pick one on that season's own page. The dropdown lists every preset
in the game's `appdata/` — Atmospherics' `Atmos_Cold`, `Atmos_Neutral` and `Atmos_Warm`, and any you
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
| [docs/SCHEDULING.md](docs/SCHEDULING.md) | The calendar: base periods, events, and recipes |
| [docs/INTERFACE.md](docs/INTERFACE.md) | The MCM pages and the Seasons app in the PDA |
| [docs/API.md](docs/API.md) | The read API other mods hook into: temperature, weather, the next emission |
| [docs/WEARABLE-DEVICES.md](docs/WEARABLE-DEVICES.md) | A blowout warning for Wearable Devices: the code, and why it cannot break that mod |
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
texture sets by the I.N.V.E.R.N.O, C Consciousness, PanceRide and Aydin authors.
