@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title HL Bot Runner (DEBUG)

echo.
echo ============================================================
echo   HL Bot Runner (DEBUG)
echo   Folder: %CD%
echo ============================================================
echo.

REM --- show environment basics
echo [INFO] whoami:
whoami
echo.

echo [INFO] python location:
where python
echo.

echo [INFO] python version:
python --version
echo.

REM --- venv activate
if exist ".venv\Scripts\activate.bat" (
  echo [INFO] Activating .venv...
  call ".venv\Scripts\activate.bat"
) else (
  echo [WARN] .venv not found.
)
echo.

REM --- .env check
if not exist ".env" (
  echo [HIBA] Nem található .env a projekt gyökerében!
  echo.
  pause
  exit /b 1
)

REM --- basic file check
if not exist "main.py" (
  echo [HIBA] main.py nem található ebben a mappában!
  echo.
  dir
  echo.
  pause
  exit /b 1
)

REM --- run without any fancy piping first
echo [INFO] Starting: python main.py
echo [INFO] (If it crashes, the error will be shown below)
echo.

python main.py

echo.
echo [INFO] python main.py finished. ERRORLEVEL=%ERRORLEVEL%
echo.
pause
endlocal
