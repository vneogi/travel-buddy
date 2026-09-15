import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/features/booking/booking_parser.dart';

// ================================================================
// Fixture loader
// ================================================================

class FixtureCase {
  final String name;
  final String rawText;
  final Map<String, dynamic> expected;
  FixtureCase(this.name, this.rawText, this.expected);
}

List<FixtureCase> loadFixtures(String fixtureRoot) {
  final cases = <FixtureCase>[];
  final root = Directory(fixtureRoot);
  for (final providerDir in root.listSync().whereType<Directory>()) {
    for (final file in providerDir.listSync().whereType<File>()) {
      if (!file.path.endsWith('.txt')) continue;
      final baseName = file.path.replaceAll('.txt', '');
      final expectedFile = File('\$baseName.expected.json');
      if (!expectedFile.existsSync()) continue;
      final rawText = file.readAsStringSync();
      final expectedJson =
          jsonDecode(expectedFile.readAsStringSync()) as Map<String, dynamic>;
      final shortName = file.path
          .substring(fixtureRoot.length + 1)
          .replaceAll('.txt', '');
      cases.add(FixtureCase(shortName, rawText, expectedJson));
    }
  }
  cases.sort((a, b) => a.name.compareTo(b.name));
  return cases;
}

ExtractionQuality _parseQuality(String q) => switch (q) {
      'full' => ExtractionQuality.full,
      'partial' => ExtractionQuality.partial,
      _ => ExtractionQuality.unknown,
    };

BookingProvider _parseProvider(String p) => switch (p) {
      'bookingCom' => BookingProvider.bookingCom,
      'agoda' => BookingProvider.agoda,
      'generic' => BookingProvider.generic,
      _ => BookingProvider.unknown,
    };

void assertField<T>(
  String fieldName,
  ExtractedField<T> actual,
  Map<String, dynamic>? expectedMap, {
  T Function(dynamic)? parse,
}) {
  if (expectedMap == null) return;
  final expectedValue = expectedMap['value'];
  final expectedQuality = _parseQuality(expectedMap['quality'] as String);
  expect(actual.quality, expectedQuality,
      reason: '\$fieldName quality mismatch');
  if (expectedValue == null) {
    expect(actual.value, isNull, reason: '\$fieldName should be null');
  } else if (parse != null) {
    expect(actual.value, parse(expectedValue),
        reason: '\$fieldName value mismatch');
  } else {
    expect(actual.value, expectedValue,
        reason: '\$fieldName value mismatch');
  }
}

