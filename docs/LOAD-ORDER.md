# Load order

Load order is the usual way an otherwise working STALKER install gets broken, so this page
says exactly where each part of Seasons of the Zone sits — and, more usefully, which parts
do not care. Line numbers quoted below are from the reference install's
`profiles/G.A.M.M.A/modlist.txt` and are examples, not targets; yours will differ.

---

## The short answer

- **Seasons of the Zone itself: anywhere.** Its position changes nothing. It must be
  *enabled*; that is the whole rule.
- **The season-scoped mods** in `TOGGLE_MODS` each sit directly above the mod they must
  beat. `play.bat` puts them there and re-checks every launch. `whowins` tells you which mod
  that is; `season.py status` tells you if something higher up is getting in the way.
- **Seasonal Soundscape** is generated at launch and placed directly above its source mod
  by the tool. It follows the source mod's enabled state.
- **INVERNO's snowfall addon: anywhere, once `level_weathers.script` is removed from it.**
  Left in, that one file takes over the weather system from wherever MO2 drops the folder.
  The patcher warns when it sees it, and `--disable-weathers` renames it out of the way.
- **Never enable** the earlier Season Flora prototype beside this mod. **Dynamic Tonemap
  Extended** is detected and given its five uniforms rather than fought over.
- A GAMMA launcher **Update** forgets all of the above. Recover from a modlist snapshot,
  not by re-ticking things at the top of the list.

---

## How MO2 priority works

MO2 keeps the load order in `profiles/<selected profile>/modlist.txt`. Line 1 is a header;
line 2 is the **highest**-priority mod and the last line the lowest; `+` is enabled, `-`
disabled. When two enabled mods ship the same file, the higher-priority one — the *lower*
line number — wins and the other copy is never seen. That is the only thing priority does:
it arbitrates same-named files. It has no effect on a mod that shares no file with anyone,
and it does not order scripts at runtime.

