# Load order

Where each part of Seasons of the Zone sits in MO2, and which parts do not care. Line
numbers below are from the reference install's `profiles/G.A.M.M.A/modlist.txt` and are
examples only.

---

## The short answer

- **Seasons of the Zone itself: anywhere.** It only has to be enabled.
- **The mods in `TOGGLE_MODS`** each sit directly above the mod they must beat. `play.bat`
  puts them there at every launch; `whowins` tells you which mod that is, and
  `season.py status` reports anything higher up that would override them.
- **Seasonal Soundscape** is generated at launch and placed directly above its source mod.
- **INVERNO's snowfall addon: anywhere, once `level_weathers.script` is removed from it.**
- **Never enable** the old Season Flora prototype alongside this mod.
- A GAMMA launcher **Update** drops all of the above from the modlist. Recover from a
  snapshot, not by re-ticking mods where MO2 put them.

---

## How MO2 priority works

MO2 keeps the load order in `profiles/<selected profile>/modlist.txt`. Line 1 is a header;
line 2 is the highest-priority mod and the last line the lowest; `+` is enabled, `-`
disabled. When two enabled mods ship the same file, the higher-priority one (the lower
line number) wins. That is all priority does. It has no effect on a mod that shares no
file with anyone, and it does not order scripts at runtime.

Two things catch people. The MO2 window shows the list upside down relative to the file:
line 2 is the bottom of the window. And a folder dropped into `mods/` by hand is added
disabled, at the top of the file (highest priority), so a newly installed mod is not
enabled until you tick it.

---

## Seasons of the Zone itself

The mod ships 44 files under `gamedata/`. No other mod, enabled or disabled, ships any of
those paths, so there is nothing for it to win or lose at any line.

Script order is not MO2's either. MO2 merges every enabled mod's `gamedata/scripts` into
one directory; the engine lists that directory and calls each script's `on_game_start()`
in filename order (`axr_main.script`, the `file_list_open_ex` loop). That is why the
scripts are named `zzz_*`: they run after `ssfx_*`, `level_weathers`, `ui_mcm` and
`yawm_snowfall`. The name is a convention rather than a requirement: the mod's first apply
runs on `actor_on_first_update`, after every `on_game_start`, and it re-applies after any
MCM change and re-asserts drifted values every 5 seconds. MCM finds the settings page by
the `*mcm.script` filename mask and sorts pages by title.

What does matter:

- It must be **enabled**. `season.py` never enables it; it warns when the mod is missing
  or disabled in the selected profile.
- Keep the file names. `_mcm.script` is MCM's discovery suffix, and the snowfall patch and
  the MCM script both refer to the module name `zzz_seasons_of_the_zone`. With the module
  gone, the snowfall gate lets it snow whenever the weather says so.
- Keep one copy. Two enabled copies resolve file by file to the higher one. To update,
  replace the folder.
- The engine must know all twenty commands. GAMMA's Modded Exes DX11 build does; an older
  or non-modded exe lacks the `ssfx_` ones, and under DX9/DX10 they do not exist. The mod
  gives up on a command the engine does not know and says so in the log.

---

## The season-scoped mods

Each entry in `TOGGLE_MODS` names an `above` anchor. On every run `season.py` inserts the
mod above its anchor if it is missing, moves it up if it sits below, and sets the flag for
the season. An anchor that no longer exists (GAMMA renumbers folders between versions)
skips that entry with a warning.

The anchors on the reference install:

| Mod | Anchor | Why |
|---|---|---|
| INVERNO Winter Textures | `388- Aydins Grass Tweaks SSS Terrain LOD Compatibility` | 14 shared `textures/terrain/*_lod_textures.dds`. INVERNO also carries `settings_screenspace_TERRAIN.h` / `_PUDDLES.h`, so it must beat SSS and Atmospherics too; 388 sits above both. |
| INVERNO Partly Snowy | `INVERNO Winter Textures` | All 52 of its files are also in base INVERNO; it is an overlay. |
| Winter PDA Maps | `INVERNO Partly Snowy` | Above both INVERNO mods: INVERNO ships its own `textures/ui/ui_global_map.dds` and is on in the same seasons. |
| PanceRide Summer / Autumn | `388- Aydins …` | Shares no file with 388. It works because 388 sits above Atmospherics, SSS 24 and the Aydin base pack. |
| Winter Loading Screens | `282- GAMMA Loading Screens` | 132 `textures/intro` files. |
| Winter Footsteps | `472- Dark Signal Amplified Footsteps Extended` | Beats all four footstep mods. |
| Swamp Ground Fog | `Atmospherics 2.69 RC7.2 SSS24` | Shares nothing; the anchor is only for grouping. |

**Choosing an anchor.** Run `python _tools/season.py whowins <gamedata-relative path>` on
a file the mod ships. It lists every mod shipping that file, enabled or not, in priority
order, and the winner. Anchor on the highest enabled shipper. It cannot see inside `.db`
archives, and it needs the full path: `configs/environment/ambients/presets/x.ltx`, not
`x.ltx`.

**The check.** `above` only puts a mod directly above one anchor. A mod higher in the
list that also ships one of the files wins. `season.py status` tests every file of every
season-scoped mod against every mod above it and reports:

- `SHADOWED` — an enabled mod above ships the file. Re-anchor, or disable that mod.
- dormant — disabled mods above share files (on the reference install, Lifestorock's Bleak
  Fall Redux shares 162 files with INVERNO). Fine until one is enabled; run `status`
  afterwards.
- note — two season-scoped mods that are both on in some season overlap. Partly Snowy
  above INVERNO is intended; the check cannot tell intent from mistake.

