import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:flutter/foundation.dart';

import '../core/api_client.dart';
import '../core/api_exception.dart';
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
///
/// Error classification uses TYPED exceptions from ApiClient (not string-matching):
/// - UnauthorizedException → halt sync, preserve events
/// - ServerException / NetworkException → backoff + retry
/// - Other ApiException (403, 404) → permanent failure
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

        // Success (2xx): process the response
        final accepted = (response['accepted'] as int?) ?? 0;
        final duplicates = (response['duplicates'] as int?) ?? 0;
        final rejected = (response['rejected'] as List?) ?? [];

        // Collect IDs that were rejected by the server (permanent failures)
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

      } on UnauthorizedException catch (e) {
        // 401: do NOT drop events — halt sync, preserve for re-auth.
        // SPEC-02 B.2: 'surface re-auth (do NOT drop events)'
        // Rows reset to pending in finally block.
        _lastError = 'Auth expired: ${e.message}';
        debugPrint('[SyncEngine] 401 — halting sync, events preserved');
        return false;

      } on ServerException catch (e) {
        // 5xx: transient — retry with backoff
        _lastError = 'Server error: ${e.message}';
        await _db.markRetry(signalIds, e.message);
        debugPrint('[SyncEngine] 5xx — will retry with backoff');
        return false;

      } on NetworkException catch (e) {
        // No connection: transient — retry with backoff
        _lastError = 'Network: ${e.message}';
        await _db.markRetry(signalIds, e.message);
        debugPrint('[SyncEngine] Network error — will retry with backoff');
        return false;

      } on ApiException catch (e) {
        // Any other API error (403, 404, 422 without per-item detail):
        // These are permanent failures — mark and stop retrying.
        _lastError = 'Permanent: ${e.message}';
        await _db.markFailed(signalIds, 'permanent: ${e.message}');
        debugPrint('[SyncEngine] Permanent failure (${e.runtimeType}) — marked failed');
        return false;
      }

    } catch (e) {
      // Catch-all for unexpected errors (e.g. JSON parse, DB errors).
      // NEVER leave rows stuck 'inflight' — finally handles recovery.
      _lastError = 'Unexpected: $e';
      debugPrint('[SyncEngine] Unexpected error: $e');
      return false;
    } finally {
      // SPEC-02 B.2: reset any lingering 'inflight' in this pass to 'pending'.
      // This is the single-flight pass's cleanup — safe because the guard
      // prevents concurrent syncs from interfering.
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
