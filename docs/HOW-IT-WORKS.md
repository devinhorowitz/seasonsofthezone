# How it works

Notes on the internals — useful if you want to retune a season, extend the system, or
understand why a launcher exists at all.

---

## The calendar

Five seasons, not four, because Polesia does not have four. Snow arrives from late
October but cover only holds from about December through March, and the thaw is what makes
spring wet. A single 110-day winter forces a choice between snow two months too early and
bare ground through February; splitting it removes the choice.

```
spring       Mar 05 - May 19    76 d   thaw and meltwater, then green-up
summer       May 20 - Sep 14   118 d   full foliage
autumn       Sep 15 - Oct 31    47 d   the turn; October is peak golden autumn
winter       Nov 01 - Nov 30    30 d   first snowfall, ground not yet covered
winter_snow  Dec 01 - Mar 04    94 d   snow lies on the ground
```

These are **phenological** dates — when the landscape actually changes — not the
astronomical equinoxes, which is why they are lopsided. `--mapping met` switches to
Ukraine's hydrometeorological convention (round month starts) for anyone who prefers tidy
numbers to accurate ones.

Seasons are resolved from `os.date()` in-game and `datetime.date.today()` in the tooling.
There is no server, no save data and no timer: the date is the whole input.

## Blending

Each boundary has a window **centred** on it, 14 days by default. Inside the window the
two seasons' uniform sets are mixed by a smoothstep on the day offset, so 7 days before
the boundary is 0% of the new season, the boundary itself is 50%, and 7 days after is
100%. Set the transition to 0 for a hard switch on the date.

`intensity` then mixes the whole result against a `[neutral]` section that holds the
vanilla values, so 0 renders stock GAMMA and 1 the full season. It is a single dial over
everything, applied after the seasonal blend.

---

## What is driven

Twenty console uniforms, all belonging to **Screen Space Shaders**:

| Group | Commands |
|---|---|
| Colour and light | `r__color_grading`, `r__saturation`, `r__gamma`, `r__exposure`, `r2_sun_lumscale`, `r2_sun_lumscale_amb`, `r2_sun_lumscale_hemi`, `r2_sunshafts_value`, `r2_tonemap_adaptation`, `r2_tonemap_lowlum`, `r2_tonemap_middlegray`, `ssfx_hud_hemi` |
| Foliage | `ssfx_florafixes_1`, `ssfx_florafixes_2`, `ssfx_floravariation` |
| Fog | `ssfx_fog`, `ssfx_fog_scattering` |
| Wind | `ssfx_wind_grass`, `ssfx_wind_trees` |
| Wetness | `ssfx_wetness_multiplier` |

`ssfx_floravariation` is **pinned at 0** on purpose. It is a hue rotation rather than a
tint: driving it turns foliage red and blue rather than autumnal.

Values live in `gamedata/configs/seasons_of_the_zone.ltx`, one section per season plus
`[neutral]`. Regenerate it with `_tools/build_seasons_ltx.py` after editing the tables
there — that script is the source of truth for the numbers, and also feeds the dial's
colours so the two cannot drift apart.

## The failure mode everything is built around

**X-Ray rejects a whole console command if any one component is out of range.** It does
not clamp. The old value stays, and the only trace is a single line in the log:

```
~ Invalid syntax in call to 'ssfx_fog'
~ Available range [0.00000, 20.00000]
```

The valid range is on the *next* line, so grep with `-A1`.

An early version shipped a fog height of 28.0 against an engine maximum of 20.0 and
silently did nothing at all. So the mod now:

1. **clamps** every value on the way out, against ranges read from the engine;
2. **reads back** every value it sets;
3. distinguishes a **refusal** (the value did not move) from **drift** (something else
   overwrote it) — drift is re-applied, a refusal is not;
4. gives up after 5 refusals on a uniform and says so loudly in the log rather than
   retrying forever.

To verify a working session, look for `[seasons] armed` followed by
`[seasons] <season> applied` with every uniform reading OK.

---

## Why textures need a launcher

Everything above changes in-engine, immediately, on a running save. Terrain and grass
**textures cannot**: X-Ray binds them out of MO2's virtual file system at level load and
freezes them for the session. There is no runtime rebind — the only `reload_textures()`
in the entire GAMMA install works by calling `ChangeLevel()`.

So the texture layer has to be decided *before* the game starts. That is the whole reason
`play.bat` exists: it runs `season.py apply`, which stages the right mods for today, then
starts MO2. On a day when nothing has changed it does nothing and costs nothing.

## The rule that governs the texture layer

**MO2 resolves a shared file to the highest enabled mod that ships it.**

That single rule is what makes seasonal toggling work — flip a flag in `modlist.txt` and a
whole texture set appears or disappears with no copying — and it is also the one thing
that fails silently. A mod anchored below the real owner of its files flips its flag
exactly as asked, reports success, and changes nothing on screen.

`season.py whowins <path>` exists for this and only this. Use it before trusting a
placement; see [CONFIGURING.md](CONFIGURING.md).

---

## How the tooling talks to the MCM page

`season.py` runs before the game exists, so it cannot ask MCM anything. It reads MCM's own
store instead: `ui_mcm`'s get/set go through `axr_main.config:w_value` + `:save()`, which
lands in `appdata/axr_options.ltx` under an `[mcm]` section, one line per option as
`<tree>/<option> = <value>`. That file is plain text on disk, so a per-mod tick made in
the menu is readable at the next launch.

Three files run the other way — generated by `season.py`, read by the mod:

| File | Holds |
|---|---|
| `configs/season_mods.ltx` | the installed season-scoped mods, their seasons, sizes and state |
| `configs/season_staged.ltx` | which season the textures were staged for, so the mod can report a mismatch |
| `configs/text/eng/ui_mcm_seasons_mods.xml` | the MCM labels and hover text for those mods |

They ship **empty**, are rewritten on every launch, and should never be edited by hand or
committed with one install's contents in them.

The MCM page is built from that list rather than hardcoded, which is why adding a mod to
`TOGGLE_MODS` makes it appear in the menu by itself, under the right season heading, with
its own size and tick box.

## Two things that bite in MCM specifically

**String keys are not what the tutorial says.** An option's caption is
`ui_mcm_<hint or id>`, its hover text the same with `_desc` appended, and a list item is
`<tree>_<id>_lst_<value>` with *no* `ui_mcm_` prefix. Get one wrong and the raw key
renders on screen — which is how all three spellings above were found.

**`game.translate_string()` returns its input unchanged when nothing matches.** That is
why a missing key shows as itself, and also why the live calendar works at all: a computed
sentence passed as a `desc` row renders verbatim.

**Colours are a coin flip.** MCM documents a `clr` field as `{a,r,b,g}` in one place and
consumes it as `{a,r,g,b}` in another, so any hue is a gamble between two readings. The
panel uses greyscale text and real textures for the season header bars instead —
generated by `_tools/build_season_headers.py` from each season's actual grading values.

**Images are not aspect-corrected.** MCM's `Register_Image` does not apply `width_factor`
the way `Register_Slide` does, so a square request renders as an ellipse. The dial and the
header bars compute the correction from the live resolution: `(1024/768) / screen_aspect`,
which is 0.75 at 16:9 and 1.0 at 4:3.
