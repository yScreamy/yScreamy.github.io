@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM 0) Self-relaunch in persistent CMD window (so it cannot auto-close)
REM ============================================================
if /I "%~1" NEQ "__INTERNAL__" (
  REM Write a proof file even if window closes instantly
  if not exist "%~dp0logs" mkdir "%~dp0logs" >nul 2>&1
  echo [%date% %time%] bootstrap: launching persistent cmd...>>"%~dp0logs\runner_bootstrap.log"

  start "HL Bot Runner" cmd.exe /k ""%~f0" __INTERNAL__"
  exit /b
)

cd /d "%~dp0"
title HL Bot Runner (PERSISTENT)

REM ============================================================
REM 1) Hard proof that THIS exact file is running
REM ============================================================
if not exist "logs" mkdir "logs" >nul 2>&1
echo [%date% %time%] internal: started ok. path=%~f0>>"logs\runner_bootstrap.log"
echo %~f0>"logs\runner_running_path.txt"

echo.
echo ============================================================
echo   HL Bot Runner (PERSISTENT)
echo   Running: %~f0
echo   Folder : %CD%
echo ============================================================
echo.

REM ============================================================
REM 2) Basic checks (never exit without a PAUSE)
REM ============================================================
where python >nul 2>&1
if errorlevel 1 (
  echo [HIBA] python nincs a PATH-ban.
  echo.
  pause
  goto :END
)

echo [INFO] Python:
python --version
echo.

if exist ".venv\Scripts\activate.bat" (
  call ".venv\Scripts\activate.bat"
  echo [INFO] .venv aktiv.
) else (
  echo [WARN] .venv nem talalhato.
)
echo.

if not exist ".env" (
  echo [HIBA] Nem talalhato .env a projekt gyokerben!
  echo.
  pause
  goto :END
)

REM Defaults
if "%BOT_PORT%"=="" set BOT_PORT=8080
if "%OLLAMA_WARMUP_ON_START%"=="" set OLLAMA_WARMUP_ON_START=1

echo [INFO] UI: http://127.0.0.1:%BOT_PORT%/
echo.

REM ============================================================
REM 3) Logfile timestamp (safe)
REM ============================================================
for /f "usebackq delims=" %%T in (`powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'"`) do set "TS=%%T"
if "%TS%"=="" set "TS=unknown_time"

set "LOGFILE=logs\runner_%TS%.log"
echo [%date% %time%] starting main.py>>"%LOGFILE%"

REM ============================================================
REM 4) Run (no tee first – keep it dead simple and reliable)
REM    If this works, later we can add Tee-Object again.
REM ============================================================
echo [INFO] Starting: python main.py
echo [INFO] Logging to: %LOGFILE%
echo.

python main.py >>"%LOGFILE%" 2>&1
set "exitcode=%ERRORLEVEL%"

echo.
echo [INFO] main.py stopped. exitcode=%exitcode%
echo [INFO] Last 80 log lines:
powershell -NoProfile -Command "if (Test-Path '%LOGFILE%') { Get-Content '%LOGFILE%' -Tail 80 } else { 'n/a' }"
echo.

:MENU
echo Valassz: (R)estart / (O)pen UI / (L)og tail / (S)top
choice /C ROLS /N /T 10 /D R >nul

if errorlevel 4 goto :END
if errorlevel 3 (
  powershell -NoProfile -Command "if (Test-Path '%LOGFILE%') { Get-Content '%LOGFILE%' -Tail 200 } else { 'n/a' }"
  echo.
  goto :MENU
)
if errorlevel 2 (
  start "" "http://127.0.0.1:%BOT_PORT%/"
  goto :MENU
)

goto :RESTART

:RESTART
echo.
echo [INFO] Restarting...
goto :EOF

:END
echo.
echo [END] Runner finished. Press any key...
pause >nul
endlocal
