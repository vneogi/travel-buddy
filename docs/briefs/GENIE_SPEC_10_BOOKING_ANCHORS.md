# Genie Brief -- SPEC-10 Booking Anchors (Manual Floor & Import Degradation)

> Status: READY TO IMPLEMENT. Paste this entire file to Genie Code.
> Land via PR to main, not direct push. Owner has no laptop -- unit and
> widget tests + flutter analyze in CI.

Canonical spec: `docs/specs/SPEC-10-booking-anchors.md`
Normalisation: `docs/specs/SPEC-16-itinerary-normalisation.md`
Signal registry: `docs/specs/SPEC-06-behavioral-signals.md`
Rules: `docs/ENGINEERING_RULES.md` (R1, R3, R5, R14, R16, R17)

## Goal

Let the traveller record bookings (flight, hotel, train, tour) as immovable
anchors, so the engine plans around the trip that actually exists.

1. **Data Model:** A booking is a locked node (`is_locked: true`, `node_kind: 'booking'`)
   with extra metadata (`booking_type`, `confirmation_code`, `booking_notes`, `import_source`).
   All new fields MUST have safe defaults so legacy trip JSON deserializes cleanly.
2. **Import & Degradation Floor:** On-device text/paste extraction (`extractBookingFromText`)
   extracts booking fields with zero network calls and pre-fills the manual entry
   form. Malformed input degrades gracefully to empty/partial fields; it never throws.
3. **Scheduler:** Booking nodes are immovable anchors (`is_locked: true`).
   `reschedule_and_validate` never moves their `scheduled_start`, and raises a hard
   conflict warning if preceding activities + transit overrun into a locked booking.
4. **Privacy:** `confirmation_code` is private to the user/node -- NEVER logged in
   plaintext and NEVER included in signal telemetry.
5. **Signal:** Register `booking_added` with `value_json: {booking_type, import_source}`
   in `models/signal_types.py` and migration `0021_booking_anchors.sql`.
6. **UI:** Visually distinct locked booking cards in `ActivityCard` (flight/hotel/train/tour
   icons + locked indicator) and an `AddBookingSheet` entry form accessible from
   the itinerary screen.

## Deliverables in this PR

1. `models/signal_types.py` -- Register `booking_added` (json).
2. `supabase/migrations/0021_booking_anchors.sql` -- Add columns to `trip_node` and seed `booking_added`.
3. `models/schemas.py` -- Add `ADD_BOOKING` to `EventType`; add `node_kind`, `booking_type`, `confirmation_code`, `booking_notes`, `import_source` to `TripNode`.
4. `services/itinerary_normaliser.py` -- Roundtrip booking metadata in `decompose_trip`, `compose_trip_nodes`, and `round_trip_equal`.
5. `services/scheduler.py` -- Enforce `is_locked=True` on booking nodes; hard conflict on overrun; immutable start times.
6. `agents/state_machine.py` -- Handle `add_booking` event in structural edits; insert booking node in chronological order.
7. `mobile/lib/data/models.dart` -- Add `addBooking` event and booking fields to Dart `TripNode` with safe defaults.
8. `mobile/lib/services/signal_service.dart` -- Add `emitBookingAdded`.
9. `mobile/lib/features/booking/booking_parser.dart` -- On-device regex/text parser with graceful degradation.
10. `mobile/lib/features/booking/add_booking_sheet.dart` -- Booking entry sheet with type picker, manual inputs, paste-and-parse auto-fill, and signal emission.
11. `mobile/lib/widgets/activity_card.dart` & `mobile/lib/features/itinerary/itinerary_screen.dart` -- Distinct booking card UI and "+ Add Booking" affordance.
12. Tests: Backend `tests/test_booking_anchors.py` + Flutter `mobile/test/features/booking/` with 4 named sabotage proofs.

---

## 1. Schema, Signals & Normalisation (Python + SQL)

### `models/signal_types.py`

Add to `SIGNAL_TYPES`:
```python
    "booking_added": "json",
```

Add to `PAYLOAD_SHAPES`:
```python
    "booking_added": "json: {booking_type: str, import_source: str}",
```

### `supabase/migrations/0021_booking_anchors.sql`

