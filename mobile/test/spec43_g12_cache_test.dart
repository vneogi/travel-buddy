// SPEC-43 Gap 12: identity-scoped cache_trip and cache_place.
//
// Unique in-memory sqflite_ffi databases per test. No network, no widgets.

import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite/sqflite.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:travel_buddy/offline/offline_database.dart';

int _dbCounter = 0;

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;

  setUp(() {
    _dbCounter++;
    db = OfflineDatabase(
      testPath: 'file:spec43_g12_cache_$_dbCounter?mode=memory&cache=shared',
    );
  });

  tearDown(() async {
    await db.close();
  });

  const userA = 'account:user-a';
  const userB = 'account:user-b';
  final tripJson = jsonEncode({'trip_id': 'trip-1', 'user_id': 'user-a'});
  final placeJson = jsonEncode({'place_ref': 'wat_xieng_thong', 'hours': 'A'});

  test('test_foreign_identity_cannot_read_cached_trip', () async {
    await db.cacheTrip('trip-1', tripJson, identityScope: userA);

    expect(await db.getCachedTrip('trip-1', identityScope: userB), isNull);
    expect(await db.getCachedTrip('trip-1', identityScope: userA), tripJson);
  });

  test('foreign identity cannot read cache_place for the same place_ref',
      () async {
    await db.cachePlace('wat_xieng_thong', placeJson, identityScope: userA);

    expect(
      await db.getCachedPlace('wat_xieng_thong', identityScope: userB),
      isNull,
    );
    expect(
      await db.getCachedPlace('wat_xieng_thong', identityScope: userA),
      placeJson,
    );
  });

  test('same identity reads what it wrote; identities do not overwrite',
      () async {
    final tripJsonB = jsonEncode({'trip_id': 'trip-1', 'user_id': 'user-b'});
    await db.cacheTrip('trip-1', tripJson, identityScope: userA);
    await db.cacheTrip('trip-1', tripJsonB, identityScope: userB);
    await db.cachePlace('p', 'place-a', identityScope: 'anonymous:device-1');

    expect(await db.getCachedTrip('trip-1', identityScope: userA), tripJson);
    expect(await db.getCachedTrip('trip-1', identityScope: userB), tripJsonB);
    expect(
      await db.getCachedPlace('p', identityScope: 'anonymous:device-1'),
      'place-a',
    );
    expect(
      await db.getCachedPlace('p', identityScope: 'anonymous:device-2'),
      isNull,
    );
  });

  test('empty / anonymous: / account: scope is refused on write', () async {
    for (final scope in const ['', 'anonymous:', 'account:']) {
      await expectLater(
        () => db.cacheTrip('trip-1', tripJson, identityScope: scope),
        throwsArgumentError,
        reason: 'cacheTrip scope="$scope"',
      );
      await expectLater(
        () => db.cachePlace('p', placeJson, identityScope: scope),
        throwsArgumentError,
        reason: 'cachePlace scope="$scope"',
      );
    }
    final raw = await db.db;
    expect(await raw.query('cache_trip'), isEmpty);
    expect(await raw.query('cache_place'), isEmpty);
  });

  test('empty / anonymous: / account: scope reads null, never scans', () async {
    await db.cacheTrip('trip-1', tripJson, identityScope: userA);
    await db.cachePlace('p', placeJson, identityScope: userA);
    for (final scope in const ['', 'anonymous:', 'account:']) {
      expect(await db.getCachedTrip('trip-1', identityScope: scope), isNull);
      expect(await db.getCachedPlace('p', identityScope: scope), isNull);
    }
  });

  test('v8 unscoped on-disk db upgrade yields no old cache_trip row',
      () async {
    final directory = await Directory.systemTemp.createTemp('spec43-g12-v8-');
    final path = '${directory.path}/offline.db';
    addTearDown(() => directory.delete(recursive: true));

    final v8 = await openDatabase(
      path,
      version: 8,
      onCreate: (raw, _) async {
        await raw.execute(
          'CREATE TABLE cache_trip ('
          'trip_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, '
          'cached_at TEXT NOT NULL)',
        );
        await raw.execute(
          'CREATE TABLE cache_place ('
          'place_ref TEXT PRIMARY KEY, data_json TEXT NOT NULL, '
          'cached_at TEXT NOT NULL)',
        );
      },
    );
    await v8.insert('cache_trip', {
      'trip_id': 'trip-1',
      'state_json': tripJson,
      'cached_at': '2026-10-01T08:00:00.000Z',
    });
    await v8.insert('cache_place', {
      'place_ref': 'wat_xieng_thong',
      'data_json': placeJson,
      'cached_at': '2026-10-01T08:00:00.000Z',
    });
    await v8.close();

    final upgraded = OfflineDatabase(testPath: path);
    addTearDown(upgraded.close);
    final raw = await upgraded.db;

    expect(await raw.getVersion(), 9);
    expect(await raw.query('cache_trip'), isEmpty);
    expect(await raw.query('cache_place'), isEmpty);
    for (final scope in const [userA, userB, 'anonymous:device-1']) {
      expect(await upgraded.getCachedTrip('trip-1', identityScope: scope),
          isNull);
      expect(
        await upgraded.getCachedPlace('wat_xieng_thong', identityScope: scope),
        isNull,
      );
    }

    // New DDL is in place: scoped write + read works after upgrade.
    await upgraded.cacheTrip('trip-1', tripJson, identityScope: userA);
    expect(await upgraded.getCachedTrip('trip-1', identityScope: userA),
        tripJson);
  });
}
