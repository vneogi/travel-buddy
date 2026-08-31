import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:travel_buddy/offline/offline_database.dart';

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  group('node outcomes', () {
    late OfflineDatabase database;

    setUp(() {
      database = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() => database.close());

    test('v6 fresh create stores visited and skipped outcomes', () async {
      final visitedAt = DateTime.utc(2026, 8, 31, 8);
      final skippedAt = DateTime.utc(2026, 8, 31, 9);
      await database.upsertNodeOutcome(
        identityScope: 'account:a',
        tripId: 'trip-1',
        nodeId: 'node-1',
        outcome: NodeOutcome.visited,
        recordedAt: visitedAt,
      );
      await database.upsertNodeOutcome(
        identityScope: 'account:a',
        tripId: 'trip-1',
        nodeId: 'node-2',
        outcome: NodeOutcome.skipped,
        reason: 'weather',
        recordedAt: skippedAt,
      );

      final outcomes = await database.getNodeOutcomes(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );

      expect(await (await database.db).getVersion(), 6);
      expect(outcomes['node-1']?.wasVisited, isTrue);
      expect(outcomes['node-1']?.recordedAt, visitedAt);
      expect(outcomes['node-2']?.wasSkipped, isTrue);
      expect(outcomes['node-2']?.reason, 'weather');
      expect(outcomes['node-2']?.recordedAt, skippedAt);
    });

    test('outcomes are isolated by identity and trip', () async {
      await database.upsertNodeOutcome(
        identityScope: 'account:a',
        tripId: 'trip-1',
        nodeId: 'node-1',
        outcome: NodeOutcome.visited,
      );

      expect(
        await database.getNodeOutcomes(
          identityScope: 'account:b',
          tripId: 'trip-1',
        ),
        isEmpty,
      );
      expect(
        await database.getNodeOutcomes(
          identityScope: 'account:a',
          tripId: 'trip-2',
        ),
        isEmpty,
      );
    });

    test('repeated venue occurrences remain distinct by node ID', () async {
      for (final nodeId in ['morning-cafe', 'afternoon-cafe']) {
        await database.upsertNodeOutcome(
          identityScope: 'account:a',
          tripId: 'trip-1',
          nodeId: nodeId,
          outcome: NodeOutcome.visited,
        );
      }

      final outcomes = await database.getNodeOutcomes(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );

      expect(outcomes.keys, containsAll(['morning-cafe', 'afternoon-cafe']));
      expect(outcomes, hasLength(2));
    });

    test('replace corrects an outcome without adding a row', () async {
      await database.upsertNodeOutcome(
        identityScope: 'account:a',
        tripId: 'trip-1',
        nodeId: 'node-1',
        outcome: NodeOutcome.visited,
      );
      await database.upsertNodeOutcome(
        identityScope: 'account:a',
        tripId: 'trip-1',
        nodeId: 'node-1',
        outcome: NodeOutcome.skipped,
        reason: 'too_tired',
      );

      final outcomes = await database.getNodeOutcomes(
        identityScope: 'account:a',
        tripId: 'trip-1',
      );
      final rows = await (await database.db).query('node_outcome');

      expect(outcomes, hasLength(1));
      expect(outcomes['node-1']?.wasSkipped, isTrue);
      expect(outcomes['node-1']?.reason, 'too_tired');
      expect(rows, hasLength(1));
    });

    test('rejects invalid outcome combinations before writing', () async {
      expect(
        () => database.upsertNodeOutcome(
          identityScope: 'account:a',
          tripId: 'trip-1',
          nodeId: 'node-1',
          outcome: 'unknown',
        ),
        throwsArgumentError,
      );
      expect(
        () => database.upsertNodeOutcome(
          identityScope: 'account:a',
          tripId: 'trip-1',
          nodeId: 'node-2',
          outcome: NodeOutcome.skipped,
        ),
        throwsArgumentError,
      );
    });
  });

  test('opening a real v5 database upgrades to v6 and preserves rows', () async {
    final directory = await Directory.systemTemp.createTemp('spec30-v5-');
    final path = '${directory.path}/offline.db';
    addTearDown(() => directory.delete(recursive: true));

    final v5 = await openDatabase(
      path,
      version: 5,
      onCreate: (db, _) async {
        await db.execute(
          'CREATE TABLE outbox ('
          'signal_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL, '
          'captured_at TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, '
          'next_retry_at TEXT, last_error TEXT, state TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE INDEX idx_outbox_state '
          'ON outbox(state, next_retry_at)',
        );
        await db.execute(
          'CREATE TABLE cache_trip ('
          'trip_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, '
          'cached_at TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE cache_place ('
          'place_ref TEXT PRIMARY KEY, data_json TEXT NOT NULL, '
          'cached_at TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE cache_trip_list ('
          'cache_key TEXT PRIMARY KEY, list_json TEXT NOT NULL, '
          'cached_at TEXT NOT NULL)',
        );
        await db.execute(
          'CREATE TABLE alert_cache ('
          'identity_scope TEXT NOT NULL, trip_id TEXT NOT NULL, '
          'payload_json TEXT NOT NULL, cached_at TEXT NOT NULL, '
          'expires_at TEXT NOT NULL, '
          'PRIMARY KEY (identity_scope, trip_id))',
        );
        await db.execute(
          'CREATE TABLE alert_dismissals ('
          'identity_scope TEXT NOT NULL, alert_id TEXT NOT NULL, '
          'dismissed_at TEXT NOT NULL, '
          'PRIMARY KEY (identity_scope, alert_id))',
        );
        await db.execute(
          'CREATE TABLE loved_places ('
          'identity_scope TEXT NOT NULL, trip_id TEXT NOT NULL, '
          'place_ref TEXT NOT NULL, loved_at TEXT NOT NULL, '
          'PRIMARY KEY (identity_scope, trip_id, place_ref))',
        );
        await db.execute(
          'CREATE TABLE app_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)',
        );
      },
    );
    await v5.insert('outbox', {
      'signal_id': 'signal-1',
      'payload_json': '{}',
      'captured_at': '2026-08-31T08:00:00.000Z',
      'attempts': 0,
      'state': 'pending',
    });
    await v5.insert('cache_trip', {
      'trip_id': 'trip-1',
      'state_json': '{"trip_id":"trip-1"}',
      'cached_at': '2026-08-31T08:00:00.000Z',
    });
    await v5.insert('loved_places', {
      'identity_scope': 'account:a',
      'trip_id': 'trip-1',
      'place_ref': 'venue-1',
      'loved_at': '2026-08-31T08:00:00.000Z',
    });
    await v5.insert('app_kv', {'key': 'last_session_at', 'value': 'kept'});
    await v5.close();

    final upgraded = OfflineDatabase(testPath: path);
    addTearDown(upgraded.close);
    final db = await upgraded.db;

    expect(await db.getVersion(), 6);
    expect(await db.query('outbox'), hasLength(1));
    expect(await db.query('cache_trip'), hasLength(1));
    expect(await db.query('loved_places'), hasLength(1));
    expect(await db.query('app_kv'), hasLength(1));
    final productionTables = await db.rawQuery(
      "SELECT name FROM sqlite_master WHERE type = 'table'",
    );
    expect(
      productionTables.map((row) => row['name']),
      containsAll({
        'outbox',
        'cache_trip',
        'cache_place',
        'cache_trip_list',
        'alert_cache',
        'alert_dismissals',
        'loved_places',
        'app_kv',
        'node_outcome',
      }),
    );
    expect(
      await db.rawQuery(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name = 'node_outcome'",
      ),
      hasLength(1),
    );

    await upgraded.upsertNodeOutcome(
      identityScope: 'account:a',
      tripId: 'trip-1',
      nodeId: 'node-1',
      outcome: NodeOutcome.visited,
    );
    expect(
      await upgraded.getNodeOutcomes(
        identityScope: 'account:a',
        tripId: 'trip-1',
      ),
      contains('node-1'),
    );
  });
}