```sql
-- =============================================================================
-- Migration: 0021_booking_anchors.sql
-- Description: Add booking metadata columns to trip_node (SPEC-10)
--              and register booking_added signal type.
-- Depends on: 0014_itinerary_normalisation.sql (trip_node table),
--             0002_signals_core.sql (signal_type table)
-- =============================================================================

-- Add booking anchor columns to trip_node (all nullable or defaulted)
ALTER TABLE trip_node
    ADD COLUMN IF NOT EXISTS node_kind TEXT NOT NULL DEFAULT 'activity',
    ADD COLUMN IF NOT EXISTS booking_type TEXT NULL,
    ADD COLUMN IF NOT EXISTS confirmation_code TEXT NULL,
    ADD COLUMN IF NOT EXISTS booking_notes TEXT NULL,
    ADD COLUMN IF NOT EXISTS import_source TEXT NULL;

-- Register booking_added signal type
INSERT INTO signal_type (key, category, value_kind, enum_values, decay_policy, description) VALUES
    ('booking_added', 'explicit_user', 'json', NULL, 'none',
     'Traveller recorded a booking anchor (flight, hotel, train, tour)')
ON CONFLICT (key) DO NOTHING;
```

### `models/schemas.py`

Add `ADD_BOOKING` to `EventType`:
```python
class EventType(str, Enum):
    # ...
    ADD_BOOKING = "add_booking"
```

Add fields with defaults to `TripNode`:
```python
class TripNode(BaseModel):
    node_id: str = Field(default_factory=lambda: generate_node_id())
    venue_name: str
    venue_id: Optional[str] = None
    scheduled_start: datetime
    duration_minutes: int = 90
    is_locked: bool = False
    status: NodeStatus = NodeStatus.PENDING
    micro_location: Optional[str] = None
    vibe_tags: List[str] = []
    lat: Optional[float] = None
    lng: Optional[float] = None
    opening_hours: Optional[str] = None
    geo_region: Optional[str] = None
    names_local: Optional[Dict[str, Any]] = None
    landmarks_local: Optional[Dict[str, Any]] = None
    nearest_landmark: Optional[str] = None
    # SPEC-10: Booking anchor fields
    node_kind: str = "activity"  # "activity" | "booking"
    booking_type: Optional[str] = None  # "flight" | "hotel" | "train" | "tour"
    confirmation_code: Optional[str] = None
    booking_notes: Optional[str] = None
    import_source: Optional[str] = None  # "manual" | "email" | "pdf" | "screenshot"
```

### `services/itinerary_normaliser.py`

Update `decompose_trip`:
```python
        node_row = {
            "node_id": node_id,
            "trip_id": trip_id,
            "day_index": 0,
            "seq": (i + 1) * _SEQ_GAP,
            "node_type": n.get("booking_type") or "activity",
            "venue_ref": n.get("venue_id"),
            "title": n.get("venue_name", "Untitled"),
            "scheduled_start": sched_start,
            "scheduled_end": sched_end,
            "duration_minutes": duration,
            "is_locked": n.get("is_locked", False) or n.get("node_kind") == "booking",
            "status": status,
            "geo_region": n.get("geo_region") or trip_geo,
            "micro_location": n.get("micro_location"),
            "lat": n.get("lat"),
            "lng": n.get("lng"),
            "vibe_tags": n.get("vibe_tags", []),
            "opening_hours": n.get("opening_hours"),
            "node_kind": n.get("node_kind", "activity"),
            "booking_type": n.get("booking_type"),
            "confirmation_code": n.get("confirmation_code"),
            "booking_notes": n.get("booking_notes"),
            "import_source": n.get("import_source"),
            "names_local": n.get("names_local"),
            "landmarks_local": n.get("landmarks_local"),
            "nearest_landmark": n.get("nearest_landmark"),
        }
```

Update `compose_trip_nodes`:
```python
        node = {
            "node_id": row["node_id"],
            "venue_name": row["title"],
            "venue_id": row.get("venue_ref"),
            "scheduled_start": row["scheduled_start"],
            "duration_minutes": row["duration_minutes"],
            "is_locked": row["is_locked"],
            "status": status_rmap.get(row["status"], "pending"),
            "micro_location": row.get("micro_location"),
            "vibe_tags": row.get("vibe_tags", []),
            "lat": row.get("lat"),
            "lng": row.get("lng"),
            "opening_hours": row.get("opening_hours"),
            "geo_region": row.get("geo_region"),
            "names_local": row.get("names_local"),
            "landmarks_local": row.get("landmarks_local"),
            "nearest_landmark": row.get("nearest_landmark"),
            "node_kind": row.get("node_kind", "activity"),
            "booking_type": row.get("booking_type"),
            "confirmation_code": row.get("confirmation_code"),
            "booking_notes": row.get("booking_notes"),
            "import_source": row.get("import_source"),
        }
```

