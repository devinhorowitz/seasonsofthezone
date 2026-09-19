# What it looks like

Everything lives on one page: **MCM → Seasons of the Zone**. There is no HUD element, no
pop-up and no extra key binding — the mod is invisible in play by design.

---

## The year dial

![The MCM page, showing the year dial](images/mcm-year-dial.png)

The page opens with a plain-language summary, today's date, and a dial of the whole year
with the needle on the current day. Each wedge is sized by that season's real length —
which is what makes the lopsidedness obvious at a glance: summer is a third of the year,
autumn barely seven weeks.

The dial is drawn from the season's own colour-grading values, so it is a legend as well
as a clock: the grey of deep winter and the amber of autumn on the dial are the colours
the game is actually graded towards.

It follows the **calendar**, always, and ignores the pin below it. In this capture
*Season* is pinned to Deep Winter for testing while the dial still shows mid-September —
which is exactly the case where the two would otherwise be confused for each other.

Below the dial:

- **Enable seasonal atmosphere** — the master switch.
- **Season** — *Automatic*, or pin one. Pinning is for screenshots, or for playing out of
  step on purpose.
- **Transition length (days)** — the window centred on each boundary. 0 is a hard switch
  on the date; 14 eases the change in over the week either side.

## The layers

![Per-layer switches and the launch-time section](images/mcm-drive-layers.png)

**Intensity** mixes the whole season against vanilla: 0 renders stock GAMMA, 1 the full
season.

Then one switch per layer — colour and light, foliage, fog, wind, wetness — so a layer you
would rather tune yourself can be handed back without losing the rest.

Below the rule, the launch-time section states plainly what was staged at launch
(*"Staged for deep winter at launch"*), because that layer cannot follow the calendar
mid-session and a mismatch would otherwise look like a bug. **Swap textures with the
season** is the master switch for it: off means the in-engine seasons carry on exactly as
before while no texture mod is mounted or unmounted — useful if you want the light and fog
to move but your terrain to stay put.

## Season-scoped mods

![The seasonal mod list, grouped by season with coloured headers](images/mcm-seasonal-mods.png)

Any mod named in `seasons_config.py` appears here by itself — the list is generated from
what is actually installed, not hardcoded. Each is grouped under its first season, behind
a coloured bar drawn from that season's grading values, with the group's mod count and
total size beside it.

The size is the point: winter is four mods and 9.2 GB where summer is one. Ticking a mod
off means *never mount this, even in season*, and it persists across restarts. The
currently staged season's heading is highlighted.

The entries shown here are third-party texture packs — I.N.V.E.R.N.O, PanceRide and others
— configured to follow the calendar. **None of them are included in this mod**; they are
mods you install yourself, credited to their own authors.

## Hover text

![Hover help explaining the ambient sound gating](images/mcm-hover-help.png)

Every option carries its own hover text, and the generated ones say what the mod is, how
big it is, and whether it is mounted right now.

The ambient gating explains itself in full, because "silences sound channels" is not
something you can verify from a menu: insects go under snow, marsh life fades in autumn,
crows and owls stay all year, and wind and interiors are never touched.

---

## In the Zone

![Autumn in the Cordon](images/zone-autumn.jpg)

Autumn: low amber sun, thinned canopy, the grade pulled towards yellow-brown.

![Deep winter at the rookie village](images/zone-deep-winter.jpg)

Deep winter: snow cover, flattened contrast, cold hemispheric light and ice fog.

Both shots combine this mod's in-engine grading with optional third-party **texture**
layers it stages for the season (PanceRide's autumn set above, Project I.N.V.E.R.N.O's
winter set below). The colour, fog, wind and wetness are the mod; the ground and foliage
textures belong to their authors.
