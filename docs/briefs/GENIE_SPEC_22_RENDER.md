# Genie Brief -- SPEC-22 Client Render Contract (October slice)

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop -- unit and
> widget tests only. Golden pixel tests and flutter analyze await device.

Canonical spec: `docs/specs/SPEC-22-render-contract.md`
Envelope shape: `docs/specs/SPEC-17-trust-and-verification.md` (Shape section).
Do not implement SPEC-17 backend (`attribute_claim`, registry table, API).
Do not implement SPEC-12 driver card UI.

## Goal

Facts can only be shown through one widget that takes a SPEC-17 envelope.
Five treatments, one interruption budget, offline as a designed state, one-tap
confirm. Stub the source: construct envelopes in tests and later screens.

Without this, SPEC-12 invents an "unconfirmed" treatment and SPEC-15/17
interrupt independently.

## October slice vs later

This PR owns the contract. These spec acceptance items stay open (do not fake):

- Bundled-font cmap vs every local-script codepoint in `data/` (SPEC-12, when
  the driver card ships a Lao-capable font)
- Migrating existing screens (`itinerary_screen`, `activity_card`, etc.) off
  bare strings -- they adopt FactView when those specs land
- Server-side interruption budget (SPEC-27). Client owns the UI budget now.

ARB English+Hindi wiring IS in this PR, for SPEC-22 strings only.

## Envelope (SPEC-17, copy exactly)

```
{ "value": ..., "source": "osm", "confidence": 0.8,
  "tier": "assert", "as_of": "2026-08-13" }
```

Dart type `FactEnvelope`:

- `value` -- `Object?` (string, num, list, map, null)
- `source` -- `String` (non-empty)
- `confidence` -- `double` -- stored for round-trip, NEVER shown as a number
  or percent
- `tier` -- enum `FactTier { assert_, hedge, ask, defer, refuse }`
  Wire names: `assert`, `hedge`, `ask`, `defer`, `refuse`. `assert` is a
  Dart keyword so the enum member is `assert_` with `wire = 'assert'`.
- `as_of` -- `DateTime` (date-only on the wire is fine)

`fromJson` rejects missing `tier` or `source`. Unknown tier fails closed
(throw / return refuse -- pick throw in fromJson so a typo cannot silently
render as assert).

No public constructor that takes a bare `String` value without `tier`.

## Treatments (decision 2)

| Tier | UI |
|---|---|
| assert | Plain text. No badge, no icon, no colour callout |
| hedge | Qualifier INSIDE the sentence, not a badge. English: "Travellers usually say {value}" (ARB). Hindi equivalent in `app_hi.arb` |
| ask | Question card. The value appears only inside the question. One-tap Confirm (not a form). Dismiss control |
| defer | No value. Labelled link: "See {deferralTarget}" (pass target as a widget arg, e.g. "Maps") |
| refuse | Explicit unknown copy, never empty/whitespace. ARB key `factRefuse` |

Do not show confidence numbers. Recency: optional `asOfLabel` only when the
caller passes `showRecency: true` -- human phrase like "confirmed in March",
not a warning icon (decision 5). Default `showRecency: false`.

## Files to add (keep under `mobile/lib/render/` so the token guard can scope)

| Path | Role |
|---|---|
| `mobile/lib/render/fact_envelope.dart` | Type + fromJson |
| `mobile/lib/render/fact_view.dart` | The only fact widget |
| `mobile/lib/render/confirm_affordance.dart` | One-tap confirm, shared with later SPEC-12 |
| `mobile/lib/render/offline_state.dart` | Live / cached / unavailable |
| `mobile/lib/render/interruption_budget.dart` | Single owner |
| `mobile/lib/l10n/app_en.arb` | SPEC-22 strings |
| `mobile/lib/l10n/app_hi.arb` | Hindi for the same keys |
| `mobile/test/render/fact_view_test.dart` | Widget tests, five tiers |
| `mobile/test/render/interruption_budget_test.dart` | Budget |
| `mobile/test/render/token_literals_test.dart` | No raw fontSize/padding in `lib/render/` |
| `supabase/migrations/0019_prompt_dismissed.sql` | Seed signal_type |
| `models/signal_types.py` | Add key (R5) |

Wire `flutter gen-l10n` in `pubspec.yaml` (`generate: true`, arb dir).
Existing screens may keep hardcoded English until they migrate.

## FactView API (compile-time, not a review comment)

```
FactView({
  required FactEnvelope envelope,
  required String attribute, // registry key later; opaque string now
  String? deferralTarget,
  bool showRecency = false,
  VoidCallback? onConfirm,
  VoidCallback? onDismiss,
})
```

No `FactView.value(String)`. No optional tier. Tests: attempting a
hypothetical helper that takes only a string must not exist -- grep
`FactView(` in `mobile/lib` and assert every call site named `envelope:`.

`refuse` test: pump widget, `tester.element` / `find.text` -- fail if the
rendered text for the fact region is empty or whitespace-only.

