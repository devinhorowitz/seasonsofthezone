# The interface

Two surfaces. **MCM → Seasons of the Zone** is where the mod is configured: six pages in
MCM's second column, Main and then one per season — Spring, Summer, Autumn, Winter, Deep
winter. **The Year** and **Forecast** are where it is read: two pages inside the PDA. There is
no HUD element, no pop-up and no key binding.

---

## Main

![The Main page, showing the year dial](images/mcm-main.png)

The page opens with a short summary, today's date, and a dial of the year with the needle
on the current day. Each wedge is sized by the season's real length: summer is a third of
the year, autumn seven weeks.

The dial's colors are each season's own color grade, so it also shows what the game is
graded towards. It follows the calendar and ignores the pin below it.

Below the dial:

- **Enable seasonal atmosphere** — the master switch.
- **Season** — automatic, or pin one. A pin drives every layer: the in-engine ones
  change within five seconds, and the textures and soundscape follow at the next
  launch, since both are staged before the game starts.
- **Transition length (days)** — the blend window centered on each boundary. 0 switches on
  the date.
- **Intensity** — 0 is GAMMA's stock look, 1 the full season.
- **Neutral preset (intensity 0)** — which preset the neutral baseline uses.

![Per-layer switches, the launch-time section, and hover help](images/mcm-main-layers.png)

Then one switch per layer — color and light, foliage, fog, wind, wetness — so a layer you
would rather tune yourself can be switched off on its own.

Below those are the two launch-time switches, which cannot change mid-session. **Swap
textures with the season** is the texture layer's master switch: off, the in-engine seasons
continue and no texture mod is mounted or unmounted. **Gate ambient sound by season** is
the soundscape's.

### Days

Six fixed dates sit on top of whatever season is running. None of them change the season:
April 26 is still spring, December 14 still deep winter.

Two are **remembrance days** — April 26, International Chernobyl Disaster Remembrance Day,
and December 14, Ukraine's Liquidators' Day. On these the Zone goes still.

- **Remembrance days: clear sky** — the weather is held on the clear cycle for the day.
Every transmission is signed and carries that speaker's portrait — Barman, Sidorovich,
Owl, Beard, Sakharov, Forester, Nimble, or an unnamed guide — so the day arrives as
people talking rather than as the game narrating.

- **Remembrance days: PDA traffic** — an opening transmission shortly after you load in,
  then further lines at random intervals of eight to twenty minutes, drawn from that
  day's pool. The pool is shuffled rather than rolled, so nothing repeats until it is
  exhausted.

Four are **anniversaries** — the release dates of the mainline games: March 20, August 22,
October 2 and November 20. These pull the other way, and the Zone gets loud.

- **Anniversaries: PDA traffic** — the same, opening with a line counting the years
  since that release. The count is computed from the date, so it never goes stale.
- **Anniversaries: the Zone gets loud** — the weather is pushed to the storm cycle.
- **Anniversaries: a few extra artefacts** — roughly nought to five on each level you
  visit that day, through Dynamic Anomalies Overhaul's own spawner. Lightly noticeable
  rather than a windfall. Unlike everything else here these persist in your save, exactly
  as ordinary spawned artefacts do, and only once per level per day even across reloads.
  Needs that mod; does nothing without it.

Last come the PDA message settings.

Every option has hover text, as shown above for *Drive wetness*.

## A season page

![The Winter page: preset, read-out, and the mods winter uses](images/mcm-season-winter.png)

Each season gets its own page, headed by a bar in that season's grade.

**Color grade preset** picks the `cfg_load` preset that season's color grade comes from:
Built-in (the season table), the mod's own six, then every other preset in `appdata/` —
Atmospherics' Cold, Neutral and Warm, and any you have tuned yourself. Only the grade
changes; it takes effect on Apply.

Under it is a read-out of what that season actually resolves to — grade, saturation, gamma,
exposure, sun, tonemap, fog, wetness and wind — with the grade's source named in brackets,
either `from season table` or the preset you picked. It is rebuilt each time the page is
opened, so reopen it after Apply to see a preset take.

**Texture mods for this season** lists the mods `seasons_config.py` scopes to that season,
each with its own tick. Unticking one leaves it out of *that* season only — a mod used by
both winters can stay on for deep winter and off for winter. The choice persists. Hover
text gives the mod's full span, file count and size.

![The Autumn page](images/mcm-season-autumn.png)

