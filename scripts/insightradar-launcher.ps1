[CmdletBinding()]
param(
    [ValidateSet("Menu", "Generate", "Import", "OpenLatest")]
    [string]$Mode = "Menu",
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
$reportDirectory = Join-Path $projectRoot "reports"

function Resolve-InsightRadarPython {
    $candidates = [System.Collections.Generic.List[string]]::new()
    $candidates.Add((Join-Path $projectRoot ".venv\Scripts\python.exe"))

    $pythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($null -ne $pythonCommand) {
        $candidates.Add($pythonCommand.Source)
    }
    $candidates.Add("C:\Python313\python.exe")

    foreach ($candidate in ($candidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        & $candidate -c "import stock_assist.cli" 2>$null
        if ($LASTEXITCODE -eq 0) {
            return $candidate
        }
    }

    throw @"
No usable InsightRadar Python environment was found.
Expected .venv\Scripts\python.exe or a Python installation with project dependencies.
See README.md for the one-time environment setup.
"@
}

function Get-LatestAfterCloseReport {
    if (-not (Test-Path -LiteralPath $reportDirectory -PathType Container)) {
        return $null
    }
    return Get-ChildItem -LiteralPath $reportDirectory -Filter "*-after-close.html" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
}

function Open-LatestAfterCloseReport {
    $latestReport = Get-LatestAfterCloseReport
    if ($null -eq $latestReport) {
        throw "No after-close HTML report exists yet. Generate one first."
    }
    Write-Host "Opening $($latestReport.FullName)"
    Start-Process -FilePath $latestReport.FullName
}

function Generate-AfterCloseReport {
    $python = Resolve-InsightRadarPython
    $startedAt = Get-Date
    Write-Host "[1/3] Python: $python"
    Write-Host "[2/3] Generating the after-close report. Provider gaps will be shown in the report."

    $output = & $python -m stock_assist.cli after-close 2>&1
    $exitCode = $LASTEXITCODE
    $output | ForEach-Object { Write-Host $_ }
    if ($exitCode -ne 0) {
        throw "Report generation failed with exit code $exitCode."
    }

    $latestReport = Get-LatestAfterCloseReport
    if ($null -eq $latestReport -or $latestReport.LastWriteTime -lt $startedAt.AddSeconds(-2)) {
        throw "The command completed but did not create a fresh after-close HTML report."
    }

    Write-Host "[3/3] Report ready: $($latestReport.FullName)"
    if (-not $NoOpen) {
        Start-Process -FilePath $latestReport.FullName
    }
}

function Start-PortfolioImporter {
    $url = "http://127.0.0.1:8765/"
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Write-Host "InsightRadar is already running: $url"
            Start-Process -FilePath $url
            return
        }
    } catch {
        # No existing local app is listening; start the owned loopback service below.
    }

    $python = Resolve-InsightRadarPython
    Write-Host "Opening the local portfolio import page..."
    Write-Host "Keep this window open while using the page. Close it to stop the local service."
    & $python -m stock_assist.cli portfolio-import --serve
    if ($LASTEXITCODE -ne 0) {
        throw "Portfolio importer failed with exit code $LASTEXITCODE."
    }
}

function Show-Menu {
    while ($true) {
        Clear-Host
        Write-Host "InsightRadar"
        Write-Host "1. Generate and open after-close report"
        Write-Host "2. Import or update portfolio"
        Write-Host "3. Open latest after-close report"
        Write-Host "0. Exit"
        $selection = Read-Host "Select"
        try {
            switch ($selection) {
                "1" { Generate-AfterCloseReport; Read-Host "Press Enter to return to the menu" | Out-Null }
                "2" { Start-PortfolioImporter; Read-Host "Press Enter to return to the menu" | Out-Null }
                "3" { Open-LatestAfterCloseReport }
                "0" { return }
                default { Write-Host "Unknown option."; Start-Sleep -Seconds 1 }
            }
        } catch {
            Write-Host ""
            Write-Host "InsightRadar could not complete the action:" -ForegroundColor Red
            Write-Host $_.Exception.Message -ForegroundColor Red
            Read-Host "Press Enter to return to the menu" | Out-Null
        }
    }
}

Push-Location $projectRoot
try {
    switch ($Mode) {
        "Generate" { Generate-AfterCloseReport }
        "Import" { Start-PortfolioImporter }
        "OpenLatest" { Open-LatestAfterCloseReport }
        "Menu" { Show-Menu }
    }
} catch {
    Write-Host ""
    Write-Host "InsightRadar could not complete the action:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    Pop-Location
}
