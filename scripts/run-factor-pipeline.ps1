param(
    [string]$Config = "configs/factor_pipeline.json"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
$logDir = Join-Path $repo "data\factor_pipeline"
$logPath = Join-Path $logDir "scheduled-run.log"

if (-not (Test-Path -LiteralPath $python)) {
    throw "InsightRadar virtual environment was not found: $python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null
Push-Location $repo
try {
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "[$timestamp] factor-pipeline start" | Add-Content -LiteralPath $logPath -Encoding UTF8
    $output = & $python -m stock_assist.cli factor-pipeline --config $Config 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object {
        Write-Host $_
        $_ | Add-Content -LiteralPath $logPath -Encoding UTF8
    }
    if ($exitCode -ne 0) {
        throw "factor-pipeline exited with code $exitCode"
    }
} finally {
    Pop-Location
}