Update `round_trip_equal`: add `"node_kind"`, `"booking_type"`, `"confirmation_code"`, `"booking_notes"`, `"import_source"` to the round-trip key list.

---

## 2. Scheduler & State Machine

### `services/scheduler.py`

In `reschedule_and_validate`:
Ensure booking nodes are always treated as locked anchors:
```python
    for node in active:
        if node.node_kind == "booking" or node.booking_type is not None:
            node.is_locked = True
```
When `node.is_locked` is true, `start = node.scheduled_start` is never changed.
If `earliest is not None and earliest > node.scheduled_start`:
`has_hard_conflict = True` and add a clear warning:
`f"Locked booking '{node.venue_name}' at {node.scheduled_start.strftime('%H:%M')} is unreachable -- previous stop + {transit_min} min transit runs {over} min over."`

### `agents/state_machine.py`

Add `EventType.ADD_BOOKING.value` to `STRUCTURAL_EDIT_EVENTS` in `agents/state_machine.py`.
In `_node_apply_structural`, handle `EventType.ADD_BOOKING.value`:
```python
        if event_type == EventType.ADD_BOOKING.value:
            prefs = state.get("preferences") or {}
            raw_start = prefs.get("scheduled_start") or state.get("message")
            try:
                if isinstance(raw_start, str):
                    start_dt = datetime.fromisoformat(raw_start.replace("Z", "+00:00"))
                else:
                    start_dt = raw_start or datetime.now(tz=timezone.utc)
            except Exception:
                start_dt = datetime.now(tz=timezone.utc)

            booking_node = TripNode(
                venue_name=prefs.get("venue_name") or prefs.get("title") or "Booking",
                scheduled_start=start_dt,
                duration_minutes=int(prefs.get("duration_minutes", 90)),
                is_locked=True,
                status=NodeStatus.PENDING,
                micro_location=prefs.get("micro_location"),
                lat=prefs.get("lat"),
                lng=prefs.get("lng"),
                node_kind="booking",
                booking_type=prefs.get("booking_type", "flight"),
                confirmation_code=prefs.get("confirmation_code"),
                booking_notes=prefs.get("booking_notes"),
                import_source=prefs.get("import_source", "manual"),
            )
            # Insert in chronological order by scheduled_start
            inserted = False
            for i, n in enumerate(nodes):
                if n.scheduled_start > booking_node.scheduled_start:
                    nodes.insert(i, booking_node)
                    inserted = True
                    break
            if not inserted:
                nodes.append(booking_node)
            return nodes
```

**Privacy invariant:** In `agents/state_machine.py` and `services/llm_service.py`, never log `confirmation_code` in plaintext.

---

## 3. Flutter Data Models & Signal Service

### `mobile/lib/data/models.dart`

Add to `EventType`:
```dart
enum EventType {
  // ...
  addBooking('add_booking'),
  // ...
```

Add to `TripNode`:
```dart
  final String nodeKind;
  final String? bookingType;
  final String? confirmationCode;
  final String? bookingNotes;
  final String? importSource;

  const TripNode({
    // ... existing fields ...
    this.nodeKind = 'activity',
    this.bookingType,
    this.confirmationCode,
    this.bookingNotes,
    this.importSource,
  });
```

In `TripNode.fromJson`:
```dart
        nodeKind: (j['node_kind'] as String?) ?? 'activity',
        bookingType: j['booking_type'] as String?,
        confirmationCode: j['confirmation_code'] as String?,
        bookingNotes: j['booking_notes'] as String?,
        importSource: j['import_source'] as String?,
```

### `mobile/lib/services/signal_service.dart`

