import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/data/signal.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

// Mocks
class MockApiClient extends Mock implements ApiClient {}

class FailingEnqueueDatabase extends OfflineDatabase {
  FailingEnqueueDatabase() : super(testPath: inMemoryDatabasePath);

  @override
  Future<void> enqueue(
    String signalId,
    String payloadJson,
    String capturedAt,
  ) =>
      Future<void>.error(StateError('outbox write failed'));
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;
  late MockApiClient mockApi;
  late SyncEngine syncEngine;
  late SignalService service;

  setUp(() async {
    db = OfflineDatabase(testPath: inMemoryDatabasePath);
    mockApi = MockApiClient();
    syncEngine = SyncEngine(db: db, api: mockApi);
    service = SignalService(db: db, syncEngine: syncEngine);

    // Default stub: simulate offline so background triggerSync doesn't crash
    when(() => mockApi.post(any(), body: any(named: 'body')))
        .thenThrow(const NetworkException());
  });

  tearDown(() async {
    syncEngine.stop();
    await Future.delayed(const Duration(milliseconds: 50));
    await db.close();
  });

  group('Signal model', () {
    test('toJson produces correct wire format', () {
      final sig = Signal(
        signalId: 'test-uuid-1234',
        signalType: 'user_loved',
        placeRef: 'dubai-mall',
        valueText: 'loved',
        capturedAt: DateTime.utc(2026, 8, 5, 14, 30),
        tripId: 'trip-001',
      );

      final json = sig.toJson();
      expect(json['signal_id'], 'test-uuid-1234');
      expect(json['signal_type'], 'user_loved');
      expect(json['place_ref'], 'dubai-mall');
      expect(json['value_text'], 'loved');
      expect(json['captured_at'], '2026-08-05T14:30:00.000Z');
      expect(json['trip_id'], 'trip-001');
    });

    test('toJson omits null optional fields', () {
      final sig = Signal(
        signalId: 'test-uuid-5678',
        signalType: 'user_loved',
        placeRef: 'burj-khalifa',
        capturedAt: DateTime.utc(2026, 8, 5, 10, 0),
      );

      final json = sig.toJson();
      expect(json.containsKey('value_text'), false);
      expect(json.containsKey('value_numeric'), false);
      expect(json.containsKey('value_json'), false);
      expect(json.containsKey('trip_id'), false);
    });
  });

  group('SignalService.emit (queue-backed — SPEC-02)', () {
    test('emit enqueues to outbox with correct payload shape', () async {
      await service.emit(
        signalType: 'user_loved',
        placeRef: 'dubai-mall',
        valueText: 'loved',
        tripId: 'trip-001',
      );

      // Let background triggerSync settle (it may mark row for retry)
      await Future.delayed(const Duration(milliseconds: 100));

      // Verify row exists in outbox (use getOutboxSize — counts all states,
      // unlike getPendingBatch which skips rows with future next_retry_at)
      final size = await db.getOutboxSize();
      expect(size, 1);

      // Query raw DB to verify payload regardless of state
      final database = await db.db;
      final rows = await database.query('outbox');
      expect(rows.length, 1);

      // Verify payload shape
      final payload = jsonDecode(rows.first['payload_json'] as String);
      expect(payload['signal_type'], 'user_loved');
      expect(payload['place_ref'], 'dubai-mall');
      expect(payload['value_text'], 'loved');
      expect(payload['trip_id'], 'trip-001');
      expect(payload['signal_id'], isNotEmpty);
      expect(payload['captured_at'], isNotEmpty);
    });

    test('emit never throws (fire-and-forget with local persistence)', () async {
      // Even with network errors, emit should not throw
      await service.emit(
        signalType: 'user_loved',
        placeRef: 'some-place',
      );
      // If we get here without exception, test passes
    });

    test('result path reports enqueue failure while emit still never throws',
        () async {
      final failingDb = FailingEnqueueDatabase();
      final failingEngine = SyncEngine(db: failingDb, api: mockApi);
      final failingService = SignalService(
        db: failingDb,
        syncEngine: failingEngine,
      );
      addTearDown(() async {
        failingEngine.stop();
        await failingDb.close();
      });

      final result = await failingService.emitVisitedConfirmedWithResult(
        placeRef: 'some-place',
        tripId: 'trip-001',
      );
      await failingService.emit(
        signalType: 'visited_confirmed',
        placeRef: 'some-place',
        tripId: 'trip-001',
      );

      expect(result, isFalse);
    });
  });
}
