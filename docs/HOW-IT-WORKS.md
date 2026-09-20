# How it works

---

## The calendar

Five seasons. Winter is split because in Polesia snow starts falling in November but only
settles from December to early March, and the thaw is what makes spring wet.

```
spring       Mar 05 - May 19    76 d   thaw, then green-up
summer       May 20 - Sep 14   118 d   full foliage
autumn       Sep 15 - Oct 31    47 d   leaves turn; October is the peak
winter       Nov 01 - Nov 30    30 d   first snowfall, bare ground
winter_snow  Dec 01 - Mar 04    94 d   snow on the ground
```

These are the dates the landscape changes, not the equinoxes. `--mapping met` uses
Ukraine's meteorological convention instead.

The season comes from `os.date()` in game and `datetime.date.today()` in the tooling.
There is no server, no save data and no timer.

## Blending

Each boundary has a window centered on it, 14 days by default. Inside the window the two
seasons' values are mixed linearly: 7 days before the boundary is 0% of the new season,
the boundary is 50%, 7 days after is 100%. A transition of 0 switches on the date.

`intensity` then mixes the result with a `[neutral]` section holding GAMMA's stock
values: 0 is stock, 1 the full season.

---

## What is driven

Twenty console values. Nine are Screen Space Shaders' own (`ssfx_*`); the rest are the
engine's.

| Group | Commands |
|---|---|
| Color and light | `r__color_grading`, `r__saturation`, `r__gamma`, `r__exposure`, `r2_sun_lumscale`, `r2_sun_lumscale_amb`, `r2_sun_lumscale_hemi`, `r2_sunshafts_value`, `r2_tonemap_adaptation`, `r2_tonemap_lowlum`, `r2_tonemap_middlegray`, `ssfx_hud_hemi` |
| Foliage | `ssfx_florafixes_1`, `ssfx_florafixes_2`, `ssfx_floravariation` |
| Fog | `ssfx_fog`, `ssfx_fog_scattering` |
| Wind | `ssfx_wind_grass`, `ssfx_wind_trees` |
| Wetness | `ssfx_wetness_multiplier` |

`ssfx_floravariation` is held at 0. It is a hue rotation, not a tint; driving it turns
foliage red and blue.

The values are in `gamedata/configs/seasons_of_the_zone.ltx`, one section per season plus
`[neutral]`. `_tools/build_seasons_ltx.py` generates that file from its tables, the six
`Seasons_*.ltx` presets in `configs/seasons_presets/`, and the dial's colors; edit the
tables and regenerate rather than editing the file.

A `cfg_load` preset is a text file of console commands in `appdata/`. With a preset
chosen for a season on the MCM page, the mod reads it when the table is loaded and again
on Apply, and replaces that season's twelve grade commands with the preset's values before
blending. Presets are found by listing `appdata/` (`user.ltx` excluded) and the mod's own
folder.

## Out-of-range values

X-Ray rejects a whole console command if any one component is out of range. It does not
clamp. The old value stays, and the only trace is one line in the log:

```
~ Invalid syntax in call to 'ssfx_fog'
~ Available range [0.00000, 20.00000]
```

The range is on the next line, so grep with `-A1`.

So the mod clamps every value to a table of the engine's ranges before sending it, reads
every value back after setting it, and tells a refusal (the value did not move) from drift
(something else changed it). Drift is re-applied every 5 seconds; a refused value is given
up on after five tries, with a log line saying which.

A working session logs `[seasons] armed`, then `[seasons] <season> applied` with every
value reading OK.

---

## Why textures need a launcher

Terrain and grass textures are loaded from MO2's virtual file system when a level loads
and kept for the session. There is no way to reload them at runtime. So the texture layer
is decided before the game starts: `play.bat` runs `season.py apply`, then starts MO2.

## The MO2 rule

MO2 gives a shared file to the highest enabled mod that ships it. That is what makes
switching a texture set on and off a one-line change to `modlist.txt`, and it is also the
one thing that fails silently: a mod anchored below the real owner of its files flips its
flag, reports success, and changes nothing on screen. `season.py whowins <path>` shows who
owns a file. See [CONFIGURING.md](CONFIGURING.md).

---

## How the tooling talks to the MCM page

`season.py` runs before the game exists, so it reads MCM's own store: MCM saves every
setting through `axr_main.config` into `gamedata/configs/axr_options.ltx`, under `[mcm]`,
one line per option as `<tree>/<option> = <value>`. MO2 maps that path to the mod that owns
it (on GAMMA, "G.A.M.M.A. MCM values"). It is plain text, so a switch set in the menu is
readable at the next launch.

Three files go the other way, written by `season.py` and read by the mod:

| File | Holds |
|---|---|
| `configs/season_mods.ltx` | the installed season-scoped mods: seasons, sizes, state |
| `configs/season_staged.ltx` | which season the textures were staged for |
| `configs/text/eng/ui_mcm_seasons_mods.xml` | the MCM labels and hover text for those mods |

They ship empty and are rewritten at every launch. Do not edit them.

The MCM page is built from that list, which is why a mod added to `TOGGLE_MODS` appears in
the menu by itself.

## MCM details

- An option's caption is the string `ui_mcm_<hint or id>`, its hover text the same with
  `_desc` appended, and a list item is `<tree>_<id>_lst_<value>` with no `ui_mcm_` prefix.
  A wrong key renders as itself on screen.
- `game.translate_string()` returns its input unchanged when nothing matches, which is
  what lets a computed sentence render as a `desc` row.
- MCM documents a desc's `clr` as `{a,r,b,g}` in one place and uses it as `{a,r,g,b}` in
  another, so the page uses grayscale text and textures for the season header bars
  (`_tools/build_season_headers.py`, from each season's grading values).
- `Register_Image` does not apply `width_factor`, so a square request renders as an
  ellipse. The dial and the bars correct for it with `(1024/768) / screen_aspect`: 0.75 at
  16:9, 1.0 at 4:3.
