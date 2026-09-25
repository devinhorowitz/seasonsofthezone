# How it works

---

## The calendar

Six seasons. Winter comes in three parts because in Polesia snow starts falling in
November, settles from December, and thaws through March and early April into mud
before anything turns green.

```
spring       Apr 15 - May 19    35 d   green-up
summer       May 20 - Sep 14   118 d   full foliage
autumn       Sep 15 - Oct 31    47 d   leaves turn; October is the peak
winter       Nov 01 - Nov 30    30 d   first snowfall, bare ground
winter_snow  Dec 01 - Mar 04    94 d   snow on the ground
late_winter  Mar 05 - Apr 14    41 d   the thaw: patchy snow, mud, bare trees
```

These are the dates the landscape changes, not the equinoxes. They are the default:
`CALENDAR` in `seasons_config.py`, which `configure.bat`'s Seasons tab writes, moves them
and turns seasons off. `season.py` hands it to the game as `configs/season_calendar.ltx`,
which the script reads when it loads, and draws a dial for it with Pillow. A file that does
not read leaves the Polesia dates running. `--mapping met` uses Ukraine's meteorological
convention for one run of the tools.

The season comes from `os.date()` in game and `datetime.date.today()` in the tooling.
There is no server, no save data and no timer.

## Blending

Each boundary has a window centered on it, 14 days by default. Inside the window the two
seasons' values are mixed linearly: 7 days before the boundary is 0% of the new season,
the boundary is 50%, 7 days after is 100%. A transition of 0 switches on the date.

Each half of a window is at most half the season on that side. A calendar of your own can
have a two-week season, and a 30-day window at each end of it would overlap the next: the
blend would jump, and a season's first day could belong to the one two back.

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
`[neutral]`. `_tools/build_seasons_ltx.py` generates that file from its tables, the seven
`Seasons_*.ltx` presets in `configs/seasons_presets/`, and the dial's colors; edit the
tables and regenerate rather than editing the file.

A `cfg_load` preset is a text file of console commands in `appdata/`. With a preset
chosen for a season on its own page, the mod reads it when the table is loaded and again
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

That is also why a season pinned in MCM reaches the textures and the soundscape only
at the next launch: `season.py` reads the pin from MCM's store before the game exists.
`--season` on the command line overrides it.

## The MO2 rule

MO2 gives a shared file to the highest enabled mod that ships it. That is what makes
switching a texture set on and off a one-line change to `modlist.txt`, and it is also the
one thing that fails silently: a mod anchored below the real owner of its files flips its
flag, reports success, and changes nothing on screen. `season.py whowins <path>` shows who
owns a file. See [CONFIGURING.md](CONFIGURING.md).

---

## How the tooling talks to the MCM pages

`season.py` runs before the game exists, so it reads MCM's own store: MCM saves every
setting through `axr_main.config` into `gamedata/configs/axr_options.ltx`, under `[mcm]`,
one line per option as `<tree>/<page>/<option> = <value>` — the launch-time switches are
`seasons_zone/main/stage_textures` and `seasons_zone/main/stage_sound`, and a mod's
per-season tick is `seasons_zone/<season>/mod_<name>`. MO2 maps that path to the mod that owns
it (on GAMMA, "G.A.M.M.A. MCM values"). It is plain text, so a switch set in the menu is
readable at the next launch.

Three files go the other way, written by `season.py` and read by the mod:

| File | Holds |
|---|---|
| `configs/season_mods.ltx` | the installed season-scoped mods: seasons, sizes, state |
| `configs/season_staged.ltx` | which season the textures were staged for |
| `configs/text/eng/ui_mcm_seasons_mods.xml` | the MCM labels and hover text for those mods |

They ship empty and are rewritten at every launch. Do not edit them.

The season pages are built from that list, which is why a mod added to `TOGGLE_MODS`
appears in the menu by itself.

## MCM details

- A page inside an addon is a node without `sh` whose children have `sh = true`; MCM
  lists the children in its next column and titles each by its `text` string.
- An option's caption is the string `ui_mcm_<hint>` (the hint defaults to the option's
  path with `/` as `_`), its hover text the same with `_desc` appended, and a list item is
  `<path>_lst_<value>` with no `ui_mcm_` prefix, or a literal label with `no_str`. A wrong
  key renders as itself on screen.
- `game.translate_string()` returns its input unchanged when nothing matches, which is
  what lets a computed sentence render as a `desc` row.
- MCM documents a desc's `clr` as `{a,r,b,g}` in one place and uses it as `{a,r,g,b}` in
  another, so the page uses grayscale text and textures for the season header bars
  (`_tools/build_season_headers.py`, from each season's grading values).
- `Register_Image` does not apply `width_factor`, so a square request renders as an
  ellipse. The dial and the bars correct for it with `(1024/768) / screen_aspect`: 0.75 at
  16:9, 1.0 at 4:3.
