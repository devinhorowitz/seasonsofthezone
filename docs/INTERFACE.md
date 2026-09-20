# The MCM pages

**MCM → Seasons of the Zone** has six pages, listed in MCM's second column: Main, then one
for each season — Spring, Summer, Autumn, Winter, Deep winter. There is no HUD element, no
pop-up and no key binding.

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
the soundscape's. Last come the PDA message settings.

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
