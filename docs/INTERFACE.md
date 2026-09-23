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

![The Year: the grid with today lit, and the days the Zone marks](images/pda-the-year.png)

Dates only. Anything running on the game clock lives on [Forecast](#forecast--the-pda-page)
instead. Reached from the PDA. With [Mod App Creator](https://www.moddb.com/mods/stalker-anomaly/addons/mod-app-creator)
installed it appears in the app launcher, its icon the current season's dial; without MAC
the page is still built but nothing links to it.

It is read-only, and it reports rather than decorates:

- **The year grid** — twelve month rows of day cells, tinted by season. Because the rows are
  real months, February stops at 28 and the thirty-day months one cell short of the rest,
  which is what makes it read as a calendar rather than as a bar chart. Today's cell is lit
  and breathes; the six days the Zone marks are underlined.
- **Days the Zone marks** — the six fixed days, soonest first, each with how far off it is
  and what it does: *Clear sky. The Zone goes quiet.* for the two remembrance days,
  *Storm. Artefacts surface.* for the four anniversaries.
- **The year** — the five seasons and the date each one begins, beside the dial that draws
  them, the current one lit.

Today and the marked days are **red**, which is the only hue nowhere in the season palette
and so the only one a month cannot camouflage — an amber mark sat invisibly on autumn and a
slate one on deep winter, the two months they most needed to be seen against. It is the same
red the forecast strobes an emission alert in, so the mod has one red and it always means
look here. Today fills its cell and a marked day underlines its own, so the two stay apart
on a day that is both.

**Nothing about the mod appears here.** An earlier version listed the staged texture mods by
name, which put MO2 folder strings on a stalker's PDA — and there is no reliable way to turn
an author-chosen folder name into something the Zone would say. MCM's season pages already
list them, which is where a question about an install belongs.

The dial and the accent bar are the mod's own textures. Nothing else on the page is an
image, which is deliberate: the PDA frame textures that other tab-adding mods borrow are
declared in no `texture_descr` in a stock GAMMA install, which is why those pages log
*Can't find texture*. This one has nothing to fail to find.

`_tools/test_calendar.py` loads the shipped page under a real Lua interpreter and runs its
drawing code, checking that every month row is filled to its own length, that the season
running December into March owns cells at both ends of the grid, that a leap year gives
February its day, and that the mark colour is not one any season wears.

---

## Forecast — the PDA page

The second page, and a different question: the calendar answers *when is it*, this answers
*what is about to happen*. They ran as one page briefly and it read badly — nobody opens a
calendar to find out whether it is going to rain this afternoon.

No scrolling. A PDA is a device, not a document, and scrolling to find out whether a storm
is coming is the friction that makes a page feel bolted on.

![Forecast, with the ecologists telling this stalker nothing](images/pda-forecast.png)

### What it shows

**The sky, now and next.** Two drawn glyphs with an arrow between them, and when the change
lands. The arrow only appears when there *is* a next — on a settled day, an arrow pointing
at a repeat of the same sky would be a lie.

**The barometer.** A face labelled STORMY / RAIN / CHANGE / FAIR / DRY, with the needle on
the band matching the weather Atmospherics is running. It is six needle images over one
shared face, so the needle can move: every few seconds it takes a short damped shiver, a
pixel or two, which is the cheapest honest way to say a reading is being taken rather than
remembered.

**The day chart.** One axis, two strata. The ribbon along the top is the weather plan; the
bars below are the temperature, with the range up the left gutter and the clock hour under
each rule. Warm hours run amber, cold hours blue.

**Later today**, then **Tomorrow** — the planned changes with their clock times, and the
next day's observed range.

### Where the numbers come from

The sky is the game's and the air is the world's; see
[API.md](API.md#temperature) for the full split. In short: weather is Atmospherics' alone,
while the temperature takes the real Chornobyl high and low as its base and lets the
in-game sky move it, so standing in a storm reads colder than clear sky off the same
station reading.

A small marker beside the source line breathes while the reading is a live observation and
sits dark when it is modelled. The °C/°F button writes the MCM option rather than keeping
its own copy, so the page and the menu cannot disagree.

### The ecologist forecast

Emissions are the one genuinely scheduled thing in the Zone, and the ecologists are the
faction that measures them. So the page will tell you — but how precisely depends on how
they feel about you. Standing is `relation_registry.community_goodwill("ecolog", …)`, which
runs from -1000 at war to +1000 at friendly.

It has a panel of its own, bordered, under the faction's own emblem, headed with the
clearance you hold:

| Ecologist standing | | What the panel says |
|---|---|---|
| below 200 | **CLASSIFIED** | the faction's emblem and the word, and nothing else |
| 200 | **LIMITED** | a bracket — `ALL CLEAR` · `8 to 16 hours` · `2 to 8 hours` · `WITHIN 2 HOURS` |
| 700 | **CLEARED** | the hour, and a red strobe under two of them |

![CLEARED: the hour, and a psi storm inside two of them](images/pda-forecast-cleared.png)

At CLEARED the panel gives the hour, and the `Psi storm` line above is caught mid-strobe:
that reading was an hour out, inside the two-hour threshold, while `Emission` at seven
hours sits calm beside it. The alarm is bound to the line that is alerting, not to the
panel.

Both thresholds are MCM tracks; those are the defaults. Setting the first to 0 and the
second to 50 is the quickest way to see the middle tier without changing your standing.

The locked state is drawn deliberately rather than hidden. A reward the player cannot see is
not one they can work towards, so the emblem and the clearance word are on the page from the
first day — but that is all they are. Spelling out what the emblem implies, or printing
*0 of 200*, turns something you might one day be trusted with into a progress bar. The
border is sized to what that tier actually draws, so it reads as a thing withheld rather
than as an empty box.

The brackets are **fixed hours, not a fraction of the period**. A fraction quietly became a
different warning whenever the frequency slider moved, and *two to eight hours* has to mean
two to eight hours. Eight hours of slop is not a limitation — it is what a warning relayed
off someone else's instrument is worth, and it still tells a stalker whether to start
walking back.

Under two hours both open tiers raise the same flag, because a LIMITED *WITHIN 2 HOURS*
means what a CLEARED *1 hour* means. It is published as `alert` on `blowout()`, already
gated by tier, so a wearable device has one boolean to pulse on rather than re-deriving the
threshold — see [WEARABLE-DEVICES.md](WEARABLE-DEVICES.md). It is never true at CLASSIFIED,
where a pulse would leak the one thing being withheld.

**Why this is not on the calendar.** It was going to be, and the numbers said no. At
`emission_frequency = 24` the manager rolls a delay of 12–24 *game* hours, and GAMMA runs
`time_factor = 6` — one emission every 2–4 real hours, six to twelve per real calendar day.
A day-scale calendar entry would read "emission likely" every single day, which is not a
forecast. The live readout is the only honest place for it.

`_tools/test_forecast.py` runs the shipped script under a real Lua interpreter and checks
all three tiers, the bracket boundaries, the alert flag, and that a locked or limited page
never leaks the exact time.

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