One widget test per tier (five). Goldens optional; do not fail CI if goldens
are not generated (no device). Prefer `find.textContaining` assertions.

Confirm: `ConfirmAffordance` is a single control, no TextField, no "edit".
Confirm calls `onConfirm` only.

## Interruption budget (decision 8)

One class `InterruptionBudget`, injectable `DateTime Function() now`.

Defaults (document in a comment; not in a spec number so they can change):

- Cap 3 granted interruptions per local calendar day
- Minimum gap 30 minutes between grants
- After dismiss, suppress 120 minutes

`request({required String category})` -> `bool` (granted). Categories are
opaque strings (`question_card`, `checklist`). Callers cannot bypass: no
public "forceShow". Persist day counts in memory for this PR (process
lifetime is enough); do not invent SQLite schema.

Tests:

- Two requests inside the min-gap window: exactly one grant
- Fourth request same day: denied
- After dismiss(), next request inside 120 min: denied

## Dismissal is data (decision 9)

When FactView dismisses (ask/defer), call `SignalService.emit` with type
`prompt_dismissed` (json). Do not swallow.

Add to `SIGNAL_TYPES`:

```
"prompt_dismissed": "json",
```

PAYLOAD_SHAPES: `{kind: str, attribute: str, entity_id: optional}`.

Migration `0019_prompt_dismissed.sql`: INSERT into `signal_type` matching
`0006_dish_signal_types.sql` (key, category, value_kind, enum_values,
decay_policy, description, ON CONFLICT DO NOTHING). Use category
`explicit_user`, value_kind `json`, decay `exp_180d`. ASCII comments only
(R14). Drift test `tests/test_signal_types.py` must stay green.

Widget/unit test: fake SignalService or inspect OfflineDatabase outbox --
assert a row with `prompt_dismissed`, not merely a callback flag (R17).

Do not apply 0019 to live Supabase in this PR. Owner applies later.

## Offline designed state (decision 7)

Three-state enum: `live`, `cached`, `unavailable`.

`OfflineStateView`:

- `cached`: show child (cached content) plus when it was cached. No
  `AppColors.danger`. Retry is NOT the primary button (may be a secondary
  text button).
- `unavailable`: explicit empty-cache copy. Still no danger red as the
  primary chrome.
- `live`: just the child.

Do not reuse `ErrorView` for `ConnectivityResult.none`. ErrorView stays for
server/unreachable. Optional: a comment on ErrorView pointing at
OfflineStateView for true offline.

Payment-methods + verdict-in-cache: add a typed stub

```
CachedPlaceFacts({ required FactEnvelope? paymentMethods, required FactEnvelope? verdict })
```

and a test that OfflineStateView(cached) still shows those envelopes via
FactView. Do not invent a new SQLite table. SPEC-02 `cache_place` can stay
as-is; this is the render contract for when that cache holds envelopes.

## Tokens (decision 10)

Existing `AppTypography` / `AppSpacing` remain the token file.

Add `AppTypography.localScript` (body size at least 16, extra height) for
native-script later. May use Inter/GoogleFonts for now.

Guard `mobile/test/render/token_literals_test.dart`: read every `.dart`
under `mobile/lib/render/` as text, fail on:

- `fontSize:\s*\d`
- `EdgeInsets.(all|only|symmetric)\([^)]*\d{2,}` that is not
  `AppSpacing.`

Allow `AppSpacing.*` and `AppTypography.*`. Icon `size: 18` if needed --
prefer a named token `AppSpacing.iconSm` rather than more exceptions.

Do not scan the whole `mobile/lib` in this PR (existing screens would fail).

## Out of scope

- SPEC-12 driver card screen
- SPEC-17 tables/API
- Rewriting itinerary/home/chat to FactView
- Flutter analyze / device goldens as a merge requirement
- Direct push to main

## R17

Sabotage before trusting:

- Add `FactView.bare(String text)` and confirm a test fails (or grep guard)
- Grant interruptions without going through `request` from a second helper
  and confirm budget test still fails if production path is skipped -- the
  ask/dismiss UI must call the real `InterruptionBudget`, not a copy

## PR

- Branch: `feat/spec-22-render-contract`
- Title: `feat(mobile): SPEC-22 render contract (envelope, budget, offline)`
- Body: October slice notes; 0019 unapplied; font cmap deferred
- Against `main`

## Acceptance for this PR

- [ ] FactView requires FactEnvelope; no bare-value constructor
- [ ] Five tier widget tests
- [ ] refuse never empty
- [ ] InterruptionBudget: one grant per window
- [ ] Dismiss writes `prompt_dismissed` to outbox path
- [ ] Offline cached state has no danger colour; retry not primary
- [ ] Token literal guard on `lib/render/`
- [ ] ARB en + hi for SPEC-22 strings
- [ ] signal_types + 0019 + drift test
- [ ] Backend pytest still green (R16: do not write counts in PROJECT_STATUS)
