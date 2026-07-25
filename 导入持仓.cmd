@echo off
setlocal
title InsightRadar - Import Portfolio
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\insightradar-launcher.ps1" -Mode Import
if errorlevel 1 (
  echo.
  echo Portfolio import failed. See the message above.
  pause
)
endlocal
