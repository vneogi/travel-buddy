# Travel Buddy — Signal & Data-Model BRD
*Status: DRAFT for review. Owner: Vikrant. Feeds the "flywheel" moat (see docs/VISION.md §4).*
*Purpose: define the extensible data model that captures on-trip signals, ingests third-party
metrics, and layers LLM-derived insight — the proprietary asset that compounds monthly.*

## 0. How to read this
This is a **design BRD**, not an implementation plan. It defines *concepts, schema, and rules*
so the data asset is extensible and legally clean from day one. Review targets: is the model
extensible enough that adding a new source (a new review site, a new signal type) is config, not
a migration? Is the provenance/consent model sound enough to survive acquisition due diligence?

## 1. Goals & non-goals

**Goals**
1. Capture every on-trip signal our users generate — explicit *and* behavioral — with provenance.
2. Ingest third-party metrics (TripAdvisor, Klook, Google, etc.) in a **source-agnostic, extensible**
   way, without hard-coding any single provider.
3. Provide a **placeholder-first** structure for LLM-derived signals (cross-source summaries,
   sentiment, extracted attributes) so they slot in later without reshaping the schema.
4. Make the **re-planning engine's observed behavior** (what alternatives users accept/reject) a
   first-class, captured signal — this is the proprietary crown jewel no competitor has.
5. Be **privacy-first and consent-based** so the resulting data asset is legally sellable.
6. Work **offline-first** (capture on-trip in low/no connectivity, sync later) — hard dependency
   for the Laos field test and the whole on-trip thesis.

**Non-goals (for this BRD / MVP)**
- Not building the actual third-party ingestion connectors yet — just the schema + provenance model
  they'll plug into.
- Not building LLM summarization yet — just the placeholder tables/fields.
- Not solving entity resolution perfectly — defining the approach + a manual-override path.

## 2. Design principles
1. **One universal `Signal` abstraction.** Every metric — a user "loved it", a TripAdvisor rating,
   an LLM sentiment score, an observed reroute-accept — is a `Signal` row with a *type*, a *source*,
   a *value*, a *timestamp*, and *provenance*. New signal types = new rows, not new tables.
2. **Source registry, not hard-coded providers.** TripAdvisor/Klook/Google/first-party/LLM are all
   entries in a `sources` table. Adding a source is data, not a migration.
3. **Provenance on everything.** Every signal knows where it came from, when, how (API/scrape/user/
   derived), and under what consent/license. No orphan data.
4. **Freshness & decay are first-class.** Travel data rots. Every signal has a captured-at and an
   optional expiry/decay policy; the engine weights fresh signals higher.
5. **Canonical entity, many external identities.** One internal `place` per real-world venue, mapped
   to many external IDs. Entity resolution is a named, testable problem — not an afterthought.
6. **Separate "product analytics" from "flywheel signals."** Retention/DAU telemetry (for us) and
   place-quality signals (the asset) are related but distinct pipelines. Don't conflate.
7. **Privacy by design.** Pseudonymous user IDs, explicit consent for location/behavioral capture,
   documented retention, right-to-delete. Built in, not bolted on.

## 3. Core entities

### 3.1 `place` (canonical venue) — the spine
The single internal identity for a real-world venue. Everything hangs off `place_id`.

```
place
  place_id          UUID PK
  canonical_name    TEXT
  city_id           FK -> city
  lat, lng          DOUBLE
  geohash           TEXT        -- for proximity + dedup
  category          TEXT        -- restaurant, gallery, ...
  status            TEXT        -- active | closed_permanently | unverified | merged_into
  merged_into       UUID NULL   -- if deduped into another place
  created_at, updated_at
```

Notes: `place` holds only *stable identity* facts. All *opinions/metrics* live in `signal`.
`status=closed_permanently` is itself derived from signals (see §5.3).

### 3.2 `place_external_id` — the entity-resolution map
Maps one canonical place to its identity on each external source. **This is the hard part.**

