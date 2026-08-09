<#
.SYNOPSIS
    Start the Travel Buddy backend (PowerShell 5.1 compatible).
.DESCRIPTION
    Pulls latest, validates environment, starts uvicorn on 0.0.0.0:8000,
    polls /health, and reports the resolved database backend.
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Write-Host "`n========== Travel Buddy: Backend Start ==========" -ForegroundColor Cyan

# ─── 1. Git pull ──────────────────────────────────────────────────────────────
Write-Host "`n[1/6] git pull origin main..." -ForegroundColor Yellow
git pull origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "FATAL: git pull failed (exit $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}

# ─── 2. Assert .env exists ────────────────────────────────────────────────────
Write-Host "[2/6] Checking .env..." -ForegroundColor Yellow
$envPath = Join-Path $PSScriptRoot '..\.env'
if (-not (Test-Path $envPath)) {
    Write-Host @"

FATAL: .env not found.
Copy .env.example to .env and fill in:
  TB_SUPABASE_URL
  TB_SUPABASE_KEY  (service_role, NOT anon)
  TB_LITELLM_API_KEY
  TB_SUPABASE_JWT_SECRET
"@ -ForegroundColor Red
    exit 1
}

# ─── 3. Assert required keys are present and non-placeholder ──────────────────
Write-Host "[3/6] Validating .env keys..." -ForegroundColor Yellow
$requiredKeys = @('TB_SUPABASE_URL', 'TB_SUPABASE_KEY', 'TB_LITELLM_API_KEY', 'TB_SUPABASE_JWT_SECRET')
$envContent = Get-Content $envPath -Raw
$missing = @()
foreach ($key in $requiredKeys) {
    $pattern = "(?m)^$key=(.+)$"
    if ($envContent -match $pattern) {
        $val = $Matches[1].Trim()
        if ($val -eq '' -or $val -like 'YOUR_*' -or $val -like 'your_*') {
            $missing += $key
        }
    } else {
        $missing += $key
    }
}
if ($missing.Count -gt 0) {
    Write-Host "FATAL: These .env keys are missing or placeholder:" -ForegroundColor Red
    foreach ($k in $missing) { Write-Host "  - $k" -ForegroundColor Red }
    exit 1
}
Write-Host "  All 4 keys present and non-placeholder." -ForegroundColor Green

# ─── 4. Assert Python deps importable ─────────────────────────────────────────
Write-Host "[4/6] Checking Python dependencies..." -ForegroundColor Yellow
$checkImport = python -c "import supabase, pytest_asyncio" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Missing packages. Installing..." -ForegroundColor Yellow
    $rootDir = Join-Path $PSScriptRoot '..'
    pip install -r (Join-Path $rootDir 'requirements.txt') -q
    pip install -r (Join-Path $rootDir 'requirements-dev.txt') -q
    python -c "import supabase, pytest_asyncio" 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "FATAL: pip install succeeded but imports still fail." -ForegroundColor Red
        exit 1
    }
}
Write-Host "  Dependencies OK." -ForegroundColor Green

# ─── 5. Detect and display LAN IP ─────────────────────────────────────────────
Write-Host "[5/6] Detecting LAN IP..." -ForegroundColor Yellow
$lanIp = $null
$adapters = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi*' -ErrorAction SilentlyContinue
if ($adapters) {
    $lanIp = ($adapters | Where-Object { $_.IPAddress -notlike '169.*' } | Select-Object -First 1).IPAddress
}
if (-not $lanIp) {
    # Fallback: parse ipconfig for any 192.168.x.x
    $ipcfg = ipconfig | Select-String 'IPv4.*: (192\.168\.[\d]+\.[\d]+)'
    if ($ipcfg) {
        $lanIp = $ipcfg.Matches[0].Groups[1].Value
    }
}
if ($lanIp) {
    Write-Host "`n  ┌──────────────────────────────────────────┐" -ForegroundColor Cyan
    Write-Host "  │  LAN IP:  $lanIp              │" -ForegroundColor Cyan
    Write-Host "  │  Phone URL: http://${lanIp}:8000       │" -ForegroundColor Cyan
    Write-Host "  └──────────────────────────────────────────┘`n" -ForegroundColor Cyan
} else {
    Write-Host "  WARNING: Could not detect LAN IP. Check ipconfig manually." -ForegroundColor Yellow
}

# ─── 6. Start uvicorn ─────────────────────────────────────────────────────────
Write-Host "[6/6] Starting uvicorn (0.0.0.0:8000)..." -ForegroundColor Yellow
Write-Host "  Ctrl+C to stop.`n" -ForegroundColor DarkGray

Set-Location (Join-Path $PSScriptRoot '..')
uvicorn main:app --reload --host 0.0.0.0 --port 8000
