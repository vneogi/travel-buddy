<#
.SYNOPSIS
    Smoke-test the Travel Buddy API (PowerShell 5.1 compatible).
.DESCRIPTION
    Uses here-strings + temp files for curl.exe (PS 5.1 mangles \").
    Checks: health, signal accept, idempotency, validation rejections.
#>
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$baseUrl = 'http://localhost:8000/api/v1'
$userId = '11111111-1111-1111-1111-111111111111'
$tmpFile = Join-Path $env:TEMP 'tb_smoke_test.json'
$pass = 0
$fail = 0

function Invoke-Curl {
    param([string]$Method, [string]$Url, [string]$Body)
    if ($Body) {
        $Body | Out-File -Encoding ascii $tmpFile -Force
        $result = curl.exe -s -X $Method $Url -H "X-Debug-User-Id: $userId" -H 'Content-Type: application/json' --data-binary "@$tmpFile" 2>&1
    } else {
        $result = curl.exe -s -X $Method $Url -H "X-Debug-User-Id: $userId" 2>&1
    }
    return $result
}

function Assert-Check {
    param([string]$Name, [bool]$Condition, [string]$Detail)
    if ($Condition) {
        Write-Host "  PASS  $Name" -ForegroundColor Green
        $script:pass++
    } else {
        Write-Host "  FAIL  $Name -- $Detail" -ForegroundColor Red
        $script:fail++
    }
}

Write-Host "`n========== Travel Buddy: Smoke Test ==========`n" -ForegroundColor Cyan

# --- Check 1: GET /health -> 200 ----------------------------------------------
$healthResp = curl.exe -s -w '\n%{http_code}' "$baseUrl/health" 2>&1
$healthLines = $healthResp -split "`n"
$healthCode = $healthLines[-1]
Assert-Check 'GET /health returns 200' ($healthCode -eq '200') "got $healthCode"

# --- Check 2: POST signal -> accepted=1 ---------------------------------------
$signalId = [guid]::NewGuid().ToString()
$now = [DateTime]::UtcNow.ToString("yyyy-MM-ddTHH:mm:ssZ")
$body = @"
{"signals":[{"signal_id":"$signalId","signal_type":"user_loved","place_ref":"dubai-museum","value_text":"loved","captured_at":"$now"}]}
"@
$resp1 = Invoke-Curl 'POST' "$baseUrl/signals" $body
Assert-Check 'POST signal accepted=1' ($resp1 -match '"accepted":\s*1') "response: $resp1"

# --- Check 3: POST same signal_id again -> duplicates=1 (idempotency) ----------
$resp2 = Invoke-Curl 'POST' "$baseUrl/signals" $body
Assert-Check 'POST duplicate -> duplicates=1' ($resp2 -match '"duplicates":\s*1') "response: $resp2"

# --- Check 4: arrival_delta with wrong value_kind -> rejected ------------------
$body4 = @"
{"signals":[
  {"signal_id":"$([guid]::NewGuid().ToString())","signal_type":"user_loved","place_ref":"dubai-mall","value_text":"loved","captured_at":"$now"},
  {"signal_id":"$([guid]::NewGuid().ToString())","signal_type":"arrival_delta","place_ref":"dubai-mall","value_text":"not_a_number","captured_at":"$now"}
]}
"@
$resp4 = Invoke-Curl 'POST' "$baseUrl/signals" $body4
Assert-Check 'arrival_delta (text instead of numeric) rejected, batch-mate accepted' ($resp4 -match '"accepted":\s*1' -and $resp4 -match '"rejected":\s*\[') "response: $resp4"

# --- Check 5: node_skipped with invalid reason -> rejected -------------------
$body5 = @"
{"signals":[{"signal_id":"$([guid]::NewGuid().ToString())","signal_type":"node_skipped","place_ref":"spice-souk","value_json":{"reason":"tired lol"},"captured_at":"$now"}]}
"@
$resp5 = Invoke-Curl 'POST' "$baseUrl/signals" $body5
Assert-Check 'node_skipped with invalid reason rejected' ($resp5 -match '"rejected":\s*\[' -and $resp5 -match '"accepted":\s*0') "response: $resp5"

# --- Check 6: Unregistered signal type -> rejected ---------------------------
$body6 = @"
{"signals":[{"signal_id":"$([guid]::NewGuid().ToString())","signal_type":"banana_peeled","place_ref":"atlantis","value_text":"yes","captured_at":"$now"}]}
"@
$resp6 = Invoke-Curl 'POST' "$baseUrl/signals" $body6
Assert-Check 'Unregistered type rejected' ($resp6 -match '"rejected":\s*\[' -and $resp6 -match '"accepted":\s*0') "response: $resp6"

# --- Cleanup ----------------------------------------------------------------
if (Test-Path $tmpFile) { Remove-Item $tmpFile -Force }

# --- Summary ----------------------------------------------------------------
Write-Host "`n========================================" -ForegroundColor Cyan
Write-Host "  Results: $pass PASS, $fail FAIL" -ForegroundColor $(if ($fail -eq 0) {'Green'} else {'Red'})
Write-Host "========================================`n" -ForegroundColor Cyan

if ($fail -gt 0) { exit 1 }
