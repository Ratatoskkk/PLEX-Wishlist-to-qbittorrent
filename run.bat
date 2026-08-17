@echo off
setlocal
cd /d "%~dp0"

REM ras launcher. Starts the server with a system-tray icon and opens the
REM dashboard. Close it from the tray icon, not by killing the window.

where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo   Python was not found on your PATH.
  echo   Install Python 3.11 or newer from https://www.python.org/downloads/
  echo   and tick "Add python.exe to PATH" during setup.
  echo.
  pause
  exit /b 1
)

if not exist ".env" (
  echo.
  echo   No .env file found.
  echo   Copy .env.example to .env and fill in your Plex, TMDB, tracker and
  echo   qBittorrent details, then run this again.
  echo.
  copy /y ".env.example" ".env" >nul 2>nul && echo   A starter .env has been created for you.
  pause
  exit /b 1
)

python -c "import fastapi, httpx, aiosqlite, pydantic_settings, tomli_w" >nul 2>nul
if errorlevel 1 (
  echo   Installing dependencies, this only happens once...
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt
  if errorlevel 1 (
    echo.
    echo   Dependency installation failed. Run this manually to see why:
    echo       python -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
  )
)

python start.py run --tray --open
if errorlevel 1 pause
endlocal