```
place_external_id
  id                UUID PK
  place_id          FK -> place
  source_id         FK -> source
  external_id       TEXT        -- e.g. TripAdvisor location_id, Google place_id, Klook activity_id
  external_url      TEXT
  match_method      TEXT        -- exact_id | geo+name | manual | llm_assisted
  match_confidence  FLOAT       -- 0..1
  verified_by       TEXT NULL   -- human/curator who confirmed, if any
  created_at
  UNIQUE(source_id, external_id)
```

Entity resolution strategy (§7) writes here. Low-confidence matches are flagged for review, never
silently merged.

### 3.3 `source` — the source registry

```
source
  source_id         UUID PK
  key               TEXT UNIQUE -- 'first_party', 'tripadvisor', 'klook', 'google_places', 'llm_derived', ...
  display_name      TEXT
  source_type       TEXT        -- first_party | third_party_api | third_party_scrape | derived
  trust_weight      FLOAT       -- default weight when fusing signals (0..1)
  legal_basis       TEXT        -- 'user_consent' | 'official_api_tos' | 'licensed' | 'public_scrape_REVIEW'
  license_notes     TEXT
  active            BOOL
```

`legal_basis` is not decoration — see §10. Anything marked `*_scrape_REVIEW` is quarantined from the
sellable asset until cleared by legal.

### 3.4 `signal` — the universal fact table
The heart of the model. Every metric, from every source, is a row here.

```
signal
  signal_id         UUID PK
  place_id          FK -> place -- what it's about (nullable if about a city/route, see §5.5)
  source_id         FK -> source
  signal_type_id    FK -> signal_type
  user_id           FK -> app_user NULL -- set for first-party; null for aggregate/third-party
  trip_id           FK NULL     -- context, for first-party on-trip signals
  value_numeric     DOUBLE NULL -- rating, count, score, price_level...
  value_text        TEXT NULL   -- short label / enum value ('loved','closed','too_crowded')
  value_json        JSONB NULL  -- structured payloads (e.g. LLM extraction, source raw)
  weight            FLOAT       -- effective weight after trust × freshness (denormalized cache)
  captured_at       TIMESTAMPTZ -- when the signal was true/observed
  ingested_at       TIMESTAMPTZ -- when we stored it
  expires_at        TIMESTAMPTZ NULL -- freshness horizon
  provenance        JSONB       -- {method, request_id, raw_ref, consent_id, ...}

  INDEX (place_id, signal_type_id, captured_at)
```

### 3.5 `signal_type` — the taxonomy registry (extensibility lever)
Defining a new signal = insert a row here. No schema change.

```
signal_type
  signal_type_id    UUID PK
  key               TEXT UNIQUE -- 'user_loved', 'user_closed_report', 'ta_rating', 'klook_price',
                                -- 'reroute_accepted', 'llm_sentiment', 'llm_summary', ...
  category          TEXT        -- explicit_user | behavioral | third_party_agg | derived
  value_kind        TEXT        -- numeric | enum | json | boolean
  enum_values       TEXT[] NULL -- for enum kinds
  decay_policy      TEXT        -- none | linear_30d | exp_90d | seasonal ...
  description       TEXT
```

### 3.6 `app_user` (pseudonymous) & `consent`

```
app_user
  user_id           UUID PK    -- pseudonymous; maps to auth (Supabase sub) separately/minimally
  home_region       TEXT NULL
  created_at
```

```
consent
  consent_id        UUID PK
  user_id           FK
  scope             TEXT        -- 'behavioral_capture' | 'location_capture' | 'data_share' ...
  granted           BOOL
  granted_at, revoked_at
  policy_version    TEXT
```

Behavioral/location signals MUST reference a valid granted `consent`. No consent → no capture.

## 4. Signal taxonomy (the "what we capture" catalog)

