import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import '../lib/core/api_client.dart';
import '../lib/data/signal.dart';
import '../lib/services/signal_service.dart';

// Mock the ApiClient
class MockApiClient extends Mock implements ApiClient {}

void main() {
  late MockApiClient mockApi;
  late SignalService service;

  setUp(() {
    mockApi = MockApiClient();
    service = SignalService(mockApi);
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

  group('SignalService.emit', () {
    test('calls POST /signals with batch body shape', () async {
      when(() => mockApi.post(
            '/signals',
            body: any(named: 'body'),
          )).thenAnswer((_) async => {'accepted': 1, 'duplicates': 0});

      await service.emit(
        signalType: 'user_loved',
        placeRef: 'dubai-mall',
        valueText: 'loved',
        tripId: 'trip-001',
      );

      final captured = verify(() => mockApi.post(
            '/signals',
            body: captureAny(named: 'body'),
          )).captured.single as Map<String, dynamic>;

      // Batch wrapper
      expect(captured.containsKey('signals'), true);
      expect(captured['signals'], isA<List>());
      expect(captured['signals'].length, 1);

      // Signal shape
      final sig = captured['signals'][0] as Map<String, dynamic>;
      expect(sig['signal_type'], 'user_loved');
      expect(sig['place_ref'], 'dubai-mall');
      expect(sig['value_text'], 'loved');
      expect(sig['trip_id'], 'trip-001');
      expect(sig['signal_id'], isNotEmpty); // UUID generated
      expect(sig['captured_at'], isNotEmpty); // timestamp set
    });

    test('swallows errors (fire-and-forget for now)', () async {
      when(() => mockApi.post(
            '/signals',
            body: any(named: 'body'),
          )).thenThrow(Exception('Network error'));

      // Should not throw
      await service.emit(
        signalType: 'user_loved',
        placeRef: 'some-place',
      );
    });
  });
}
