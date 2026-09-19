# Changelog

## 1.0.1 — 2026-09-19

Fixes from a full pass over the tooling against a simulated fresh install. Nothing about
how the seasons look has changed.

### Fixed

- `season.py apply` failed on every install but the author's with *missing grade
  preset*: the user.ltx colour-grade layer depended on `Atmos_*.ltx` console presets that
  never shipped. The mod drives those uniforms itself, so the layer is now skipped when
  the presets are absent instead of aborting every launch.
- The generated `Seasonal Soundscape` mod was never placed in the modlist. MO2 appends a
  folder it discovers on its own as disabled, so on a new install the ambient gating wrote
  correct presets the game never read. It is now placed above its source and switched
  with the MCM setting, like every other toggle.
- `patches/` ships `apply_seasonal_snowfall.py`, a patcher, instead of a modified copy of
  Project I.N.V.E.R.N.O's `yawm_snowfall.script`. None of their code is redistributed.
- Season identification re-extracted every option of every configured archive on every
  run — two minutes per launch with `LAYOUT` configured. Archive-side hashes are now
  memoised, keyed on the archive's size and date; the live folder is still hashed fresh.
- Two runs at once (`status` while `play.bat` staged, or `play.bat` twice) shared one
  staging folder and corrupted each other. Each run now stages in its own.
- The running-game check knew three executables; a DX10 player could have the game up
  while the modlist was rewritten under it. Any Anomaly binary now counts.
- A malformed `seasons_config.py` is refused with a sentence naming the entry, not a
  traceback — including `("winter")`, a string rather than a tuple, which used to enable
  a mod in deep winter through substring matching.
- Missing `py7zr` / `rarfile` packages are reported with the install command.
- `build_seasons_ltx.py` carries the grade values as data instead of reading one
  machine's presets from a hardcoded path, so it runs from a clone.
- `play.bat` prefers the `py` launcher, which the python.org installer puts on PATH even
  when `python` is not.
- Switching the mod off in MCM restores the colour grade to neutral before releasing
  control, so the console is not left seasonal.
- The MCM date line and the PDA report use fixed English month names; `os.date("%B")` is
  locale-dependent and rendered as garbage on non-English, non-Cyrillic Windows.
- The release builder now runs `status`, `apply --dry-run` and `apply` against a
  simulated fresh install and refuses to package on any failure.

## 1.0.0 — 2026-09-19

First public release.

### The seasonal engine

- Five phenological seasons for Polesia — spring, summer, autumn, winter and deep winter
  — resolved from the real-world date. Winter is split because snow arrives long before
  cover holds, and the thaw is what makes spring wet.
- Twenty Screen Space Shaders uniforms driven per season: colour grading, saturation,
  gamma, exposure, three sun lumscales, sunshafts, three tonemap controls, HUD hemi,
  two flora-fix vectors, fog and fog scattering, grass and tree wind, and wetness.
- Blending across a window centred on each boundary, 14 days by default, so seasons
  arrive gradually. 0 gives a hard switch on the date.
- An `intensity` dial mixing the whole season against vanilla values.
- Every value clamped to the engine's own range, read back after setting, with a refusal
  (the value did not move) told apart from drift (something else overwrote it). Gives up
  after five refusals on a uniform and says so in the log rather than retrying forever.
- `ssfx_floravariation` pinned at 0 deliberately: it is a hue rotation, not a tint.

### The MCM page

- A year dial showing where today sits, drawn from each season's own grading colours, and
  aspect-corrected for the live resolution.
- A live calendar panel listing all five seasons with the current one highlighted.
- Master switch, season pin (Automatic or any one season), transition length, intensity.
- Per-layer switches for colour, foliage, fog, wind and wetness.
- A generated list of season-scoped mods, grouped under coloured season headers with each
  group's mod count and total size, every mod independently switchable.
- Master switches for the launch-time texture layer and for ambient sound gating.
- Hover text on every option, generated for the per-mod entries.
- An optional PDA report on loading in, delayed so it does not land under the loading
  screen.

### The tooling

- `season.py status` — read-only: today's season, what is staged, what is installed.
- `season.py apply` — stage the texture layer; a no-op when it already matches the date.
  Supports `--season`, `--mapping pheno|met`, `--dry-run` and `--no-textures`.
- `season.py whowins <path>` — name every mod shipping a file and which one MO2 actually
  gives it to. Anchoring a seasonal mod below the real owner fails silently, so this
  exists to make the one silent failure visible.
- Paths detected from `ModOrganizer.ini`: drive letter, game folder and selected profile
  are read rather than assumed.
- A preflight that names what is missing and confirms nothing was changed, instead of a
  traceback, when run outside an MO2 install.
- Reads the per-mod ticks straight out of MCM's own `axr_options.ltx`, so a choice made
  in the menu is honoured at the next launch.

### Optional layers

- `TOGGLE_MODS` — switch whole mods on and off per season by flipping the modlist flag.
  Nothing is copied. Placement is re-checked every run, not only on insert.
- `LAYOUT` — restage a mod's contents per season out of its original archive, for mods
  shipping one folder per season. Staged contents are identified by hash, so a correct
  season is never re-copied.
- `SOUND_SRC` — generate a seasonal ambience mod from whichever soundscape wins your
  preset files: insects silenced under snow, marsh life fading in autumn, crows and owls
  kept year-round, wind and interiors untouched.
- `patches/apply_seasonal_snowfall.py` — a patcher for Project I.N.V.E.R.N.O's snowfall
  addon: gates snowfall, blowing leaves, seeds, dust and mist by season and scales snow
  with how deep into winter you are. Applies to the copy you installed, backs it up
  first, reverts on request. Ships none of INVERNO's code.
- `play.bat` — stages the season, then launches. The MO2 executable name is a variable at
  the top.

### Notes

- No third-party assets are redistributed. The texture, snowfall and soundscape layers all
  read mods you install yourself, and the configuration ships empty, so the mod does
  nothing to anyone's files until they ask it to.
- The three generated files inside the mod (`season_mods.ltx`, `season_staged.ltx` and
  `ui_mcm_seasons_mods.xml`) ship empty and are rewritten at every launch.
