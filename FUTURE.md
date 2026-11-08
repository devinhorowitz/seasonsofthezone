# Future possibilities

Ideas looked at and set aside for now, with why and what each would take.

## Melancholy Weathers

Melancholy Weathers, by PIPNIK, is a weather overhaul with its own weather manager, skies and
lighting, and Shrike's Dark Signal soundscape rebuilt for it (DSSO Melancholy). It takes the
place of Atmospherics rather than adding to it, and it doesn't support INVERNO or Weather
Expansion.

**Why not yet:** it is in paid Early Access for now, and Seasons of the Zone is built on
Atmospherics. Under Melancholy today, Seasons would take it for the base game's weather: the
seasonal odds would do nothing, and the Forecast page would have little to read.

**What it would take,** from a review of Early Access 10 (October 2026):

- **Weather odds:** Melancholy's scheduler weighs each kind of sky, much as W.P.W.M. does, from
  `dynamic_weather_graphs.ltx`. Seasons would stage a seasonal copy of those weights at launch,
  as it stages textures, so a season change waits for the next launch.
- **The Forecast page:** read Melancholy's day plan. Emissions and psi storms can reshuffle it,
  which suits a page that gives odds, not a timetable.
- **Marked days' skies:** left out. Melancholy has no way to ask for a sky on a coming day.
- **Telling it apart:** by its scheduler's fields, or a version marker if a later build adds
  one.
- **The look:** season values and a seasonal LUT of its own. Melancholy uses
  `r2_tonemap_lowlum` as its brightness setting and ships its own LUTs.
- **Sound:** a cut list for DSSO Melancholy's ambience, which doesn't use Dark Signal
  Amplified's insect and bird names.
- **Winters:** Melancholy has no snow, so the winters would be bare, dead textures without
  falling snow.
- **Testing** in an MO2 profile of its own, and a "With Melancholy Weathers" section in the
  README, beside "With ROMEO".

## VAsgen's Falling Stars

VAsgen's Falling Stars, by vasgen9769 (ModDB), adds starry-night weathers with shooting
stars, and an aurora. BamaWater suggested it in ROMEO's Seasons thread (2026-10-31): the
aurora's chance by season, meteor showers by date, and a place among the recommended mods.

**Why not yet:** its aurora is built from 32 alife objects, so a save made while one shows
keeps them, and removing the addon can then break that save. It is never a seasonal mod:
it stays on all year, and Seasons would only set what it exposes.

**What it would take,** from a review of v0.8 (November 2026):

- **A bridge script,** active only when the addon is there, like the INVERNO and RTZ bridges,
  with an MCM switch.
- **Shooting stars by season:** set `vasgen_nightsky_weathers.CHANCE.clear`/`.partly` (0.40 a
  night) from a table of Seasons' at each apply. Both are module globals.
- **Meteor showers by date:** on the peak nights of the seven yearly showers (Quadrantids,
  Lyrids, Eta Aquariids, Perseids, Orionids, Leonids, Geminids), raise that chance near 1.0
  and add a fast profile to `vasgen_nightsky_stars.PROFILES` and `PROFILE_WEIGHTS`. Never
  touch `COLORS`: a particle name without its file is a hard fatal. A PDA message and a
  "Coming up" line on The Year would fit the marked days.
- **The aurora by season:** its `CHANCE` is a file local. Ask the author to make it a module
  global, rather than reaching it through `debug` upvalues.
- **For the author:** remove the NumPad 7 debug key v0.8 still ships, and build the aurora
  without alife objects if the engine allows it.
- **Unaffected today:** it keeps the cycle and swaps only the preset, so the weather
  messages, the Forecast page, marked days' held skies and No Rain in Winter don't change.
  None of its files is in another mod, so MO2's order doesn't matter.
