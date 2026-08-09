/// Signal data model for the flywheel data asset (SPEC-01 Part B).
///
/// Each signal has a client-generated [signalId] (UUID) that serves as the
/// idempotency key — the server upserts on it, so retries (including from
/// an offline queue in SPEC-02) never create duplicates.
class Signal {
  final String signalId;
  final String signalType;
  final String placeRef;
  final String? valueText;
  final double? valueNumeric;
  final Map<String, dynamic>? valueJson;
  final DateTime capturedAt;
  final String? tripId;
  final String entityType; // 'venue' | 'dish' | 'area' | 'transit_leg'
  final String? entityId;  // FK to the entity (dish_id for dish signals)

  Signal({
    required this.signalId,
    required this.signalType,
    required this.placeRef,
    this.valueText,
    this.valueNumeric,
    this.valueJson,
    required this.capturedAt,
    this.tripId,
    this.entityType = 'venue',
    this.entityId,
  });

  Map<String, dynamic> toJson() => {
        'signal_id': signalId,
        'signal_type': signalType,
        'place_ref': placeRef,
        'entity_type': entityType,
        if (entityId != null) 'entity_id': entityId,
        if (valueText != null) 'value_text': valueText,
        if (valueNumeric != null) 'value_numeric': valueNumeric,
        if (valueJson != null) 'value_json': valueJson,
        'captured_at': capturedAt.toUtc().toIso8601String(),
        if (tripId != null) 'trip_id': tripId,
      };
}
