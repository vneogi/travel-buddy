# Travel Buddy — Testing Guide

> Complete testing playbook: backend, Flutter app, end-to-end integration.
> Use this on your personal laptop (no VPN/corporate restrictions needed).

## Quick Start

1. `pytest -q` → 21 passed, 5 skipped
2. `uvicorn main:app --reload --port 8000` (clear TB_SUPABASE_JWT_SECRET for dev auth)
3. `cd mobile && flutter pub get && flutter run`

## Full guide: see docs/PROJECT_STATUS.md §3 for Supabase flip steps.
