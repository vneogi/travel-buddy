import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/data/signal.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

// Mocks
class MockApiClient extends Mock implements ApiClient {}

void main() {
  // Use in-memory SQLite for tests
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;
  late MockApiClient mockApi;
  late SyncEngine syncEngine;
  late SignalService service;

  setUp(() async {
    db = OfflineDatabase();
    mockApi = MockApiClient();
    syncEngine = SyncEngine(db: db, api: mockApi);
    service = SignalService(db: db, syncEngine: syncEngine);
  });

  tearDown(() async {
    syncEngine.stop();
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

      // Verify persisted to outbox
      final batch = await db.getPendingBatch();
      expect(batch.length, 1);
      expect(batch.first['state'], 'pending');

      // Verify payload shape
      final payload = jsonDecode(batch.first['payload_json'] as String);
      expect(payload['signal_type'], 'user_loved');
      expect(payload['place_ref'], 'dubai-mall');
      expect(payload['value_text'], 'loved');
      expect(payload['trip_id'], 'trip-001');
      expect(payload['signal_id'], isNotEmpty);
      expect(payload['captured_at'], isNotEmpty);
    });

    test('emit never throws (fire-and-forget with local persistence)', () async {
      // Even without any mock setup, emit should not throw
      // because it persists locally and triggers sync in background
      await service.emit(
        signalType: 'user_loved',
        placeRef: 'some-place',
      );
      // If we get here without exception, test passes
    });
  });
}
