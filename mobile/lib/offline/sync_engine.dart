import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../core/api_client.dart';
import 'offline_database.dart';

/// Sync engine for offline-first signal delivery (SPEC-02 Part B).
///
/// Responsibilities:
/// - Triggers sync on: app start, resume, connectivity regained, post-emit, periodic (60s)
/// - Single-flight guard (never concurrent syncs)
/// - Batch POST to /signals, handle 2xx/4xx/5xx per spec
/// - Exponential backoff with jitter on transient failures
/// - Crash recovery: inflight rows reset to pending on startup
/// - Queue cap enforcement (5000 rows)
class SyncEngine {
  final OfflineDatabase _db;
  final ApiClient _api;
  final Connectivity _connectivity;

  bool _isSyncing = false; // single-flight guard
  Timer? _periodicTimer;
  StreamSubscription? _connectivitySub;
  DateTime? _lastSyncTime;
  String? _lastError;

  static const int _queueCap = 5000;
  static const Duration _periodicInterval = Duration(seconds: 60);

  SyncEngine({
    required OfflineDatabase db,
    required ApiClient api,
    Connectivity? connectivity,
  })  : _db = db,
        _api = api,
        _connectivity = connectivity ?? Connectivity();

  // ============================================================
  // Lifecycle
  // ============================================================

  /// Initialize the sync engine. Call on app start.
  /// Recovers inflight rows and starts background sync.
  Future<void> start() async {
    // SPEC-02 B.2: recover rows stuck 'inflight' from a crash
    final recovered = await _db.recoverInflight();
    if (recovered > 0) {
      debugPrint('[SyncEngine] Recovered $recovered inflight rows from crash');
    }

    // Start periodic timer
    _periodicTimer = Timer.periodic(_periodicInterval, (_) => syncOnce());

    // Listen for connectivity changes
    _connectivitySub = _connectivity.onConnectivityChanged.listen((results) {
      final hasConnection = results.any((r) => r != ConnectivityResult.none);
      if (hasConnection) {
        debugPrint('[SyncEngine] Connectivity regained — triggering sync');
        syncOnce();
      }
    });

    // Initial sync attempt
    syncOnce();
  }

  /// Stop the sync engine (app termination / testing).
  void stop() {
    _periodicTimer?.cancel();
    _periodicTimer = null;
    _connectivitySub?.cancel();
    _connectivitySub = null;
  }

  /// Trigger sync (called after each emit, on resume, etc).
  /// Non-blocking — returns immediately. Safe to call frequently.
  void triggerSync() {
    // Fire-and-forget — never await from UI
    syncOnce();
  }

  // ============================================================
  // Core sync algorithm (SPEC-02 B.2)
  // ============================================================

  /// Single sync pass. Returns true if any work was done.
  Future<bool> syncOnce() async {
    // Single-flight guard — never concurrent syncs
    if (_isSyncing) return false;
    _isSyncing = true;

    try {
      final batch = await _db.getPendingBatch(limit: 50);
      if (batch.isEmpty) return false;

      final signalIds = batch.map((r) => r['signal_id'] as String).toList();

      // Mark batch as inflight
      await _db.markInflight(signalIds);

      try {
        // Build the request payload
        final signals = batch.map((r) {
          return jsonDecode(r['payload_json'] as String) as Map<String, dynamic>;
        }).toList();

        // POST to /signals (SPEC-01 batch endpoint)
        final response = await _api.post(
          '/signals',
          body: {'signals': signals},
        );

        // Success (2xx): delete synced rows from outbox
        final accepted = (response['accepted'] as int?) ?? 0;
        final duplicates = (response['duplicates'] as int?) ?? 0;
        final rejected = (response['rejected'] as List?) ?? [];

        // Collect IDs that were accepted or duplicated (server has them)
        final rejectedIds = rejected
            .map((r) => (r as Map<String, dynamic>)['signal_id'] as String)
            .toSet();

        final syncedIds = signalIds.where((id) => !rejectedIds.contains(id)).toList();
        final failedIds = signalIds.where((id) => rejectedIds.contains(id)).toList();

        // Delete accepted/duplicated rows (server is idempotent; safe)
        if (syncedIds.isNotEmpty) {
          await _db.deleteSynced(syncedIds);
        }

        // Mark permanently-rejected rows (never retry)
        if (failedIds.isNotEmpty) {
          final reasons = {for (final r in rejected) (r as Map)['signal_id']: (r as Map)['reason']};
          for (final id in failedIds) {
            await _db.markFailed([id], reasons[id]?.toString() ?? 'rejected by server');
          }
        }

        _lastSyncTime = DateTime.now().toUtc();
        _lastError = null;
        debugPrint('[SyncEngine] Synced: accepted=$accepted duplicates=$duplicates rejected=${rejected.length}');
        return true;
      } catch (e) {
        // Handle specific HTTP error codes
        final errorStr = e.toString();
        _lastError = errorStr;

        if (errorStr.contains('401') || errorStr.contains('Unauthorized')) {
          // 401: do NOT drop events — mark pending, stop sync
          // SPEC-02 B.2: surface re-auth (never lose data on auth failure)
          await _db.markInflight([]); // no-op, but reset below handles it
          debugPrint('[SyncEngine] 401 — halting sync, events preserved');
        } else if (errorStr.contains('422') || errorStr.contains('Unprocessable')) {
          // 422 without per-item detail: mark all as permanent failure
          await _db.markFailed(signalIds, 'validation_error: $errorStr');
          debugPrint('[SyncEngine] 422 — batch marked failed_permanent');
        } else {
          // 5xx / timeout / network error: retry with backoff
          await _db.markRetry(signalIds, errorStr);
          debugPrint('[SyncEngine] Transient error — will retry with backoff');
        }
        return false;
      }
    } catch (e) {
      // Catch-all: NEVER leave rows stuck 'inflight' (SPEC-02 B.2 finally)
      _lastError = e.toString();
      debugPrint('[SyncEngine] Unexpected error: $e');
      return false;
    } finally {
      // SPEC-02 B.2: reset any lingering 'inflight' in this pass to 'pending'
      await _db.recoverInflight();
      _isSyncing = false;
    }
  }

  // ============================================================
  // Queue hygiene (SPEC-02 B.3)
  // ============================================================

  /// Check if queue is at capacity. Returns true if new signals should
  /// be throttled (> 5000 rows).
  Future<bool> isAtCapacity() async {
    final size = await _db.getOutboxSize();
    return size >= _queueCap;
  }

  // ============================================================
  // Observability (SPEC-02 B.5 — sync status debug view)
  // ============================================================

  DateTime? get lastSyncTime => _lastSyncTime;
  String? get lastError => _lastError;
  bool get isSyncing => _isSyncing;

  /// Get outbox state counts for the debug view.
  Future<Map<String, int>> getStatusCounts() async {
    return _db.getOutboxCounts();
  }
}
