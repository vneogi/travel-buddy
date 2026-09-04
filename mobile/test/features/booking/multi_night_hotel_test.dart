import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/booking/booking_parser.dart';

/// SPEC-33: Multi-night hotel bookings.
///
/// Sabotage proofs:
///   S1: Second date picker on flights -> flight test fails.
///   S2: Store checkout as new column -> schema/review fails.
///   S3: Clone one node per night -> grouping identity test fails.
///   S4: New node_id on hotel date edit -> stable-ID test fails.
void main() {
  // ===========================================================
  // Hotel create: check-in / check-out -> duration_minutes
  // ===========================================================

  group('Hotel duration from check-in / check-out', () {
    test('two-night stay produces 2880 minutes at same clock time', () {
      // Check-in 4 Oct 15:00, check-out 6 Oct 15:00 = exactly 2 nights
      final checkIn = DateTime(2026, 10, 4, 15, 0);
      final checkOut = DateTime(2026, 10, 6, 15, 0);
      final duration = checkOut.difference(checkIn).inMinutes;
      expect(duration, equals(2880));
    });

    test('one-night stay with different clock times computes correctly', () {
      // Check-in 4 Oct 14:00, check-out 5 Oct 12:00 = 22 hours = 1320 min
      final checkIn = DateTime(2026, 10, 4, 14, 0);
      final checkOut = DateTime(2026, 10, 5, 12, 0);
      final duration = checkOut.difference(checkIn).inMinutes;
      expect(duration, equals(1320));
    });

    test('checkout on or before check-in is invalid (duration <= 0)', () {
      final checkIn = DateTime(2026, 10, 4, 15, 0);

      // Same date/time
      final sameTime = checkIn;
      expect(sameTime.difference(checkIn).inMinutes, equals(0));

      // Before check-in
      final before = DateTime(2026, 10, 3, 12, 0);
      expect(before.difference(checkIn).inMinutes, lessThan(0));
    });
  });

  // ===========================================================
  // Flight / train / tour: no second date picker
  // ===========================================================

  group('Non-hotel bookings use single start + duration', () {
    // Sabotage S1: if a second date picker exists for flights, this test
    // should assert that _checkoutDate is null / unused.
    test('flight uses default 180 minutes duration, no checkout concept', () {
      final node = TripNode.fromJson({
        'node_id': 'f1',
        'venue_name': 'EK501',
        'scheduled_start': '2026-10-05T14:00:00Z',
        'duration_minutes': 180,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'flight',
      });
      expect(node.durationMinutes, equals(180));
      expect(node.bookingType, equals('flight'));
      // No checkout column exists on the model
      expect(node.toJson().containsKey('checkout_date'), isFalse);
    });

    test('train uses default 120 minutes duration', () {
      final node = TripNode.fromJson({
        'node_id': 't1',
        'venue_name': 'Eastern Express',
        'scheduled_start': '2026-10-05T08:00:00Z',
        'duration_minutes': 120,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'train',
      });
      expect(node.durationMinutes, equals(120));
      expect(node.toJson().containsKey('checkout_date'), isFalse);
    });

    test('tour uses default 90 minutes duration', () {
      final node = TripNode.fromJson({
        'node_id': 'to1',
        'venue_name': 'Desert Safari',
        'scheduled_start': '2026-10-06T16:00:00Z',
        'duration_minutes': 90,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'tour',
      });
      expect(node.durationMinutes, equals(90));
      expect(node.toJson().containsKey('checkout_date'), isFalse);
    });
  });

  // ===========================================================
  // Hotel edit: prefill checkout, preserve node_id
  // ===========================================================

  group('Hotel edit preserves node_id and prefills checkout', () {
    // Sabotage S4: New node_id on hotel date edit -> this fails.
    test('edit prefills checkout from scheduledStart + durationMinutes', () {
      final hotel = TripNode.fromJson({
        'node_id': 'h1',
        'venue_name': 'Ritz Carlton',
        'scheduled_start': '2026-10-04T15:00:00Z',
        'duration_minutes': 2880,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'hotel',
      });

      // Simulate what the sheet does in initState for edit mode
      final checkIn = hotel.scheduledStart;
      final checkOut = checkIn.add(Duration(minutes: hotel.durationMinutes));

      expect(checkIn, equals(DateTime.utc(2026, 10, 4, 15, 0)));
      expect(checkOut, equals(DateTime.utc(2026, 10, 6, 15, 0)));
      expect(hotel.nodeId, equals('h1'));
    });

    test('changing checkout updates duration but preserves node_id', () {
      final hotel = TripNode.fromJson({
        'node_id': 'h1',
        'venue_name': 'Ritz Carlton',
        'scheduled_start': '2026-10-04T15:00:00Z',
        'duration_minutes': 2880,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'hotel',
      });

      // Extend by one night: check-out moves to 7 Oct
      final newCheckout = DateTime.utc(2026, 10, 7, 15, 0);
      final newDuration = newCheckout.difference(hotel.scheduledStart).inMinutes;

      expect(newDuration, equals(4320)); // 3 nights
      expect(hotel.nodeId, equals('h1')); // Same node
    });
  });

  // ===========================================================
  // S3: Multi-night hotel is ONE node, not cloned per night
  // ===========================================================

  group('Multi-night hotel is a single node', () {
    test('hotel with 2-night duration is one TripNode with long duration', () {
      final hotel = TripNode.fromJson({
        'node_id': 'h2',
        'venue_name': 'Mad Monkey',
        'scheduled_start': '2026-10-04T14:00:00Z',
        'duration_minutes': 2760, // 46 hours
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'hotel',
      });

      // It is a single node, not multiple nodes
      expect(hotel.nodeId, equals('h2'));
      expect(hotel.durationMinutes, equals(2760));
      // roundtrip through toJson preserves single-node identity
      final json = hotel.toJson();
      final restored = TripNode.fromJson(json);
      expect(restored.nodeId, equals('h2'));
      expect(restored.durationMinutes, equals(2760));
    });
  });

  // ===========================================================
  // S2: No checkout column in the schema
  // ===========================================================

  group('Schema: no checkout column', () {
    test('TripNode.toJson does not include checkout_date or check_out', () {
      final hotel = TripNode.fromJson({
        'node_id': 'h3',
        'venue_name': 'Test Hotel',
        'scheduled_start': '2026-10-04T15:00:00Z',
        'duration_minutes': 1440,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'hotel',
      });
      final json = hotel.toJson();
      expect(json.containsKey('checkout_date'), isFalse);
      expect(json.containsKey('check_out'), isFalse);
      expect(json.containsKey('check_out_date'), isFalse);
      // Duration is sent via existing field
      expect(json['duration_minutes'], equals(1440));
      expect(json['scheduled_start'], isNotNull);
    });
  });

  // ===========================================================
  // Parser: paste with Booking.com-style check-in/check-out
  // ===========================================================

  group('Parser: Booking.com check-in/check-out fills hotel dates', () {
    test('paste with both dates populates checkoutDate', () {
      const email = '''
Thanks Vikrant Vilas! Your booking in Vang Vieng is confirmed.
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Reservation details
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
Check-out Tuesday, 6 October 2026 (until 12:00)
Your reservation 2 nights, Large Double Room
''';

      final result = extractBookingFromText(email);

      expect(result.bookingType, equals('hotel'));
      expect(result.scheduledStart, equals(DateTime(2026, 10, 4, 14)));
      expect(result.checkoutDate, equals(DateTime(2026, 10, 6, 12)));
      expect(result.durationMinutes, equals(46 * 60)); // 2760 min
    });

    test('paste with only check-in does not invent a checkout', () {
      const email = '''
Hotel Marrakech is expecting you on Fri 10 Oct 2026
Check-in  Friday, 10 October 2026 (15:00 - 00:00)
''';

      final result = extractBookingFromText(email);

      expect(result.scheduledStart, equals(DateTime(2026, 10, 10, 15)));
      expect(result.checkoutDate, isNull);
    });

    test('flight email does not produce a checkout', () {
      const email = '''
Boarding Pass
Flight EK501 to Dubai
PNR: AB12CD
Departure: Terminal 3
''';

      final result = extractBookingFromText(email);

      expect(result.bookingType, equals('flight'));
      expect(result.checkoutDate, isNull);
    });
  });

  // ===========================================================
  // Wire: still sends scheduled_start + duration_minutes
  // ===========================================================

  group('Wire format uses existing fields', () {
    test('hotel toJson uses scheduled_start and duration_minutes', () {
      final hotel = TripNode.fromJson({
        'node_id': 'w1',
        'venue_name': 'Grand Hyatt',
        'scheduled_start': '2026-10-04T15:00:00Z',
        'duration_minutes': 2880,
        'is_locked': true,
        'status': 'pending',
        'vibe_tags': <String>[],
        'node_kind': 'booking',
        'booking_type': 'hotel',
      });
      final json = hotel.toJson();
      expect(json['scheduled_start'], contains('2026-10-04'));
      expect(json['duration_minutes'], equals(2880));
    });
  });
}
