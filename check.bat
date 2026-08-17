@echo off
setlocal
cd /d "%~dp0"

REM Validates your configuration and probes Plex, TMDB, every tracker and
REM qBittorrent. Run this first if something is not working.

python start.py check
echo.
pause
endlocal
