@echo off
REM  Seasons of the Zone launcher: stage today's season, then start the game.
REM
REM  The in-engine layers follow the calendar on their own. Textures cannot change
REM  while the game runs, so the texture layer is decided here, before launch.
REM  season.py does nothing on a day when nothing has changed.
REM
REM  Use this instead of ModOrganizer.exe.

cd /d "%~dp0"

REM  play.bat runs from the GAMMA folder: MO2's settings and the tools sit beside it.
if not exist "ModOrganizer.ini" (
    echo.
    echo  ** play.bat has to be in your GAMMA folder, next to ModOrganizer.exe.
    echo     Copy play.bat and the _tools folder there, and run it from there.
    echo.
    pause
    exit /b 1
)
if not exist "_tools\season.py" (
    echo.
    echo  ** The _tools folder is missing. Copy it from the mod's folder into your GAMMA
    echo     folder, next to play.bat.
    echo.
    pause
    exit /b 1
)

REM  The MO2 shortcut to launch. GAMMA ships: Anomaly (DX11-AVX), Anomaly (DX11),
REM  Anomaly (DX10-AVX), Anomaly Launcher. Change this line if you use another.
set "SHORTCUT=Anomaly (DX11-AVX)"

findstr /C:"title=%SHORTCUT%" ModOrganizer.ini >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ** MO2 has no shortcut named "%SHORTCUT%".
    echo     Open play.bat and set SHORTCUT to one of these, exactly:
    findstr /R "title=" ModOrganizer.ini
    echo.
    pause
    exit /b 1
)

REM  Prefer the py launcher: the python.org installer puts it on PATH even when
REM  `python` is not, and a bare `python` on a fresh Windows can open the Store.
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"

echo.
echo  Checking the season...
REM  The real Zone's weather, for the forecast page and the "freezing" period. This
REM  talks to open-meteo for Chornobyl's coordinates - no account, no key, and nothing
REM  about this machine. It is allowed to fail: without it the game models the
REM  temperature from regional normals instead, so the error is never fatal.
%PY% "_tools\fetch_weather.py"

%PY% "_tools\season.py" apply
if errorlevel 1 (
    echo.
    echo  season.py failed - read the lines above. The textures will be whatever was
    echo  staged last; the in-game layer is unaffected. Press a key to launch anyway.
    echo.
    pause
)

echo.
echo  Starting Anomaly...
start "" "%~dp0ModOrganizer.exe" "moshortcut://:%SHORTCUT%"
