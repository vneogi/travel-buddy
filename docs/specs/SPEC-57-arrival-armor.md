# SPEC-57: Arrival Armor (thin slice)

> Status: SLICE 1 ON MAIN (PR #292, `b8a6ac3`), 2026-11-17. Brief:
> `docs/briefs/GENIE_SPEC57_ARRIVAL_ARMOR.md`. Device check waits for the
> owner-return APK. Seed hubs have no fares or scam notes yet (owner
> on-site data). Slice 1b (brightness) not started.
> Amends SPEC-12 (Driver Card) and SPEC-49 (Show-to-driver) for the
> captain-facing arrival surface only. Uses SPEC-10 booking anchors as
> the open trigger. Fare and scam text follow SPEC-17 provenance:
> sourced or absent, never invented.
>
> Source: Nov 2026 moonshot UI/UX draft (owner + product/UI head),
> triaged 2026-11-17. Full moonshot set and phase calls live in
> `VISION.md` section 32 and `UX_BACKLOG.md`.

## Goal

Give the trip captain a calm, offline arrival surface at a transit hub:
fair-fare bounds and scam notes when we have a source, plus a one-tap
path to the existing Driver Card for the destination hotel. Eradicate
curb panic without geofences, background GPS, or backend changes.

## Why this is the near-term moonshot

VISION section 21 (local transport) and section 31 (last-mile arrival)
already name fare bounds and scam warnings as the install-worthy
moment. SPEC-49 already owns hand-to-driver presentation. Arrival Armor
extends that moment; it does not invent a new system.

## Slice 1 (first, Flutter-only)

1. **Open trigger:** traveller taps an overflow item on a locked
   `booking` with `booking_type == flight` whose `geo_region` maps to a
   hub in the local asset. No geofence, no arrival-time auto switch, no
   notification.
2. **Captain HUD** (new screen): hub label; fair-fare band, hard
   ceiling, and official option only when the asset has non-null sourced
   fields; scam notes only when the asset lists them; always a clear
   "ranges are guides, not guarantees" caption when any fare field
   shows. Omit empty sections entirely. Never invent amounts.
3. **Driver path:** a button that opens the existing Driver Card route
   for the next hotel booking on the same trip (earliest hotel with
   `scheduled_start >=` the flight's start, prefer same `geo_region`).
   Hide the button when no such hotel exists. Fare text never appears
   on the Driver Card or in Show-to-driver mode (driver respect).
4. **Offline:** the HUD reads only the bundled asset plus the cached
   itinerary nodes already on the phone. Zero network calls.
5. **High contrast:** use existing theme tokens at large type. No new
   palette.

### Slice 1b (same feature, after slice 1 lands)

Temporary screen-brightness boost while the HUD is open, restored on
exit, route pop, dispose, and app pause. Needs an explicit package
choice and a restore proof. SPEC-49 Show-to-driver still has no
brightness override.

## Data (static asset)

File: `mobile/assets/arrival_hubs.json` (bundled; listed in
`pubspec.yaml`). Shape (ASCII keys):

- `hubs[]`: `id`, `label`, `geo_regions[]`, `booking_types[]`,
  `currency`, `fare_band_low`, `fare_band_high`, `hard_ceiling`,
  `official_option`, `scam_notes[]`, `surveyed_on`, `source`.
- Nullable money and note fields are allowed. Null or missing means
  "do not show", not "unknown amount".
- Seed hubs for the December trip: `znz_airport` (regions
  `zanzibar_tanzania`, `nungwi_tanzania`; booking type `flight`) and
  `stone_town_ferry` (same regions; booking type `train` as the closest
  existing type until SPEC-55 transfer lands). Seed money and scam
  fields as null or empty until the owner records on-site sources.
- Owner updates to the JSON are data PRs; they are not Genie invention.

## Out of scope (this spec)

- Geofenced or time-based auto HUD.
- Background location, BLE, camera, TTS, route deviation.
- Putting a fare on the driver-facing flash card.
- Backend endpoints, migrations, Cloud Run env, or SPEC-23 money engine.
- Ferry-specific booking type (waits on SPEC-55 or a later type).
- "Report the fare I paid" signal (Phase 2; needs a new signal type).

## Constraints

- SPEC-17: every shown amount cites `source` and `surveyed_on`.
- SPEC-43: no new location permission for this feature.
- SPEC-49 brightness rule is amended only for Arrival Armor slice 1b;
  Show-to-driver stays as written.
- ASCII in docs and asset keys. No non-ASCII in Dart comments.

## Acceptance

- Flight booking in a mapped region opens the HUD offline.
- Null fare and empty scam lists produce no invented text and no empty
  section chrome that looks like a missing claim.
- Driver Card button opens the next hotel card when one exists, and is
  absent otherwise.
- Show-to-driver still never shows fare.
- Widget tests cover hub match, empty asset sections, hotel button
  presence and absence, and offline render (no Dio / no sockets).

## Trip relevance

High for Zanzibar Airport and Stone Town ferry curb moments. Content
quality depends on the owner's on-site fare and scam notes.

## Amendment 2026-11-27: ferry rates recorded; official option shows without bands

- Owner recorded the Azam Marine published rates (https://azammarine.com/rates/,
  read 2026-11-27; the page has no publication date and does not name the
  route) as `stone_town_ferry`'s `official_option`, with `source` and
  `surveyed_on`. Fare bands stay null: these are fixed ticket prices, not a
  taxi band.
- The HUD shows the official option and source line even when the hub has no
  fare bands (brief `docs/briefs/GENIE_SPEC57_FERRY_OFFICIAL_OPTION.md`).
  Fare bands and the "guides, not guarantees" caption still show only with
  bands.
- No ferry booking type is added. Scheduling treats `flight` and `train` as
  travel; the ferry hub stays on `train` until SPEC-55.
- Owner to confirm the route the fares cover before the December trip.
