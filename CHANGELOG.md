# Changelog

## 1.9.0 — 2026-09-25

- **`configure.bat` sets the mod up without editing Python.** A window lists your MO2
  mods; tick the seasons each one belongs to, and save. It works out the mod each one has
  to sit above from the files they share, names any other seasonal mod it overlaps with in
  the same season, and makes and deletes events. Copy it into your GAMMA folder along with
  `_tools/` and `play.bat`.
- **Your own calendar.** The window's Seasons tab moves the day each season starts and
  turns seasons off, for a year of only summer and deep winter, or one on the
  meteorological dates. Polesia's stays the default. A season turned off gives its days to
  the one before it; the game follows from its next start, MCM shows pages and pins for the
  seasons that are on, and the year dial is redrawn for your dates. Redrawing needs Pillow,
  which the tool offers to install; without it the dial is hidden.
- **Names of your own for the seasons.** Call deep winter "The Long Cold" and the PDA, the
  messages, MCM's pages and the dial all say so.
- **Presets.** Save your setup under a name - the calendar and names, the events, the mods
  on the calendar, texture sets and sound - and load it again, or load someone else's.
  Loading leaves out mods you don't have and places the rest for your install. Four
  calendars come with the tool, and a GAMMA example with the setup these tools were made
  on. Between the window and the presets, the config needs no editing by hand.
- **Events that repeat.** Besides a window of dates, an event can be days of the week, days
  of the month, the first or last of a weekday in the month, some months, or any mix of
  them: weekends, paydays, Friday the 13th.
- **The same from a command prompt,** for when someone is helping you: `configure.py add`,
  `remove`, `event`, `calendar`, `name`, `preset` and `list`. A mod name MO2 doesn't have
  gets suggestions instead of a silent skip.
- **Every save is checked with `season.py`'s own rules first,** keeps the previous file as
  `seasons_config.py.bak`, and rewrites only the entries that changed, so comments and
  anything written by hand stay. It repairs two common mistakes - an empty
  `TOGGLE_MODS = {}` left below the real table, and `("summer,spring")` - and refuses
  rather than guess: a file in another encoding, a table sharing its line with another
  statement, or a file changed since it was opened is left as it is, with a message.
- **`season.py` refuses more broken configs with a plain message** instead of a traceback
  or a wrong reading: dates written as text or decimals, periods and events on days that
  don't exist, a mod anchored above itself or in a loop with another, this mod on its own
  calendar, a file saved as UTF-16 or ANSI, and `exit()` in the config. It reads the
  config fresh on every run.
- The weather a mod can be scoped to - `freezing`, `thaw` and `heat`, as docs/API.md
  describes - is accepted in `when`.
- Fixed: a LAYOUT mod that isn't installed, or has no option for the season, stopped
  staging with a traceback. It is now left as it is.
- Fixed: a TOGGLE_MODS name that differs from the mod's folder only in case wrote a line
  for a mod MO2 doesn't have into modlist.txt.
- Fixed: in the week before each season turned, the log warned that the textures were
  staged for the wrong season.
- Fixed: the PDA message could say a season "begins in 1 days".
- Fixed: in December of a leap year, and the December before one, the PDA message on load
  counted a day wrong to late winter. February 29 itself was always handled.
- Fixed: the 1.8 zips carried the old `play.bat` comment about `SHORTCUT`.

## 1.8.3 — 2026-09-23

- **Fixed: MCM said no weather manager was found** on installs with Atmospherics 2.69. The
  Main page loaded Atmospherics' weather script while MCM was still building its menus,
  which fails there and left "Failed to load script level_weathers" in the log. At the
  main menu the page now reads the file instead of loading it.
- **Fixed: the Temperature units dropdown showed a raw key** instead of Celsius and
  Fahrenheit.
- When `when` is one name with commas in it, like `("summer,spring")`, `season.py` now
  says to give each season its own quotes, instead of pointing at a trailing comma.

## 1.8.2 — 2026-09-23

- **A mistake in `seasons_config.py` is reported in one plain message** with the line at
  fault, instead of a Python traceback. That covers a misplaced or missing comma, a name
  without quotes, and anything else Python can't read.
- **Fixed: a table set twice was thrown away without a word.** An entry added above the
  template's empty `TOGGLE_MODS = {}` counted for nothing, since Python keeps the last
  one, and every MCM page said no mods were set. `season.py` now names both lines.
- A config that imports something missing is reported instead of being treated as no
  config.
- `whowins` still runs while the config has a mistake in it.

## 1.8.1 — 2026-09-23

