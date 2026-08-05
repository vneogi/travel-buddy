import 'package:uuid/uuid.dart';

import '../data/signal.dart';
import '../core/api_client.dart';

/// The signal-emission abstraction (THE OFFLINE SEAM).
///
/// All UI code emits signals through this service — never directly via the
/// repository/API client. This lets SPEC-02 swap the implementation from
/// "send immediately" to "enqueue locally, sync later" without touching
/// any UI code. One-place change.
///
/// Current implementation: fire-and-forget POST to /signals.
/// SPEC-02 implementation: enqueue to local SQLite/Hive, sync on reconnect.
class SignalService {
  final ApiClient _api;
  static const _uuid = Uuid();

  SignalService(this._api);

  /// Emit a signal. Fire-and-forget — errors are swallowed (SPEC-02 adds
  /// retry via offline queue).
  Future<void> emit({
    required String signalType,
    required String placeRef,
    String? valueText,
    double? valueNumeric,
    Map<String, dynamic>? valueJson,
    String? tripId,
  }) async {
    final signal = Signal(
      signalId: _uuid.v4(),
      signalType: signalType,
      placeRef: placeRef,
      valueText: valueText,
      valueNumeric: valueNumeric,
      valueJson: valueJson,
      capturedAt: DateTime.now(),
      tripId: tripId,
    );

    try {
      await _sendSignals([signal]);
    } catch (_) {
      // Swallow errors for now — SPEC-02 replaces this with enqueue
    }
  }

  /// Send a batch of signals to the server.
  /// Extracted so SPEC-02 can reuse for sync flush.
  Future<void> _sendSignals(List<Signal> signals) async {
    await _api.post(
      '/signals',
      body: {
        'signals': signals.map((s) => s.toJson()).toList(),
      },
    );
  }
}