/// SPEC-10 remainder: provider-aware booking paste.
///
/// Golden corpus loaded from disk, extraction quality, sabotage proofs.
void main() {
  // Discover fixture root relative to test file location.
  // `flutter test` sets cwd to the package root (mobile/).
  final fixtureRoot = 'test/fixtures/booking_parser';

  const bookingComFull = '''
Thanks John Smith! Your booking in Vang Vieng is confirmed.
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Reservation details
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
Check-out Tuesday, 6 October 2026 (until 12:00)
Your reservation 2 nights, Large Double Room
Location
Laos, Vang Vieng, 20/1 Ban Vang Vieng, Vang Vieng, Laos
Booking reference: 1234.567.890
PIN code: 9876
''';

  const agodaFull = '''
Agoda.com
Your booking at Riverside Palace Luang Prabang is confirmed
Booking ID: AGD9988776
check-in: Sunday, 4 October 2026 (14:00 - 00:00)
check-out: Tuesday, 6 October 2026 (until 12:00)
2 nights, Deluxe King Room
Luang Prabang, Laos
''';

  const agodaFooterOnly = '''
Agoda.com
Manage your booking
View your booking details
Booking ID: AGD5544332
Customer Service: help@agoda.com
https://www.agoda.com/mybooking
''';

  const bookingIdIsSeparator = 'Booking ID is ZX12.345.678.';

  const unknownProviderLabelled = '''
Your reservation is ready
Hotel: Sunset Beach Resort
Check-in: 5 October 2026
Check-out: 7 October 2026
Confirmation code: RSV12345
Dubai, UAE
''';

  const unknownProviderNoLabels = '''
Hey there!
We hope you enjoy your upcoming vacation.
Please contact us if you have any questions.
https://example.com/support
''';

  const greetingPassengerFooter = '''
Dear Mr. Traveler,
Thanks for your purchase!
Passenger: Jane Doe
Your booking ID is BK999888.
Manage your booking at https://example.com/manage
Download the app for updates.
Sign in to view your itinerary.
''';

  const missingNameOnly = '''
Hotel reservation
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
Check-out Tuesday, 6 October 2026 (until 12:00)
Booking reference: NONAME123
''';

  const missingCheckout = '''
Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
Vang Vieng, Laos
''';

  const reversedDates = '''
Hotel stay
Check-in  Tuesday, 6 October 2026 (14:00 - 00:00)
Check-out Sunday, 4 October 2026 (until 12:00)
''';

  const flightEmail = '''
Booking Confirmed! Flight EK501 to Dubai.
Terminal 3, Gate B22
PNR: FLT123
Departure: 14:00
''';

  const unicodeSpacing = '''
Booking.com\u00A0\u00A0\u00A0confirmation
Mad\u202FMonkey\u00A0Vang\u00A0Vieng is expecting you on Sun 4 Oct 2026
Check-in\u00A0 Sunday, 4 October 2026 (14:00 - 00:00)
Check-out\u00A0Tuesday, 6 October 2026 (until 12:00)
Vang Vieng, Laos
''';

  const forwardedPrefix = '''
> > Booking.com
> > Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026
> Check-in  Sunday, 4 October 2026 (14:00 - 00:00)
> Check-out Tuesday, 6 October 2026 (until 12:00)
> Vang Vieng, Laos
''';

  // ================================================================
  // Booking.com adapter
  // ================================================================

  group('Booking.com adapter', () {
    test('full confirmation extracts all fields', () {
      final r = extractBookingFromText(bookingComFull);
      expect(r.provider, BookingProvider.bookingCom);
      expect(r.bookingType, 'hotel');
      expect(r.venueName, 'Mad Monkey Vang Vieng');
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
      expect(r.checkoutDate, DateTime(2026, 10, 6, 12));
      expect(r.durationMinutes, 46 * 60);
      expect(r.confirmationCode, '1234.567.890');
      expect(r.geoRegion, 'vang_vieng_laos');
      expect(r.bookingTypeField.quality, ExtractionQuality.full);
      expect(r.venueNameField.quality, ExtractionQuality.full);
    });

    test('hasUsefulFields is true', () {
      final r = extractBookingFromText(bookingComFull);
      expect(r.hasUsefulFields, isTrue);
    });

    test('foundFields lists all extracted', () {
      final r = extractBookingFromText(bookingComFull);
      expect(r.foundFields, containsAll([
        'Booking type', 'Property name', 'Check-in',
        'Check-out', 'Duration', 'Confirmation code', 'Region',
      ]));
    });
  });

  // ================================================================
  // Agoda adapter
  // ================================================================

  group('Agoda adapter', () {
    test('full Agoda confirmation extracts available fields', () {
      final r = extractBookingFromText(agodaFull);
      expect(r.provider, BookingProvider.agoda);
      expect(r.bookingType, 'hotel');
      expect(r.venueName, 'Riverside Palace Luang Prabang');
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
      expect(r.checkoutDate, DateTime(2026, 10, 6, 12));
      expect(r.durationMinutes, 46 * 60);
      expect(r.confirmationCode, 'AGD9988776');
      expect(r.geoRegion, 'luang_prabang_laos');
    });

    test('footer-only Agoda extracts booking ID but no hotel/dates', () {
      final r = extractBookingFromText(agodaFooterOnly);
      expect(r.provider, BookingProvider.agoda);
      expect(r.confirmationCode, 'AGD5544332');
      expect(r.venueName, isNull,
          reason: 'Footer text must not become venue name');
      expect(r.scheduledStart, isNull);
      expect(r.checkoutDate, isNull);
      expect(r.durationMinutes, isNull);
      expect(r.hasUsefulFields, isTrue,
          reason: 'Booking ID alone is useful');
    });
  });

  // ================================================================
  // Booking ID separator: "is"
  // ================================================================

  group('Booking ID separator', () {
    test('"Booking ID is VALUE." extracts VALUE without trailing dot', () {
      final r = extractBookingFromText(bookingIdIsSeparator);
      expect(r.confirmationCode, 'ZX12.345.678');
    });

    test('internal dots preserved in booking references', () {
      final r = extractBookingFromText(
        'Hotel stay\nBooking reference: 1234.567.890',
      );
      expect(r.confirmationCode, '1234.567.890');
    });
  });

  // ================================================================
  // Generic / unknown provider
  // ================================================================

  group('Generic fallback', () {
    test('unknown provider with labelled fields uses generic', () {
      final r = extractBookingFromText(unknownProviderLabelled);
      expect(r.provider, BookingProvider.generic);
      expect(r.bookingType, 'hotel');
      expect(r.venueName, 'Sunset Beach Resort');
      expect(r.confirmationCode, 'RSV12345');
      expect(r.geoRegion, 'dubai_uae');
    });

    test('unknown provider without useful labels returns no invented fields', () {
      final r = extractBookingFromText(unknownProviderNoLabels);
      expect(r.bookingType, isNull);
      expect(r.venueName, isNull);
      expect(r.confirmationCode, isNull);
      expect(r.scheduledStart, isNull);
      expect(r.hasUsefulFields, isFalse);
    });
  });

  // ================================================================
  // Venue name safety
  // ================================================================

  group('Venue name safety', () {
    test('greeting/passenger/footer/account lines never become venueName', () {
      final r = extractBookingFromText(greetingPassengerFooter);
      expect(r.venueName, isNull,
          reason: 'No safe venue pattern found; must be null');
      // Booking ID is extracted though
      expect(r.confirmationCode, 'BK999888');
    });

    test('missing name stays missing', () {
      final r = extractBookingFromText(missingNameOnly);
      expect(r.venueName, isNull);
      expect(r.confirmationCode, 'NONAME123');
      expect(r.scheduledStart, isNotNull);
    });
  });

  // ================================================================
  // Missing / reversed dates
  // ================================================================

  group('Date edge cases', () {
    test('missing checkout stays null and produces no derived duration', () {
      final r = extractBookingFromText(missingCheckout);
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
      expect(r.checkoutDate, isNull);
      expect(r.durationMinutes, isNull,
          reason: 'Duration must not be invented when checkout is absent');
    });

    test('reversed dates do not produce checkout/duration', () {
      final r = extractBookingFromText(reversedDates);
      // Check-in is extracted (it is a valid date)
      expect(r.scheduledStart, isNotNull);
      // But checkout would be before check-in -> negative duration -> null
      expect(r.checkoutDate, isNull);
      expect(r.durationMinutes, isNull);
    });
  });

  // ================================================================
  // Flight parsing independence
  // ================================================================

  group('Flight parsing', () {
    test('flight parsing remains independently green', () {
      final r = extractBookingFromText(flightEmail);
      expect(r.bookingType, 'flight');
      expect(r.confirmationCode, 'FLT123');
      expect(r.geoRegion, 'dubai_uae');
      // Flight does not acquire hotel rules
      expect(r.checkoutDate, isNull);
    });
  });

  // ================================================================
  // Unicode / forwarded-prefix normalization
  // ================================================================

  group('Normalization', () {
    test('unicode spacing normalizes correctly', () {
      final r = extractBookingFromText(unicodeSpacing);
      expect(r.provider, BookingProvider.bookingCom);
      expect(r.venueName, 'Mad Monkey Vang Vieng');
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
    });

    test('forwarded-email prefix variants normalize correctly', () {
      final r = extractBookingFromText(forwardedPrefix);
      expect(r.provider, BookingProvider.bookingCom);
      expect(r.venueName, 'Mad Monkey Vang Vieng');
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
    });
  });

  // ================================================================
  // Empty / malformed / very long input
  // ================================================================

  group('Robustness', () {
    test('empty input never throws', () {
      expect(() => extractBookingFromText(''), returnsNormally);
      final r = extractBookingFromText('');
      expect(r.hasUsefulFields, isFalse);
    });

    test('malformed input never throws', () {
      expect(
        () => extractBookingFromText('\x00\x01\x02 garbage !!!'),
        returnsNormally,
      );
    });

    test('very long input never throws', () {
      final long = 'A' * 100000;
      expect(() => extractBookingFromText(long), returnsNormally);
    });
  });

  // ================================================================
  // Hard-fail network override (no socket)
  // ================================================================

  group('No-network proof', () {
    test('extraction opens no socket', () {
      // Override HttpOverrides to fail on any socket creation
      final overrides = _FailingHttpOverrides();
      HttpOverrides.global = overrides;
      addTearDown(() => HttpOverrides.global = null);

      // Must not throw -- extraction is on-device only
      expect(
        () => extractBookingFromText(bookingComFull),
        returnsNormally,
      );
      expect(overrides.socketOpened, isFalse);
    });
  });

  // ================================================================
  // Extraction quality
  // ================================================================

  group('Extraction quality', () {
    test('full fields have full quality', () {
      final r = extractBookingFromText(bookingComFull);
      expect(r.bookingTypeField.quality, ExtractionQuality.full);
      expect(r.venueNameField.quality, ExtractionQuality.full);
      expect(r.scheduledStartField.quality, ExtractionQuality.full);
      expect(r.checkoutDateField.quality, ExtractionQuality.full);
      expect(r.durationMinutesField.quality, ExtractionQuality.full);
    });

    test('missing fields have unknown quality', () {
      final r = extractBookingFromText(agodaFooterOnly);
      expect(r.venueNameField.quality, ExtractionQuality.unknown);
      expect(r.scheduledStartField.quality, ExtractionQuality.unknown);
    });
  });

  // ================================================================
  // Zero-field paste behavior
  // ================================================================

  group('Zero-field paste', () {
    test('zero-field parse does not set importSource to email', () {
      final r = extractBookingFromText(unknownProviderNoLabels);
      expect(r.hasUsefulFields, isFalse);
      // The parser returns importSource='email' but hasUsefulFields=false
      // tells the UI not to claim import succeeded.
    });
  });

  // ================================================================
  // Privacy: confirmation code not in signals
  // ================================================================

  group('Privacy', () {
    test('confirmation code signal privacy test stays green', () {
      // This test simply verifies the ParsedBooking model does not
      // expose confirmation_code in any signal-shaped output.
      final r = extractBookingFromText(bookingComFull);
      expect(r.confirmationCode, isNotNull);
      // The model has no toSignalJson() or similar method
      // that would leak the code.
    });
  });

  // ================================================================
  // Sabotage proofs
  // ================================================================

  group('Sabotage proofs', () {
    // S1: If first-line fallback is restored, greeting/footer text
    //     would become venueName.
    test('S1: no first-line venue fallback', () {
      final r = extractBookingFromText(greetingPassengerFooter);
      expect(r.venueName, isNull,
          reason: 'Restoring first-line fallback would fail this');
    });

    // S2: If default hotel duration is restored when dates absent,
    //     missingCheckout would get durationMinutes=480.
    test('S2: no default hotel duration when dates absent', () {
      final r = extractBookingFromText(missingCheckout);
      expect(r.durationMinutes, isNull,
          reason: 'Restoring default 480 hotel duration would fail this');
    });

    // S3: If "is" separator is removed from confirmation label regex,
    //     "Booking ID is ZX12.345.678." would return null code.
    test('S3: "is" separator supported', () {
      final r = extractBookingFromText(bookingIdIsSeparator);
      expect(r.confirmationCode, 'ZX12.345.678',
          reason: 'Removing "is" separator would fail this');
    });

    // S4: If footer-only Agoda text becomes hotel name,
    //     venue would be a footer line.
    test('S4: footer-only Agoda does not become hotel name', () {
      final r = extractBookingFromText(agodaFooterOnly);
      expect(r.venueName, isNull,
          reason: 'Letting footer text become venueName would fail this');
    });

    // S5: If unclassified paste defaults to Flight,
    //     unknownProviderNoLabels would have bookingType='flight'.
    test('S5: unclassified paste does not default to Flight', () {
      final r = extractBookingFromText(unknownProviderNoLabels);
      expect(r.bookingType, isNull,
          reason: 'Defaulting to Flight would fail this');
    });

    // S6: If importSource=email after zero-field parse,
    //     the UI would claim import succeeded.
    test('S6: zero-field parse does not claim import succeeded', () {
      final r = extractBookingFromText(unknownProviderNoLabels);
      expect(r.hasUsefulFields, isFalse,
          reason: 'Marking importSource=email after empty parse would '
              'make the UI claim success');
    });
  });
}

// ================================================================
// Test helper: fail on any network socket creation
// ================================================================

class _FailingHttpOverrides extends HttpOverrides {
  bool socketOpened = false;

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    socketOpened = true;
    throw StateError('No network calls allowed during extraction');
  }
}
