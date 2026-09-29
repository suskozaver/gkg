@echo off
setlocal enabledelayedexpansion
rem  GKG - start the Connect IQ simulator and load the watch app (fenix 8 AMOLED 47/51 mm).
rem
rem      scripts\sim.bat          load garmin\bin\GKG.prg, building it first if it is missing
rem      scripts\sim.bat build    build it again first
rem
rem  A build is asked of the deploy watcher, which must be running.

set "REPO=%~dp0.."
set "DEVICE=fenix847mm"
set "PRG=%REPO%\garmin\bin\GKG.prg"

set "CFG=%APPDATA%\Garmin\ConnectIQ\current-sdk.cfg"
if not exist "%CFG%" (
  echo No Connect IQ SDK selected - open the SDK Manager and pick one.
  exit /b 1
)
set /p SDK=<"%CFG%"
if "!SDK:~-1!"=="\" set "SDK=!SDK:~0,-1!"
set "BIN=!SDK!\bin"
if not exist "!BIN!\simulator.exe" set "BIN=!SDK!"
if not exist "!BIN!\simulator.exe" (
  echo simulator.exe not found under !SDK!
  exit /b 1
)

if /I "%~1"=="build" if exist "!PRG!" del "!PRG!"
if exist "!PRG!" goto ready

echo Building - the deploy watcher has to be running...
> "%REPO%\.garmin-build-request" echo build
set /a WAITED=0
:wait
timeout /t 3 /nobreak >nul
set /a WAITED+=3
if exist "!PRG!" goto ready
if !WAITED! GEQ 180 (
  echo Gave up after three minutes - look at .garmin-build.log
  exit /b 1
)
goto wait

:ready
tasklist /FI "IMAGENAME eq simulator.exe" 2>nul | find /I "simulator.exe" >nul
if errorlevel 1 (
  echo Starting the simulator...
  start "" "!BIN!\simulator.exe"
  timeout /t 6 /nobreak >nul
)
echo Loading...
call "!BIN!\monkeydo.bat" "!PRG!" %DEVICE%
endlocal
exit /b 0