Add typed emission helper:
```dart
  Future<void> emitBookingAdded({
    required String bookingType,
    required String importSource,
    String? placeRef,
    String? tripId,
  }) =>
      emit(
        signalType: 'booking_added',
        placeRef: placeRef ?? 'booking',
        tripId: tripId,
        valueJson: {
          'booking_type': bookingType,
          'import_source': importSource,
        },
      );
```

---

## 4. On-Device Text Extractor & Parser

Create `mobile/lib/features/booking/booking_parser.dart`:

```dart
class ParsedBooking {
  final String? bookingType; // 'flight' | 'hotel' | 'train' | 'tour'
  final String? venueName;
  final DateTime? scheduledStart;
  final int? durationMinutes;
  final String? confirmationCode;
  final String? notes;
  final String importSource; // 'email' | 'screenshot' | 'manual'

  const ParsedBooking({
    this.bookingType,
    this.venueName,
    this.scheduledStart,
    this.durationMinutes,
    this.confirmationCode,
    this.notes,
    this.importSource = 'manual',
  });
}

/// Zero-network, on-device regex & keyword extractor.
/// Degrades gracefully to partial/empty fields -- NEVER throws on malformed text.
ParsedBooking extractBookingFromText(String rawText, {String importSource = 'email'}) {
  if (rawText.trim().isEmpty) {
    return ParsedBooking(importSource: importSource);
  }

  final text = rawText.trim();
  final lower = text.toLowerCase();

  // 1. Detect booking type
  String? bookingType;
  if (lower.contains('flight') || lower.contains('airline') || lower.contains('boarding pass') || lower.contains('terminal')) {
    bookingType = 'flight';
  } else if (lower.contains('hotel') || lower.contains('check-in') || lower.contains('resort') || lower.contains('stay')) {
    bookingType = 'hotel';
  } else if (lower.contains('train') || lower.contains('railway') || lower.contains('station')) {
    bookingType = 'train';
  } else if (lower.contains('tour') || lower.contains('guide') || lower.contains('excursion')) {
    bookingType = 'tour';
  }

  // 2. Extract confirmation code (e.g. PNR: ABC123, Confirmation #12345, Booking ref: XYZ)
  String? confirmationCode;
  final codeRegex = RegExp(r'(?:pnr|confirmation|booking\s*(?:ref|id|number|code)?|reservation\s*#?)\s*[:#]?\s*([A-Z0-9]{5,10})', caseSensitive: false);
  final codeMatch = codeRegex.firstMatch(text);
  if (codeMatch != null) {
    confirmationCode = codeMatch.group(1);
  }

  // 3. Extract title/venue hint
  String? venueName;
  final lines = text.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
  if (lines.isNotEmpty) {
    // Pick first line under 50 chars as venue title fallback
    venueName = lines.first.length <= 50 ? lines.first : lines.first.substring(0, 50);
  }

  return ParsedBooking(
    bookingType: bookingType,
    venueName: venueName,
    confirmationCode: confirmationCode,
    durationMinutes: bookingType == 'hotel' ? 480 : (bookingType == 'flight' ? 180 : 90),
    importSource: importSource,
  );
}
```

---

## 5. UI: Booking Entry Sheet & Activity Card

### `mobile/lib/features/booking/add_booking_sheet.dart`

Modal bottom sheet for booking entry:
- Booking Type choice chips: `Flight`, `Hotel`, `Train`, `Tour`.
- Title / Venue input field.
- Date and Time picker (sets `scheduledStart`).
- Duration picker (defaults to 180m for flight, 480m for hotel, etc.).
- Optional Confirmation Code input.
- Optional Notes input.
- **Import / Paste Box:**
  - ExpansionTile / Textfield: *"Paste confirmation text / email"*.
  - *"Auto-fill"* button calls `extractBookingFromText` and populates the form fields.
- **Save Anchor Button:**
  - Submits event via `ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(type: EventType.addBooking, message: 'Add booking anchor', preferences: {...})`.
  - Emits signal: `ref.read(signalServiceProvider).emitBookingAdded(bookingType: ..., importSource: ..., tripId: ...)`.
  - Pops sheet.

### `mobile/lib/widgets/activity_card.dart`

Visually distinct booking representation when `node.nodeKind == 'booking'` or `node.bookingType != null`:
- Distinct leading icon based on `bookingType`:
  - `flight`: `Icons.flight_takeoff`
  - `hotel`: `Icons.hotel`
  - `train`: `Icons.train`
  - `tour`: `Icons.explore`
  - default: `Icons.bookmark_border`
