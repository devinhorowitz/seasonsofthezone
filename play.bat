@echo off
REM ---------------------------------------------------------------------------
REM  Start GAMMA with the seasonal textures already correct for today's date.
REM
REM  WHY THIS EXISTS
REM    Everything the Seasons of the Zone mod drives at runtime - light, colour,
REM    foliage, fog, wind, wetness, snowfall, ambience - follows the calendar by
REM    itself, inside the game, with no help.
REM
REM    Terrain and grass TEXTURES cannot. X-Ray binds them from MO2's virtual
REM    file system at launch and freezes them for the session; there is no
REM    runtime rebind. So the texture layer has to be decided BEFORE the game
REM    starts. This runs that step, then launches, so you never have to.
REM
REM    season.py is a no-op when the staged season already matches the date, so
REM    running it every launch costs nothing. It only does real work about five
REM    times a year, when a season actually turns.
REM
REM  USE THIS INSTEAD OF ModOrganizer.exe.
REM ---------------------------------------------------------------------------

cd /d "%~dp0"

REM  Which MO2 executable to launch. GAMMA ships these four:
REM      Anomaly (DX11-AVX)      Anomaly (DX11)
REM      Anomaly (DX10-AVX)      Anomaly Launcher
REM  DX11-AVX is GAMMA's default. If your CPU has no AVX, or MO2 lists the entry
REM  under another name, change this one line - a wrong name opens MO2 and starts
REM  nothing, silently, because `start` cannot report a bad moshortcut.
set "SHORTCUT=Anomaly (DX11-AVX)"

echo.
echo  Checking the season...
python "_tools\season.py" apply
if errorlevel 1 (
    echo.
    echo  season.py failed - launching anyway with whatever is currently staged.
    echo  The textures will be whatever was staged last; the in-game layer is unaffected.
    echo.
    REM  No pause: a launcher must never block waiting for a keypress.
    timeout /t 4 >nul
)

echo.
echo  Starting Anomaly...
start "" "%~dp0ModOrganizer.exe" "moshortcut://:%SHORTCUT%"