A mod is listed on the page of every season it serves, so its name carries no season: on
the Autumn page above, *CCon Autumn* is the autumn set.

The mods shown are third-party texture packs (I.N.V.E.R.N.O, C Consciousness and others). None
of them are included in this mod.

---

## The Year — the calendar page

Dates only. Anything running on the game clock lives on [Forecast](#forecast--the-pda-page)
instead. Reached from the PDA. With [Mod App Creator](https://www.moddb.com/mods/stalker-anomaly/addons/mod-app-creator)
installed it appears in the app launcher, its icon the current season's dial; without MAC
the page is still built but nothing links to it.

It is read-only, and it reports rather than decorates:

- **The year** — the five seasons with their dates and lengths, the current one lit.
- **Days the Zone marks** — the six fixed days, soonest first, each with how far off it is
  and what it does: *clear sky, quiet* for the two remembrance days, *storm, artifacts*
  for the four anniversaries.
- **On the calendar** — the mods the calendar is scheduling, with their spans. A mod the
  calendar wants but cannot stage is marked `!` rather than dropped silently.

The dial and the accent bar are the mod's own textures. Nothing else on the page is an
image, which is deliberate: the PDA frame textures that other tab-adding mods borrow are
declared in no `texture_descr` in a stock GAMMA install, which is why those pages log
*Can't find texture*. This one has nothing to fail to find.

---

## Forecast — the PDA page

The second page, and a different question: the calendar answers *when is it*, this
answers *what is about to happen*. They ran as one page briefly and it read badly —
nobody opens a calendar to find out whether it is going to rain this afternoon.

It is also the extension point. Anything that is near-term world state rather than a date
belongs here; adding a reading means a section in `Fill()` and a field on
`forecast_page()`, and nothing else changes.

### The next day

Not a guess. Atmospherics does not roll the weather as it goes — `WeatherManager:roll_day_plan`
plans `self.day_plan` out to a full 24 game hours ahead as a list of `{minute, cycle}`.
The page reads that plan, so the times shown are the times it will actually change.

Only *changes* are listed. The plan repeats a cycle to extend a spell, and six rows of
"rain" is not a forecast. A plan with no change in it reads *Settled*.

This one is **not** gated. Weather is something a stalker reads by looking up, the
ecologists have no special claim on it, and it gives the page something to say at zero
standing rather than a single locked row.

### The ecologist forecast

Emissions are the one genuinely scheduled thing in the Zone, and the ecologists are the
faction that measures them. So the page will tell you — but how precisely depends on how
they feel about you. Standing is `relation_registry.community_goodwill("ecolog", …)`,
which runs from -1000 at war to +1000 at friendly.

| Ecologist standing | What the page says |
|---|---|
| below 200 | *They keep their readings to themselves*, and your current standing |
| 200 | `close` · `building` · `no sign` — a warning, never a time |
| 700 | the hour |

Both thresholds are MCM tracks; those are the defaults.

The locked row is drawn deliberately rather than hidden. A reward the player cannot see
is not one they can work towards, so the row names the standing they have and the
standing they need.

The bands are a **fraction of the current period, not fixed hours**, so they keep their
meaning if you move the frequency slider: with `emission_frequency` at the stock 24,
*building* is a few hours; at 168 it is most of a day.

**Why this is not on the calendar.** It was going to be, and the numbers said no. At
`emission_frequency = 24` the manager rolls a delay of 12–24 *game* hours, and GAMMA runs
`time_factor = 6` — one emission every 2–4 real hours, six to twelve per real calendar
day. A day-scale calendar entry would read "emission likely" every single day, which is
not a forecast. The live readout is the only honest place for it.

`_tools/test_forecast.py` runs the shipped script under a real Lua interpreter and checks
all three tiers, the band boundaries, and that a locked or coarse page never leaks the
exact time.


---

## In the Zone

![Autumn in the Cordon](images/zone-autumn.jpg)

Autumn: low amber sun, thinned canopy, the grade pulled towards yellow-brown.

![Deep winter at the rookie village](images/zone-deep-winter.jpg)

Deep winter: snow cover, flat contrast, cold light, and the bare stems of the dead set
showing through. The PDA line carries no date because the season is pinned rather than
read from the calendar.

Both shots combine this mod's in-engine grading with third-party texture layers it stages
for the season - C Consciousness' autumn set above, and its dead set under Project
I.N.V.E.R.N.O's snow below. The color, fog, wind and wetness are the mod; the ground and
foliage textures are their authors'.
