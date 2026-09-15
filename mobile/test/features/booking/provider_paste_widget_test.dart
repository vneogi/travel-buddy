import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/features/booking/booking_parser.dart';

/// Widget-level tests for the extraction review in AddBookingSheet.
///
/// These test the ParsedBooking model's review contract rather than pumping
/// the full widget tree (which requires Riverpod + DB scaffolding). The
/// AddBookingSheet reads these properties to render the review.
void main() {
  group('Extraction review contract', () {
    test('found/missing review appears for useful parse', () {
      const email = '''
Thanks John! Your booking in Vang Vieng is confirmed.
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
Check-out Tuesday, 6 October 2026 (until 12:00)
Vang Vieng, Laos
''';
      final parsed = extractBookingFromText(email);
      expect(parsed.hasUsefulFields, isTrue);
      expect(parsed.foundFields, isNotEmpty);
      expect(parsed.foundFields, contains('Property name'));
      expect(parsed.foundFields, contains('Check-in'));
      expect(parsed.foundFields, contains('Check-out'));
    });

    test('zero-useful-field paste preserves manual mode', () {
      const junk = 'Hello! How are you? Visit our website.';
      final parsed = extractBookingFromText(junk);
      expect(parsed.hasUsefulFields, isFalse);
      expect(parsed.foundFields, isEmpty);
      expect(parsed.missingFields, containsAll([
        'Booking type',
        'Property name',
        'Check-in',
      ]));
    });

    test('partial parse shows found and missing fields', () {
      const partial = '''
Agoda.com
Booking ID: AGD5544332
''';
      final parsed = extractBookingFromText(partial);
      expect(parsed.hasUsefulFields, isTrue);
      expect(parsed.foundFields, contains('Confirmation code'));
      expect(parsed.missingFields, contains('Property name'));
      expect(parsed.missingFields, contains('Check-in'));
    });

    test('provider name is available for display', () {
      const email = '''
Booking.com
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
''';
      final parsed = extractBookingFromText(email);
      expect(parsed.provider, BookingProvider.bookingCom);

      const agoda = 'Agoda.com\nBooking ID: TEST1234';
      final parsedAgoda = extractBookingFromText(agoda);
      expect(parsedAgoda.provider, BookingProvider.agoda);
    });
  });
}
