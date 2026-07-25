@echo off
setlocal
title InsightRadar - Open Latest Report
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\insightradar-launcher.ps1" -Mode OpenLatest
if errorlevel 1 (
  echo.
  echo No report could be opened. See the message above.
  pause
)
endlocal
