# Installing Seasons of the Zone with Claude Code

For an AI coding agent (Claude Code or similar) that a player has asked to install, set up,
update or remove Seasons of the Zone in their S.T.A.L.K.E.R. GAMMA. Player: open Claude Code in
your GAMMA folder (where `ModOrganizer.exe` is) and paste:

> Install Seasons of the Zone by following https://raw.githubusercontent.com/devinhorowitz/seasonsofthezone/main/docs/INSTALL-WITH-CLAUDE.md

Agent: follow these steps in order. Say what you are about to do before each change, and stop
and ask whenever something doesn't match what this guide describes. The same install for a
person, a window at a time, is [INSTALL-GUIDE.md](INSTALL-GUIDE.md).

## Rules

- Change only the mod's folder under `mods\`, one line of the active profile's `modlist.txt`,
  and what the mod's own tools write: `play.bat`, `configure.bat` and `_tools\` in the GAMMA
  folder, and the setup kept there. Leave every other mod and file alone.
- Change the setup only through `configure.py` commands, never by editing
  `_tools\seasons_config.py`: each command checks the setup the way `play.bat` will before
  saving it. An update keeps the player's setup; never replace it.
- Never delete. Move anything you replace into a backup folder (below) and say where it went.
- Never press, start or suggest the GAMMA launcher's **Update** button; it can reset the
  player's mod list.
- MO2 and the game must be closed before you touch `modlist.txt` or run the tools: MO2 writes
  `modlist.txt` when it exits and would silently undo your edit.
- Don't install Python, and don't start the game, unless the player asks.

## 1. Check the folder, what's running, and what's there

1. The working folder must hold `ModOrganizer.exe`, `ModOrganizer.ini`, `mods\` and
   `profiles\`. If not, ask the player where their GAMMA folder is.
2. Run `tasklist`. If `ModOrganizer.exe` or any `Anomaly*.exe` is listed, ask the player to
   close MO2 and the game, then check again.
3. In `ModOrganizer.ini`, `selected_profile=@ByteArray(<name>)` is the active profile (GAMMA's
   is `G.A.M.M.A`); its mod list is `profiles\<name>\modlist.txt`. `gamePath=@ByteArray(...)`
   is the Anomaly folder (backslashes are doubled there).
4. Run `py -3 --version`, or `python --version` if there is no `py` (`play.bat` tries them in
   that order). Without Python 3, ask the player to install it from
   https://www.python.org/downloads/ with **Add python.exe to PATH** checked. The mod works in
   game without it, but `play.bat` and the setup need it. Below, `py -3` stands for whichever
   worked.
5. MCM, Screen Space Shaders and the Modded Exes come with GAMMA. **Mod App Creator** gives the
   Seasons app its PDA tile; it is present if an enabled mod (`+` in `modlist.txt`) has
   `gamedata\scripts\mac_mcm.script`. Without it, the app opens on a key the player sets on
   MCM's Main page. MAC is at https://www.moddb.com/mods/stalker-anomaly/addons/mod-app-creator-mac
   (the player downloads it; don't, unless they ask).

## 2. Is it installed already?

It is installed if a folder under `mods\` has `gamedata\scripts\zzz_seasons_of_the_zone.script`;
its version is the `VERSION = "x.y.z"` line in `gamedata\scripts\sotz_pda.script` there. Below,
`<folder>` is that folder's name, or `Seasons of the Zone` for a new install.

- Installed and current: say so, and offer the setup (step 7).
- Installed and older: this is an update. `play.bat` and `_tools\seasons_config.py` in the
  GAMMA folder mean the player has a setup; step 6 keeps it.

## 3. Download and check the release

1. Read `https://api.github.com/repos/devinhorowitz/seasonsofthezone/releases/latest`. Take the
   asset named `SeasonsOfTheZone.zip`: its `browser_download_url` and its `digest`
   (`sha256:...`).