Two things catch people. First, the MO2 window shows the list upside down relative to the
file: line 2 of `modlist.txt` is the *bottom* of the window. Second, a folder you drop into
`mods/` by hand is appended **disabled** — on the reference install at the top of the
file, i.e. highest priority (inferred from a snapshot in which fifty such folders sat at
lines 2–51, all `-`; not confirmed against MO2's source). A mod installed through MO2's
own archive dialog may be enabled on install; check rather than assume.

---

## Seasons of the Zone itself

**Files.** The mod ships 44 files under `gamedata/` (two scripts, three `.ltx`, two text
XML, 37 `.dds`). No other mod, enabled or disabled, ships any of those paths — a scan of
863 other mod folders (120,491 files) found zero collisions, and
`python _tools/season.py whowins scripts/zzz_seasons_of_the_zone.script` lists exactly one
provider. So there is nothing for the mod to win or lose at any line. It uses no DLTX
overlays either.

**Scripts.** MO2 merges every enabled mod's `gamedata/scripts` into one virtual directory.
The engine enumerates that directory and calls each script's `on_game_start()` in the order
it came back (`axr_main.script`, the `file_list_open_ex("$game_scripts$", …, "*.script")`
loop — no sort applied, nothing consults the modlist). That order is by filename
(lowercased byte order — an inference from OpenXRay's file table, corroborated by the print
order in the reference install's log). This is why the script is called
`zzz_seasons_of_the_zone.script`: it enumerates after `ssfx_*`, `level_weathers`, `ui_mcm`
and `yawm_snowfall`. But the name is convention and insurance, not a requirement: the mod's
first apply runs on `actor_on_first_update`, which fires after the entire `on_game_start`
pass in which SSS pushes its own values; an MCM change is re-applied 0.5 s after the
callback; drift is re-asserted every 5 s. MCM discovers the settings page by the
`*mcm.script` filename mask and sorts pages by title, so position is irrelevant there too.

**What actually matters:**

- It must be **enabled**. `season.py` never enables it for you — it only reads the mod's
  config files by name — and it disappears from the list after a launcher Update. Since
  1.0.2 the tool says so plainly when the mod is missing or disabled in the selected profile.
- Keep the file names. `_mcm.script` is MCM's discovery suffix. The module name
  `zzz_seasons_of_the_zone` is referenced by the snowfall gate (which falls back to
  *unconditional* snow when it is nil) and by the MCM script; a rename breaks both silently.
- Only one copy. Two enabled copies resolve **per file** to the higher one, with any
  leftover files from the lower copy still mounted; nothing stamps a version. If you
  update, replace the folder.
- The engine must know all twenty commands. GAMMA's Modded Exes build does
  (`AnomalyDX11.exe` / `AnomalyDX11AVX.exe` contain all twenty); an older or non-modded
  exe lacks the `ssfx_` ones, and under DX9/DX10 they do not exist at all. On such a build
  the mod gives up on each unknown command after five tries and says so in the log. Read
  "requires Screen Space Shaders" as *SSS plus the engine GAMMA ships it with, on DX11*.

---

## The season-scoped mods and their anchors

Each entry in `TOGGLE_MODS` names an `above` anchor: the mod yours must outrank. On every
run `season.py` inserts the mod above its anchor if it is missing, moves it up if it sits
below, and sets the flag for the current season. Positions are checked every launch, so
hand-moving them is pointless. An anchor that no longer exists (GAMMA renumbers folders
between versions) skips that one entry with a printed warning; the rest still run.

The anchors on the reference install, all verified with `whowins`:

| Mod | Anchor | Why |
|---|---|---|
| INVERNO Winter Textures | `388- Aydins Grass Tweaks SSS Terrain LOD Compatibility` | Real collision: 14 `textures/terrain/*_lod_textures.dds`. INVERNO also carries `settings_screenspace_TERRAIN.h` / `_PUDDLES.h`, so it must beat SSS and Atmospherics too, and 388 sits above both. |
| INVERNO Partly Snowy | `INVERNO Winter Textures` | All 52 of its files are also in base INVERNO; it is an overlay and must be above. |
| Winter PDA Maps | `INVERNO Partly Snowy` | Above **both** INVERNO mods, because INVERNO ships its own `textures/ui/ui_global_map.dds` and is on in the same seasons. Anchored on the map mod alone it sat below INVERNO and the winter global map never showed. |
| PanceRide Summer / Autumn | `388- Aydins …` | **Zero shared files with 388.** Purely positional: it works because 388 sits above Atmospherics, SSS 24 and the Aydin base pack. That invariant is recorded beside the entry in the example config. |
| Winter Loading Screens | `282- GAMMA Loading Screens` | 132 `textures/intro` files. |
| Winter Footsteps | `472- Dark Signal Amplified Footsteps Extended` | Beats all four footstep mods. |
| Swamp Ground Fog | `Atmospherics 2.69 RC7.2 SSS24` | Cosmetic grouping only; its 7 files collide with nothing. |

**Finding the right anchor.** Pick a file the mod ships and run
`python _tools/season.py whowins <gamedata-relative path>`. It prints every mod shipping
that file, enabled or not, in priority order, and the winner. Anchor on the highest
*enabled* shipper. If it reports that the base game `.db` provides the file, any placement
wins. Two limits: it cannot see inside `.db` archives, and it compares full
`gamedata`-relative paths — `configs/environment/ambients/presets/x.ltx`, not `x.ltx`.

**The audit.** `above` means "directly above X", not "above everything that ships the
file". A mod far higher in the list that also ships one of the files wins silently.
`season.py status` therefore tests every file of every season-scoped mod against every mod
above it and reports three things:

- `SHADOWED` — an enabled mod above ships the file. Wrong now; re-anchor or disable it.
- *dormant* — disabled mods above share files (on the reference install: Lifestorock's Bleak
  Fall Redux with 162 of INVERNO's files, Grulag's Dead Bushes, six shader packs, RETUNE).
  Harmless today, a trap the day one is ticked — run `status` afterwards.
- *note* — two season-scoped mods that are both on in some season overlap. One seasonal mod
  deliberately overriding another (Partly Snowy above INVERNO) looks identical to a mistake
  here, so this is information, not an error.

`play.bat` runs the same audit whenever the modlist has changed since it last ran.

INVERNO also shares 239 paths with PanceRide Autumn and 222 with PanceRide Summer
(`build_details.dds`, the lfo trees). Harmless only while their seasons stay disjoint
(`winter`/`winter_snow` versus `summer`/`autumn`); never widen one window over the other.
And INVERNO's `textures/anamflares` overrides seven Atmospherics sun/flare textures and all
four of Roadside's Lens Flares every winter; prune the folder unless you want INVERNO's sun.

---

## The generated Seasonal Soundscape

`SOUND_SRC` names the ambience mod that wins your
`configs/environment/ambients/presets/` files. At launch the tool reads that mod's presets,
writes season-gated copies into a mod called `Seasonal Soundscape`, and places it directly
above the source. On the reference install that is line 570 above `304- Dark Signal Weather
and Ambiance Audio` at 571, winning all 21 presets. Do not move it.

If you disable the source mod — to go back to another soundscape, say — the generated mod
is disabled and its overrides removed at the next launch, so it cannot keep carrying the
old presets. It is only placed *above the source*, so a preset mod higher in the list would
beat it; `status` reports that as a shadow.

---

## INVERNO's snowfall addon

You install the addon yourself and run `patches/apply_seasonal_snowfall.py` on it. Where it
sits does not matter: `yawm_snowfall.script` is shipped by nothing else, its 13
`particles/yawm/snow` files are byte-identical to the stock Particles Cinematic VFX copies,
and the gate finds Seasons of the Zone by global name, not by priority. Keep the module
**enabled all year** — its particles are created when the script loads, and the gate, not
the modlist, decides what plays in each season (seeds in spring, leaves in autumn, dust in
the dry months). Do not put it in `TOGGLE_MODS`.

**The hazard is one file.** INVERNO's standalone download (`Snowfall (light + Dynamic
Fog).7z`) also ships `gamedata/scripts/level_weathers.script`, an older fork of the weather
manager. **Remove it from the module before enabling it** (delete it, hide it in MO2, or run
the patcher with `--disable-weathers`). Why:

- Wherever MO2 drops the module, that file beats the base game's copy — priority only
  arbitrates between mods, and the base `.db` always loses. If your weather manager comes
  from a mod (on the reference install the weighted weather manager that ships with the
  Atmospherics 2.69 RC, at line 193), then above that mod INVERNO's fork wins instead and
  everything it lacks — weather weights, the progression matrix, climatology, the MCM
  starting-weather option — silently goes away. No crash, no log line; the MCM page still
  renders, every option on it is dead, and the default cycle flips to cloudy.
- On stock GAMMA (no mod-shipped `level_weathers.script`) the damage is smaller — the fork
  differs from vanilla by 27 lines — but there is then *nothing to place the module below*,
  so the only fix is removal.

Check with `python _tools/season.py whowins scripts/level_weathers.script`. The only
acceptable answers are your weather-manager mod, or "no enabled or disabled mod ships it".
If the snowfall module appears, remove the file.

**Two more traps for people who own the all-in-one FOMOD (v1.08.4):**

- Its "Light Snowfall" / "Heavy Snowfall" options install a *different*, cut-down script
  that declares no seed, leaf or fog particles. The seasonal layer keys on those, so the
  patcher refuses that copy (it names the missing particles) rather than produce a script
  that fails at load. Use the standalone addon.
- The addon ships no textures. Its 15 particle textures (`grpl\`, `pfx\pfx_yawm_*`,
  `semitone\environmental\`) exist only inside INVERNO's base-module archive
  `db/addons/inverno_textures.db` (particle and effect textures only — no terrain). That
  archive, and with the FOMOD layout the `particles/graupel` and `particles/yawm`
  definitions too, must live in a mod that is enabled all year — never in a season-toggled
  INVERNO texture mod. Otherwise the non-winter effects render with missing textures, and a
  missing particle *definition* is a fatal "Particle effect or group doesn't exist" at level
  load (the string is in the engine; the fatal is inferred).

---

## Things that must not be enabled together

None of these is a file conflict, so no modlist position resolves them.

- **Season Flora** (the earlier prototype; not shipped in this release). It writes five of
  the seven SSS uniforms this mod drives — two writers, one console value. `season.py`
  warns when both are enabled. Keep it disabled; delete it.
- **37- Dynamic Tonemap Extended.** Disabled by default in GAMMA and a common opt-in. It
  pushes `r2_tonemap_adaptation`, `r2_tonemap_lowlum`, `r2_tonemap_middlegray`,
  `r2_sun_lumscale_amb` and `r2_sun_lumscale_hemi` on a timer of `60 / time_factor`
  seconds. Left to fight, the two alternate every few seconds — a visible exposure pulse.
  Since 1.0.2 the mod detects the DTE module at load, leaves those five uniforms to it and
  says so once in the log; the other seven grade uniforms and every other layer still
  follow the season.
- **A second copy of Seasons of the Zone.** Per-file shadowing, no version check.
- **Not a conflict, but worth knowing:** while a layer is on, SSS's own MCM sliders for
  fog, wind, flora fixes and wetness are silent no-ops — they apply, then are overwritten
  0.5 s after you unpause and every 5 s after that. The vanilla Options sunshafts slider
  and `r__gamma` are overridden the same way while the colour layer is on, and a
  `cfg_load` of any preset that sets those values is reverted within five seconds. Switch
  the layer off first. The driven values are also written into `appdata/user.ltx` at every
  normal exit; switching the mod off in MCM restores the mod's own `[neutral]` block, which
  is *not* GAMMA's stock `user.ltx`. If you want your exact pre-mod look back, keep a copy of
  `user.ltx` and `cfg_load` it.

---

## What a GAMMA launcher Update does, and how to recover

The launcher's **Update** button — even with no definition-version change — overwrites the
profile's `modlist.txt` with GAMMA's stock list and restores the stock `appdata/user.ltx`.
It does not delete anything in `mods/`. The stock list has no entry for Seasons of the
Zone, the snowfall module, Seasonal Soundscape or any season-scoped texture mod — nor, on
the reference install, for SSS 24, Atmospherics 2.69 or the Modded Exes gamedata mod. All
of them drop out of the load order; MO2 then re-discovers the folders and appends them
**disabled**.

The failure is silent in the worst way. The modded exe in `bin/` is not touched, so every
console command still lands and the mod logs every uniform OK — while the SSS shaders that
consume those values are no longer mounted. Nothing looks wrong in the log. The texture
layer half-heals: `season.py` re-inserts and re-enables `TOGGLE_MODS` and the soundscape
on the next launch, never the main mod or the snowfall module — it warns that the main mod
is missing, and `play.bat` now stops and waits for a keypress on any failure rather than
launching regardless.

**Recovery, in order:**

1. Close MO2 completely. It rewrites `modlist.txt` from memory on exit and would revert
   your edit.
2. Restore `profiles/<profile>/modlist.txt` from a snapshot. `season.py` writes one before
   every toggle (`_baseline/modfile-backups/modlist-*-pre-toggle.txt`); a copy you took
   yourself is better. **Do not** recover by re-ticking the re-appended mods where MO2 put
   them: at the top of the file SSS and Atmospherics would then outrank mods that
   deliberately beat them today, and `season.py` never moves those.
3. If you have no snapshot: tick Seasons of the Zone and the snowfall module, re-enable SSS
   / Atmospherics / Modded Exes and drag them back to where they were, confirm every
   `above` name in `seasons_config.py` still exists, and run `season.py status`.
4. Run `play.bat` and read its output.
5. Restore your `user.ltx` if you kept one.

Use `play.bat` for the game, never the launcher's Update, and snapshot `modlist.txt` and
`user.ltx` before any GAMMA update.

---

## Checklist

- [ ] `Seasons of the Zone` is listed and **enabled** in the *selected* profile (the tool
      reads `selected_profile` from `ModOrganizer.ini`; a second profile has its own list).
- [ ] Only one copy of it exists under `mods/`, at `mods/Seasons of the Zone/gamedata/…`
      (the zip's outer and inner folders share the name — copy the inner one).
- [ ] `190- Screen Space Shaders` (the version GAMMA ships) is enabled, and you launch the
      Modded Exes DX11 build.
- [ ] `whowins scripts/level_weathers.script` shows your weather-manager mod or nothing —
      never the snowfall module.
- [ ] The snowfall module is enabled all year and is not in `TOGGLE_MODS`;
      `inverno_textures.db` sits in an always-on mod.
- [ ] `season.py status` reports no `SHADOWED` line.
- [ ] Season Flora is disabled.
- [ ] `play.bat` names the Anomaly shortcut you actually use (`SHORTCUT=` near the top;
      default `Anomaly (DX11-AVX)`; it refuses to launch a name MO2 does not have).
- [ ] A snapshot of `modlist.txt` and `user.ltx` exists before any GAMMA update.
