# Changelog

## Unreleased

- **A page in the PDA.** The calendar is now readable in game: the next emission and psi
  storm, the five seasons with the current one lit, the six marked days with how far off
  each is, and the mods the calendar is scheduling. Read-only.
  - Registered with Mod App Creator when it is present, so the page lives in the app
    launcher instead of taking space on the PDA tab bar. Without MAC nothing links to it
    and nothing breaks. The tab id is injected into `ui/pda*.xml` at runtime rather than
    by shipping a fork of a file three other mods also edit.
  - The emission and psi-storm countdowns read the surge and psi-storm managers' existing
    singletons directly. Calling `get_surge_manager()` would *construct* one, and that
    constructor allocates a dozen `sound_object` handles; the page never does that.
- **The sky, at the top of the forecast page.** A glyph for what you are under, an arrow,
  a glyph for what you are getting, and when. The page could already say it - in words, in
  a table, four rows down. Seven drawn glyphs in the mod's own palette, from the new
  `_tools/build_weather_icons.py`. The arrow only appears when there IS a next: on a
  settled day, an arrow pointing at a repeat of the same sky would be a lie.
- **Fixed: the barometer showed the wrong weather.** The gauge picked its image from `w`
  nine lines above the `local w = d.weather` that creates it, so it read a nil global and
  fell through to its default. Nothing failed and nothing logged - it just drew cloudy
  during a storm.
  - New **`_tools/check_locals.py`**: within a function body, flags a name read above the
    `local` that declares it. Narrow on purpose, and clean on the whole mod - `for`
    variables, nested-function parameters and table-constructor keys are all declarations
    or non-reads, and treating any of them wrongly made it cry wolf on real code.
- **Both PDA pages, after seeing them in game.**
  - **Columns line up now.** `letterica` is a proportional font, so `string.format("%-12s")`
    padded with spaces narrower than the glyphs around them and every table came out
    ragged. Each column is its own text widget at a fixed x inside a row holder, which is
    how MAC positions its launcher tiles.
  - **A back button**, and Escape now leaves the page instead of being swallowed. Both go
    to the MAC launcher.
  - **The launcher tiles were empty.** `Init3tButton` + `InitTexture` is a four-state
    button: the engine appends `_e`/`_h`/`_t`/`_d` and looks those up as *declared* texture
    ids. A loose `.dds` satisfies none of them and nothing is drawn. New
    `_tools/build_app_icons.py` renders 512x512 state sheets and the `textures_descr` to
    declare them, laid out the way MAC's own `ui_icon_apps.xml` is.
  - The year tile is no longer the dial. The dial's season names and day counts read at
    200px on the page and are mud at the ~48px a tile gets, so the tile is a plain ring
    with the live season lit - five variants, changing five times a year.
  - Eight weather changes instead of six, now that the rows are tidy.
- **Fixed: a hard crash on opening either page.** `widget:GetWndRect()` does not exist in
  this engine - it appears nowhere in ~16,000 lines of other mods' scripts. `GetHeight()`
  is the real call. It passed a syntax check, passed the Lua-runtime tests because the
  harness stubs the widget layer, and fataled on the first click.
  - New **`_tools/check_engine_api.py`**: builds a corpus of every method called across
    all other installed scripts and flags any this mod calls that no other mod calls
    anywhere. Invented API has nowhere to hide.
  - New **`_tools/check_ui_xml.py`**: asserts a ui xml begins with its root element. A
    comment above the root is valid XML but X-Ray takes the first element as the document,
    so `ParseFile` fails - and it does not raise, it just makes every `Init*` return nil.
