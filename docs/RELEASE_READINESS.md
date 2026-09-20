# Release readiness

> Status: OPEN. Recorded 20 Sep 2026. Owner: Vikrant.
>
> This is the cross-functional launch ledger. It does not replace
> `docs/specs/SPEC-43-security-privacy-and-data-governance.md` (the twelve
> security and privacy gaps), `docs/HOSTED_STATE.md` (hosted schema and
> credentials), `docs/ANDROID_BUILD.md` (signed APK), or
> `docs/PROJECT_STATUS.md` (what is built). Those remain the sources of
> truth for their rows. This file answers one question: what still has to
> be true before Travel Buddy is safe to give to a stranger, and later to
> put on a public store.
>
> Current operating posture: owner-only field-test service. Cloud Run and
> a signed APK exist for the owner's Laos trip. That is not a beta, not a
> Play listing, and not world-ready. SPEC-43's owner-only exception expires
> at the first non-owner tester or the public-launch gate, whichever comes
> first.

## The three gates

Work is sequenced by who can hold the APK, not by how complete the product
feels.

| Gate | Who may use it | What closes it |
|------|----------------|----------------|
| G0 Owner field test | The owner, on a signed APK against hosted Cloud Run | Laos reliability slices, hosted/API/APK acceptance, airplane-mode itinerary. SPEC-37 and SPEC-38 already closed the phone-independent floor. Remaining Laos-facing slices still land here. |
| G1 First non-owner | One other person, sideloaded or Test Track, still not a store listing | Every applicable SPEC-43 gap for that distribution. No production LLM processing of personal trip data until the redacting egress and provider/region/retention contract pass. No hostel QR, no cohort, no learned ranking. |
| G2 Public store | Anyone who can find the listing | G1 plus store, legal, support, and ops rows below. Play is the first store; App Store is a later platform, not a parallel launch. |

Do not skip G1 because a hostel common-area QR is cheap. A QR is
distribution of personal-data software.

## What this file is not

- Not a city-expansion plan. Seeding order lives in
  `docs/MARKET_STRATEGY.md` (Sep 2026 addendum). Adding a city remains a
  code change until SPEC-13 and SPEC-20 exist.
- Not a claim that December 2026 is committed. SPEC-43 names that month as
  a planned public launch; this ledger treats it as a deadline to plan
  against, not as evidence the product will be ready.
- Not legal advice. Counsel still has to confirm the operating entity,
  controller roles, jurisdiction triggers, processor contracts, and
  current local rules before G2.
- Not a second copy of the twelve SPEC-43 gaps. The table below only
  points at them.

## G1 -- first non-owner (SPEC-43)

Until these are closed, the product holds itineraries, booking references,
party context, and behavioural signals behind a self-issued UUID. That is
not anonymous, and it is not safe to hand to a tester.

| Area | Spec / ledger | G1 bar |
|------|---------------|--------|
| Server-issued anonymous auth, rotation, revocation | SPEC-43 gap 1, SPEC-09, SPEC-24 | No self-issued replayable UUID as an account |
| RLS and ownership on every personal table | SPEC-43 gap 2 | Two hosted JWTs cannot read each other's trips |
| LLM egress allowlist; no booking secrets in prompts | SPEC-43 gap 3 | Personal LLM traffic stays off until this passes |
| Export, deletion, retention, backup tombstones | SPEC-43 gap 4, SPEC-27 | A tester can leave and take or erase their data |
| Encrypted offline store; backup exclusion | SPEC-43 gap 5, SPEC-04 | Extracted SQLite is not plaintext bookings |
| Real sign-out and account-switch isolation | SPEC-43 gap 6, SPEC-24 | Shared-phone hostel use does not leak the last identity |
| Versioned purpose consent; optional capture blocked | SPEC-43 gap 7 | No cohort analytics before a real choice |
| Private semantic-cache isolation | SPEC-43 gap 8 | Ask cache cannot cross users |
| Signal ownership and poisoning controls | SPEC-43 gap 9 | A supplied trip id is not a write primitive |
| Redacted diagnostics; no production debug | SPEC-43 gap 10, SPEC-05 | Failures do not retain secrets |
| Abuse and provider-spend limits | SPEC-43 gap 11 | A stolen APK cannot run unbounded Ask |
| Release HTTPS and identity-scoped caches | SPEC-43 gap 12 | HTTP rejected; chat text not in route URLs |

SPEC-24 (merge, aliases, sign-out) and SPEC-27 (rights, minimum client,
push transport) are implementation dependencies inside this gate, not
work that may slip past the first non-owner build.

Hosted configuration is a separate proof from laptop `.env`. Record
provider and flag state only in `docs/HOSTED_STATE.md` after a dated
observation. Never commit secret values.

## G2 -- public store

Sideload-safe is not store-safe. These rows are empty on purpose: none of
them have a dated pass.

### Product and trust

