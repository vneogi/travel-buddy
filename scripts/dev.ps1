# scripts/dev.ps1 -- one-command dev environment for Travel Buddy
# Usage:  .\scripts\dev.ps1 backend    (terminal 1)
#         .\scripts\dev.ps1 app        (terminal 2 -- USB tunnel, always works)
#         .\scripts\dev.ps1 app-lan    (terminal 2 -- LAN mode for real offline drill)
#         .\scripts\dev.ps1 check      (verify environment)
#         .\scripts\dev.ps1 tunnel     (re-establish adb reverse after disconnect)
#         .\scripts\dev.ps1 verify     (check backend health + recent errors)
param([Parameter(Position=0)][ValidateSet('backend','app','app-lan','check','tunnel','verify')][string]$Mode = 'check')

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent $PSScriptRoot

# --- Android SDK / adb on PATH (the #1 recurring pain) ---
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
$env:ANDROID_SDK_ROOT = $env:ANDROID_HOME
$platformTools = "$env:ANDROID_HOME\platform-tools"
if ($env:Path -notlike "*$platformTools*") { $env:Path += ";$platformTools" }

# --- Detect this machine's LAN IP (changes between networks!) ---
# Filters out loopback, APIPA, and Hyper-V/WSL adapters
$LanIp = (Get-NetIPAddress -AddressFamily IPv4 |
  Where-Object {
    $_.IPAddress -notlike '127.*' -and
    $_.IPAddress -notlike '169.254.*' -and
    $_.IPAddress -notlike '172.16.*' -and
    $_.IPAddress -notlike '172.17.*' -and
    $_.InterfaceAlias -notlike '*WSL*' -and
    $_.InterfaceAlias -notlike '*vEthernet*' -and
    $_.InterfaceAlias -notlike '*Loopback*'
  } |
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
    $pyOk = $false
    try { $null = & py -3.12 --version 2>&1; $pyOk = $true } catch { }
    if ($pyOk) { Write-Host "  [OK] Python 3.12" -ForegroundColor Green }
    else { Write-Host "  [MISSING] Python 3.12 not found" -ForegroundColor Red }

    Write-Host "Flutter:"
    $flutterOk = $false
    try { $null = & flutter --version 2>&1; $flutterOk = $true } catch { }
    if ($flutterOk) { Write-Host "  [OK] Flutter" -ForegroundColor Green }
    else { Write-Host "  [MISSING] Flutter not found" -ForegroundColor Red }
    Write-Host ""

    Write-Host "--- adb devices ---" -ForegroundColor Yellow
    & adb devices
    Write-Host ""

    Write-Host "--- .env file ---" -ForegroundColor Yellow
    if (Test-Path "$RepoRoot\.env") {
      Write-Host "  .env found" -ForegroundColor Green
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
    $tunnels = & adb reverse --list 2>&1
    if ($tunnels -and $tunnels -notlike '*error*') { Write-Host "  $tunnels" -ForegroundColor Green }
    else { Write-Host "  No tunnels active. Run: .\scripts\dev.ps1 tunnel" -ForegroundColor Yellow }
    Write-Host ""

    Write-Host "--- Quick reference ---" -ForegroundColor Yellow
    Write-Host "  Terminal 1:  .\scripts\dev.ps1 backend"
    Write-Host "  Terminal 2:  .\scripts\dev.ps1 app          (USB tunnel -- always works)"
    Write-Host "  Terminal 2:  .\scripts\dev.ps1 app-lan      (Wi-Fi -- for real offline drill)"
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
    Write-Host "Errors visible at: http://localhost:8000/api/v1/debug/errors" -ForegroundColor Green
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
    Write-Host "NOTE: airplane mode will NOT cut traffic in this mode (USB tunnel" -ForegroundColor Yellow
    Write-Host "      stays alive). Use 'app-lan' mode for the offline drill." -ForegroundColor Yellow
    Write-Host ""

    Write-Host "--- Connected devices ---" -ForegroundColor Yellow
    & adb devices
    Write-Host ""

    # Use localhost (via USB tunnel) -- reliable for general dev
    Write-Host "Launching app against http://localhost:8000 (via USB tunnel) ..." -ForegroundColor Green
    Write-Host "Debug user: $DebugUserId" -ForegroundColor Green
    Write-Host ""
    & flutter run `
      --dart-define=TB_API_BASE_URL="http://localhost:8000" `
      --dart-define=TB_DEBUG_USER_ID=$DebugUserId
  }

  'app-lan' {
    Set-Location "$RepoRoot\mobile"
    # LAN mode: API traffic goes over Wi-Fi, so airplane mode ACTUALLY cuts it.
    # (adb reverse tunnels over USB, which airplane mode does not disable --
    #  that made the first offline drill attempt meaningless.)
    & adb reverse --remove-all 2>&1 | Out-Null
    Write-Host "USB tunnel removed. Using LAN IP $LanIp (your laptop Wi-Fi)." -ForegroundColor Green
    Write-Host ""
    Write-Host "REQUIREMENTS:" -ForegroundColor Yellow
    Write-Host "  1. Phone on same Wi-Fi as laptop"
    Write-Host "  2. Windows Firewall allows TCP 8000 inbound"
    Write-Host "  3. Router AP isolation disabled (or both on same subnet)"
    Write-Host ""
    Write-Host "If phone can't connect: allow TCP 8000 in Windows Firewall:" -ForegroundColor Yellow
    Write-Host '  New-NetFirewallRule -Name "TravelBuddyDev" -Dir Inbound -Protocol TCP -LocalPort 8000 -Action Allow'
    Write-Host ""

    & flutter run `
      --dart-define=TB_API_BASE_URL="http://${LanIp}:8000" `
      --dart-define=TB_DEBUG_USER_ID=$DebugUserId
  }

  'tunnel' {
    Write-Host "Re-establishing adb reverse tunnel..." -ForegroundColor Yellow
    & adb reverse tcp:8000 tcp:8000
    Write-Host "Done! Phone's localhost:8000 now routes to laptop's localhost:8000" -ForegroundColor Green
  }

  'verify' {
    Write-Host "--- Backend health ---" -ForegroundColor Yellow
    try {
      $health = (Invoke-WebRequest -UseBasicParsing "http://localhost:8000/api/v1/health" -TimeoutSec 5).Content
      Write-Host "  $health" -ForegroundColor Green
    } catch {
      Write-Host "  Backend unreachable. Start with: .\scripts\dev.ps1 backend" -ForegroundColor Red
      return
    }
    Write-Host ""
    Write-Host "--- Recent errors (SPEC-05 ring buffer) ---" -ForegroundColor Yellow
    try {
      $errors = (Invoke-WebRequest -UseBasicParsing "http://localhost:8000/api/v1/debug/errors" -TimeoutSec 5).Content
      Write-Host "  $errors"
    } catch {
      Write-Host "  Debug endpoint unavailable (TB_DEBUG may be off)" -ForegroundColor Yellow
    }
    Write-Host ""
    Write-Host "--- Signal delivery ---" -ForegroundColor Yellow
    Write-Host "  Check the backend terminal for 'POST /api/v1/signals -> 200' lines."
    Write-Host "  On the phone: Profile > Sync Status shows pending/inflight/failed counts."
  }
}
