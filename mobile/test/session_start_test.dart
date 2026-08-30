import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/main.dart';

class MockApiClient extends Mock implements ApiClient {}

/// SPEC-30: session_start client tests.
void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;
  late SyncEngine syncEngine;
  late SignalService signalService;

  setUp(() async {
    db = OfflineDatabase(testPath: inMemoryDatabasePath);
    final mockApi = MockApiClient();
    // Default stub: simulate offline so background triggerSync doesn't crash
    when(() => mockApi.post(any(), body: any(named: 'body')))
        .thenThrow(const NetworkException());
    syncEngine = SyncEngine(db: db, api: mockApi);
    signalService = SignalService(db: db, syncEngine: syncEngine);
  });

  tearDown(() async {
    syncEngine.stop();
    await Future.delayed(const Duration(milliseconds: 50));
    await db.close();
  });

  // ----------------------------------------------------------
  // Test 1: emitSessionStart enqueues with documented payload shape
  // ----------------------------------------------------------
  test('emitSessionStart enqueues one outbox row with correct shape', () async {
    await signalService.emitSessionStart(
      coldStart: true,
      minutesSinceLastOpen: 120,
      tripDay: 3,
      tripId: 'trip-1',
    );

    final rows = await (await db.db).query('outbox');
    expect(rows.length, 1);
    final payload =
        jsonDecode(rows.first['payload_json'] as String) as Map<String, dynamic>;
    expect(payload['signal_type'], 'session_start');
    expect(payload['place_ref'], 'session');
    expect(payload['trip_id'], 'trip-1');
    final vj = payload['value_json'] as Map<String, dynamic>;
    expect(vj['cold_start'], true);
    expect(vj['minutes_since_last_open'], 120);
    expect(vj['trip_day'], 3);
  });

  // ----------------------------------------------------------
  // Test 2: minutes_since_last_open is null on first open
  // ----------------------------------------------------------
  test('minutes_since_last_open is null on first open', () async {
    // No prior last_session_at stored -> null
    final lastStr = await db.getAppValue('last_session_at');
    expect(lastStr, isNull);

    // Emit with null minutesSinceLastOpen (first ever open)
    await signalService.emitSessionStart(
      coldStart: true,
      minutesSinceLastOpen: null,
    );

    final rows = await (await db.db).query('outbox');
    expect(rows.length, 1);
    final payload =
        jsonDecode(rows.first['payload_json'] as String) as Map<String, dynamic>;
    final vj = payload['value_json'] as Map<String, dynamic>;
    // minutes_since_last_open absent (null omitted by if-collection)
    expect(vj.containsKey('minutes_since_last_open'), false);
    expect(vj['cold_start'], true);
  });

  // ----------------------------------------------------------
  // Test 3: minutes_since_last_open computed from persisted last_session_at
  // ----------------------------------------------------------
  test('minutes_since_last_open is elapsed minutes from persisted timestamp',
      () async {
    // Simulate a prior session 90 minutes ago
    final priorTime =
        DateTime.now().toUtc().subtract(const Duration(minutes: 90));
    await db.setAppValue('last_session_at', priorTime.toIso8601String());

    // Read it back and compute
    final lastStr = await db.getAppValue('last_session_at');
    expect(lastStr, isNotNull);
    final last = DateTime.parse(lastStr!);
    final elapsed = DateTime.now().toUtc().difference(last).inMinutes;

    // Should be approximately 90 (within 1 min of test execution)
    expect(elapsed, greaterThanOrEqualTo(89));
    expect(elapsed, lessThanOrEqualTo(91));
  });

  // ----------------------------------------------------------
  // Test 4: cold_start true on first emit, false on subsequent
  // ----------------------------------------------------------
  test('cold_start true on first, false on subsequent', () async {
    // First emit: cold_start = true
    await signalService.emitSessionStart(coldStart: true);

    // Second emit: cold_start = false (resume)
    await signalService.emitSessionStart(coldStart: false);

    final rows = await (await db.db).query('outbox', orderBy: 'captured_at ASC');
    expect(rows.length, 2);

    final p1 =
        jsonDecode(rows[0]['payload_json'] as String) as Map<String, dynamic>;
    final p2 =
        jsonDecode(rows[1]['payload_json'] as String) as Map<String, dynamic>;

    expect((p1['value_json'] as Map)['cold_start'], true);
    expect((p2['value_json'] as Map)['cold_start'], false);
  });

  test('activeTripIdFromUri recognizes all trip routes', () {
    expect(activeTripIdFromUri(Uri.parse('/')), isNull);
    expect(activeTripIdFromUri(Uri.parse('/profile')), isNull);
    expect(activeTripIdFromUri(Uri.parse('/trip/trip-1')), 'trip-1');
    expect(activeTripIdFromUri(Uri.parse('/trip/trip-1/chat')), 'trip-1');
    expect(
      activeTripIdFromUri(Uri.parse('/trip/trip-1/card/node-1')),
      'trip-1',
    );
  });

  test('resume debounce suppresses rapid lifecycle flicker', () {
    final coldStartAt = DateTime.utc(2026, 10, 2, 8);
    expect(
      shouldEmitSessionStartOnResume(
        lastEmitAt: coldStartAt,
        now: coldStartAt.add(const Duration(seconds: 5)),
        debounce: const Duration(seconds: 30),
      ),
      isFalse,
    );
    expect(
      shouldEmitSessionStartOnResume(
        lastEmitAt: coldStartAt,
        now: coldStartAt.add(const Duration(seconds: 31)),
        debounce: const Duration(seconds: 30),
      ),
      isTrue,
    );
  });

  test('tripDayFromCachedTrip uses earliest scheduled node date', () async {
    final trip = TripState(
      tripId: 'trip-1',
      userId: 'user-1',
      nodes: [
        TripNode(
          nodeId: 'node-2',
          venueName: 'Second stop',
          scheduledStart: DateTime.utc(2026, 10, 4, 9),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
        ),
        TripNode(
          nodeId: 'node-1',
          venueName: 'First stop',
          scheduledStart: DateTime.utc(2026, 10, 2, 18),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
        ),
      ],
    );
    await db.cacheTrip('trip-1', jsonEncode(trip.toJson()));

    final tripDay = await tripDayFromCachedTrip(
      db,
      'trip-1',
      DateTime.utc(2026, 10, 4, 8),
    );

    expect(tripDay, 2);
  });

  test('tripDayFromCachedTrip is null without a usable cache', () async {
    expect(
      await tripDayFromCachedTrip(
        db,
        'missing-trip',
        DateTime.utc(2026, 10, 4),
      ),
      isNull,
    );
  });
}