- **Fixed: `whowins` could name your own mod as its anchor.** MO2 enables a new install at
  the top of the list, so the mod you asked about was often the one winning the file, and
  `whowins` told you to put it above itself. Name your mod with `--for "<your mod>"` and it
  is left out of the answer. Without `--for`, the mod under the top one is named as well.
- `whowins` runs even when `seasons_config.py` has a mistake in it, since it's the tool
  you fill in `above` with.
- When an `above` mod isn't in the modlist, the warning gives the `whowins` command that
  finds the right one.

## 1.8.0 — 2026-09-23

- **Late winter, a sixth season.** March 5 to April 14 is the thaw: patchy snow, mud and
  bare trees, and the wettest weeks of the year. Spring now starts April 15, with the
  green-up. It has its own grade, fog, wind and wetness, light snow, a `Seasons_LateWinter`
  preset, an MCM page and a pin, and a place on the dial and The Year. `--mapping met` puts
  it in March.
- **Your `seasons_config.py` needs `late_winter`** on the mods that should stay through the
  thaw. The example adds it to INVERNO, Partly Snowy, the CCon dead set, the winter loading
  screens and PDA maps, and swamp fog. Without it, those mods switch off on March 5, and
  spring's don't come on until April 15.
- **Its own soundscape.** The marsh birds are back and the insects are not.
- **The snowfall patch updates in place.** Run `apply_seasonal_snowfall.py` again after an
  update and it replaces the layer in a patched copy; before, it said "already patched" and
  stopped. Late winter gets its light snow either way, but the thaw mist needs the update.
- The Year lists the seasons from spring, like the MCM pages.
- `calendar().season` can be `late_winter`.
- `play.bat` explains that `SHORTCUT` is the name of an MO2 entry, not an .exe, so a custom
  exe copied over the stock one needs no change.

## 1.7.0 — 2026-09-23

- **Installs through MO2.** *Install a new mod from archive* now accepts the zip; before,
  MO2 said it "does not look valid". `_tools/` and `play.bat` come along in the mod's
  folder. Copy them to your GAMMA folder for real-world temperatures and the texture and
  sound layers.
- **A forecast, not a timetable.** With Atmospherics 2.69's day planner, the Forecast page
  calls the weather the way a forecaster would: times are rounded and can be an hour or two
  out a day ahead, about one call in ten is wrong, and both improve as the change gets
  closer. Each call shows how likely it is, and calls shown at 90% come true about 90% of
  the time. MCM's **Exact weather forecast** shows the plan itself.
- **Odds on the base game's weather**, which GAMMA uses. Under **Next sky**, the page gives the
  chance that the next sky is rain or storm, overcast or fog, or clear or broken cloud. The
  scheduler draws it at random from a list it keeps, so these odds are exact.
- **Works outside GAMMA.** Tested on Anomaly 1.5.3 with Modded Exes, MCM and Mod App
  Creator. On base Anomaly the ecologist panel shows base Anomaly's own ecologist icon (the
  shield is from GAMMA's UI), and without DXML the mod no longer logs a stack trace at every
  start.
- **Fixed: real-world temperatures never worked from a release.** The 1.5.0 and 1.6.0 zips
  left out `fetch_weather.py`, so the forecast always used the climate model.
- **Fixed: a season change stopped halfway when it restaged the soundscape.** `season.py
  apply` swapped the textures and the soundscape, then failed before switching the seasonal
  mods. It only happened with `SOUND_SRC` set, and dates back to 1.4.0.
- The list under the chart is headed **Next 24 hours**, since it covers a full day.
- MCM names the weather scheduler as the base game's rather than GAMMA's, since it's the same
  one outside GAMMA.
- `weather()` adds `forecast` (the calls, each with `chance`) and, on stock, `odds`.
- The tools find the mod by its files, so it can have any name in MO2. `season.py status`
  warns when the mod is installed twice.
- The zip no longer includes `seasons_config.py`, so copying `_tools/` on an update keeps
  yours. It also drops a stale MO2 `meta.ini` and the build machine's fetched weather.
- `play.bat` says so when it's run from the wrong folder.
- Fixed: MCM's description of the warning-level forecast named brackets the page doesn't
  use.

## 1.6.0 — 2026-09-23

- **Fixed: the forecast said "Atmospherics is not running" on stock GAMMA.** GAMMA's
  Atmospherics mods don't include a weather manager, so a stock install uses the base game's,
  which doesn't plan ahead. The forecast now shows the current sky and when it will change
  ("turns in 3 to 5 hours"). With Atmospherics 2.69 installed separately, it still shows the
  whole day.
