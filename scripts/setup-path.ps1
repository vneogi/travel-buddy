# scripts/setup-path.ps1 — Run ONCE to permanently add Android SDK to PATH
# After this, `adb` and `flutter devices` work in every new terminal forever.
# Requires: restart terminal after running.

$sdkPath = "$env:LOCALAPPDATA\Android\Sdk\platform-tools"

# Set ANDROID_HOME permanently
[Environment]::SetEnvironmentVariable("ANDROID_HOME", "$env:LOCALAPPDATA\Android\Sdk", "User")
Write-Host "Set ANDROID_HOME = $env:LOCALAPPDATA\Android\Sdk" -ForegroundColor Green

# Add platform-tools to user PATH if not already there
$currentPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($currentPath -notlike "*$sdkPath*") {
    [Environment]::SetEnvironmentVariable("Path", "$currentPath;$sdkPath", "User")
    Write-Host "Added $sdkPath to user PATH" -ForegroundColor Green
} else {
    Write-Host "platform-tools already in PATH" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Done! Close and reopen PowerShell for changes to take effect." -ForegroundColor Cyan
Write-Host "Then verify with: adb version" -ForegroundColor Cyan
