@echo off
setlocal
cd /d "%~dp0"

REM Makes ras start automatically when you log in to Windows.
REM
REM It drops a shortcut to start_hidden.vbs in your Startup folder, so ras
REM launches with no console window and only a tray icon. This is per-user and
REM needs no admin rights -- run uninstall_startup.bat to undo it.

set "TARGET=%~dp0start_hidden.vbs"
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "LINK=%STARTUP%\ras.lnk"

REM The shortcut used to be called Conduit.lnk. Remove the old one, or an
REM upgrade leaves two entries both launching the same server on login.
if exist "%STARTUP%\Conduit.lnk" del "%STARTUP%\Conduit.lnk"

if not exist "%TARGET%" (
  echo.
  echo   Could not find start_hidden.vbs next to this script.
  echo.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%LINK%');" ^
  "$s.TargetPath = 'wscript.exe';" ^
  "$s.Arguments = '\"%TARGET%\"';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.Description = 'ras media automation';" ^
  "$s.WindowStyle = 7;" ^
  "$s.Save()"

if errorlevel 1 (
  echo.
  echo   Could not create the startup shortcut.
  echo.
  pause
  exit /b 1
)

echo.
echo   ras will now start automatically when you log in.
echo   Shortcut: %LINK%
echo.
echo   It runs hidden -- look for the tray icon, or open
echo   http://localhost:5050
echo.
echo   Run uninstall_startup.bat to stop it starting automatically.
echo.
pause
endlocal
