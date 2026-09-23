@echo off
REM  Seasons of the Zone: put mods on the calendar without editing seasons_config.py.
REM
REM  Opens a window listing your MO2 mods. Tick the seasons each one belongs to, and
REM  play.bat switches it on in those seasons and off the rest of the year. The window
REM  also finds the mod each one has to sit above, and checks the file before saving.

cd /d "%~dp0"

if not exist "ModOrganizer.ini" (
    echo.
    echo  ** configure.bat has to be in your GAMMA folder, next to ModOrganizer.exe.
    echo     Copy it, play.bat and the _tools folder there, and run it from there.
    echo.
    pause
    exit /b 1
)
if not exist "_tools\configure.py" (
    echo.
    echo  ** _tools\configure.py is missing. Copy the _tools folder from the mod's folder
    echo     into your GAMMA folder, next to configure.bat.
    echo.
    pause
    exit /b 1
)

REM  Prefer the py launcher: the python.org installer puts it on PATH even when
REM  `python` is not, and a bare `python` on a fresh Windows can open the Store.
set "PY=python"
where py >nul 2>&1 && set "PY=py -3"

%PY% "_tools\configure.py" %*
if errorlevel 1 pause
