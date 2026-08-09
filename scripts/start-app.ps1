<#
.SYNOPSIS
    Start the Travel Buddy Flutter app on a connected device (PowerShell 5.1).
.DESCRIPTION
    Pulls latest, detects the LAN IP from ipconfig, asserts the backend is
    reachable, and launches flutter run with the correct --dart-define values.
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

Write-Host "`n========== Travel Buddy: App Start ==========" -ForegroundColor Cyan

# --- 1. Git pull --------------------------------------------------------------
Write-Host "`n[1/4] git pull origin main..." -ForegroundColor Yellow
Set-Location (Join-Path $PSScriptRoot '..')
git pull origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "FATAL: git pull failed (exit $LASTEXITCODE)." -ForegroundColor Red
    exit 1
}

# --- 2. Assert ADB device connected ------------------------------------------
Write-Host "[2/4] Checking for connected device..." -ForegroundColor Yellow
$adbOutput = adb devices 2>&1 | Select-String 'device
if (-not $adbOutput) {
    Write-Host @"

FATAL: No device found.
  1. Connect phone via USB
  2. Unlock the screen
  3. Accept the USB debugging prompt
  4. Run 'adb devices' to confirm
"@ -ForegroundColor Red
    exit 1
}
$deviceId = ($adbOutput -split "`t")[0]
Write-Host "  Device: $deviceId" -ForegroundColor Green

# --- 3. Detect LAN IP and assert backend reachable -------------------------
Write-Host "[3/4] Detecting LAN IP and checking backend..." -ForegroundColor Yellow
$lanIp = $null
$adapters = Get-NetIPAddress -AddressFamily IPv4 -InterfaceAlias 'Wi-Fi*' -ErrorAction SilentlyContinue
if ($adapters) {
    $lanIp = ($adapters | Where-Object { $_.IPAddress -notlike '169.*' } | Select-Object -First 1).IPAddress
}
if (-not $lanIp) {
    $ipcfg = ipconfig | Select-String 'IPv4.*: (192\.168\.[\d]+\.[\d]+)'
    if ($ipcfg) {
        $lanIp = $ipcfg.Matches[0].Groups[1].Value
    }
}
if (-not $lanIp) {
    Write-Host "FATAL: Could not detect LAN IP. Check Wi-Fi connection." -ForegroundColor Red
    exit 1
}
Write-Host "  LAN IP: $lanIp" -ForegroundColor Green

$healthUrl = "http://${lanIp}:8000/api/v1/health"
Write-Host "  Checking $healthUrl ..." -ForegroundColor DarkGray
try {
    $resp = curl.exe -s -o NUL -w '%{http_code}' $healthUrl 2>&1
    if ($resp -ne '200') {
        throw "got HTTP $resp"
    }
} catch {
    Write-Host @"

FATAL: Backend not reachable at $healthUrl
  Run scripts\start-backend.ps1 in another terminal first.
"@ -ForegroundColor Red
    exit 1
}
Write-Host "  Backend healthy." -ForegroundColor Green

# --- 4. Flutter run -----------------------------------------------------------
Write-Host "`n[4/4] Launching Flutter app..." -ForegroundColor Yellow
Write-Host "  API: http://${lanIp}:8000" -ForegroundColor Green
Write-Host "  User: 11111111-1111-1111-1111-111111111111 (debug)" -ForegroundColor Green
Write-Host ""

Set-Location (Join-Path $PSScriptRoot '..\mobile')
flutter run --dart-define="TB_API_BASE_URL=http://${lanIp}:8000" --dart-define="TB_DEBUG_USER_ID=11111111-1111-1111-1111-111111111111"
