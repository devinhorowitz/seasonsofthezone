@echo off
REM  Seasons of the Zone: set up seasonal mods without editing seasons_config.py.
REM
REM  Opens a window listing your MO2 mods. Check the seasons each one belongs to, and
REM  play.bat enables it in those seasons and disables it the rest of the year. The
REM  window also finds the mod each one wins over, and checks the file before saving.
REM
REM  Opened from the mod's folder, where MO2 installs the zip, it first puts the tools
REM  in the GAMMA folder, or updates them there, and carries on from that copy.

cd /d "%~dp0"

REM  Prefer the py launcher: the python.org installer puts it on PATH even when
REM  `python` is not, and a bare `python` on a fresh Windows can open the Store.
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"
%PY% --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo  ** configure.bat needs Python 3, and this PC doesn't have it. Get it from
    echo     python.org, check "Add python.exe to PATH" as it installs, then run
    echo     configure.bat again.
    echo.
    pause
    exit /b 1
)

if exist "ModOrganizer.ini" goto gamma
REM  The mod's folder sits two levels below the GAMMA folder, in its mods folder.
if exist "..\..\ModOrganizer.ini" goto install

echo.
echo  ** configure.bat has to be in your GAMMA folder, next to ModOrganizer.exe.
echo     Copy configure.bat, play.bat and the _tools folder there, then run
echo     configure.bat from that folder.
echo.
pause
exit /b 1

:install
if not exist "_tools\configure.py" (
    echo.
    echo  ** The _tools folder is missing from this folder. In MO2, reinstall Seasons of the
    echo     Zone from its zip, then run configure.bat here again.
    echo.
    pause
    exit /b 1
)
%PY% "_tools\configure.py" install %*
if errorlevel 1 (
    pause
    exit /b 1
)
exit /b 0

:gamma
if not exist "_tools\configure.py" (
    echo.
    echo  ** _tools\configure.py is missing. In MO2, right-click Seasons of the Zone and
    echo     choose Open in Explorer; copy _tools from there into your GAMMA folder,
    echo     next to configure.bat.
    echo.
    pause
    exit /b 1
)

%PY% "_tools\configure.py" %*
if errorlevel 1 pause
