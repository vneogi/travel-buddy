# Travel Buddy -- Flutter Mobile App

AI-powered travel companion for Dubai and the Laos field-test corridor.
Material 3, Riverpod state management, Dio HTTP client.

## Quick Start

```bash
cd mobile
flutter pub get
flutter run
```

### Connect to Backend

By default connects to `http://10.0.2.2:8000` (Android emulator -> host localhost).

Override at runtime:
```bash
flutter run --dart-define=TB_API_BASE_URL=https://your-api.railway.app
```

`ApiClient` appends `/api/v1`; do not include that suffix in
`TB_API_BASE_URL`.

For the field-test artifact, use the stable hosted HTTPS API and a standalone
release build:

```bash
flutter build apk --release \
  --dart-define=TB_API_BASE_URL=https://your-hosted-api.example
```

The acceptance build must launch without `flutter run`, USB, localhost,
`10.0.2.2`, a laptop LAN address, or `adb reverse`. See
`../docs/specs/SPEC-37-phone-field-test-delivery.md`. Provider and Supabase
service-role keys belong on the backend only.

### Identity (SPEC-09)

The app generates a per-device UUID v4 on first launch and stores it in
platform secure storage (Keychain / EncryptedSharedPrefs). Every request
without a Supabase JWT sends:

```
Authorization: Anonymous <device-uuid>
```

The backend must opt in to accept anonymous identity:
```
TB_ALLOW_ANONYMOUS=true
```

Without this flag the server returns 401 for Anonymous requests (fail-closed).
See `security.py` for details.

### Environment Variables (via --dart-define)

| Variable | Purpose | Default |
|----------|---------|---------|
| `TB_API_BASE_URL` | Backend API base URL | `http://10.0.2.2:8000` |
| `TB_SUPABASE_URL` | Supabase project URL (auth) | empty |
| `TB_SUPABASE_ANON_KEY` | Supabase anon key (auth) | empty |

## Architecture

```
lib/
+-- core/           # API client, device identity, env, Riverpod providers
+-- data/           # Models + repositories (the API contract)
+-- theme/          # Design tokens: colors, typography, spacing
+-- widgets/        # Shared components (activity card, badge, shimmer)
+-- features/       # Screen-per-feature
|   +-- onboarding/
|   +-- home/
|   +-- itinerary/  # Hero screen -- live timeline
|   +-- chat/       # REST-based (no WebSocket)
|   +-- activity_detail/
|   +-- swap_sheet/
|   +-- map/        # Flutter map UI placeholder; separate from backend routing key
|   +-- profile/
|   +-- upgrade/    # RevenueCat paywall scaffold
+-- routing/        # GoRouter config + auth guard
+-- main.dart       # Entry point
```

## Key Design Decisions

1. **No WebSocket** -- Chat uses `POST /trip/event` over REST
2. **No codegen** -- Hand-written `fromJson` for flexibility
3. **Map placeholder** -- Flutter tiles remain deferred. The backend Distance
   Matrix key is separately verified in `../docs/HOSTED_STATE.md`.
4. **RevenueCat scaffold** -- Activates when keys are set, no-ops otherwise
5. **Error-typed exceptions** -- `RerouteLimitException` drives upgrade CTA, not error toast
6. **Auth guard** -- GoRouter redirect; Supabase session check
7. **Anonymous identity** -- Device UUID generated once; persisted in secure storage (SPEC-09)

## Design Language

- "Calm editorial luxury" -- Dubai desert-at-dusk palette
- Primary: Deep teal `#0E7C7B` / Accent: Warm amber `#E8A33D`
- Typography: Fraunces (headings) + Inter (body)
- 4pt spacing grid, 16px card radius, minimal elevation
