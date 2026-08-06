# SPEC-04 — Offline Vault / Rescue Pack
*Implements VISION capability #7 (calm in the unexpected). P1 per docs/UX_BACKLOG.md.*
*Depends on: SPEC-02 offline cache (`cache_trip`, `cache_place`). No new architecture.*

## Why this exists
Our offline work so far solved **data durability** (signals survive no-signal). It never answered:
*what does the user actually need to DO when stranded?* Lost, no signal, in a country whose script
they can't read, needing to get back to the hotel. The Vault is that answer — and it's a structural
USP: online-only incumbents cannot serve this moment.

## Non-negotiable requirements
1. **Renders with ZERO network**, including on a **cold boot with no connectivity**.
2. **Fast:** usable content on screen in < 500ms from local store.
3. **Reachable in ≤ 2 taps from anywhere** (shield icon in the itinerary top bar).
4. **Never shows a spinner or an error state** — if data is missing, show what we have plus a clear
   "not saved yet" affordance. A blank Vault when stranded is a product failure.
5. **No new DB engine.** Extends the SPEC-02 SQLite cache.

## Contents (v1)
### A. `NativeLanguageAddressCard`  ⭐ the standout
Hotel/accommodation name + address rendered **in the local script** (Lao, Arabic, Georgian, Thai,
Cyrillic…) at large size, full-screen on tap, to **show a taxi driver** with no internet and no
translation app.
- Store BOTH: local-script string AND romanized/English.
- Full-screen mode: max brightness, no chrome, high contrast, address dominant.
- Include a small map thumbnail (cached tile/static image) if available — a picture helps even
  without shared language.
- **Translation is fetched and cached ONLINE, ahead of time** (when the trip/accommodation is set).
  Never attempt translation offline.

### B. `OfflinePassTile`
Cached ticket/boarding-pass QR or barcode.
- Tap → full-screen, **auto-boost screen brightness** (scanners need it), restore on exit.
- v1 scope: user-attached images/PDF pages + any QR string we already hold. **No OCR/parsing.**

### C. Emergency actions grid
- One-tap dial local emergency numbers (per-city, curated static data).
- Hotel/accommodation location pin (cached).
- Saved taxi directions / "take me back" note.
- Consulate/embassy contact if available.

### D. Per-city "if X happens" pack
Small curated static content, bundled or cached per city: lost wallet, sick/pharmacy, missed
transport, common scams, a handful of essential phrases (local script + phonetic).

## Data model (extends SPEC-02 cache — no new engine)
```sql
CREATE TABLE cache_vault (
  vault_id      TEXT PRIMARY KEY,     -- e.g. 'trip:<tripId>'
  trip_id       TEXT NOT NULL,
  payload_json  TEXT NOT NULL,        -- accommodation, contacts, phrases, passes metadata
  cached_at     TEXT NOT NULL
);
CREATE TABLE cache_asset (            -- binary blobs: QR images, map thumbnails, PDF pages
  asset_id      TEXT PRIMARY KEY,
  trip_id       TEXT,
  kind          TEXT NOT NULL,        -- pass_image | map_thumb | doc_page
  bytes         BLOB NOT NULL,
  mime          TEXT,
  cached_at     TEXT NOT NULL
);
```
**Pre-caching rule:** populate `cache_vault` + `cache_asset` **whenever online** — on trip create,
on accommodation set, and on each successful trip fetch. Assume the user will be offline exactly when
they need it. Log a warning if a trip has no vault payload.

## UI
- Route `/vault` (also `/trip/:tripId/vault`); shield icon in the itinerary floating top bar.
- Grid of large tiles (thumb-reachable, glanceable in bright sun): Address • Passes • Emergency • Map.
- Header pill shows cache freshness ("saved 2h ago") — honest, never fake-fresh.
- Tiles with no data render as "Add / not saved yet", never as an error.

## Tests
**Flutter:**
1. Vault renders from `cache_vault` with the API mock throwing `NetworkException` (no network path).
2. Cold-boot: fresh `OfflineDatabase` + seeded cache → content present, no network call attempted.
3. Missing accommodation → "not saved yet" affordance, **no exception, no spinner**.
4. Local-script string renders when present; falls back to romanized when absent.
5. `cache_asset` blob round-trips (write → read → decode).
6. Pre-cache writes `cache_vault` on a successful trip fetch.

**Manual (pre-Laos, real device):** airplane mode → cold boot app → open Vault in ≤2 taps → hotel
address readable in local script at full brightness → emergency dial works offline.

## Out of scope (v1)
Offline vector maps (P3/MapLibre), OCR of tickets, live translation offline, document scanning,
sharing/export.

## Review checklist
- [ ] No network call on the Vault path (test 1 + 2 prove it)
- [ ] Cold boot works (not just warm cache)
- [ ] Missing data → graceful affordance, never error/spinner
- [ ] Local script stored alongside romanized; translation fetched online only
- [ ] Brightness boost restores on exit
- [ ] Uses existing SQLite store — no new DB engine
- [ ] Reachable in ≤ 2 taps
