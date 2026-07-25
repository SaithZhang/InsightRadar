@echo off
setlocal
title InsightRadar - Generate Report
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\insightradar-launcher.ps1" -Mode Generate
if errorlevel 1 (
  echo.
  echo Report generation failed. See the message above.
  pause
)
endlocal
