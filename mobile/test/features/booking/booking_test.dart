import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/booking/booking_parser.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

class MockSyncEngine extends Mock implements SyncEngine {}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // =========================================================
  // Parser tests
  // =========================================================

  group('extractBookingFromText', () {
    test('extracts flight and code without network', () {
      final result = extractBookingFromText(
        'Booking Confirmed! Flight EK501 to Dubai. PNR: AB12CD',
        importSource: 'email',
      );
      expect(result.bookingType, equals('flight'));
      expect(result.confirmationCode, equals('AB12CD'));
      expect(result.importSource, equals('email'));
    });

    // Sabotage 3: throw FormatException on empty -> this test FAILS
    test('degrades on malformed text without throwing', () {
      // Empty
      expect(
        () => extractBookingFromText(''),
        returnsNormally,
      );
      final empty = extractBookingFromText('');
      expect(empty.bookingType, isNull);
      expect(empty.confirmationCode, isNull);

      // Gibberish
      expect(
        () => extractBookingFromText('gibberish 123456789 !!!'),
        returnsNormally,
      );
      final gibberish = extractBookingFromText('gibberish 123456789 !!!');
      expect(gibberish.bookingType, isNull);
    });

    test('extracts Booking.com hostel name and stay dates from email', () {
      const email = '''
Thanks Vikrant Vilas! Your booking in Vang Vieng is confirmed.
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Reservation details
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
Check-out Tuesday, 6 October 2026 (until 12:00)
Your reservation 2 nights, Large Double Room
Location
Laos, Vang Vieng, 20/1 Ban Vang Vieng, Vang Vieng, Laos
''';

      final result = extractBookingFromText(email);

      expect(result.bookingType, equals('hotel'));
      expect(result.venueName, equals('Mad Monkey Vang Vieng'));
      expect(result.scheduledStart, equals(DateTime(2026, 10, 4, 14)));
      expect(result.durationMinutes, equals(46 * 60));
      expect(result.confirmationCode, isNull);
      expect(result.confirmationCode, isNot(equals('details')));
      expect(result.geoRegion, equals('vang_vieng_laos'));
    });

    test('does not treat Reservation details as a confirmation code', () {
      const email = '''
Thanks Vikrant Vilas! Your booking in Vang Vieng is confirmed.
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Reservation details
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
''';
      expect(extractBookingFromText(email).confirmationCode, isNot(equals('details')));
      expect(extractBookingFromText(email).confirmationCode, isNull);
    });

    test('supports dotted Booking.com references and explicit PIN labels', () {
      expect(
        extractBookingFromText(
          'Hotel stay\nBooking reference: 1234.567.890',
        ).confirmationCode,
        '1234.567.890',
      );
      expect(
        extractBookingFromText('Hotel stay\nPIN code: 9876').confirmationCode,
        '9876',
      );
    });
  });

  // =========================================================
  // TripNode fromJson
  // =========================================================

  group('TripNode fromJson booking fields', () {
    // Sabotage 4: node_kind required (no default) -> this FAILS on legacy JSON
    test('handles booking fields and defaults', () {
      // Legacy JSON without booking fields
      final legacy = TripNode.fromJson({
        'node_id': 'n1',
        'venue_name': 'Old Place',
        'scheduled_start': '2026-10-05T09:00:00Z',
        'duration_minutes': 60,
        'is_locked': false,
        'status': 'pending',
        'vibe_tags': <String>[],
      });
      expect(legacy.nodeKind, equals('activity'));
      expect(legacy.bookingType, isNull);
      expect(legacy.confirmationCode, isNull);
      expect(legacy.bookingNotes, isNull);
      expect(legacy.importSource, isNull);

      // Full booking JSON
      final booking = TripNode.fromJson({
        'node_id': 'n2',
        'venue_name': 'Flight EK501',
        'scheduled_start': '2026-10-05T14:00:00Z',
        'duration_minutes': 180,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'flight',
        'confirmation_code': 'AB12CD',
        'booking_notes': 'Window seat',
        'import_source': 'email',
      });
      expect(booking.nodeKind, equals('booking'));
      expect(booking.bookingType, equals('flight'));
      expect(booking.confirmationCode, equals('AB12CD'));
    });
  });

  // =========================================================
  // Signal emission
  // =========================================================

  group('emitBookingAdded signal', () {
    late OfflineDatabase db;
    late SignalService signalService;

    setUp(() async {
      db = OfflineDatabase(testPath: inMemoryDatabasePath);
      final mockSync = MockSyncEngine();
      signalService = SignalService(db: db, syncEngine: mockSync);
    });

    tearDown(() async {
      await db.close();
    });

    // Sabotage 2: add confirmation_code to valueJson -> this test FAILS
    test('enqueues outbox record without confirmation code', () async {
      await signalService.emitBookingAdded(
        bookingType: 'flight',
        importSource: 'email',
        tripId: 'trip_123',
      );

      final batch = await db.getPendingBatch();
      expect(batch, hasLength(1));
      final payload = jsonDecode(batch.first['payload_json'] as String);
      expect(payload['signal_type'], equals('booking_added'));
      final valueJson = payload['value_json'] as Map<String, dynamic>;
      expect(valueJson['booking_type'], equals('flight'));
      expect(valueJson['import_source'], equals('email'));
      // Privacy: confirmation_code MUST NOT be in the signal
      expect(valueJson.containsKey('confirmation_code'), isFalse);
    });
  });
}
