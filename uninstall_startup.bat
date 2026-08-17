@echo off
setlocal

REM Stops ras from starting when you log in. Does not touch anything else --
REM your database, settings and downloads are untouched.

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\ras.lnk"
REM Conduit.lnk is the pre-rename name; remove either, so an install made
REM before the rename can still be undone with this script.
set "LEGACY=%STARTUP%\Conduit.lnk"

if exist "%LINK%" del "%LINK%"
if exist "%LEGACY%" del "%LEGACY%"

if not exist "%LINK%" if not exist "%LEGACY%" (
  echo.
  echo   ras will no longer start automatically.
  echo.
)

echo   Note: this does not stop ras if it is running right now.
echo   Quit it from the tray icon.
echo.
pause
endlocal