- Badge: `[BOOKING: Flight]` or `[BOOKING: Hotel]` with `Icons.lock` (accent color).
- If `confirmationCode != null && confirmationCode.isNotEmpty`: display `Code: ${node.confirmationCode}` in caption.
- Resists swipe to swap / cancel (booking nodes are immovable anchors).

### `mobile/lib/features/itinerary/itinerary_screen.dart`

Add "+ Add Booking" affordance (e.g. FloatingActionButton or AppBar action) that displays `AddBookingSheet`.

---

## 6. Tests & Sabotage Proofs (R17)

### Backend: `tests/test_booking_anchors.py`

1. **`test_legacy_trip_node_deserializes_with_safe_defaults`**:
   - TripNode JSON without `node_kind`, `booking_type`, etc. loads cleanly with `node_kind="activity"`, `booking_type=None`, `is_locked=False`.
2. **`test_booking_anchor_is_always_locked`**:
   - A node created with `node_kind="booking"` has `is_locked=True`.
3. **`test_booking_anchor_scheduled_start_never_moves`**:
   - Rescheduling an itinerary with a locked booking anchor keeps `scheduled_start` identical.
4. **`test_scheduler_flags_hard_conflict_on_booking_overrun`**:
   - Activity scheduled 08:00 for 90 min + 60 min transit before a 09:30 locked flight raises `has_hard_conflict=True`.
5. **`test_itinerary_normaliser_preserves_booking_metadata`**:
   - `decompose_trip` and `compose_trip_nodes` roundtrip all 5 booking fields.
6. **`test_booking_added_signal_drift_guard_and_ingest`**:
   - `booking_added` is accepted by `/api/v1/signals` with `{booking_type: 'flight', import_source: 'email'}`.
7. **`test_confirmation_code_not_in_signal_or_logs`**:
   - `booking_added` payload only carries `booking_type` and `import_source`.

### Mobile Flutter Tests: `mobile/test/features/booking/`

1. **`extractBookingFromText extracts flight and code without network`**:
   - Input: `"Booking Confirmed! Flight EK501 to Dubai. PNR: AB12CD"`
   - Output: `bookingType == 'flight'`, `confirmationCode == 'AB12CD'`, `importSource == 'email'`.
2. **`extractBookingFromText degrades on malformed text without throwing`**:
   - Input: `""` or `"gibberish 123456789 !!!"`
   - Output: Does not throw, returns `ParsedBooking` with null type and code.
3. **`TripNode fromJson handles booking fields and defaults`**:
   - Validates JSON deserialization.
4. **`emitBookingAdded enqueues outbox record without confirmation code`**:
   - Verifies SQLite outbox row has `booking_type` and `import_source` and no code.

### Sabotage Proofs (R17)
- **Sabotage 1:** In `services/scheduler.py`, allow `node.is_locked` booking nodes to be pushed by `earliest`.
  - Named test `test_booking_anchor_scheduled_start_never_moves` must FAIL.
- **Sabotage 2:** In `SignalService.emitBookingAdded`, add `'confirmation_code'` to `valueJson`.
  - Named test `test_confirmation_code_not_in_signal_or_logs` must FAIL.
- **Sabotage 3:** In `extractBookingFromText`, throw `FormatException` on empty input.
  - Named test `test_malformed_import_degrades_without_throwing` must FAIL.
- **Sabotage 4:** In `TripNode` schema, make `node_kind` required with no default.
  - Named test `test_legacy_trip_node_deserializes_with_safe_defaults` must FAIL.

---

## Proof Checklist before PR

- `grep -rn '\\$' mobile/lib` -- only upgrade_screen price strings (R1)
- `flutter analyze --no-fatal-infos` -- 0 errors, 0 warnings
- `flutter test` -- all unit and widget tests pass
- Python: `pytest -q -ra` clean, `ruff check .` clean, `ruff format --check .` clean
- All living docs and comments pure ASCII (R14)

## PR Details

- Branch: `feat/spec-10-booking-anchors`
- Title: `feat(core): SPEC-10 booking anchors, locked scheduler rules, manual & import floor, signals`
- Body: Summary of deliverables, verification evidence, sabotage proofs.
