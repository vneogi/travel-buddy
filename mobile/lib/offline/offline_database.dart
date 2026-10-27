import 'package:flutter/foundation.dart';
import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

import 'offline_open.dart';

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
  static const _dbVersion = 9;

  /// Optional path override for testing (pass inMemoryDatabasePath for isolation).
  final String? _testPath;

  Database? _db;
  Future<Database>? _opening;

  /// Creates an OfflineDatabase. Pass [testPath] in unit tests to use an
  /// in-memory database (`:memory:`) for full test isolation.
  OfflineDatabase({String? testPath}) : _testPath = testPath;

  /// Lazy-open the database (creates tables on first run).
  Future<Database> get db async {
    final existing = _db;
    if (existing != null) return existing;
    final opening = _opening;
    if (opening != null) return opening;

    final nextOpening = _open();
    _opening = nextOpening;
    try {
      final opened = await nextOpening;
      _db = opened;
      return opened;
    } finally {
      _opening = null;
    }
  }

  Future<Database> _open() async {
    final testPath = _testPath;
    if (testPath != null) {
      // Tests: unencrypted in-memory / temp-file database.
      return openDatabase(
        testPath,
        version: _dbVersion,
        onCreate: _onCreate,
        onUpgrade: _onUpgrade,
      );
    }
    final String path;
    if (kIsWeb) {
      path = _dbName;
    } else {
      path = join(await getDatabasesPath(), _dbName);
    }
    // SPEC-43 Gap 5: Android/iOS open with SQLCipher; web/desktop stay
    // unencrypted this slice (see offline_open_io.dart).
    return openOfflineStore(
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
    await _createScopedTripAndPlaceCache(db);
    await _createTripListCache(db);
    await _createAlertTables(db);
    await _createLovedPlacesTable(db);
    await _createAppKvTable(db);
    await _createNodeOutcomeTable(db);
    await _createNotificationTables(db);
    await _createAskThreadTables(db);
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
    if (oldVersion < 7) {
      await _createNotificationTables(db);
    }
    if (oldVersion < 8) {
      await _createAskThreadTables(db);
    }
    if (oldVersion < 9) {
      // SPEC-43 Gap 12: unscoped cache rows have no owner. Drop them
      // (fail closed) and rebuild with identity_scope in the primary key.
      await db.execute('DROP TABLE IF EXISTS cache_trip');
      await db.execute('DROP TABLE IF EXISTS cache_place');
      await _createScopedTripAndPlaceCache(db);
    }
  }

  /// SPEC-43 Gap 12: trip and place caches keyed by identity scope.
  Future<void> _createScopedTripAndPlaceCache(Database db) async {
    await db.execute(
      'CREATE TABLE cache_trip ('
      '  identity_scope TEXT NOT NULL,'
      '  trip_id        TEXT NOT NULL,'
      '  state_json     TEXT NOT NULL,'
      '  cached_at      TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, trip_id)'
      ')',
    );
    await db.execute(
      'CREATE TABLE cache_place ('
      '  identity_scope TEXT NOT NULL,'
      '  place_ref      TEXT NOT NULL,'
      '  data_json      TEXT NOT NULL,'
      '  cached_at      TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, place_ref)'
      ')',
    );
  }

  /// SPEC-43 Gap 12: a usable cache scope is non-empty and, for the
  /// `anonymous:` / `account:` namespaces, has an id after the colon.
  static bool isUsableIdentityScope(String identityScope) {
    if (identityScope.isEmpty) return false;
    for (final prefix in const ['anonymous:', 'account:']) {
      if (identityScope.startsWith(prefix)) {
        return identityScope.length > prefix.length;
      }
    }
    return true;
  }

  static void _requireIdentityScope(String identityScope) {
    if (!isUsableIdentityScope(identityScope)) {
      throw ArgumentError.value(
        identityScope,
        'identityScope',
        'must be a non-empty identity scope',
      );
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
  Future<void> enqueue(
    String signalId,
    String payloadJson,
    String capturedAt,
  ) async {
    final database = await db;
    await database.insert('outbox', {
      'signal_id': signalId,
      'payload_json': payloadJson,
      'captured_at': capturedAt,
      'attempts': 0,
      'state': 'pending',
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
  }

  /// Get pending signals ready to sync (ordered oldest-first).
  Future<List<Map<String, dynamic>>> getPendingBatch({int limit = 50}) async {
    final database = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    return database.query(
      'outbox',
      where:
          "state = 'pending' AND (next_retry_at IS NULL OR next_retry_at <= ?)",
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
      final rows = await database.query(
        'outbox',
        where: 'signal_id = ?',
        whereArgs: [id],
      );
      if (rows.isEmpty) continue;
      final attempts = (rows.first['attempts'] as int) + 1;
      final backoffMs = _backoffMs(attempts);
      final nextRetry = DateTime.now().toUtc().add(
        Duration(milliseconds: backoffMs),
      );
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
    final result = await database.rawQuery(
      'SELECT COUNT(*) as cnt FROM outbox',
    );
    return (result.first['cnt'] as int?) ?? 0;
  }

  // ============================================================
  // Cache operations (offline reads — SPEC-02 B.4)
  // ============================================================

  /// Cache a trip state for one identity (SPEC-43 Gap 12).
  Future<void> cacheTrip(
    String tripId,
    String stateJson, {
    required String identityScope,
  }) async {
    _requireIdentityScope(identityScope);
    final database = await db;
    await database.insert('cache_trip', {
      'identity_scope': identityScope,
      'trip_id': tripId,
      'state_json': stateJson,
      'cached_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Read cached trip state for one identity (null if not cached or the
  /// scope is unusable). Never looks up by trip_id alone.
  Future<String?> getCachedTrip(
    String tripId, {
    required String identityScope,
  }) async {
    if (!isUsableIdentityScope(identityScope)) return null;
    final database = await db;
    final rows = await database.query(
      'cache_trip',
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
    );
    return rows.isEmpty ? null : rows.first['state_json'] as String;
  }

  Future<void> cacheTripList(String cacheKey, String listJson) async {
    final database = await db;
    await database.insert('cache_trip_list', {
      'cache_key': cacheKey,
      'list_json': listJson,
      'cached_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
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

  /// Cache a place/venue for one identity (SPEC-43 Gap 12).
  Future<void> cachePlace(
    String placeRef,
    String dataJson, {
    required String identityScope,
  }) async {
    _requireIdentityScope(identityScope);
    final database = await db;
    await database.insert('cache_place', {
      'identity_scope': identityScope,
      'place_ref': placeRef,
      'data_json': dataJson,
      'cached_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Read cached place data for one identity (null if not cached or the
  /// scope is unusable). Never looks up by place_ref alone.
  Future<String?> getCachedPlace(
    String placeRef, {
    required String identityScope,
  }) async {
    if (!isUsableIdentityScope(identityScope)) return null;
    final database = await db;
    final rows = await database.query(
      'cache_place',
      where: 'identity_scope = ? AND place_ref = ?',
      whereArgs: [identityScope, placeRef],
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
    await database.insert('loved_places', {
      'identity_scope': identityScope,
      'trip_id': tripId,
      'place_ref': placeRef,
      'loved_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
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
      throw ArgumentError.value(
        outcome,
        'outcome',
        'must be visited or skipped',
      );
    }
    if (outcome == NodeOutcome.skipped && (reason == null || reason.isEmpty)) {
      throw ArgumentError.value(
        reason,
        'reason',
        'is required for skipped outcomes',
      );
    }
    if (outcome == NodeOutcome.visited && reason != null) {
      throw ArgumentError.value(
        reason,
        'reason',
        'must be null for visited outcomes',
      );
    }

    final database = await db;
    await database.insert('node_outcome', {
      'identity_scope': identityScope,
      'trip_id': tripId,
      'node_id': nodeId,
      'outcome': outcome,
      'reason': reason,
      'recorded_at': (recordedAt ?? DateTime.now()).toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
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
    await database.insert('app_kv', {
      'key': key,
      'value': value,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  // ============================================================
  // Internal helpers
  // ============================================================

  /// Exponential backoff with jitter (SPEC-02 B.2).
  /// min(2^attempts * 2s, 15min) + random 0-20%.
  int _backoffMs(int attempts) {
    final baseMs = 2000 * (1 << attempts);
    final cappedMs = baseMs.clamp(0, 15 * 60 * 1000);
    final jitter = (cappedMs * 0.2 * (DateTime.now().millisecond / 1000))
        .round();
    return cappedMs + jitter;
  }

  /// SPEC-25 Phase C: Durable Ask thread tables.
  Future<void> _createAskThreadTables(Database db) async {
    await db.execute(
      'CREATE TABLE ask_thread ('
      '  thread_id      TEXT PRIMARY KEY,'
      '  identity_scope TEXT NOT NULL,'
      '  trip_id        TEXT NOT NULL,'
      '  title          TEXT NOT NULL,'
      '  created_at     TEXT NOT NULL,'
      '  updated_at     TEXT NOT NULL'
      ')',
    );
    await db.execute(
      'CREATE INDEX idx_ask_thread_scope_trip '
      'ON ask_thread(identity_scope, trip_id, updated_at)',
    );
    await db.execute(
      'CREATE TABLE ask_message ('
      '  message_id     TEXT PRIMARY KEY,'
      '  thread_id      TEXT NOT NULL,'
      '  role           TEXT NOT NULL,'
      '  text           TEXT NOT NULL,'
      '  envelope_json  TEXT,'
      '  created_at     TEXT NOT NULL'
      ')',
    );
    await db.execute(
      'CREATE INDEX idx_ask_message_thread '
      'ON ask_message(thread_id, created_at)',
    );
  }

  // ============================================================
  // Ask thread operations (SPEC-25 Phase C)
  // ============================================================

  /// Create a new Ask thread.
  Future<void> createAskThread({
    required String threadId,
    required String identityScope,
    required String tripId,
    required String title,
    DateTime? createdAt,
  }) async {
    final database = await db;
    final now = (createdAt ?? DateTime.now()).toUtc().toIso8601String();
    await database.insert('ask_thread', {
      'thread_id': threadId,
      'identity_scope': identityScope,
      'trip_id': tripId,
      'title': title,
      'created_at': now,
      'updated_at': now,
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
    // Retention: keep at most 50 threads per trip.
    await _pruneAskThreads(identityScope: identityScope, tripId: tripId);
  }

  /// Insert a message into a thread.
  Future<void> insertAskMessage({
    required String messageId,
    required String threadId,
    required String role,
    required String text,
    String? envelopeJson,
    DateTime? createdAt,
  }) async {
    final database = await db;
    final now = (createdAt ?? DateTime.now()).toUtc().toIso8601String();
    await database.insert('ask_message', {
      'message_id': messageId,
      'thread_id': threadId,
      'role': role,
      'text': text,
      'envelope_json': envelopeJson,
      'created_at': now,
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
    // Touch the thread's updated_at.
    await database.rawUpdate(
      'UPDATE ask_thread SET updated_at = ? WHERE thread_id = ?',
      [now, threadId],
    );
    // Retention: keep at most 200 messages per thread.
    await _pruneAskMessages(threadId: threadId);
  }

  /// List threads for a trip, newest first.
  Future<List<Map<String, dynamic>>> listAskThreads({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    return database.query(
      'ask_thread',
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
      orderBy: 'updated_at DESC',
    );
  }

  /// Load messages for a thread, oldest first.
  /// Requires identityScope: the thread must belong to this identity.
  Future<List<Map<String, dynamic>>> loadAskMessages({
    required String threadId,
    required String identityScope,
  }) async {
    final database = await db;
    // Verify thread ownership first.
    final thread = await database.query(
      'ask_thread',
      where: 'thread_id = ? AND identity_scope = ?',
      whereArgs: [threadId, identityScope],
    );
    if (thread.isEmpty) return [];
    return database.query(
      'ask_message',
      where: 'thread_id = ?',
      whereArgs: [threadId],
      orderBy: 'created_at ASC',
    );
  }

  /// Get the most recent thread for a trip (or null).
  Future<Map<String, dynamic>?> getMostRecentAskThread({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final rows = await database.query(
      'ask_thread',
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
      orderBy: 'updated_at DESC',
      limit: 1,
    );
    return rows.isEmpty ? null : rows.first;
  }

  /// Delete one thread and its messages.
  /// Requires identityScope: refuses to delete another identity's thread.
  Future<void> deleteAskThread({
    required String threadId,
    required String identityScope,
  }) async {
    final database = await db;
    // Verify ownership before deleting.
    final thread = await database.query(
      'ask_thread',
      where: 'thread_id = ? AND identity_scope = ?',
      whereArgs: [threadId, identityScope],
    );
    if (thread.isEmpty) return;
    await database.delete(
      'ask_message',
      where: 'thread_id = ?',
      whereArgs: [threadId],
    );
    await database.delete(
      'ask_thread',
      where: 'thread_id = ? AND identity_scope = ?',
      whereArgs: [threadId, identityScope],
    );
  }

  /// Delete all Ask threads and messages for a trip.
  Future<void> deleteAskHistoryForTrip({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final threads = await database.query(
      'ask_thread',
      columns: ['thread_id'],
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
    );
    for (final t in threads) {
      await database.delete(
        'ask_message',
        where: 'thread_id = ?',
        whereArgs: [t['thread_id']],
      );
    }
    await database.delete(
      'ask_thread',
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
    );
  }

  /// Delete all Ask threads and messages for an identity.
  Future<void> deleteAskHistoryForIdentity({
    required String identityScope,
  }) async {
    final database = await db;
    final threads = await database.query(
      'ask_thread',
      columns: ['thread_id'],
      where: 'identity_scope = ?',
      whereArgs: [identityScope],
    );
    for (final t in threads) {
      await database.delete(
        'ask_message',
        where: 'thread_id = ?',
        whereArgs: [t['thread_id']],
      );
    }
    await database.delete(
      'ask_thread',
      where: 'identity_scope = ?',
      whereArgs: [identityScope],
    );
  }

  /// Retention: keep at most 50 threads per trip, prune oldest.
  Future<void> _pruneAskThreads({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final count = await database.rawQuery(
      'SELECT COUNT(*) as cnt FROM ask_thread '
      'WHERE identity_scope = ? AND trip_id = ?',
      [identityScope, tripId],
    );
    final total = (count.first['cnt'] as int?) ?? 0;
    if (total <= 50) return;
    final excess = total - 50;
    final oldest = await database.query(
      'ask_thread',
      columns: ['thread_id'],
      where: 'identity_scope = ? AND trip_id = ?',
      whereArgs: [identityScope, tripId],
      orderBy: 'updated_at ASC',
      limit: excess,
    );
    for (final t in oldest) {
      await deleteAskThread(
        threadId: t['thread_id'] as String,
        identityScope: identityScope,
      );
    }
  }

  /// Retention: keep at most 200 messages per thread, prune oldest.
  Future<void> _pruneAskMessages({required String threadId}) async {
    final database = await db;
    final count = await database.rawQuery(
      'SELECT COUNT(*) as cnt FROM ask_message WHERE thread_id = ?',
      [threadId],
    );
    final total = (count.first['cnt'] as int?) ?? 0;
    if (total <= 200) return;
    final excess = total - 200;
    final oldest = await database.query(
      'ask_message',
      columns: ['message_id'],
      where: 'thread_id = ?',
      whereArgs: [threadId],
      orderBy: 'created_at ASC',
      limit: excess,
    );
    final ids = oldest.map((m) => m['message_id'] as String).toList();
    final placeholders = ids.map((_) => '?').join(',');
    await database.rawDelete(
      'DELETE FROM ask_message WHERE message_id IN ($placeholders)',
      ids,
    );
  }

  /// Close the database (for testing).

  /// SPEC-43 Gap 6: wipe every local row during sign-out.
  ///
  /// Deletes data only; never drops the database file or recreates schema.
  /// Includes the entire outbox so identity A's pending rows can never POST
  /// under identity B's Bearer after the auth transition.
  Future<void> deleteAllLocalRows() async {
    final database = await db;
    const tables = [
      'outbox',
      'cache_trip',
      'cache_place',
      'cache_trip_list',
      'alert_cache',
      'alert_dismissals',
      'loved_places',
      'app_kv',
      'node_outcome',
      'ask_message',
      'ask_thread',
      'notification_cache',
      'notification_dismissals',
    ];
    await database.transaction((txn) async {
      final batch = txn.batch();
      for (final table in tables) {
        batch.delete(table);
      }
      await batch.commit(noResult: true);
    });
  }

  Future<void> close() async {
    final opening = _opening;
    if (opening != null) {
      try {
        _db = await opening;
      } catch (_) {}
    }
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
    await database.insert('alert_cache', {
      'identity_scope': identityScope,
      'trip_id': tripId,
      'payload_json': payloadJson,
      'cached_at': DateTime.now().toUtc().toIso8601String(),
      'expires_at': expiresAt,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
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
    await database.insert('alert_dismissals', {
      'identity_scope': identityScope,
      'alert_id': alertId,
      'dismissed_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
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

  /// SPEC-35: Notification cache and dismissal tables (separate from alerts).
  Future<void> _createNotificationTables(Database db) async {
    await db.execute(
      'CREATE TABLE notification_cache ('
      '  identity_scope TEXT NOT NULL,'
      '  trip_id        TEXT NOT NULL,'
      '  payload_json   TEXT NOT NULL,'
      '  cached_at      TEXT NOT NULL,'
      '  expires_at     TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, trip_id)'
      ')',
    );
    await db.execute(
      'CREATE TABLE notification_dismissals ('
      '  identity_scope  TEXT NOT NULL,'
      '  notification_id TEXT NOT NULL,'
      '  dismissed_at    TEXT NOT NULL,'
      '  PRIMARY KEY (identity_scope, notification_id)'
      ')',
    );
  }

  // ============================================================
  // Notification cache (SPEC-35)
  // ============================================================

  /// Cache notifications scoped by identity and trip.
  Future<void> cacheNotifications({
    required String identityScope,
    required String tripId,
    required String payloadJson,
    required String expiresAt,
  }) async {
    final database = await db;
    await database.insert('notification_cache', {
      'identity_scope': identityScope,
      'trip_id': tripId,
      'payload_json': payloadJson,
      'cached_at': DateTime.now().toUtc().toIso8601String(),
      'expires_at': expiresAt,
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  /// Retrieve cached notifications (only if not expired).
  Future<String?> getCachedNotifications({
    required String identityScope,
    required String tripId,
  }) async {
    final database = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    final rows = await database.query(
      'notification_cache',
      where: 'identity_scope = ? AND trip_id = ? AND expires_at > ?',
      whereArgs: [identityScope, tripId, now],
    );
    if (rows.isEmpty) return null;
    return rows.first['payload_json'] as String?;
  }

  /// Record a dismissed notification in the dedicated table.
  Future<void> dismissNotification({
    required String identityScope,
    required String notificationId,
  }) async {
    final database = await db;
    await database.insert('notification_dismissals', {
      'identity_scope': identityScope,
      'notification_id': notificationId,
      'dismissed_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.ignore);
  }

  /// Get all dismissed notification IDs for this identity.
  Future<Set<String>> getDismissedNotificationIds({
    required String identityScope,
  }) async {
    final database = await db;
    final rows = await database.query(
      'notification_dismissals',
      columns: ['notification_id'],
      where: 'identity_scope = ?',
      whereArgs: [identityScope],
    );
    return rows.map((r) => r['notification_id'] as String).toSet();
  }

  /// Prune expired notification cache and stale dismissals (> 30 days).
  Future<void> pruneNotificationData() async {
    final database = await db;
    final now = DateTime.now().toUtc().toIso8601String();
    await database.delete(
      'notification_cache',
      where: 'expires_at <= ?',
      whereArgs: [now],
    );
    final cutoff = DateTime.now()
        .toUtc()
        .subtract(const Duration(days: 30))
        .toIso8601String();
    await database.delete(
      'notification_dismissals',
      where: 'dismissed_at < ?',
      whereArgs: [cutoff],
    );
  }
}
