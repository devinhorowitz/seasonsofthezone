# Changelog

## 1.2.0 — 2026-09-20

- The seasonal soundscape now gives all five seasons a different sound. Spring and summer
  cut nothing at all before, and autumn cut one channel that appears in two presets, so
  three of the five were acoustically identical. Spring loses the night crickets and is
  carried by the dawn chorus; autumn loses the daytime insects but keeps crickets calling
  until the first frost; the winters are unchanged. On the reference ambience mod that is
  48 cuts across 16 presets for spring, and 58 across 11 for autumn, where both were
  previously near zero.
- Editing `SOUND_CUT` now rebuilds the generated presets. The marker on their first line
  records the channels they were cut with, and a mismatch counts as stale - before this
  the season name alone was compared, so an edit did nothing until the season turned.

## 1.1.1 — 2026-09-20

- `seasons_config.example.py` rewritten to read as a worked example rather than one
  install's notes. The headline case is now a pack that ships several seasonal variants
  of the same files - install each variant as its own mod, give it one season, and only
  one can ever be mounted - beside the existing two-season case.
- Nothing in the mod itself changed.

## 1.1.0 — 2026-09-20

- Caught before release, in the preset lookup added below: listing `appdata/` costs the
  engine its registry for `appdata/savedgames` underneath it, and loading a save then
  failed with "Cannot find the specified saved game" on a save that was plainly on disk.
  MCM builds a mod's page at startup, so it happened on every load, not only after opening
  the menu. The lookup now restores the registry, and the build refuses to package without
  that repair. No released version was affected.
- The MCM entry is now six pages: Main (calendar, dial, the in-engine layers, the two
  launch-time switches) and one for each season. A season's page holds its color grade
  preset, a read-out of the values that season resolves to, and a tick for every texture
  mod scoped to it.
- A mod's tick is per-season now, stored as `seasons_zone/<season>/mod_<name>`: a mod used
  by both winters can be left out of one and kept in the other. The global switches moved
  to `seasons_zone/main/`; earlier per-mod choices reset to on.
- Mod captions no longer repeat the season, since each mod is listed on the page of every
  season it serves: "Grass and Trees - Summer" reads as "Grass and Trees". Two mods that
  would then read alike on one page keep their full names.
- Color grade presets: the dropdown on a season's page (and Neutral on Main) picks the
  `cfg_load` preset that grade comes from — the mod's own six, Atmospherics' Cold/Neutral/
  Warm, or any preset in `appdata/`. Only the grade changes.
- The mod ships its six grades as `Seasons_*.ltx` presets; `play.bat` copies them into
  `appdata/` beside Atmospherics' (never overwriting), so they can be `cfg_load`-ed or
  edited in place.
- `GRADE_PRESETS` from 1.0.3 is gone; the dropdowns replace it.

## 1.0.3 — 2026-09-19

- `GRADE_PRESETS` in `seasons_config.py`: a season's color grade can be taken from a
  `cfg_load` preset — Atmospherics' own, or yours — at each launch instead of the shipped
  table. Only the grade keys are rewritten.
- The old user.ltx color-grade layer and the Season Flora staging layer are gone from
  `season.py`; the mod sets those values itself. `status` output is shorter.
- Documentation and comments rewritten shorter. Corrected: the blend is linear, not a
  smoothstep; nine of the twenty values are SSS's, not all twenty; MCM's store is
  `gamedata/configs/axr_options.ltx`, not `appdata/`.

## 1.0.2 — 2026-09-19

Load order.

Seasons of the Zone can sit anywhere in MO2: no other mod ships any of its files, and
script order comes from the engine's directory listing, not from priority. `docs/LOAD-ORDER.md`
covers what does need placing and how to recover from a GAMMA launcher Update.

- `season.py status` checks every file of every season-scoped mod against every mod above
  it and reports `SHADOWED` (an enabled mod would win), dormant (a disabled mod would if
  enabled) and overlaps between season-scoped mods. `apply` runs the check when the
  modlist has changed.
