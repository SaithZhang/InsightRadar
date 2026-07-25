param(
    [string]$TaskName = "InsightRadar-FactorPipeline",
    [string]$StartTime = "15:40"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $repo "scripts\run-factor-pipeline.ps1"

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Pipeline runner was not found: $runner"
}

$taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$runner`""
& schtasks.exe /Create /F /TN $TaskName /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST $StartTime /TR $taskCommand
if ($LASTEXITCODE -ne 0) {
    throw "Failed to register scheduled task $TaskName"
}

Write-Host "Registered $TaskName for weekdays at $StartTime."
Write-Host "The model still checks completed K-lines; exchange holidays simply add no new observations."