### 4.1 First-party — explicit (user tells us)
`user_loved`, `user_liked`, `user_disliked`, `user_rating` (1–5), `user_closed_report`,
`user_too_crowded`, `user_not_as_described`, `user_saved`, `user_photo` (json ref), `user_note`.
Cheap taps, captured in-context on the itinerary/venue card. **Design for one-tap** — friction kills
signal volume.

### 4.2 First-party — behavioral / implicit (the proprietary gold)

#### 4.2.0 Registry status (verified 2026-08-08)

| Signal type | Specified | Registered server-side | Emitted by client |
|---|---|---|---|
| `user_loved` | Yes | **Yes** | **Yes** |
| `reroute_accepted` | Yes | **Yes** (SPEC-06) | No (SPEC-07) |
| `reroute_rejected` | Yes | **Yes** (SPEC-06) | No (SPEC-07) |
| `visited_confirmed` | Yes | **Yes** (SPEC-06) | No (SPEC-07) |
| `node_skipped` | Yes | **Yes** (SPEC-06) | No (SPEC-07) |
| `arrival_delta` | Yes | **Yes** (client POST rejected 422) | Not yet derived (SPEC-07) |
| `dwell_minutes` | Yes | No (needs background location — post-Laos) | No |

A type must appear in BOTH the `signal_type` table (Supabase migration) and
`models/signal_types.py` before ingest will accept it. `models/signal_types.py`
is the single source of truth; `tests/test_signal_types.py` enforces that the
migrations agree. `arrival_delta` is registered but cannot be POSTed by clients
— it will be derived server-side from `visited_confirmed` timestamps (SPEC-07).
`dwell_minutes` requires background location permission and is deferred post-Laos.

The signals **only an on-trip app can capture**, and the core of the moat:
- `reroute_suggested` / `reroute_accepted` / `reroute_rejected` — engine offered alternative X for
  node Y; user accepted/rejected. Ranking training data + venue quality signal + preference model.
- `visited_confirmed` — did the planned/swapped venue actually happen (dwell + proximity, consented).
- `node_skipped`, `node_reordered`, `dwell_minutes`, `arrival_delta` (planned vs actual time).
- `search_then_ignore` — surfaced in results but never chosen (negative signal).
These are **observations of real behavior at real venues in real conditions** — expensive to fake,
impossible to buy. Prioritize capturing these correctly above all else.

### 4.3 Third-party — aggregate (ingested, placeholder connectors)
Per-source, per-place aggregate metrics, e.g.:
- `ta_rating`, `ta_review_count`, `ta_rank` (TripAdvisor)
- `klook_rating`, `klook_price`, `klook_bookings` (Klook)
- `google_rating`, `google_review_count`, `google_price_level`, `google_popular_times`
- generic `partner_rating` etc. for future sources.
Stored as `signal` rows with the source's `source_id`. **The schema is ready now; the connectors
are later** — but nothing about the schema assumes any particular provider (add via `source` +
`signal_type`).

### 4.4 Derived — LLM (placeholder-first)
Structured slots so LLM work drops in without reshaping:
- `llm_summary` (value_json: {summary, source_refs[], model, prompt_version}) — cross-source synthesis
  ("what everyone says about this place").
- `llm_sentiment` (numeric −1..1), `llm_attributes` (json: extracted vibe/good-for/warnings),
  `llm_tourist_trap_score`, `llm_freshness_flag`.
- Provenance MUST record model + prompt version + input source_refs for reproducibility/audit.
LLM signals are **derived** (source_type=derived) and never overwrite primary signals — they sit
alongside with their own trust weight.

### 4.5 Non-place signals (routes / cities)
Some signals aren't about a single venue: transit reliability on a route, "city X in monsoon",
neighborhood safety/vibe. Model as `signal` with `place_id NULL` + a `subject` in `value_json`
({subject_type:'route'|'city'|'area', ref}). Keeps the universal table universal.

## 5. Fusion, freshness, conflict

