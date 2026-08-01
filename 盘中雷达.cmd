@echo off
setlocal
title InsightRadar - Intraday Radar
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\insightradar-launcher.ps1" -Mode Intraday
if errorlevel 1 (
  echo.
  echo Intraday radar could not start. See the message above.
  pause
)
endlocal
