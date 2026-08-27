import 'package:flutter/foundation.dart';
import 'package:path/path.dart';
import 'package:sqflite/sqflite.dart';

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
  static const _dbVersion = 2;

  /// Optional path override for testing (pass inMemoryDatabasePath for isolation).
  final String? _testPath;

  Database? _db;

  /// Creates an OfflineDatabase. Pass [testPath] in unit tests to use an
  /// in-memory database (`:memory:`) for full test isolation.
  OfflineDatabase({String? testPath}) : _testPath = testPath;

  /// Lazy-open the database (creates tables on first run).
  Future<Database> get db async {
    _db ??= await _open();
    return _db!;
  }

  Future<Database> _open() async {
    final String path;
    if (_testPath != null) {
      path = _testPath!;
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
  }

  Future<void> _onUpgrade(Database db, int oldVersion, int newVersion) async {
    if (oldVersion < 2) {
      await _createTripListCache(db);
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
}