- **One app instead of two.** The Year and Forecast are now a single Seasons tile in Mod App
  Creator, with a switch at the top of each page. The page you're on is lit.
- **MCM shows what the app needs.** The top of the Main page says whether Mod App Creator is
  installed (red if not, since the app can't open without it) and which weather scheduler is
  running.
- **`weather()` adds `source` and `window`.** `source` is `"plan"` or `"stock"`, and stock adds
  the window the next change falls in, so an empty plan on stock GAMMA no longer reads as
  settled weather.
- **Running outside GAMMA** is covered in the README.
- For modders: `sotz_pda.script` routes the app's PDA pages without MAC, so a standalone
  version only needs its own way to open the app. See the note at the top of that file.

## 1.5.0 — 2026-09-23

- **Two PDA pages**, opened from Mod App Creator's launcher.
  - **The Year**: a twelve-month grid with today lit and the six marked days underlined,
    a list of the marked days with how far off each is and what it does, and the season
    start dates. On a marked day, its line and cell pulse red.
  - **Forecast**: the current and next sky, a barometer, a day chart of the weather and
    temperature, the day's coming changes, and tomorrow's range. A °C/°F button that
    matches the MCM option.
  - **The ecologist forecast**: how precisely the page times the next emission depends on
    your standing with the ecologists. Below 200 it's CLASSIFIED; at 200 it gives a
    bracket (`ALL CLEAR`, `8 to 16 hours`, `2 to 8 hours`, `WITHIN 2 HOURS`); at 700 it
    gives the hour, and strobes red under two hours. Sakharov messages you when you reach
    200. Both thresholds are MCM sliders.
- **Real-world temperature.** `play.bat` fetches Chornobyl's observed high and low before
  launch, and the in-game weather adjusts it, so a storm reads colder than clear sky.
  Without a connection it falls back to a climate model, and the page says which it's
  using. It never blocks a launch.
- **Temperature periods for staging.** A below-zero day adds a `freezing` period (also
  `thaw` and `heat`), so a mod can be scoped to `when = ["freezing"]` the way it's scoped
  to a season.
- **A read API**, `sotz_api.script`: `temperature()`, `weather()`, `blowout()` (with an
  `alert` flag for devices), `calendar()` and `tomorrow()`. See [docs/API.md](docs/API.md).
- **A Wearable Devices integration proposal** in
  [docs/WEARABLE-DEVICES.md](docs/WEARABLE-DEVICES.md), with its snippet tested against the
  API.
- Fixed: the emission countdown never showed a time, the barometer could show the wrong
  weather, opening either page could crash the game, and the launcher tiles were blank.
- Developer checks: `check_layout.py`, `check_locals.py`, `check_engine_api.py` and
  `check_ui_xml.py`, plus Lua tests for the API, both pages, and the Wearable Devices
  snippet.

## 1.4.0 — 2026-09-22

- **Six fixed days**, laid over the season rather than replacing it.
  - *Remembrance days*: April 26 (International Chernobyl Disaster Remembrance Day) and
    December 14 (Liquidators' Day). The weather is held clear and the PDA carries the day.
    No reward, no drop, no marker.
  - *Anniversaries*: March 20, August 22, October 2 and November 20, the mainline release
    dates. The weather is pushed to storm and a few extra artifacts are seeded on each
    level you visit, about zero to five, once per level per day.
  - Each day has three opening transmissions and a pool of fifteen more, 108 in all, sent
    every eight to twenty minutes. Every line is signed and carries its speaker's
    portrait. The pool is shuffled, so nothing repeats until it's used up.
  - Anniversary lines count the years in-world, from the in-game year and the year each
    game is set in. A fresh save hears "6 years since Operation Fairway." Heart of
    Chornobyl is set after Anomaly's start date, so its lines carry no count.
  - Six MCM switches, all on by default.
- The extra artifacts use Dynamic Anomalies Overhaul's own spawner and persist in the save
  like any spawned artifact.
- **The calendar is open.** `PERIODS` adds base periods alongside the five seasons, and
  `EVENTS` adds windows that overlay the period they land in, so a Christmas event keeps
  deep winter's snow. A window can be a single day or wrap the year end.
- `when` is the config key for a mod's periods. `seasons` still works.
- A season pin fixes only the base period; events still follow the real date.
- `--season` and the config check accept any declared period or event name.
- Fixed: `season_mods.ltx` recorded the wrong period, and the soundscape cut count came from
  the wrong season.
- `build_release.py` refuses to build while a test rig is still active in the scripts.
- New [docs/SCHEDULING.md](docs/SCHEDULING.md): the model, the config reference, recipes,
  and what the calendar can't express yet.

## 1.3.0 — 2026-09-20

- The season pinned in MCM now drives the staged layers too; before, a pin changed only
  the in-engine layers. Precedence is `--season`, then the pin, then the calendar.
- `status` names the pin and what the calendar would have said.
- The in-world screenshots are retaken on the current textures.

## 1.2.0 — 2026-09-20

- The seasonal soundscape now differs in all five seasons. Spring drops the night crickets
  and keeps the dawn chorus; autumn drops the daytime insects but keeps crickets until the
  first frost; the winters are unchanged.
- Editing `SOUND_CUT` now rebuilds the generated presets.

## 1.1.1 — 2026-09-20

- `seasons_config.example.py` rewritten as a worked example. Nothing in the mod changed.

## 1.1.0 — 2026-09-20

- The MCM entry is six pages: Main, and one for each season. A season's page has its color
  grade preset, the values that season resolves to, and a tick for each texture mod scoped
  to it.
- Mod ticks are per season, so a mod used by both winters can be left out of one. Earlier
  per-mod choices reset to on.
- Mod captions no longer repeat the season.
- A dropdown on each season's page picks the `cfg_load` preset its color grade comes from:
  the mod's own six, Atmospherics' Cold/Neutral/Warm, or any preset in `appdata/`.
- The mod's six grades ship as `Seasons_*.ltx` presets, and `play.bat` copies them into
  `appdata/` without overwriting.
- `GRADE_PRESETS` from 1.0.3 is replaced by the dropdowns.
- Fixed before release: reading `appdata/` could make saves fail to load with "Cannot find
  the specified saved game". The build now checks for the repair.

## 1.0.3 — 2026-09-19

- `GRADE_PRESETS` in `seasons_config.py`: a season's color grade can come from a
  `cfg_load` preset at each launch. Only the grade keys are rewritten.
- The user.ltx color grade layer and the Season Flora staging layer are removed from
  `season.py`; the mod sets those values itself. `status` output is shorter.
- Shorter documentation and comments, with corrections: the blend is linear, nine of the
  twenty values are SSS's, and MCM's store is `gamedata/configs/axr_options.ltx`.

## 1.0.2 — 2026-09-19

The mod can sit anywhere in MO2: no other mod ships its files, and script order doesn't
follow MO2 priority. [docs/LOAD-ORDER.md](docs/LOAD-ORDER.md) covers what does need placing
and how to recover from a GAMMA launcher Update.

- `season.py status` checks season-scoped mods against every mod above them and reports
  shadowed files, dormant conflicts, and overlaps. `apply` runs the check when the modlist
  changes.
- A missing `above` anchor skips that entry with a warning instead of stopping the run.
- `season.py` warns when the mod is missing or disabled, and when Season Flora is enabled
  beside it.
- Seasonal Soundscape follows its source mod.
- The running-game check only matches this install, so another GAMMA install on the same
  PC doesn't block it.
- MCM's settings file is found by MO2's rules, not by timestamp.
- Dynamic Tonemap Extended is detected at load and its five values are left to it.
- The snowfall patcher refuses INVERNO's FOMOD Light/Heavy scripts, warns about a nearby
  `level_weathers.script`, and has `--disable-weathers`.
- Winter PDA Maps in the example config is anchored above both INVERNO mods.
- `play.bat` refuses a missing MO2 shortcut and stops if `season.py` fails.
- README: which folder to copy, the shortcut step, the engine requirement, SSS sliders
  while a layer is on, and removing the snowfall patch.

## 1.0.1 — 2026-09-19

- `season.py apply` failed on other installs ("missing grade preset"); that layer is now
  skipped when the presets are absent.
- The generated Seasonal Soundscape mod is now added to the modlist, above its source.
- `patches/` ships a patcher, `apply_seasonal_snowfall.py`, instead of a modified copy of
  INVERNO's script.
- Archive hashes are cached, so identifying seasons no longer re-extracts every archive on
  every launch.
- Concurrent runs no longer share a staging folder.
- The running-game check recognizes every Anomaly executable.
- A malformed `seasons_config.py` entry is rejected by name, including `("winter")` written
  as a string instead of a tuple.
- Missing `py7zr` / `rarfile` packages are reported with the install command.
- `build_seasons_ltx.py` stores the grade values as data.
- `play.bat` prefers the `py` launcher.
- Switching the mod off in MCM restores the neutral color grade.
- Month names are always English.
- The release build tests `status`, `apply --dry-run` and `apply` against a fresh install.

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
