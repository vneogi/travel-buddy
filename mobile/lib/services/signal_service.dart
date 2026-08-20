import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../data/signal.dart';
import '../offline/offline_database.dart';
import '../offline/sync_engine.dart';

/// Signal service -- THE OFFLINE SEAM (SPEC-02 Part A.3).
///
/// UI call sites do NOT change from SPEC-01. The only change is internal:
/// emit() now persists to SQLite outbox BEFORE any network attempt, then
/// triggers a background sync. The UI never awaits network.
///
/// Non-negotiable invariants (SPEC-02):
/// 1. A tap is persisted to local disk BEFORE any network attempt.
/// 2. emit() never throws and never blocks on network.
/// 3. If the app is killed, the event survives (SQLite durability).
class SignalService {
  final OfflineDatabase _db;
  final SyncEngine _syncEngine;
  final _uuid = const Uuid();

  static const int _queueCap = 5000;

  SignalService({
    required OfflineDatabase db,
    required SyncEngine syncEngine,
  })  : _db = db,
        _syncEngine = syncEngine;

  /// Emit a signal. Persists locally, then triggers background sync.
  ///
  /// NEVER throws. NEVER awaits network. Returns immediately after
  /// local persistence. This is the contract UI code depends on.
  Future<void> emit({
    required String signalType,
    required String placeRef,
    String? valueText,
    double? valueNumeric,
    Map<String, dynamic>? valueJson,
    String? tripId,
    String entityType = 'venue',
    String? entityId,
  }) async {
    try {
      // Queue cap check (SPEC-02 B.3): protect unbounded growth
      final size = await _db.getOutboxSize();
      if (size >= _queueCap) {
        debugPrint('[SignalService] Queue at capacity ($size) -- signal throttled');
        return;
      }

      // Build signal with client-generated UUID (idempotency key)
      final signalId = _uuid.v4();
      final capturedAt = DateTime.now().toUtc();

      final signal = Signal(
        signalId: signalId,
        signalType: signalType,
        placeRef: placeRef,
        valueText: valueText,
        valueNumeric: valueNumeric,
        valueJson: valueJson,
        capturedAt: capturedAt,
        tripId: tripId,
        entityType: entityType,
        entityId: entityId,
      );

      // STEP 1: Persist to outbox BEFORE any network (durability guarantee)
      final payloadJson = jsonEncode(signal.toJson());
      await _db.enqueue(
        signalId,
        payloadJson,
        capturedAt.toIso8601String(),
      );

      // STEP 2: Trigger background sync (non-awaited -- never block UI)
      _syncEngine.triggerSync();
    } catch (e) {
      // NEVER throw from emit -- fire-and-forget with local persistence
      debugPrint('[SignalService] emit error (signal may be lost): $e');
    }
  }

  // ===========================================================
  // SPEC-07: Typed emission methods
  // ===========================================================

  Future<void> emitUserLoved({required String placeRef, String? tripId}) =>
      emit(signalType: 'user_loved', placeRef: placeRef, tripId: tripId, valueText: 'loved');

  Future<void> emitRerouteAccepted({required String placeRef, required String replacementRef, String? tripId}) =>
      emit(signalType: 'reroute_accepted', placeRef: placeRef, tripId: tripId, valueJson: {'replacement_ref': replacementRef});

  Future<void> emitRerouteRejected({required String placeRef, required List<String> rejectedRefs, String? tripId}) =>
      emit(signalType: 'reroute_rejected', placeRef: placeRef, tripId: tripId, valueJson: {'rejected_refs': rejectedRefs});

  Future<void> emitVisitedConfirmed({required String placeRef, String? tripId}) =>
      emit(signalType: 'visited_confirmed', placeRef: placeRef, tripId: tripId, valueText: 'true');

  Future<void> emitNodeSkipped({required String placeRef, required String reason, String? tripId}) {
    assert(validSkipReasons.contains(reason), 'Invalid skip reason: $reason');
    return emit(signalType: 'node_skipped', placeRef: placeRef, tripId: tripId, valueJson: {'reason': reason});
  }

  Future<void> emitDishLoved({required String placeRef, required String dishName, required String dishId, String? tripId}) =>
      emit(signalType: 'dish_loved', placeRef: placeRef, tripId: tripId, valueText: 'loved', valueJson: {'dish_name': dishName}, entityType: 'dish', entityId: dishId);

  Future<void> emitDishOrdered({required String placeRef, required String dishName, required String dishId, String? tripId}) =>
      emit(signalType: 'dish_ordered', placeRef: placeRef, tripId: tripId, valueText: 'true', valueJson: {'dish_name': dishName}, entityType: 'dish', entityId: dishId);

  // ===========================================================
  // SPEC-12: Driver card signals
  // ===========================================================

  Future<void> emitDriverCardShown({
    required String placeRef,
    required bool wasOffline,
    required String nameSource,
    String? tripId,
  }) =>
      emit(
        signalType: 'driver_card_shown',
        placeRef: placeRef,
        tripId: tripId,
        valueJson: {
          'place_ref': placeRef,
          'was_offline': wasOffline,
          'name_source': nameSource,
        },
      );

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

  Future<void> emitNameConfirmed({
    required String placeRef,
    required String lang,
    required String shownValue,
    required String verdict,
    String? tripId,
  }) {
    assert(verdict == 'confirmed' || verdict == 'rejected',
        'Invalid verdict: $verdict');
    return emit(
      signalType: 'name_confirmed',
      placeRef: placeRef,
      tripId: tripId,
      valueJson: {
        'place_ref': placeRef,
        'lang': lang,
        'shown_value': shownValue,
        'verdict': verdict,
      },
    );
  }

  static const validSkipReasons = {'too_far', 'too_tired', 'closed', 'crowded', 'not_interested', 'ran_out_of_time', 'weather'};
}
