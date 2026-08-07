# scripts/dev.ps1 — one-command dev environment for Travel Buddy
# Usage:  .\scripts\dev.ps1 backend    (terminal 1)
#         .\scripts\dev.ps1 app        (terminal 2)
#         .\scripts\dev.ps1 check      (verify environment)
#         .\scripts\dev.ps1 tunnel     (re-establish adb reverse after disconnect)
#         .\scripts\dev.ps1 verify     (curl the signals endpoint to check drill results)
param([Parameter(Position=0)][ValidateSet('backend','app','check','tunnel','verify')][string]$Mode = 'check')

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

# --- Android SDK / adb on PATH (the #1 recurring pain) ---
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$platformTools = "$env:ANDROID_HOME\platform-tools"
if ($env:Path -notlike "*$platformTools*") { $env:Path += ";$platformTools" }

# --- Detect this machine's LAN IP (changes between networks!) ---
$LanIp = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
  Select-Object -First 1).IPAddress
$DebugUserId = '11111111-1111-1111-1111-111111111111'

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " Travel Buddy Dev Environment" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "Repo:     $RepoRoot"
Write-Host "LAN IP:   $LanIp"
Write-Host "ADB:      $platformTools"
Write-Host "Debug ID: $DebugUserId"
Write-Host ""

switch ($Mode) {
  'check' {
    Write-Host "--- Environment ---" -ForegroundColor Yellow
    Write-Host "Python:"
    & py -3.12 --version 2>$null || Write-Host "  [MISSING] Python 3.12 not found" -ForegroundColor Red
    Write-Host "Flutter:"
    & flutter --version 2>$null | Select-Object -First 1
    Write-Host ""

    Write-Host "--- adb devices ---" -ForegroundColor Yellow
    & adb devices
    Write-Host ""

    Write-Host "--- flutter devices ---" -ForegroundColor Yellow
    & flutter devices
    Write-Host ""

    Write-Host "--- .env file ---" -ForegroundColor Yellow
    if (Test-Path "$RepoRoot\.env") {
      Write-Host "  .env found" -ForegroundColor Green
      # Show keys present (not values)
      Get-Content "$RepoRoot\.env" | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=') { Write-Host "  $($Matches[1]) = [set]" }
      }
    } else {
      Write-Host "  [MISSING] No .env file at $RepoRoot\.env" -ForegroundColor Red
      Write-Host "  Create it with: TB_DEBUG=true and TB_LITELLM_API_KEY=..." -ForegroundColor Red
    }
    Write-Host ""

    Write-Host "--- backend health ---" -ForegroundColor Yellow
    try {
      $r = Invoke-WebRequest -UseBasicParsing "http://localhost:8000/api/v1/health" -TimeoutSec 3
      Write-Host "  Backend running!" -ForegroundColor Green
      Write-Host "  $($r.Content)"
    } catch {
      Write-Host "  Backend not running" -ForegroundColor Red
      Write-Host "  Start with: .\scripts\dev.ps1 backend"
    }
    Write-Host ""

    Write-Host "--- adb reverse tunnel ---" -ForegroundColor Yellow
    $tunnels = & adb reverse --list 2>$null
    if ($tunnels) { Write-Host "  $tunnels" -ForegroundColor Green }
    else { Write-Host "  No tunnels active. Run: .\scripts\dev.ps1 tunnel" -ForegroundColor Red }
    Write-Host ""

    Write-Host "--- Quick reference ---" -ForegroundColor Yellow
    Write-Host "  Terminal 1:  .\scripts\dev.ps1 backend"
    Write-Host "  Terminal 2:  .\scripts\dev.ps1 app"
    Write-Host "  USB tunnel:  .\scripts\dev.ps1 tunnel"
    Write-Host "  Check drill: .\scripts\dev.ps1 verify"
    Write-Host ""
  }

  'backend' {
    Set-Location $RepoRoot
    # Load .env if present (pydantic-settings reads it too, but belt+suspenders)
    if (Test-Path "$RepoRoot\.env") {
      Get-Content "$RepoRoot\.env" | ForEach-Object {
        if ($_ -match '^([A-Z_]+)=(.*)$') {
          [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], "Process")
        }
      }
      Write-Host "Loaded .env" -ForegroundColor Green
    }
    # Force debug mode, clear JWT secret
    $env:TB_DEBUG = 'true'
    Remove-Item Env:\TB_SUPABASE_JWT_SECRET -ErrorAction SilentlyContinue
    Write-Host ""
    Write-Host "Starting backend on http://0.0.0.0:8000 ..." -ForegroundColor Green
    Write-Host "Auth: debug mode (X-Debug-User-Id header)" -ForegroundColor Green
    Write-Host "Press Ctrl+C to stop" -ForegroundColor DarkGray
    Write-Host ""
    & py -3.12 -m uvicorn main:app --reload --port 8000 --host 0.0.0.0
  }

  'app' {
    Set-Location "$RepoRoot\mobile"

    # Establish adb reverse tunnel (so localhost works on the phone)
    Write-Host "Setting up adb reverse tunnel..." -ForegroundColor Yellow
    & adb reverse tcp:8000 tcp:8000
    Write-Host "Tunnel active: phone localhost:8000 -> laptop localhost:8000" -ForegroundColor Green
    Write-Host ""

    Write-Host "--- Connected devices ---" -ForegroundColor Yellow
    & adb devices
    Write-Host ""

    # Use localhost (via USB tunnel) — much more reliable than LAN IP
    Write-Host "Launching app against http://localhost:8000 (via USB tunnel) ..." -ForegroundColor Green
    Write-Host "Debug user: $DebugUserId" -ForegroundColor Green
    Write-Host ""
    & flutter run `
      --dart-define=TB_API_BASE_URL="http://localhost:8000" `
      --dart-define=TB_DEBUG_USER_ID=$DebugUserId
  }

  'tunnel' {
    Write-Host "Re-establishing adb reverse tunnel..." -ForegroundColor Yellow
    & adb reverse tcp:8000 tcp:8000
    Write-Host "Done! Phone's localhost:8000 now routes to laptop's localhost:8000" -ForegroundColor Green
  }

  'verify' {
    Write-Host "--- Checking signals on backend ---" -ForegroundColor Yellow
    try {
      $r = Invoke-WebRequest -UseBasicParsing `
        "http://localhost:8000/api/v1/signals" `
        -Headers @{"X-Debug-User-Id"=$DebugUserId} `
        -TimeoutSec 5
      $signals = $r.Content | ConvertFrom-Json
      if ($signals.Count -gt 0) {
        Write-Host "  Found $($signals.Count) signal(s):" -ForegroundColor Green
        $signals | ForEach-Object {
          Write-Host "    [$($_.signal_type)] $($_.place_ref) — $($_.captured_at)"
        }
      } else {
        Write-Host "  No signals found yet." -ForegroundColor Yellow
        Write-Host "  (Tap some hearts in the app, then check again)"
      }
    } catch {
      Write-Host "  Failed to reach backend. Is it running?" -ForegroundColor Red
      Write-Host "  Start with: .\scripts\dev.ps1 backend"
    }
  }
}
