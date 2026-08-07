# scripts/

Dev-environment helpers for Travel Buddy. Windows PowerShell only.

## First-time setup

```powershell
# 1. Allow script execution (once per machine):
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned

# 2. Permanently add Android SDK to PATH (once per machine):
.\scripts\setup-path.ps1
# Close and reopen terminal after this.

# 3. Create .env file at repo root (once, gitignored):
# TB_DEBUG=true
# TB_LITELLM_API_KEY=<your key>
```

## Daily dev workflow (two terminals)

```powershell
# Terminal 1 — backend:
.\scripts\dev.ps1 backend

# Terminal 2 — Flutter app on phone:
.\scripts\dev.ps1 app
```

## Other commands

| Command | What it does |
|---------|-------------|
| `.\scripts\dev.ps1 check` | Verify env: Python, Flutter, adb, .env, backend health, tunnel |
| `.\scripts\dev.ps1 tunnel` | Re-establish adb reverse (if USB reconnected) |
| `.\scripts\dev.ps1 verify` | Hit GET /signals to check drill results |

## Airplane-mode drill (the real test)

1. `.\scripts\dev.ps1 backend` (Terminal 1)
2. `.\scripts\dev.ps1 app` (Terminal 2 — waits for build, launches on phone)
3. On phone: verify venues load
4. Airplane mode ON → tap ❤ on 5 venues → force-kill app
5. Reopen app → Profile → Sync Status → expect 5 pending
6. Airplane mode OFF → watch drain to 0
7. `.\scripts\dev.ps1 verify` → expect 5 signals, no duplicates

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `adb` not found | Run `.\scripts\setup-path.ps1`, reopen terminal |
| Backend 500 "auth misconfiguration" | Missing `.env` file or `TB_DEBUG` not set |
| Phone can't reach backend | Run `.\scripts\dev.ps1 tunnel` |
| `flutter run` Gradle lock | `Stop-Process -Name "java" -Force` then retry |
| First build takes 10+ min | Normal (Gradle downloads). Subsequent builds are fast. |