`play.bat` runs the same check whenever the modlist has changed.

INVERNO shares 239 paths with PanceRide Autumn and 222 with PanceRide Summer. That is fine
while their seasons stay disjoint. INVERNO's `textures/anamflares` also overrides seven
Atmospherics sun textures and Roadside's Lens Flares every winter; delete the folder from
INVERNO unless you want that.

---

## The generated Seasonal Soundscape

`SOUND_SRC` names the ambience mod that wins your `configs/environment/ambients/presets/`
files. At launch the tool writes season-gated copies of that mod's presets into a mod
called `Seasonal Soundscape` and places it directly above the source. Do not move it. If
you disable the source mod, the generated mod is disabled and its files removed at the
next launch.

---

## INVERNO's snowfall addon

Install the standalone "Snowfall (light + Dynamic Fog)" addon and run
`patches/apply_seasonal_snowfall.py` on it. Its position does not matter: nothing else
ships `yawm_snowfall.script`, its snow particle files are identical to the stock Particles
Cinematic VFX copies, and the gate finds Seasons of the Zone by module name. Keep the
addon enabled all year; the gate decides what plays in each season. Do not put it in
`TOGGLE_MODS`.

**The one hazard.** The addon also ships `gamedata/scripts/level_weathers.script`, an older
version of the weather manager. Remove it before enabling the addon (delete it, hide it in
MO2, or run the patcher with `--disable-weathers`). Wherever MO2 puts the addon, that file
beats the base game's copy; above your weather-manager mod it beats that too, and you lose
weather weights, the progression matrix and the MCM starting-weather option with no error
anywhere. On stock GAMMA no mod ships the file, so there is nothing to place the addon
below; removal is the only fix.

Check with `python _tools/season.py whowins scripts/level_weathers.script`. Only your
weather-manager mod, or no mod at all, should appear.

If you own the all-in-one FOMOD (v1.08.4) instead:

- Its "Light Snowfall" / "Heavy Snowfall" options install a cut-down script without the
  seed, leaf and fog particles the seasonal layer uses. The patcher refuses it. Use the
  standalone addon.
- The addon's particle textures are in INVERNO's base-module archive
  `db/addons/inverno_textures.db`. That archive, and the `particles/graupel` and
  `particles/yawm` definitions, must be in a mod that is enabled all year, never in a
  season-toggled INVERNO texture mod.

---

## Things that must not be enabled together

None of these is a file conflict, so no position fixes them.

- **Season Flora**, the earlier prototype (not shipped). It writes five of the same SSS
  values. `season.py` warns when both are enabled.
- **37- Dynamic Tonemap Extended.** Off by default in GAMMA. It sets five of the grade
  values on a timer. The mod detects it at load and leaves those five to it, so the two do
  not fight; the other values still follow the season.
- **A second copy of Seasons of the Zone.**

While a layer is on, SSS's own MCM sliders for fog, wind, flora fixes and wetness, the
vanilla sunshafts slider and `r__gamma` are overridden within five seconds, and a
`cfg_load` of a preset that sets those values is reverted. Switch the layer off first.
The values are also saved into `appdata/user.ltx` on exit; switching the mod off restores
the mod's `[neutral]` values, which are GAMMA's defaults, not necessarily yours. Keep a
copy of `user.ltx` if you want your exact pre-mod look back.

---

## A GAMMA launcher Update

The launcher's **Update** button overwrites the profile's `modlist.txt` with GAMMA's stock
list and restores the stock `appdata/user.ltx`, even when nothing has changed upstream. It
does not delete anything in `mods/`. Seasons of the Zone, the snowfall addon, Seasonal
Soundscape and every season-scoped mod drop out of the load order — on the reference
install so do SSS 24, Atmospherics 2.69 and the Modded Exes gamedata mod — and MO2 re-adds
the folders disabled.

Nothing reports this. The modded exe is untouched, so every console command still lands
and the mod logs every value OK while the SSS shaders that use them are no longer mounted.
`season.py` re-inserts the `TOGGLE_MODS` and the soundscape on the next launch, never the
main mod or the snowfall addon; it warns that the main mod is missing, and `play.bat`
stops for a keypress instead of launching.

**Recovery:**

1. Close MO2. It rewrites `modlist.txt` from memory on exit.
2. Restore `profiles/<profile>/modlist.txt` from a snapshot. `season.py` keeps one from
   before every toggle in `_baseline/modfile-backups/`. Do not recover by re-ticking the
   re-added mods where MO2 put them: at the top of the file, SSS and Atmospherics would
   then outrank mods that are meant to beat them.
3. Without a snapshot: tick Seasons of the Zone and the snowfall addon, re-enable SSS,
   Atmospherics and Modded Exes and drag them back to where they were, check every
   `above` name in `seasons_config.py` still exists, and run `season.py status`.
4. Run `play.bat` and read its output.
5. Restore your `user.ltx` if you kept one.

Snapshot `modlist.txt` and `user.ltx` before any GAMMA update.

---

## Checklist

- [ ] `Seasons of the Zone` is enabled in the selected profile.
- [ ] One copy, at `mods/Seasons of the Zone/gamedata/…`.
- [ ] Screen Space Shaders is enabled and you launch the Modded Exes DX11 build.
- [ ] `whowins scripts/level_weathers.script` shows your weather mod or nothing.
- [ ] The snowfall addon is enabled all year and not in `TOGGLE_MODS`.
- [ ] `season.py status` reports no `SHADOWED` line.
- [ ] Season Flora is disabled.
- [ ] `play.bat`'s `SHORTCUT=` names the Anomaly entry you use.
- [ ] You have a snapshot of `modlist.txt` and `user.ltx`.