2. Download it into a new folder outside `mods\`, such as `downloads\seasons-<version>\`.
3. Compute its SHA-256 (`certutil -hashfile <zip> SHA256`, or Python's hashlib). It must equal
   the digest. If it doesn't, tell the player and stop.
4. List the zip. It holds one folder, `Seasons of the Zone`, with `gamedata\`, `_tools\`,
   `docs\`, `patches\`, `play.bat`, `configure.bat`, `README.md`, `CHANGELOG.md` and `LICENSE`.
   Anything else: stop and ask.

## 4. Install

1. For an update, move `mods\<folder>` to `mods_backup\<folder>-<old version>-<date>` in the
   GAMMA folder.
2. Extract what is inside the zip's `Seasons of the Zone` folder to `mods\<folder>`, so that
   `mods\<folder>\gamedata\` and `mods\<folder>\_tools\configure.py` exist. The folder must sit
   directly in `mods\`: the tools find the GAMMA folder two levels up.
3. Write `mods\<folder>\meta.ini` so MO2 shows the version (CRLF line endings):

   ```
   [General]
   gameName=stalkeranomaly
   modid=0
   version=<version>
   installationFile=SeasonsOfTheZone.zip
   ```

## 5. Enable it in MO2's mod list

1. Copy `modlist.txt` to `modlist.txt.before-seasons-<date>` beside it.
2. If a line reads `+<folder>` or `-<folder>`, make it `+` and change nothing else.
3. Otherwise insert `+<folder>` as the first line after the `# This file was automatically
   generated by Mod Organizer.` comment. The mod shares no file with any other, so its place
   doesn't matter, and this is where MO2 puts a new mod.
4. Keep the file's CRLF line endings and every other line byte for byte. Read it back and
   confirm that the only difference is the one line.

## 6. Put the tools in the GAMMA folder

1. From the GAMMA folder, run `py -3 "mods\<folder>\_tools\configure.py" install --yes`. It
   copies `play.bat`, `configure.bat` and `_tools\` into the GAMMA folder, or on an update
   replaces only the files that changed. It keeps the player's setup, their saved presets and
   the MO2 entry `play.bat` starts. If it says the GAMMA folder's tools are newer, stop and
   ask. Afterwards, check that `play.bat` and `_tools\season.py` are there.
2. `play.bat` starts the MO2 entry named on its line `set "SHORTCUT=..."` (normally
   `Anomaly (DX11-AVX)`). It must match, exactly, one of the `N\title=` values under
   `[customExecutables]` in `ModOrganizer.ini`. If none matches, ask the player which entry
   they play with and set it on that one line, keeping the file's line endings. In
   `configure.bat`, the same choice is beside **play.bat starts**.

## 7. The setup (ask the player what they want)

All of it is optional: with no setup, the light and weather, the marked days, the PDA app and
MCM already follow the calendar. Run the commands from the GAMMA folder;
`py -3 _tools\configure.py --help` lists them all, and `configure.bat` is the same setup in a
window if the player prefers that.

- **Where the real weather comes from** (Chornobyl unless set):
  `py -3 _tools\configure.py place "<city>"`.
- **Mods that switch with the season**, such as winter textures or seasonal grass the player
  already has in MO2. Ask which, and in which seasons; `py -3 _tools\configure.py name` shows
  the season names (normally spring, summer, autumn, winter, "deep winter" and "late
  winter"). For each, named as in MO2's list:
  `py -3 _tools\configure.py add "<mod>" --when <seasons>`. It picks the mod it has to win over
  from the files they share; if it can't, show the player what it said. Switching is safe for
  mods that change how the Zone looks or sounds. A mod that adds locations, quests or items
  leaves them in saves, which lose them, or don't load, while it is off: tell the player
  before adding one. When `add` says a mod's files put things into saves, `play.bat` leaves
  it as it is; show the player the files it names, and add `"save_content": True` to its
  entry only if they ask. A full INVERNO 1.09 install is such a mod: only its textures go
  seasonal (the README's *Optional: seasonal snowfall* says how). The README's *Mods that
  work well this way* lists packs and their seasons.
- **Seasonal ambient sound:** `py -3 _tools\configure.py sound` shows which mod the soundscape
  comes from, and `sound "<mod>"` sets one. Set it only if the player wants it.
- **No rain in the winters**, for a player with a snowfall layer (the README's *Optional:
  seasonal snowfall*): `py -3 _tools\configure.py rain` shows the weathers that rain, and
  `rain --build` makes a mod of them without their rain, on in winter and deep winter. MO2
  has to be closed. Build it only if the player wants it.
- **Presets:** `py -3 _tools\configure.py preset` lists them; `GAMMA example` is the setup the
  tools were made on, and leaves out the mods the player doesn't have.
  `py -3 _tools\configure.py preset load "<name>"` loads one. If it says it would replace part
  of the player's setup, show them what it said; add `--force` only if they agree (the old
  setup is kept as `seasons_config.py.bak`).

Then run `py -3 _tools\season.py status` and show the player what the next launch will switch.
A `!` line about particle effects means a script that stays on makes particles that only a mod
switched off has, and `play.bat` will stop before that launch: show the player the line, and
copy the `gamedata\particles` it names only if they agree. A `-` line about textures the game
won't find means those particles will draw as squares, though the launch goes ahead: show it
too, and copy the file it names only if they agree.

## 8. First launch

Tell the player: from now on, close MO2 and start the game with `play.bat` in the GAMMA folder.
It stages the season, then starts MO2's entry itself. Starting from MO2 still works, but only
`play.bat` moves the seasonal mods with the date. Ask them to load a save, open the Seasons app
(its PDA tile, or the key from MCM's Main page), then quit and tell you. Then read
`<gamePath>\appdata\logs\xray_<Windows user name>.log` and report:

- lines containing `STACK TRACEBACK` or `FATAL` (search without case);
- `[seasons] <season> applied (<n> uniforms)`, which means the mod ran. The lines after it
  name a setting each and end in `OK`, or `WANT <value>` where the game didn't take it;
- lines starting `[seasons] !`, the mod's warnings.

No traceback, an `applied` line and no warnings mean it is working.

## Updating, removing

- **Update:** steps 1 to 6. The old copy goes to `mods_backup`, and step 6 keeps the player's
  setup. If a mod folder has `gamedata\scripts\yawm_snowfall.script.orig`, the player applied
  the seasonal snowfall patch: offer to rerun
  `py -3 "mods\<folder>\patches\apply_seasonal_snowfall.py"`, which brings it up to date.
- **Remove:** the player first switches the mod off on its MCM page (this puts the color grade
  back to neutral). Then, with MO2 closed, change `+<folder>` to `-<folder>`, and the player
  starts the game from MO2 again. Seasonal mods stay as `play.bat` last left them; the player
  enables or disables them in MO2. If the snowfall patch was applied, offer to run the same
  command with `--revert`.

## If something's wrong

- **`play.bat` says MO2 has no shortcut by that name:** step 6.2.
- **`play.bat` stops with an error:** the lines above it say why, and
  [CONFIGURING.md](CONFIGURING.md#troubleshooting) covers the common ones.
- **Errors or warnings in the log:** show the player the lines, then open an issue at
  https://github.com/devinhorowitz/seasonsofthezone/issues with the log attached.
