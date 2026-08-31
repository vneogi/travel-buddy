import 'package:flutter/foundation.dart';
import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

@immutable
class NodeOutcome {
  static const visited = 'visited';
  static const skipped = 'skipped';

  final String outcome;
  final String? reason;
  final DateTime recordedAt;

  const NodeOutcome({
    required this.outcome,
    required this.recordedAt,
    this.reason,
  });

  bool get wasVisited => outcome == visited;
  bool get wasSkipped => outcome == skipped;
}

/// Local SQLite database for offline-first queue + cache (SPEC-02 Part A).
///
/// Tables:
/// - outbox: outbound signal queue (persist before network, sync later)
/// - cache_trip: cached trip state for offline reads
/// - cache_place: cached venue data for offline reads
/// - cache_trip_list: the self-contained home projection
///
/// Invariant: a user action is durable in outbox BEFORE any network attempt.
class OfflineDatabase {
  static const _dbName = 'travel_buddy_offline.db';
  static const _dbVersion = 6;

  /// Optional path override for testing (pass inMemoryDatabasePath for isolation).
  final String? _testPath;

  Database? _db;

  /// Creates an OfflineDatabase. Pass [testPath] in unit tests to use an
  /// in-memory database (`:memory:`) for full test isolation.
  OfflineDatabase({String? testPath}) : _testPath = testPath;

  /// Lazy-open the database (creates tables on first run).
  Future<Database> get db async {
    final existing = _db;
    if (existing != null) return existing;
    final opened = await _open();
    _db = opened;
    return opened;
  }

  Future<Database> _open() async {
    final String path;
    if (_testPath != null) {
      path = _testPath;
    } else if (kIsWeb) {
      path = _dbName;
    } else {
      path = join(await getDatabasesPath(), _dbName);
    }
    return openDatabase(
      path,
      version: _dbVersion,
      onCreate: _onCreate,
      onUpgrade: _onUpgrade,
    );
  }

