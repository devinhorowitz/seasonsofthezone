@echo off
REM  Seasons of the Zone launcher: stage today's season, then start the game.
REM
REM  The seasonal atmosphere follows the calendar on its own. Textures can't change
REM  while the game runs, so the seasonal mods and texture sets are switched here,
REM  before launch. season.py does nothing on a day when nothing has changed.
REM
REM  Use this instead of ModOrganizer.exe.

cd /d "%~dp0"

REM  play.bat runs from the GAMMA folder: MO2's settings and the tools sit beside it.
if exist "ModOrganizer.ini" goto gamma
REM  The copy in the mod's folder, two levels below the GAMMA folder: configure.bat
REM  beside it installs this file and the tools there.
if exist "..\..\ModOrganizer.ini" goto modfolder

echo.
echo  ** play.bat has to be in your GAMMA folder, next to ModOrganizer.exe.
echo     Copy play.bat, configure.bat and the _tools folder there, then run
echo     play.bat from that folder.
echo.
pause
exit /b 1

:modfolder
for %%G in ("%~dp0..\..") do set "GAMMA=%%~fG"
echo.
echo  ** This is the copy of play.bat in the mod's folder, where MO2 installed it. Run
echo     configure.bat from this folder once: it installs play.bat and the tools into
echo     your GAMMA folder, "%GAMMA%". Then start the game with the play.bat there.
echo.
pause
exit /b 1

:gamma
if not exist "_tools\season.py" (
    echo.
    echo  ** The _tools folder is missing. In MO2, right-click Seasons of the Zone and
    echo     choose Open in Explorer; copy _tools from there into your GAMMA folder,
    echo     next to play.bat.
    echo.
    pause
    exit /b 1
)

REM  The entry to launch, by its name in MO2's executable dropdown, not the .exe file.
REM  GAMMA ships Anomaly (DX11-AVX), (DX11), (DX10-AVX), (DX10) and (DX9-AVX). A custom
REM  exe copied over the stock one in bin\ needs no change here; one added to MO2 as
REM  its own entry does.
set "SHORTCUT=Anomaly (DX11-AVX)"

findstr /C:"title=%SHORTCUT%" ModOrganizer.ini >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ** MO2 has no shortcut named "%SHORTCUT%".
    echo     Open play.bat in Notepad and set SHORTCUT to one of these names, the part
    echo     after title=, exactly:
    findstr /R "title=" ModOrganizer.ini
    echo.
    pause
    exit /b 1
)

REM  Prefer the py launcher: the python.org installer puts it on PATH even when
REM  `python` is not, and a bare `python` on a fresh Windows can open the Store.
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"

REM  The lines shown on every launch come from season.py, in the player's language: a
REM  batch file can't read a translation. The English after || is for when Python can't.
echo.
%PY% "_tools\season.py" say checking 2>nul || echo  Checking the season...
REM  The real weather, for the forecast page and the freezing, thaw and heat days. This
REM  asks Open-Meteo (open-meteo.com, CC BY 4.0) about the place set in configure.bat,
REM  Chornobyl by default: its coordinates, no account, no key, and nothing
REM  about this machine. It is allowed to fail: without it the game models the
REM  temperature from the place's climate instead, so the error is never fatal.
%PY% "_tools\fetch_weather.py"

%PY% "_tools\season.py" apply
if errorlevel 1 (
    echo.
    %PY% "_tools\season.py" say stopped 2>nul || (
        echo  season.py stopped with an error - read the lines above. Seasonal mods and
        echo  textures stay as they were after the last launch; light and weather still
        echo  follow the season. Press a key to start the game anyway, or close this
        echo  window to fix it first.
    )
    echo.
    pause
)

echo.
%PY% "_tools\season.py" say starting 2>nul || echo  Starting Anomaly...
start "" "%~dp0ModOrganizer.exe" "moshortcut://:%SHORTCUT%"
