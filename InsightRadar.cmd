@echo off
setlocal
title InsightRadar
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\insightradar-launcher.ps1" -Mode Import
if errorlevel 1 (
  echo.
  echo InsightRadar stopped because of an error.
  pause
)
endlocal