- A missing `above` anchor skips that entry with a warning instead of aborting the run.
- `season.py` warns when the mod itself is missing or disabled in the selected profile,
  and when Season Flora is enabled beside it.
- Seasonal Soundscape follows its source mod: disabling the source removes the generated
  presets.
- The running-game check matches executable paths against this install, so another GAMMA
  install on the same machine no longer blocks it.
- MCM's settings file is found by MO2's rules (overwrite/, then the highest enabled mod),
  not by timestamp.
- In game, Dynamic Tonemap Extended is detected at load and its five values are left to
  it. A console command the engine does not know is reported as such, not as out of range.
- The snowfall patcher refuses INVERNO's FOMOD Light/Heavy scripts (they lack the
  particles the seasonal layer uses), warns when `level_weathers.script` is beside the
  target, and has `--disable-weathers`. It is tested against INVERNO's real script.
- Winter PDA Maps in the example config are anchored above both INVERNO mods; INVERNO
  ships its own `ui_global_map.dds`.
- `play.bat` refuses an MO2 shortcut that does not exist and stops on a `season.py`
  failure instead of launching.
- README: which folder to copy, the shortcut step, the engine requirement, SSS sliders
  being overridden while a layer is on, and reverting the snowfall patch on removal.

## 1.0.1 — 2026-09-19

Fixes from running the tooling against a fresh install.

- `season.py apply` failed on any install but the author's ("missing grade preset"): the
  color-grade layer read `Atmos_*.ltx` presets that never shipped. The mod sets those
  values itself, so the layer is skipped when the presets are absent.
- The generated Seasonal Soundscape mod was never added to the modlist, so its presets
  were never read. It is now placed above its source and follows the MCM switch.
- `patches/` ships `apply_seasonal_snowfall.py`, a patcher, instead of a modified copy of
  INVERNO's `yawm_snowfall.script`.
- Season identification no longer re-extracts every archive on every run (two minutes per
  launch with `LAYOUT` configured); archive-side hashes are cached.
- Concurrent runs no longer share a staging folder.
- The running-game check recognises every Anomaly executable, not three of them.
- A malformed `seasons_config.py` is refused with a message naming the entry, including
  `("winter")` — a string, not a tuple — which used to enable a mod in the wrong season.
- Missing `py7zr` / `rarfile` packages are reported with the install command.
- `build_seasons_ltx.py` carries the grade values as data instead of reading presets from
  a hardcoded path.
- `play.bat` prefers the `py` launcher.
- Switching the mod off in MCM restores the color grade to neutral.
- Month names are fixed English; `os.date("%B")` depends on the Windows locale.
- The release build runs `status`, `apply --dry-run` and `apply` against a simulated fresh
  install and refuses to package on a failure.

## 1.0.0 — 2026-09-19

First release.

- Five seasons for Polesia, resolved from the real-world date, blended across a 14-day
  window centered on each boundary, with an intensity slider.
- Twenty console values per season: color grading, saturation, gamma, exposure, sun
  lumscale, sunshafts, tonemap, HUD hemi, flora fixes, fog, wind and wetness. Every value
  is clamped, read back, and given up on after five refusals.
- MCM page: year dial, today's date, master switch, season pin, transition length,
  intensity, one switch per layer, a generated list of season-scoped mods grouped by
  season, master switches for the texture and sound layers, hover text, and a PDA message
  on load.
- `season.py`: `status`, `apply` (`--season`, `--mapping`, `--dry-run`,
  `--no-textures`) and `whowins`. Paths come from `ModOrganizer.ini`. Per-mod switches
  are read from MCM's `axr_options.ltx`.
- `TOGGLE_MODS` (switch a mod per season), `LAYOUT` (restage a mod's contents from its
  archive), `SOUND_SRC` (season-gated ambient presets generated from your own).
- `patches/apply_seasonal_snowfall.py` for INVERNO's snowfall addon.
- `play.bat`: stage, then launch.
- No third-party assets are included. The three generated files in the mod ship empty.
