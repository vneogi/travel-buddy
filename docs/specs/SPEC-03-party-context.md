# SPEC-03 — Trip party & party_context stamping
*Implements DATA_MODEL §16.1/§16.5. MUST ship before Oct 2 (Laos): party context cannot be
backfilled — signals captured without it are unsegmentable forever.*

## Why this matters
Our moat is not "4.2 stars" — it's *"loved by daddy-kiddo trips at golden hour when rerouted-to."*
That granularity requires knowing **who was travelling** at capture time. Profiles/parties mutate, so
the context must be **frozen onto each signal**, not joined later.

## Scope (deliberately minimal for Laos)
IN: `trip_party` + `party_member` entities; party selection at trip creation; `party_context`
stamped into `signal.value_json`; recommendations *receive* the party (using it well is later).
OUT: `traveler_profile` / cross-trip memory, multi-preference optimizer, per-member preference
vectors, audience-segmented fused scoring. Those are post-Laos.

## Migration `0003_trip_party.sql`
```sql
CREATE TABLE IF NOT EXISTS trip_party (
  party_id    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  trip_id     TEXT NOT NULL UNIQUE,
  party_type  TEXT NOT NULL,      -- solo|couple|friends|family_young_kids|family_teens|
                                  -- multigen|daddy_kiddo|accessibility_focused|mixed
  size        INTEGER NOT NULL DEFAULT 1,
  notes       TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS party_member (
  member_id   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id    UUID NOT NULL REFERENCES trip_party(party_id) ON DELETE CASCADE,
  role        TEXT NOT NULL,      -- self|partner|child|teen|parent|friend
  age_band    TEXT NOT NULL,      -- infant|toddler|child|teen|adult|senior  (NEVER a birth date)
  needs       TEXT[] DEFAULT '{}' -- nap_schedule|stroller|dietary:*|low_stamina
);
CREATE INDEX IF NOT EXISTS idx_party_member_party ON party_member(party_id);
-- ROLLBACK: DROP TABLE party_member; DROP TABLE trip_party;
```
**Privacy:** `age_band` only — never a child's birth date or name (DATA_MODEL §16.7).

## Server
- **Models** (`models/schemas.py`): `PartyMemberIn {role, age_band, needs[]}`,
  `TripPartyIn {party_type, size, members[]}`; add optional `party: TripPartyIn?` to
  `CreateTripRequest`. Default when absent: `party_type='solo', size=1`.
- **DB methods** on BOTH backends behind `db_provider`: `save_trip_party(trip_id, party)`,
  `get_trip_party(trip_id)`. In-memory = dict; Supabase = insert + select.
- **`POST /trip/create`**: persist the party (default solo if omitted).
- **`POST /signals`**: on ingest, look up the trip's party and **merge `party_context` into
  `value_json`** — server-side, so it's authoritative and clients can't forge it:
```python
value_json["party_context"] = {
    "party_type": party.party_type,
    "size": party.size,
    "age_bands": sorted({m.age_band for m in party.members}),
    "time_of_day": captured_at.strftime("%H:%M"),
    "day_index": (captured_at.date() - trip_start.date()).days,   # if trip_start known
}
```
⚠️ **Design decision:** stamp on the **server at ingest**, not the client. Rationale: the client may
be running an old build or have stale party data, and offline-queued signals could carry a party the
user has since changed. Server-side at ingest is authoritative and handles the offline case naturally.
Trade-off: a signal for a deleted trip can't be stamped — in that case omit `party_context` rather
than fail the ingest.
- **`GET /trip/{id}`**: include the party so the client can display it.
- Keep `weather_bucket` out of v1 (needs the weather service wired) — note it as a future key.

## Flutter
- **Models**: `PartyMember {role, ageBand, needs}`, `TripParty {partyType, size, members}` with
  `toJson`/`fromJson`.
- **Trip creation flow**: a simple party picker before creating — chips for party type, plus
  "add child/teen" with an **age-band dropdown** (not a date picker). Functional, not pretty.
- **`AudienceBadge`** in the itinerary top bar showing e.g. "Family — kids 3, 6"; tap = no-op for now
  (quick-swap sheet is post-Laos, UX_BACKLOG P2).
- **Repository**: `create({startDate, mood, party})` sends the party; `TripState` parses it back.

## Tests
**Python:** create-trip with a party persists it and `GET /trip/{id}` returns it; create-trip
*without* a party defaults to solo/1; a signal for a trip with a party gets `party_context` in
`value_json` (assert `party_type` and `age_bands`); signal for an unknown trip still succeeds with no
`party_context` (never fail ingest); `age_band` accepted but a birth-date field is rejected/absent.
**Flutter:** `TripParty.toJson`/`fromJson` round-trip; create sends the party in the body;
`AudienceBadge` renders the party type.

## Acceptance
1. Migration `0003` applies cleanly.
2. Create a family trip on the device → party persisted → badge shows it.
3. Tap ❤ → server-side signal carries `party_context` with correct `party_type` + `age_bands`.
4. Existing suites stay green (45 py / 29 dart, plus new).
5. No child birth dates or names anywhere in the schema or payloads.

## Review checklist
- [ ] `party_context` stamped **server-side at ingest**, merged (not overwriting) into `value_json`
- [ ] Missing/unknown trip → ingest still succeeds, `party_context` omitted
- [ ] Defaults to solo when no party supplied (no breaking change to existing clients)
- [ ] `age_band` only — no birth dates
- [ ] Works on both backends behind `db_provider`
- [ ] Offline-queued signals still stamp correctly on later ingest (they're stamped at ingest, so yes — verify)


## Outstanding (added 2026-08-08)

Acceptance criteria are NOT fully met. The application code is complete
and correct, but the Supabase migration was never written:

- [ ] `supabase/migrations/0003_trip_party.sql` creating `trip_party`
      and `party_member`
- [ ] Migration applied to the Supabase project
- [ ] `save_trip_party` exercised against real Supabase, not just in-memory

`supabase_service.save_trip_party` will raise at runtime until this
lands. Do not flip `db_provider` to Supabase before then.
