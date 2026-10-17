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
