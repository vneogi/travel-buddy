import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:uuid/uuid.dart';

import '../data/signal.dart';
import '../offline/offline_database.dart';
import '../offline/sync_engine.dart';

/// Signal service — THE OFFLINE SEAM (SPEC-02 Part A.3).
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
  }) async {
    try {
      // Queue cap check (SPEC-02 B.3): protect unbounded growth
      final size = await _db.getOutboxSize();
      if (size >= _queueCap) {
        debugPrint('[SignalService] Queue at capacity ($size) — signal throttled');
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
      );

      // STEP 1: Persist to outbox BEFORE any network (durability guarantee)
      final payloadJson = jsonEncode(signal.toJson());
      await _db.enqueue(
        signalId,
        payloadJson,
        capturedAt.toIso8601String(),
      );

      // STEP 2: Trigger background sync (non-awaited — never block UI)
      _syncEngine.triggerSync();
    } catch (e) {
      // NEVER throw from emit — fire-and-forget with local persistence
      debugPrint('[SignalService] emit error (signal may be lost): $e');
    }
  }
}
