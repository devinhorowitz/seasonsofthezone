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

REM  The entry by its whole name: a line of ModOrganizer.ini like 2\title=Anomaly (DX11),
REM  which "Anomaly (DX11) custom" doesn't match.
set "FOUND="
for /f "usebackq tokens=1,* delims==" %%A in ("ModOrganizer.ini") do if "%%B"=="%SHORTCUT%" for /f "tokens=2 delims=\" %%K in ("%%A") do if /i "%%K"=="title" set "FOUND=1"
if not defined FOUND (
    echo.
    echo  ** MO2 has no shortcut named "%SHORTCUT%". Pick the one you play with in
    echo     configure.bat, beside "play.bat starts", or open play.bat in Notepad and set
    echo     SHORTCUT to one of these names, the part after title=, exactly:
    findstr /R "title=" ModOrganizer.ini
    echo.
    pause
    exit /b 1
)

REM  Prefer the py launcher: the python.org installer puts it on PATH even when
REM  `python` is not, and a bare `python` on a fresh Windows can open the Store.
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ** The tools that stage the season need Python 3, and this PC doesn't have it.
    echo     Get it from python.org, and check "Add python.exe to PATH" as it installs.
    echo     Press a key to start the game anyway, on what was staged last.
    echo.
    pause
    start "" "%~dp0ModOrganizer.exe" "moshortcut://:%SHORTCUT%"
    exit /b 0
)

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

REM  From here on one block, which cmd reads whole before it runs any of it: the setup can
REM  rewrite this file while the window waits at the pause. An exit below zero is a crash.
set "FAILED="
(
    %PY% "_tools\season.py" apply
    if errorlevel 1 set "FAILED=1"
    if not errorlevel 0 set "FAILED=1"
    if defined FAILED (
        echo.
        %PY% "_tools\season.py" say stopped 2>nul || (
            echo  season.py stopped with an error - the lines above say why, and what it did
            echo  before it stopped. Light and weather still follow the season. Press a key to
            echo  start the game anyway, or close this window to fix it first.
        )
        echo.
        pause
    )
    echo.
    %PY% "_tools\season.py" say starting 2>nul || echo  Starting Anomaly...
    start "" "%~dp0ModOrganizer.exe" "moshortcut://:%SHORTCUT%"
    exit /b 0
)