### 5.1 Effective weight
`weight = source.trust_weight × freshness(decay_policy, captured_at) × (signal-specific modifiers)`.
Cached on the row, recomputed on read/aggregate. The engine consumes a *fused* place score, not raw
rows.

### 5.2 Place quality view (materialized/aggregated)
A read model per place: fused rating, confidence, freshness, top attributes, warnings — computed
from signals across sources with trust weighting. This is what the RAG/re-planning engine reads.

### 5.3 Conflict resolution
When sources disagree (Google says open, 3 users report closed): recency + first-party weight win;
`user_closed_report × N` within a window can flip `place.status` to `unverified`/`closed`. Rules
live in config, not code, where feasible.

### 5.4 Freshness / decay
Ratings decay slowly; "too_crowded" and "closed" decay fast (hours/days) and may be time-of-day/
seasonal. `decay_policy` per signal_type drives this.

## 6. Event pipeline (capture → sync → store → aggregate)
1. **Capture** (client): user tap or observed behavior → local event, queued (offline-first).
2. **Sync** (client→API): batched on reconnect; idempotent (client-generated event UUIDs).
3. **Ingest** (API): validate consent, resolve `place_id`, write `signal`.
4. **Aggregate** (async): recompute place-quality read model; recompute weights.
5. **Serve** (engine): RAG/re-planning reads the fused view.
Third-party + LLM enter at step 3/4 via their own jobs, same `signal` table.
(Offline queue/sync detail = the #3 BRD; this BRD just mandates client events are queueable +
idempotent.)

## 7. Entity resolution (the hard problem — define it now)
The same venue appears as our seed row, a Google place_id, a TripAdvisor location_id, a Klook
activity. Getting these wrong corrupts the whole asset.
- **Tier 1:** exact external-ID match when we already have a mapping.
- **Tier 2:** geo (geohash proximity) + normalized-name fuzzy match → candidate; confidence scored.
- **Tier 3:** LLM-assisted disambiguation for ambiguous candidates.
- **Human override:** a curation queue for low-confidence matches; nothing auto-merges below a
  threshold. `place_external_id.match_confidence` + `verified_by` track this.
- **Never destructive:** merges are soft (`place.merged_into`), reversible.
Open question for reviewers: buy an entity-resolution/places service vs. build? (See §14.)

## 8. Privacy, consent, retention, compliance
- **Pseudonymous** user IDs; separate the identity↔auth mapping, minimize its exposure.
- **Explicit consent** per scope (behavioral, location, data-sharing); enforced at ingest.
- **Location data** is sensitive: store coarse where possible, document purpose, allow opt-out
  without breaking core function.
- **Retention policy** per signal category; **right-to-delete** cascades to first-party signals.
- **Regional law:** GDPR (EU users), plus local laws across our footprint (SE/Central Asia, ME).
  Assume we'll operate cross-border → design for the strictest.
- **This is a sale enabler:** an acquirer's diligence will audit consent + provenance. Clean data =
  higher multiple; tainted data = deal risk.

## 9. How signals close the flywheel loop
`on-trip use → behavioral + explicit signals → fused place-quality + preference model →
better re-planning/RAG ranking → better on-trip experience → more use`.
Concretely: `reroute_accepted/rejected` trains alternative-ranking; `user_closed`/`too_crowded`
correct freshness faster than any competitor's stale data; `visited_confirmed` validates
recommendations. Each month the fused view should measurably beat raw third-party data — that delta
IS the moat. **We should track that delta explicitly** (see §11).

## 10. ⚠️ Legal note on third-party data (read before building connectors)
Scraping TripAdvisor/Klook/Google typically **violates their ToS**, and a data asset built on it is a
**liability at acquisition**, not value. Compliant paths, in order of preference:
1. **Official APIs** under their ToS (Google Places API, TripAdvisor Content API, Klook partner API).
2. **Licensed data** / partnerships.
3. Public data only where clearly permissible, reviewed by counsel.
The schema treats every source's `legal_basis` explicitly and **quarantines** unreviewed scrape data
from the sellable asset. Decision needed before any connector is built. Do NOT let an agent
"just scrape it" — that mortgages the exit.