| Row | Why it is a launch item | Points at |
|-----|-------------------------|-----------|
| Sponsored ranking disclosed and inspectable | Affiliate or ads without this falsifies "trust is the product" | VISION section 9, SPEC-17 |
| Grounded Ask with named fallbacks | A public composer that invents venues is a support and safety incident | SPEC-25 |
| Hours and reachability honest | A stranger's first day is the product | SPEC-41 |
| No dietary suitability claims | Already retired; do not reopen for launch copy | SPEC-14 |

### Legal, privacy, support

| Row | G2 bar |
|-----|--------|
| Operating entity and privacy policy URL | Live URL, not a repo file. Controller named. Counsel-reviewed. |
| Data-safety / nutrition-label forms | Match actual collection: identity, location if used, itinerary, bookings, diagnostics. Do not declare "not collected" for fields the app writes. |
| Account deletion | In-app path plus the store-required web or in-app deletion flow. SPEC-27 is the engineering contract. |
| Age 18+ position | SPEC-43: adult accounts; coarse party age bands only. Store rating and listing copy must match. |
| Processor record | Supabase, Cloud Run, Maps, OpenWeather, LLM provider, and any affiliate partner: region, retention, subprocessors. |
| OSM / ODbL | Advice before onboarding a city from OSM at scale. Recorded as open in PROJECT_STATUS. |
| Support channel | A mailbox or form a stranger can reach. Crash and abuse reports have somewhere to go. |

### Play (first store)

Build facts already in `docs/ANDROID_BUILD.md`: applicationId
`com.vneogi.travelbuddy`, signed release APK, minify off. That is a
field-test artifact, not a Play upload.

Still owed before a listing:

- Play Console account, app listing, content rating questionnaire
- Data safety form aligned with SPEC-43 purposes
- Signing: Play App Signing vs the current local keystore; do not lose
  the upload key
- Target API and 16 KB page-size / policy rows current at upload time
  (do not snapshot a year into this file)
- Internal or closed testing track before production
- Package uniqueness and store presence checks for the chosen name
- Privacy policy and deletion URL reachable without installing the app

iOS / App Store is not on the G2 critical path. When it is, it needs its
own privacy labels, account-deletion proof, and a paid Apple Developer
account. Do not treat a working Android APK as App Store evidence.

### Operations

| Row | G2 bar |
|-----|--------|
| Hosted LLM and Maps spend alarms | SPEC-43 gap 11 plus a human who notices |
| Rollback | Previous Cloud Run revision can take traffic; APK minimum-version via SPEC-27 |
| Secret handling | Service-role key never in Flutter. JWT secret not in the client. No `.env` in git. |
| `TB_ALLOW_ANONYMOUS` | Field-test flag. G2 identity is server-issued (SPEC-43 gap 1), not an open UUID header. |
| Logging region and retention | Matches the privacy policy, not the debug ring buffer |
| On-call | Even a one-founder product needs a named person for the first week of store traffic |

## Moat and flywheel -- what launch must not break

The durable asset is on-trip signal density in a connected strip, not
city count and not a store ranking. VISION section 6 and the MARKET_STRATEGY
seeding addendum still win:

- Do not collect a cohort, train on behaviour, or sell density until G1
  consent, ownership, and deletion exist. SPEC-43 is the flywheel gate as
  much as the security gate. See `docs/DATA_LAYER_ROADMAP.md`.
- Do not hand-load ten Banana Pancake towns through Python exceptions.
  SPEC-13 and SPEC-20 turn "add a city" into a registry row plus an ingest
  that can refuse. Until then, Laos remains the field graph.
- Hostel QR and Offline Vault remain the backpacker acquisition wedge
  (VISION section 3). They are G1 features, not G0 shortcuts.
- Affiliate (eSIM, activities) stays behind disclosed ranking. Subscription
  is not the beachhead lever.

A public listing that is wide and shallow is the failure mode the vision
already named. G2 does not require a second country.

## Marketing -- allowed before G2, forbidden before G1

Allowed now: founder-network field notes, closed conversations, listing
copy drafted offline, measuring OSM coverage for later towns
(`docs/CORRIDOR_COVERAGE.md`).

Forbidden until G1: a public download link, a hostel QR that installs an
APK, Test Track that a stranger can join, production LLM on personal
trips, "GDPR/DPDP compliant" or residency claims, paid UA.

G2 marketing is still the corridor funnel, not a global brand campaign.
See `docs/MARKET_STRATEGY.md`.

## How to update this file

- Close a row only with a dated observation (commit, hosted sentinel, or
  owner device result you watched). Do not close from an agent summary.
- Do not paste pytest counts here.
- Security implementation detail stays in SPEC-43. Hosted facts stay in
  `docs/HOSTED_STATE.md`. City sequence stays in `docs/MARKET_STRATEGY.md`.
- If a store policy changes, update the owed row; do not freeze a 2026
  Play checklist as if it were code.