  Future<void> _onCreate(Database db, int version) async {
    await db.execute(
      'CREATE TABLE outbox ('
      '  signal_id     TEXT PRIMARY KEY,'
      '  payload_json  TEXT NOT NULL,'
      '  captured_at   TEXT NOT NULL,'
      '  attempts      INTEGER NOT NULL DEFAULT 0,'
      '  next_retry_at TEXT,'
      '  last_error    TEXT,'
      '  state         TEXT NOT NULL'
      ')',
    );
    await db.execute(
      'CREATE INDEX idx_outbox_state ON outbox(state, next_retry_at)',
    );
    await db.execute(
      'CREATE TABLE cache_trip ('
      '  trip_id     TEXT PRIMARY KEY,'
      '  state_json  TEXT NOT NULL,'
      '  cached_at   TEXT NOT NULL'
      ')',
    );
    await db.execute(
      'CREATE TABLE cache_place ('
      '  place_ref   TEXT PRIMARY KEY,'
      '  data_json   TEXT NOT NULL,'
      '  cached_at   TEXT NOT NULL'
      ')',
    );
    await _createTripListCache(db);
    await _createAlertTables(db);
    await _createLovedPlacesTable(db);
    await _createAppKvTable(db);
    await _createNodeOutcomeTable(db);
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      await _createTripListCache(db);
    }
    if (oldVersion < 3) {
      await _createAlertTables(db);
    }
    if (oldVersion < 4) {
      await _createLovedPlacesTable(db);
    }
    if (oldVersion < 5) {
      await _createAppKvTable(db);
    }
    if (oldVersion < 6) {
      await _createNodeOutcomeTable(db);
    }
  }

  Future<void> _createTripListCache(Database db) async {
    await db.execute(
      'CREATE TABLE cache_trip_list ('
      '  cache_key    TEXT PRIMARY KEY,'
      '  list_json    TEXT NOT NULL,'
      '  cached_at    TEXT NOT NULL'
      ')',
    );
  }

  /// SPEC-29: Alert cache and dismissal tables.
  Future<void> _createAlertTables(Database db) async {
    await db.execute(
      'CREATE TABLE alert_cache ('
      '  identity_scope TEXT NOT NULL,'
      '  trip_id        TEXT NOT NULL,'
      '  payload_json   TEXT NOT NULL,'
      '  cached_at      TEXT NOT NULL,'
      '  expires_at     TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, trip_id)'
      ')',
    );
    await db.execute(
      'CREATE TABLE alert_dismissals ('
      '  identity_scope TEXT NOT NULL,'
      '  alert_id       TEXT NOT NULL,'
      '  dismissed_at   TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, alert_id)'
      ')',
    );
  }

  // ============================================================
  // Outbox operations
  // ============================================================

  /// Insert a signal into the outbox (state='pending').
  /// Called BEFORE any network attempt — this is the durability guarantee.
  Future<void> enqueue(String signalId, String payloadJson, String capturedAt) async {
    final database = await db;
    await database.insert(
      'outbox',
      {
        'signal_id': signalId,
        'payload_json': payloadJson,
        'captured_at': capturedAt,
        'attempts': 0,
        'state': 'pending',
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  /// Get pending signals ready to sync (ordered oldest-first).
  Future<List<Map<String, dynamic>>> getPendingBatch({int limit = 50}) async {
    final database = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    return database.query(
      'outbox',
      where: "state = 'pending' AND (next_retry_at IS NULL OR next_retry_at <= ?)",
      whereArgs: [now],
      orderBy: 'captured_at ASC',
      limit: limit,
    );
  }

  /// Mark rows as inflight (being sent).
  Future<void> markInflight(List<String> signalIds) async {
    final database = await db;
    final placeholders = signalIds.map((_) => '?').join(',');
    await database.rawUpdate(
      "UPDATE outbox SET state = 'inflight' WHERE signal_id IN ($placeholders)",
      signalIds,
    );
  }

  /// Delete successfully synced rows.
  Future<void> deleteSynced(List<String> signalIds) async {
    final database = await db;
    final placeholders = signalIds.map((_) => '?').join(',');
    await database.rawDelete(
      "DELETE FROM outbox WHERE signal_id IN ($placeholders)",
      signalIds,
    );
  }

  /// Mark rows as permanently failed (never retry).
  Future<void> markFailed(List<String> signalIds, String error) async {
    final database = await db;
    final placeholders = signalIds.map((_) => '?').join(',');
    await database.rawUpdate(
      "UPDATE outbox SET state = 'failed_permanent', last_error = ? "
      "WHERE signal_id IN ($placeholders)",
      [error, ...signalIds],
    );
  }

  /// Increment attempts and set backoff for transient failures.
  Future<void> markRetry(List<String> signalIds, String error) async {
    final database = await db;
    for (final id in signalIds) {
      final rows = await database.query('outbox', where: 'signal_id = ?', whereArgs: [id]);
      if (rows.isEmpty) continue;
      final attempts = (rows.first['attempts'] as int) + 1;
      final backoffMs = _backoffMs(attempts);
      final nextRetry = DateTime.now().toUtc().add(Duration(milliseconds: backoffMs));
      await database.update(
        'outbox',
        {
          'state': 'pending',
          'attempts': attempts,
          'next_retry_at': nextRetry.toIso8601String(),
          'last_error': error,
        },
        where: 'signal_id = ?',
        whereArgs: [id],
      );
    }
  }

  /// Reset any lingering 'inflight' rows to 'pending' (crash recovery).
  /// SPEC-02 B.2: the classic silent-loss bug — crashed mid-POST rows
  /// must be retried, not stuck forever.
  Future<int> recoverInflight() async {
    final database = await db;
    return database.rawUpdate(
      "UPDATE outbox SET state = 'pending' WHERE state = 'inflight'",
    );
  }

  /// Clear accumulated backoff so pending rows are eligible immediately.
  /// Called when connectivity is regained: a fresh connection invalidates the
  /// reason we were backing off, so users shouldn't wait minutes to sync.
  Future<int> resetBackoff() async {
    final database = await db;
    return database.rawUpdate(
      "UPDATE outbox SET next_retry_at = NULL "
      "WHERE state = 'pending'",
    );
  }

  /// Get counts by state (for sync status debug view).
  Future<Map<String, int>> getOutboxCounts() async {
    final database = await db;
    final result = await database.rawQuery(
      'SELECT state, COUNT(*) as cnt FROM outbox GROUP BY state',
    );
    final counts = <String, int>{};
    for (final row in result) {
      counts[row['state'] as String] = row['cnt'] as int;
    }
    return counts;
  }

  /// Total outbox size (for cap check — SPEC-02 B.3).
  Future<int> getOutboxSize() async {
    final database = await db;
    final result = await database.rawQuery('SELECT COUNT(*) as cnt FROM outbox');
    return (result.first['cnt'] as int?) ?? 0;
  }

  // ============================================================
  // Cache operations (offline reads — SPEC-02 B.4)
  // ============================================================

  /// Cache a trip state.
  Future<void> cacheTrip(String tripId, String stateJson) async {
    final database = await db;
    await database.insert(
      'cache_trip',
      {
        'trip_id': tripId,
        'state_json': stateJson,
        'cached_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// Read cached trip state (returns null if not cached).
  Future<String?> getCachedTrip(String tripId) async {
    final database = await db;
    final rows = await database.query(
      'cache_trip',
      where: 'trip_id = ?',
      whereArgs: [tripId],
    );
    return rows.isEmpty ? null : rows.first['state_json'] as String;
  }

  Future<void> cacheTripList(String cacheKey, String listJson) async {
    final database = await db;
    await database.insert(
      'cache_trip_list',
      {
        'cache_key': cacheKey,
        'list_json': listJson,
        'cached_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<({String json, DateTime cachedAt})?> getCachedTripList(
    String cacheKey,
  ) async {
    final database = await db;
    final rows = await database.query(
      'cache_trip_list',
      where: 'cache_key = ?',
      whereArgs: [cacheKey],
    );
    if (rows.isEmpty) return null;
    return (
      json: rows.first['list_json'] as String,
      cachedAt: DateTime.parse(rows.first['cached_at'] as String),
    );
  }

  /// Cache a place/venue.
  Future<void> cachePlace(String placeRef, String dataJson) async {
    final database = await db;
    await database.insert(
      'cache_place',
      {
        'place_ref': placeRef,
        'data_json': dataJson,
        'cached_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// Read cached place data (returns null if not cached).
  Future<String?> getCachedPlace(String placeRef) async {
    final database = await db;
    final rows = await database.query(
      'cache_place',
      where: 'place_ref = ?',
      whereArgs: [placeRef],
    );
    return rows.isEmpty ? null : rows.first['data_json'] as String;
  }


  /// Durable heart storage (identity-scoped, per-trip).
  Future<void> _createLovedPlacesTable(Database db) async {
    await db.execute(
      'CREATE TABLE loved_places ('
      '  identity_scope TEXT NOT NULL,'
      '  trip_id        TEXT NOT NULL,'
      '  place_ref      TEXT NOT NULL,'
      '  loved_at       TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, trip_id, place_ref)'
      ')',
    );
  }

  // ============================================================
  // Loved-place operations (durable hearts)
  // ============================================================

  /// Persist a loved place (insert-or-ignore: idempotent).
  Future<void> upsertLovedPlace({
    required String identityScope,
    required String tripId,
    required String placeRef,
  }) async {
    final database = await db;
    await database.insert(
      'loved_places',
      {
        'identity_scope': identityScope,
        'trip_id': tripId,
        'place_ref': placeRef,
        'loved_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  /// Retrieve all loved place refs for this identity + trip.
  Future<Set<String>> getLovedPlaceRefs({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final rows = await database.query(
      'loved_places',
      columns: ['place_ref'],
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
    );
    return rows.map((r) => r['place_ref'] as String).toSet();
  }


  /// Minimal durable key-value store for app-level state (e.g. last_session_at).
  Future<void> _createAppKvTable(Database db) async {
    await db.execute(
      'CREATE TABLE app_kv ('
      '  key   TEXT PRIMARY KEY,'
      '  value TEXT NOT NULL'
      ')',
    );
  }

  Future<void> _createNodeOutcomeTable(Database db) async {
    await db.execute(
      'CREATE TABLE node_outcome ('
      '  identity_scope TEXT NOT NULL,'
      '  trip_id        TEXT NOT NULL,'
      '  node_id        TEXT NOT NULL,'
      '  outcome        TEXT NOT NULL,'
      '  reason         TEXT,'
      '  recorded_at    TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, trip_id, node_id)'
      ')',
    );
  }

  Future<void> upsertNodeOutcome({
    required String identityScope,
    required String tripId,
    required String nodeId,
    required String outcome,
    String? reason,
    DateTime? recordedAt,
  }) async {
    if (outcome != NodeOutcome.visited && outcome != NodeOutcome.skipped) {
      throw ArgumentError.value(outcome, 'outcome', 'must be visited or skipped');
    }
    if (outcome == NodeOutcome.skipped && (reason == null || reason.isEmpty)) {
      throw ArgumentError.value(reason, 'reason', 'is required for skipped outcomes');
    }
    if (outcome == NodeOutcome.visited && reason != null) {
      throw ArgumentError.value(reason, 'reason', 'must be null for visited outcomes');
    }

    final database = await db;
    await database.insert(
      'node_outcome',
      {
        'identity_scope': identityScope,
        'trip_id': tripId,
        'node_id': nodeId,
        'outcome': outcome,
        'reason': reason,
        'recorded_at': (recordedAt ?? DateTime.now()).toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  Future<Map<String, NodeOutcome>> getNodeOutcomes({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final rows = await database.query(
      'node_outcome',
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
    );
    return {
      for (final row in rows)
        row['node_id'] as String: NodeOutcome(
          outcome: row['outcome'] as String,
          reason: row['reason'] as String?,
          recordedAt: DateTime.parse(row['recorded_at'] as String),
        ),
    };
  }

  // ============================================================
  // App key-value operations
  // ============================================================

  /// Read a value from the app_kv table (returns null if key absent).
  Future<String?> getAppValue(String key) async {
    final database = await db;
    final rows = await database.query(
      'app_kv',
      columns: ['value'],
      where: 'key = ?',
      whereArgs: [key],
    );
    return rows.isEmpty ? null : rows.first['value'] as String?;
  }

  /// Write a value to the app_kv table (upsert).
  Future<void> setAppValue(String key, String value) async {
    final database = await db;
    await database.insert(
      'app_kv',
      {'key': key, 'value': value},
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  // ============================================================
  // Internal helpers
  // ============================================================

  /// Exponential backoff with jitter (SPEC-02 B.2).
  /// min(2^attempts * 2s, 15min) + random 0-20%.
  int _backoffMs(int attempts) {
    final baseMs = 2000 * (1 << attempts);
    final cappedMs = baseMs.clamp(0, 15 * 60 * 1000);
    final jitter = (cappedMs * 0.2 * (DateTime.now().millisecond / 1000)).round();
    return cappedMs + jitter;
  }

  /// Close the database (for testing).
  Future<void> close() async {
    await _db?.close();
    _db = null;
  }

  // ============================================================
  // Alert cache (SPEC-29)
  // ============================================================

  /// Cache alerts scoped by identity and trip.
  Future<void> cacheAlerts({
    required String identityScope,
    required String tripId,
    required String payloadJson,
    required String expiresAt,
  }) async {
    final database = await db;
    await database.insert(
      'alert_cache',
      {
        'identity_scope': identityScope,
        'trip_id': tripId,
        'payload_json': payloadJson,
        'cached_at': DateTime.now().toUtc().toIso8601String(),
        'expires_at': expiresAt,
      },
      conflictAlgorithm: ConflictAlgorithm.replace,
    );
  }

  /// Retrieve cached alerts (only if not expired).
  Future<String?> getCachedAlerts({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    final rows = await database.query(
      'alert_cache',
      where: 'identity_scope = ? AND trip_id = ? AND expires_at > ?',
      whereArgs: [identityScope, tripId, now],
    );
    if (rows.isEmpty) return null;
    return rows.first['payload_json'] as String?;
  }

  /// Record a dismissed alert.
  Future<void> dismissAlert({
    required String identityScope,
    required String alertId,
  }) async {
    final database = await db;
    await database.insert(
      'alert_dismissals',
      {
        'identity_scope': identityScope,
        'alert_id': alertId,
        'dismissed_at': DateTime.now().toUtc().toIso8601String(),
      },
      conflictAlgorithm: ConflictAlgorithm.ignore,
    );
  }

  /// Get all dismissed alert IDs for this identity.
  Future<Set<String>> getDismissedAlertIds({
    required String identityScope,
  }) async {
    final database = await db;
    final rows = await database.query(
      'alert_dismissals',
      columns: ['alert_id'],
      where: 'identity_scope = ?',
      whereArgs: [identityScope],
    );
    return rows.map((r) => r['alert_id'] as String).toSet();
  }

  /// Prune expired alert cache rows and stale dismissals (> 30 days).
  Future<void> pruneAlertData() async {
    final database = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    await database.delete(
      'alert_cache',
      where: 'expires_at <= ?',
      whereArgs: [now],
    );
    final cutoff = DateTime.now()
        .toUtc()
        .subtract(const Duration(days: 30))
        .toIso8601String();
    await database.delete(
      'alert_dismissals',
      where: 'dismissed_at < ?',
      whereArgs: [cutoff],
    );
  }
}
