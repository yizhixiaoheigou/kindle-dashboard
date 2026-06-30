@echo off
REM ============================================================
REM  Moshui Desktop Dashboard - Windows one-click setup
REM  Double-click this file. It will:
REM    1) detect Python (install from npmmirror only if missing)
REM    2) install dependencies
REM    3) build MoshuiDesktop.exe
REM    4) launch it into the system tray (autostart auto-enabled)
REM  First run may take a few minutes. Do NOT close this window.
REM ============================================================
setlocal
REM strip trailing backslash from %~dp0 (avoids \" escaping the quote)
set "HERE=%~dp0"
if "%HERE:~-1%"=="\" set "HERE=%HERE:~0,-1%"

pushd "%HERE%"
echo.
echo === Moshui Desktop Dashboard : one-click setup starting ===
echo Folder: "%HERE%"
echo Please wait, this can take a few minutes on the first run...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%HERE%\installers\windows\run-on-windows.ps1" -Dest "%HERE%" -Build 1.0 -Launch
echo.
echo === Finished. If you saw red errors above, send them to Claude. ===
popd
endlocal
pause