- **A read API — `sotz_api.script`.** The mod keeps a schedule nothing else in the game
  does, and until now the only way to see it was our own pages. This publishes it: four
  pure, non-throwing, cached accessors any mod can read. `sotz_api.VERSION` is the
  compatibility check. New in [docs/API.md](docs/API.md).
  - `temperature()` — a **model**, and labelled one: nothing in Anomaly or GAMMA has an
    ambient temperature to read. Daily high and low come from climate normals for the
    Polesia region and slide between months; the curve between them runs on the *game*
    clock, because the day is accelerated and a fixed number would be wrong twice over.
    Cloud squeezes the swing, rain and storms drag the day down. Endpoints are published
    next to the current value so a consumer can draw a band without re-deriving anything.
  - `weather()` — now, next and the plan, straight from Atmospherics' own schedule.
  - `blowout()` — the emission and psi countdowns at the tier the player has earned, plus
    a `fraction` (0 at the event, 1 a period away) meant for driving a gauge or a pulse
    rate. A locked tier exposes nothing, deliberately.
  - `calendar()` — season, next turn, and today's marked day.
  - **No Wearable Devices bridge ships here, on purpose.** WD gates sensors on the device
    tier config, so adding one would make this mod a fork of it. API.md gives the ~15-line
    pulse sensor a separate compat mod would use — the device ticking faster as an
    emission closes, and staying silent for a stalker the ecologists do not trust.
- New **`_tools/test_api.py`**: twelve cases under a real Lua interpreter, in a harness
  that reproduces X-Ray's per-file namespacing, so a cross-file reference that would
  silently fail in game fails here too.
- The forecast page now shows air temperature through the same API, rather than deriving
  its own and disagreeing with a device by a degree.
- **A second page: Forecast.** The calendar answers *when is it* and runs on real dates;
  the forecast answers *what is about to happen* and runs on the game clock. Splitting
  them also gives the mod a place to put near-term world state that is not a date —
  adding a reading is a section in `Fill()` and a field on `forecast_page()`.
  - **The next day.** Atmospherics plans the weather rather than rolling it as it goes:
    `roll_day_plan` fills `day_plan` 24 game hours ahead. The page reads that plan, so the
    change times are the real ones. Only changes are listed, never a repeated cycle, and
    a plan with no change in it reads *Settled*. Ungated.
  - Its own barometer icon, generated by the new `_tools/build_forecast_icon.py` in the
    year dial's drawing language — same needle, same hub — so the two apps sit together
    in the launcher without looking like two addons.
- **The forecast is earned.** How precisely the page reports the next emission depends on
  your standing with the ecologists — the faction that would actually be taking the
  readings. Below 200 goodwill it shows the number you need and nothing else; at 200 it
  warns without timing (`close` / `building` / `no sign`); at 700 it gives the hour. Both
  thresholds are MCM tracks.
  - The bands are a fraction of the live `emission_frequency`, not fixed hours, so they
    still mean something at any setting.
  - Emissions are deliberately **not** calendar entries. At the stock frequency and
    `time_factor = 6` they land every 2–4 real hours — six to twelve per real calendar
    day — so a day-scale entry would say "likely" every day forever.
- New **`_tools/test_forecast.py`**: runs the shipped script under a real Lua interpreter
  with the engine bindings stubbed. Fourteen cases — the three tiers, the band
  boundaries, that neither locked nor coarse ever leaks the exact time, and the weather
  plan's handling of past segments, repeated cycles, a settled day and a missing
  Atmospherics.
  - Textureless but for the mod's own dial and accent bar. The shared PDA frame textures
    other tab-adding mods reach for are declared in no `texture_descr` in a stock install,
    which is why those pages log *Can't find texture*.

## 1.4.0 — 2026-09-22

The launch-time half was never seasonal — it maps a date to a set of names and stages the
mods scoped to them. This release stops pretending otherwise: the calendar is now open.

