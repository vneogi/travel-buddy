import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
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
      final expectedFile = File('$baseName.expected.json');
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
      reason: '$fieldName quality mismatch');
  if (expectedValue == null) {
    expect(actual.value, isNull, reason: '$fieldName should be null');
  } else if (parse != null) {
    expect(actual.value, parse(expectedValue),
        reason: '$fieldName value mismatch');
  } else {
    expect(actual.value, expectedValue,
        reason: '$fieldName value mismatch');
  }
}

/// SPEC-10 remainder: provider-aware booking paste.
///
/// Golden corpus loaded from disk, extraction quality, sabotage proofs.
void main() {
  // `flutter test` sets cwd to the package root (mobile/).
  final fixtureRoot = 'test/fixtures/booking_parser';

  // ================================================================
  // Parameterized golden corpus from disk
  // ================================================================

  group('Golden corpus (parameterized)', () {
    final cases = loadFixtures(fixtureRoot);

    for (final c in cases) {
      test('fixture: ${c.name}', () {
        final r = extractBookingFromText(c.rawText);
        final e = c.expected;

        expect(r.provider, _parseProvider(e['provider'] as String),
            reason: '${c.name} provider');

        assertField<String>('bookingType', r.bookingTypeField,
            e['bookingType'] as Map<String, dynamic>?);
        assertField<String>('venueName', r.venueNameField,
            e['venueName'] as Map<String, dynamic>?);
        assertField<DateTime>('scheduledStart', r.scheduledStartField,
            e['scheduledStart'] as Map<String, dynamic>?,
            parse: (v) => DateTime.parse(v as String));
        assertField<DateTime>('checkoutDate', r.checkoutDateField,
            e['checkoutDate'] as Map<String, dynamic>?,
            parse: (v) => DateTime.parse(v as String));
        assertField<int>('durationMinutes', r.durationMinutesField,
            e['durationMinutes'] as Map<String, dynamic>?,
            parse: (v) => (v as num).toInt());
        assertField<String>('confirmationCode', r.confirmationCodeField,
            e['confirmationCode'] as Map<String, dynamic>?);
        assertField<String>('geoRegion', r.geoRegionField,
            e['geoRegion'] as Map<String, dynamic>?);
      });
    }
  });

  // ================================================================
  // Booking ID separator: "is"
  // ================================================================

  group('Booking ID separator', () {
    test('"Booking ID is VALUE." extracts VALUE without trailing dot', () {
      final r = extractBookingFromText('Booking ID is ZX12.345.678.');
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
  // Venue name safety
  // ================================================================

  group('Venue name safety', () {
    test('greeting/passenger/footer/account lines never become venueName', () {
      const greetingPassengerFooter =
          'Dear Mr. Traveler,\n'
          'Thanks for your purchase!\n'
          'Passenger: Jane Doe\n'
          'Your booking ID is BK999888.\n'
          'Manage your booking at https://example.com/manage\n'
          'Download the app for updates.\n'
          'Sign in to view your itinerary.';
      final r = extractBookingFromText(greetingPassengerFooter);
      expect(r.venueName, isNull,
          reason: 'No safe venue pattern found; must be null');
      expect(r.confirmationCode, 'BK999888');
    });
  });

  // ================================================================
  // Flight departure independence
  // ================================================================

  group('Flight parsing', () {
    test('Departure in flight context is NOT rewritten to check-out', () {
      const flightEmail =
          'Booking Confirmed! Flight EK501 to Dubai.\n'
          'Terminal 3, Gate B22\n'
          'PNR: FLT123\n'
          'Departure: 14:00';
      final r = extractBookingFromText(flightEmail);
      expect(r.bookingType, 'flight');
      expect(r.confirmationCode, 'FLT123');
      expect(r.geoRegion, 'dubai_uae');
      expect(r.checkoutDate, isNull,
          reason: 'Departure must stay a flight field, not rewritten');
    });
  });

  // ================================================================
  // Label separator variants
  // ================================================================

  group('Label separator variants', () {
    test('colon separator parses dates', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 5 October 2026\nCheck-out: 7 October 2026',
      );
      expect(r.scheduledStart, DateTime(2026, 10, 5));
      expect(r.checkoutDate, DateTime(2026, 10, 7));
    });

    test('hash separator parses dates', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in # 5 October 2026\nCheck-out # 7 October 2026',
      );
      expect(r.scheduledStart, DateTime(2026, 10, 5));
      expect(r.checkoutDate, DateTime(2026, 10, 7));
    });

    test('equals separator parses dates', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in = 5 October 2026\nCheck-out = 7 October 2026',
      );
      expect(r.scheduledStart, DateTime(2026, 10, 5));
      expect(r.checkoutDate, DateTime(2026, 10, 7));
    });

    test('"is" separator parses dates', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in is 5 October 2026\nCheck-out is 7 October 2026',
      );
      expect(r.scheduledStart, DateTime(2026, 10, 5));
      expect(r.checkoutDate, DateTime(2026, 10, 7));
    });

    test('whitespace-only separator parses dates', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in  Sunday, 4 October 2026 (14:00 - 00:00)\n'
        'Check-out Tuesday, 6 October 2026 (until 12:00)',
      );
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
      expect(r.checkoutDate, DateTime(2026, 10, 6, 12));
    });
  });

  // ================================================================
  // Invalid calendar dates
  // ================================================================

  group('Invalid calendar dates', () {
    test('Feb 30 is rejected, not normalized to Mar 2', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 30 February 2026',
      );
      expect(r.scheduledStart, isNull,
          reason: 'Feb 30 does not exist; must be rejected');
    });

    test('Apr 31 is rejected', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 31 April 2026',
      );
      expect(r.scheduledStart, isNull,
          reason: 'Apr 31 does not exist; must be rejected');
    });

    test('Mar 32 is rejected', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 32 March 2026',
      );
      expect(r.scheduledStart, isNull,
          reason: 'Mar 32 does not exist; must be rejected');
    });

    test('valid Feb 28 is accepted', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 28 February 2026',
      );
      expect(r.scheduledStart, DateTime(2026, 2, 28));
    });
  });

  // ================================================================
  // Normalization
  // ================================================================

  group('Normalization', () {
    test('unicode spacing normalizes correctly', () {
      const unicodeSpacing =
          'Booking.com\u00A0\u00A0\u00A0confirmation\n'
          'Mad\u202FMonkey\u00A0Vang\u00A0Vieng is expecting you on Sun 4 Oct 2026\n'
          'Check-in\u00A0 Sunday, 4 October 2026 (14:00 - 00:00)\n'
          'Check-out\u00A0Tuesday, 6 October 2026 (until 12:00)\n'
          'Vang Vieng, Laos';
      final r = extractBookingFromText(unicodeSpacing);
      expect(r.provider, BookingProvider.bookingCom);
      expect(r.venueName, 'Mad Monkey Vang Vieng');
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
    });

    test('forwarded-email prefix variants normalize correctly', () {
      const forwardedPrefix =
          '> > Booking.com\n'
          '> > Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026\n'
          '> Check-in  Sunday, 4 October 2026 (14:00 - 00:00)\n'
          '> Check-out Tuesday, 6 October 2026 (until 12:00)\n'
          '> Vang Vieng, Laos';
      final r = extractBookingFromText(forwardedPrefix);
      expect(r.provider, BookingProvider.bookingCom);
      expect(r.venueName, 'Mad Monkey Vang Vieng');
      expect(r.scheduledStart, DateTime(2026, 10, 4, 14));
    });
  });

  // ================================================================
  // Robustness
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
  // No-network proof
  // ================================================================

  group('No-network proof', () {
    test('extraction opens no socket', () {
      final overrides = _FailingHttpOverrides();
      HttpOverrides.global = overrides;
      addTearDown(() => HttpOverrides.global = null);
      expect(
        () => extractBookingFromText(
          'Booking.com\nMad Monkey is expecting you on Sun 4 Oct 2026\n'
          'Check-in Sunday, 4 October 2026 (14:00 - 00:00)',
        ),
        returnsNormally,
      );
      expect(overrides.socketOpened, isFalse);
    });
  });

  // ================================================================
  // Extraction quality assertions
  // ================================================================

  group('Extraction quality', () {
    test('Booking.com full fields have full quality', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/booking_com/full_confirmation.txt')
            .readAsStringSync(),
      );
      expect(r.bookingTypeField.quality, ExtractionQuality.full);
      expect(r.venueNameField.quality, ExtractionQuality.full);
      expect(r.scheduledStartField.quality, ExtractionQuality.full);
      expect(r.checkoutDateField.quality, ExtractionQuality.full);
      expect(r.durationMinutesField.quality, ExtractionQuality.full);
      expect(r.confirmationCodeField.quality, ExtractionQuality.full);
    });

    test('generic fields have partial quality', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/generic/labelled_fields.txt')
            .readAsStringSync(),
      );
      expect(r.bookingTypeField.quality, ExtractionQuality.partial);
      expect(r.venueNameField.quality, ExtractionQuality.partial);
      expect(r.scheduledStartField.quality, ExtractionQuality.partial);
      expect(r.confirmationCodeField.quality, ExtractionQuality.partial);
    });

    test('missing fields have unknown quality', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/agoda/footer_only.txt').readAsStringSync(),
      );
      expect(r.venueNameField.quality, ExtractionQuality.unknown);
      expect(r.scheduledStartField.quality, ExtractionQuality.unknown);
      expect(r.bookingTypeField.quality, ExtractionQuality.unknown);
    });
  });

  // ================================================================
  // Sabotage proofs
  // ================================================================

  group('Sabotage proofs', () {
    test('S1: no first-line venue fallback', () {
      const greetingText =
          'Dear Mr. Traveler,\n'
          'Thanks for your purchase!\n'
          'Passenger: Jane Doe\n'
          'Your booking ID is BK999888.\n'
          'Manage your booking at https://example.com/manage';
      final r = extractBookingFromText(greetingText);
      expect(r.venueName, isNull,
          reason: 'Restoring first-line fallback would fail this');
    });

    test('S2: no default hotel duration when dates absent', () {
      const missingCheckout =
          'Mad Monkey Vang Vieng is expecting you on Sun 4 Oct 2026\n'
          'Check-in  Sunday, 4 October 2026 (14:00 - 00:00)\n'
          'Vang Vieng, Laos';
      final r = extractBookingFromText(missingCheckout);
      expect(r.durationMinutes, isNull,
          reason: 'Restoring default 480 hotel duration would fail this');
    });

    test('S3: "is" separator supported', () {
      final r = extractBookingFromText('Booking ID is ZX12.345.678.');
      expect(r.confirmationCode, 'ZX12.345.678',
          reason: 'Removing "is" separator would fail this');
    });

    test('S4: footer-only Agoda does not become hotel name', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/agoda/footer_only.txt').readAsStringSync(),
      );
      expect(r.venueName, isNull,
          reason: 'Letting footer text become venueName would fail this');
    });

    test('S5: unclassified paste does not default to Flight', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/malformed/no_labels.txt').readAsStringSync(),
      );
      expect(r.bookingType, isNull,
          reason: 'Defaulting to Flight would fail this');
    });

    // S6: Discriminating UI/payload assertion.
    // If the zero-field guard in _autoFill() is removed, the UI would
    // set _importSource = 'email' even on junk. This test verifies
    // the contract that prevents that: hasUsefulFields must be false
    // AND foundFields must be empty.
    test('S6: zero-field parse contract prevents false import claim', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/malformed/no_labels.txt').readAsStringSync(),
      );
      expect(r.hasUsefulFields, isFalse,
          reason: 'Zero-field parse must report no useful fields');
      expect(r.foundFields, isEmpty,
          reason: 'Zero-field parse must have empty foundFields');
      expect(r.missingFields, isNotEmpty,
          reason: 'Must list missing fields for the UI');
      // Parser returns importSource=email but UI guard prevents applying it.
      expect(r.importSource, 'email');
    });

    test('S7: flight Departure not rewritten to check-out', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/generic/flight_departure.txt').readAsStringSync(),
      );
      expect(r.bookingType, 'flight',
          reason: 'Flight must be detected independently');
      expect(r.checkoutDate, isNull,
          reason: 'Restoring global departure->check-out rewrite '
              'would give this flight a check-out date');
    });

    test('S8: impossible dates rejected', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/malformed/invalid_date.txt').readAsStringSync(),
      );
      expect(r.scheduledStart, isNull,
          reason: 'Removing date validation would normalize Feb 30');
      expect(r.checkoutDate, isNull,
          reason: 'Removing date validation would normalize Mar 32');
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
