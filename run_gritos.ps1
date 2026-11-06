<#
  Start GritOS on Windows from a fresh clone.
    .\run_gritos.ps1             # set up (first run) and start backend + frontend
    .\run_gritos.ps1 -LoadData   # also download and load SEC EDGAR data (needs SEC_USER_AGENT)
#>
param([switch]$LoadData)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

$venv = Join-Path $root "backend\.venv"
if (-not (Test-Path $venv)) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Cyan
    python -m venv $venv
}
$py = Join-Path $venv "Scripts\python.exe"
& $py -m pip install -q -r (Join-Path $root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

if ($LoadData) {
    Write-Host "Loading SEC EDGAR data..." -ForegroundColor Cyan
    Push-Location (Join-Path $root "backend")
    & $py -m etl.edgar_ingest --fetch --load
    $code = $LASTEXITCODE
    Pop-Location
    if ($code -ne 0) { throw "EDGAR ETL failed (is SEC_USER_AGENT set? see .env.example)" }
}

if (-not (Test-Path (Join-Path $root "frontend\node_modules"))) {
    Write-Host "Installing frontend packages..." -ForegroundColor Cyan
    npm ci --prefix frontend
    if ($LASTEXITCODE -ne 0) { throw "npm ci failed" }
}

$backendDir = Join-Path $root "backend"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$backendDir'; & '$py' -m uvicorn main:app --port 8000"
Write-Host "Backend  http://localhost:8000  (API docs: /docs)" -ForegroundColor Green
Write-Host "Frontend http://localhost:3000" -ForegroundColor Green
npm run dev --prefix frontend