## 11. What we measure (asset health)
- Signal volume/velocity per city, per type (esp. behavioral).
- Coverage: % of active places with ≥N fresh first-party signals.
- **Moat delta:** agreement/lift of our fused score vs raw third-party alone (does our data add
  signal?).
- Reroute-accept rate (also the engine-quality metric).
- Entity-resolution precision (sampled).

## 12. Extensibility checklist (the acid test for reviewers)
Adding a new review site should be: (1) insert a `source`, (2) insert relevant `signal_type`s,
(3) write a connector that emits `signal` rows. **Zero schema migrations.** If a proposed signal
can't be expressed as a `signal` row, the model needs revisiting — flag it.

## 13. Phased delivery vs. Laos (Oct 2)
- **Must-have before Laos (capture or lose forever):** `place`, `signal`, `signal_type`,
  `source`(first_party seeded), `app_user`, `consent`; first-party explicit + behavioral capture
  (esp. reroute_accepted/rejected, visited_confirmed, closed/crowded reports); offline queue +
  idempotent sync (#3 BRD).
- **Fast-follow (post-trip):** third-party connectors (start with one compliant API), place-quality
  aggregation view, entity resolution Tier 2/3.
- **Later:** LLM-derived signals, cross-source summaries, sellable-asset export.
Rationale: the field trip's value is the *behavioral* data — that's the part you can't backfill.

## 14. Open questions for review (bring these to other models/friends)
1. Build vs. buy **entity resolution / places graph** (Google Places as spine? Foursquare/other?).
2. Which **third-party source first**, and is its official API viable/affordable?
3. **Consent UX:** how to get behavioral/location consent without killing onboarding conversion?
4. **Store choice for signals at scale:** Postgres/Supabase now — when (if) do we need a
   warehouse/columnar store for the analytics side?
5. **Anonymization bar** for the eventual data-share/sale — what exactly is sellable?
6. Do we need **event-sourcing/audit log** of raw events distinct from the `signal` table?
7. `popular_times`/seasonal signals — model as time-series in `value_json` or a separate table?

## 15. Non-goals restated
No connectors, no LLM summarization, no sale-export in this phase. This BRD delivers the *model* and
the *first-party capture* that must exist before Oct 2.

## 16. Audience model & capability signals (adds to §3-§4)

*Operationalizes VISION §11 (in-trip capabilities -> moat) and the audience-aware principle.
Everything here obeys §2: new signals are `signal_type` rows, not new tables, except the two
genuinely new *entities* below (traveler profile + trip party), which the signals reference.*

### 16.1 New entities

#### `traveler_profile` — persistent "who this user is as a traveler"
One per `app_user`; slow-changing preferences that carry across trips (feeds capability #8 memory).

```
traveler_profile
  profile_id          UUID PK
  user_id             FK -> app_user (unique)
  traveler_types      TEXT[]    -- self-declared defaults: solo|couple|friends|family_*|...
  dietary             TEXT[]    -- veg|vegan|halal|allergy:nuts|...
  mobility            TEXT[]    -- stairs_ok|wheelchair|low_stamina|stroller|...
  interest_vector     JSONB     -- learned + declared: {art:0.8, nightlife:0.2, food:0.9,...}
  pace_preference     TEXT      -- packed | balanced | relaxed
  budget_band         TEXT      -- shoestring | mid | premium
  updated_at
```

`interest_vector` is *learned* over time from behavioral signals (§16.3) — declared values seed it.

#### `trip_party` & `party_member` — "who is on THIS trip"
Per-trip composition. The same user has different parties on different trips (daddy-kiddo vs solo).
This is the key input that makes recommendations audience-aware per-trip.

```
trip_party
  party_id            UUID PK
  trip_id             FK -> trip_state (unique)
  party_type          TEXT      -- solo|couple|friends|family_young_kids|family_teens|
                                -- multigen|daddy_kiddo|accessibility_focused|mixed
  size                INT
  notes               TEXT NULL
```

```
party_member
  member_id           UUID PK
  party_id            FK -> trip_party
  role                TEXT      -- self|partner|child|teen|parent|friend|...
  age_band            TEXT      -- infant|toddler|child|teen|adult|senior (NOT exact age — privacy)
  needs               TEXT[]    -- nap_schedule|stroller|dietary:*|low_stamina|...
  preference_vector   JSONB NULL -- optional per-member interests (drives capability #6)
```

Design notes: **age_band not birth date** (minimize sensitive data on minors). `preference_vector`
per member is what the multi-preference optimizer (capability #6) reconciles.

### 16.2 New `signal_type` rows (explicit — capability #1, #5, audience-segmented)
Insert-only; no schema change. Each row also carries the **party context** at capture time via
`signal.value_json.party_context` (see §16.5), so every opinion is segmentable by who was travelling.

| key | category | value_kind | decay | notes |
|---|---|---|---|---|
| `user_loved` / `user_liked` / `user_disliked` | explicit_user | enum | exp_180d | already in §4.1 |
| `user_rating` | explicit_user | numeric(1-5) | exp_365d | |
| `user_not_as_described` | explicit_user | boolean | exp_180d | feeds anti-trap (#5) |
| `user_kid_verdict` | explicit_user | enum | exp_180d | kids_loved/ok/hated — **audience-segmented** (#1) |
| `user_accessibility_ok` | explicit_user | enum | exp_365d | stairs/stroller/wheelchair reality vs listing |

### 16.3 New `signal_type` rows (behavioral — the crown jewels, capabilities #2/#4/#6)
These are the *outcome-linked, segmented, unscrapable* signals that are the actual moat. **Highest
capture priority before Laos.**

| key | category | value_kind | decay | powers |
|---|---|---|---|---|
| `reroute_suggested` | behavioral | json | none(event) | #2 — {from_node, candidate, trigger:weather/closure/fatigue, confidence} |
| `reroute_accepted` | behavioral | json | none(event) | #2 — training signal for suggestion quality |
| `reroute_rejected` | behavioral | json | none(event) | #2 — negative signal + reason if given |
| `visited_confirmed` | behavioral | json | none(event) | validates recs — {planned_vs_swapped, dwell_min} (consented location) |
| `node_skipped` | behavioral | boolean | none(event) | negative signal |
| `node_reordered` | behavioral | json | none(event) | pacing signal |
| `arrival_delta` | behavioral | numeric(min) | none(event) | #4 — planned vs actual arrival -> real timing |
| `dwell_minutes` | behavioral | numeric | none(event) | #4 — engagement + real visit duration |
| `search_then_ignore` | behavioral | boolean | exp_30d | surfaced-but-not-chosen (negative rank signal) |
| `group_compromise_accepted` | behavioral | json | none(event) | #6 — {members[], chosen_option, alternatives} |
| `proactive_suggestion_shown` / `_actioned` | behavioral | json | none(event) | #2 — nag-avoidance tuning |

### 16.4 New `signal_type` rows (derived/time — capability #4, placeholder for LLM)

| key | category | value_kind | notes |
|---|---|---|---|
| `observed_best_time` | derived | json | #4 — computed from timed `arrival_delta`+`dwell`+`too_crowded`+ratings -> {venue, window, confidence}. **This is proprietary timing data** incumbents lack. |
| `llm_audience_fit` | derived | json | placeholder — LLM scores venue fit per party_type from fused signals |
| (existing) `llm_summary`, `llm_sentiment`, `llm_tourist_trap_score` | derived | json | §4.4 |

### 16.5 Party context on every signal (the segmentation lever)
To make the moat *segmented* (VISION §11: "loved by daddy-kiddo trips at golden hour"), first-party
signals stamp the party context at capture time — denormalized into `signal.value_json`:

```
value_json.party_context = {
  party_type,
  size,
  age_bands[],
  time_of_day,
  weather_bucket,
  day_index
}
```

Rationale: parties/profiles change over time; freezing context on the signal keeps historical
segmentation correct (don't join to mutable current profile). This is what lets the fused
place-quality view (§5.2) produce *audience-and-condition-specific* scores rather than a flat rating.

### 16.6 Fusion additions (extends §5)
- The place-quality read model (§5.2) gains **segment dimensions**: fused score can be sliced by
  `party_type`, `time_window`, `weather_bucket`. Engine reads the slice matching the current trip.
- **Preference learning:** `traveler_profile.interest_vector` and `party_member.preference_vector`
  are updated asynchronously from behavioral signals (accepted/loved/dwell -> up; rejected/skipped ->
  down). This is capability #8 (cross-trip memory) made concrete.
- **Multi-preference optimizer (#6)** consumes party member vectors + schedule + transit; its
  chosen option and the alternatives it weighed are logged as `group_compromise_accepted` -> the
  optimizer trains on its own outcomes.

### 16.7 Privacy additions (extends §8)
- **Minors:** store `age_band`, never birth date or name for child members. `party_member` for
  children holds no PII beyond band + needs.
- **Behavioral + location signals** (`visited_confirmed`, `dwell_minutes`, `arrival_delta`) require
  granted `consent` scope `behavioral_capture` / `location_capture` (§3.6) — enforced at ingest.
- Right-to-delete cascades to `traveler_profile`, `trip_party`, `party_member`, and all first-party
  `signal` rows for the user.

### 16.8 Laos-critical subset (extends §13)
Must exist before Oct 2 to capture the moat signals (cannot be backfilled):
- `trip_party` + `party_member` (so signals are segmentable from day one).
- Behavioral signal_types: `reroute_suggested/accepted/rejected`, `visited_confirmed`,
  `node_skipped`, `arrival_delta`, `dwell_minutes`, `group_compromise_accepted`.
- `party_context` stamping on all first-party signals.
- Consent scopes wired (`behavioral_capture`, `location_capture`).
Fast-follow (post-trip): `observed_best_time` computation, segment-sliced fusion, LLM `llm_audience_fit`.

### 16.9 Open questions (adds to §14)
8. Multi-preference optimizer (#6): build as constraint solver vs. LLM-planner vs. hybrid? (Affects
   what we log as "alternatives weighed".)
9. `interest_vector` representation — fixed taxonomy vs. embedding? (Extensibility vs. interpretability.)
10. How much location granularity for `visited_confirmed`/`dwell` to prove a visit without over-collecting?
11. Do child `party_member` rows need their own (guardian-granted) consent handling?


## 17. Vault cache (extends §6 pipeline; supports SPEC-04)

The Offline Vault requires *survival* data cached ahead of need. This is **client-side cache only** —
it is NOT part of the signal/flywheel asset and carries no provenance or trust weighting.

- `cache_vault` — per-trip JSON payload: accommodation (local-script + romanized address), emergency
  contacts, essential phrases, pass metadata.
- `cache_asset` — binary blobs (pass QR images, map thumbnails, document pages).

**Pre-caching rule:** populate whenever online (trip create, accommodation set, successful trip
fetch). Assume the user is offline exactly when they need it.

**Server-side additions needed:** accommodation must store the address in **both** local script and
romanized form; local-script translation is generated/fetched **online** and cached — never attempted
offline. Per-city emergency numbers and phrase packs are curated static content served with the city.

**Answer to open question #3 (consent UX):** the travelogue (VISION §14) is the benefit framing for
the location/behavioral consent ask — *"allow location so your trip diary builds itself."*