- **Six fixed days**, laid over the season rather than replacing it.
  - *Remembrance*: April 26 (International Chernobyl Disaster Remembrance Day) and
    December 14 (Liquidators' Day). The weather is held clear and the PDA carries the
    day's transmissions. No reward, no drop, no marker.
  - *Anniversaries*: March 20, August 22, October 2 and November 20 - the mainline
    releases. These pull the opposite way: the weather is pushed to storm, and an extra
    few extra artefacts are seeded on each level visited - roughly nought to five, once
    per level per day and persisted across reloads. The opening line counts the years and
    is computed from the date, so it never goes stale.
  - **Every line is signed and carries its speaker's portrait.** Eight voices, each
    given the lines its vantage point fits: bar gossip from the Bar, readings from
    Yantar, military traffic from Skadovsk, routes from a guide. A speaker never narrates
    themselves, so "Barman poured one and left it on the counter" comes from Nimble.
    Portraits come from `configs/plugins/mod_news_tips_icons_sotz.ltx`, a DLTX overlay of
    the base tips-icon table; every texture it names is one the base game already
    references, and an unknown key falls back to the default icon rather than failing.
  - Each day has three opening transmissions and a pool of fifteen more - 108 in all -
    sent at random intervals of eight to twenty minutes. Roughly 15,000 distinct sets per
    day, so a playthrough hears about a third of a pool and no two sound alike. The pool
    is a shuffle bag rather than a straight roll: with a plain random pick, repeats land
    often enough to read as a bug.
  - **The anniversary counts are measured in-world, not out of it.** The four dates are
    release dates, which is deliberate - but the lines are spoken by stalkers, so the
    arithmetic is the in-game year against the year the game is SET in, not the release
    year against the real one. Shadow of Chernobyl is set in May 2012, Clear Sky in 2011,
    Call of Pripyat in August 2012; Anomaly starts on 26.10.2018. A fresh save therefore
    hears "6 years since Operation Fairway", and the count advances as the save ages.
  - Heart of Chornobyl is set in 2021-22, which is still ahead of Anomaly's calendar, so
    it carries no count at all - its transmissions are premonitory rather than
    remembered. That also stops all four anniversaries striking the same nostalgic note.
  - Every day keeps at least one opening with no count in it, so an unreadable in-game
    year falls back to a line that renders instead of printing a format specifier.
  - Six MCM switches, all on by default.
- The artefact crop calls Dynamic Anomalies Overhaul's own public spawner rather than its
  spawn-chance setting, which is a file local and unreachable - and which, written to MCM,
  would have survived a crash and left the rate raised for good. Those artefacts do
  persist in the save, as any spawned artefact does.
- The weather is driven through Atmospherics' own weather manager, the accessor
  surge_manager.script already uses, and only written when the cycle has drifted.
- `build_release.py` refuses to build while a test rig is still armed in the mod's
  scripts. A remapped date and shortened message intervals, left in place after live
  testing, had otherwise gone into several builds unnoticed.
- **`PERIODS`** adds base periods alongside the five seasons. They partition the year the
  same way: one is active at a time, each runs until the next begins.
- **`EVENTS`** adds windows that *overlay* whatever period they land in rather than
  replacing it, so a Christmas event keeps deep winter's snow underneath. A window may be
  a single day, and a start after its end wraps the year end.
- A date now resolves to a **list** — the base period, then every event covering it — and
  a mod is staged if any name it is scoped to is in that list.
- **`when`** is the config key for a mod's periods. `seasons` is the original spelling and
  still works; existing configurations need no edit.
- A pin or `--season` fixes the *base* period only. Events still resolve against the real
  date, so pinning summer in December does not cancel a Christmas event.
- `--season` and config validation accept any declared period or event name, and an
  unknown name is reported by name before anything is staged.
- **Fixed:** `write_mod_panel` named its loop variable the same as its parameter, so the
  `staged_for` value written to `season_mods.ltx` and the soundscape cut count were both
  read from the last name in the season tuple (`winter_snow`) rather than the period being
  staged. Present since the MCM mod panel was added.
- New **[docs/SCHEDULING.md](docs/SCHEDULING.md)**: the model, the config reference,
  recipes, and an honest list of what the calendar cannot express yet (weekday and
  nth-of-month recurrence, moveable feasts, per-event MCM ticks).

## 1.3.0 — 2026-09-20

- The season pinned in MCM now drives the staged layers too. MCM offers "automatic, or
  pin one" and the in-engine layers honoured it, but `season.py` only ever read the
  calendar - so pinning Deep winter gave you winter light and fog over autumn ground
  textures and an autumn soundscape. Precedence is `--season`, then the pin, then the
  calendar; a value in the store that is not a season falls back to the calendar.
- `status` names the pin and prints what the calendar would have said, instead of
  reporting the calendar's answer as though it were the reason.
- The two in-world screenshots are retaken on the current texture stack; the caption
  named a pack that no longer stages for either season.

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
