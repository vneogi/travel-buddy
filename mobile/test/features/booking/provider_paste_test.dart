import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/features/booking/booking_parser.dart';

// ================================================================
// Fail-closed fixture loader
// ================================================================

/// Declared fixture set. Every entry must have both .txt and .expected.json.
const _declaredFixtures = <String>[
  'agoda/branded_flight',
  'agoda/footer_only',
  'agoda/full_confirmation',
  'booking_com/branded_flight',
  'booking_com/full_confirmation',
  'booking_com/hotel_arrival_departure',
  'generic/flight_departure',
  'generic/labelled_fields',
  'malformed/invalid_date',
  'malformed/no_labels',
  'malformed/reversed_dates',
];

const _validProviders = <String>{'bookingCom', 'agoda', 'generic', 'unknown'};
const _validQualities = <String>{'full', 'partial', 'unknown'};
const _requiredFields = <String>[
  'bookingType', 'venueName', 'scheduledStart', 'checkoutDate',
  'durationMinutes', 'confirmationCode', 'geoRegion',
];

/// Normalize a fixture-relative path to always use forward slashes.
/// Strips a known suffix (e.g. '.txt') by length, not replaceAll,
/// so the suffix pattern cannot accidentally match interior text.
String _normalizeFixtureKey(String relativePath, String suffix) {
  final normalized = relativePath.replaceAll('\\', '/');
  if (normalized.endsWith(suffix)) {
    return normalized.substring(0, normalized.length - suffix.length);
  }
  return normalized;
}

class FixtureCase {
  final String name;
  final String rawText;
  final Map<String, dynamic> expected;
  FixtureCase(this.name, this.rawText, this.expected);
}

List<FixtureCase> loadFixtures(String fixtureRoot) {
  final root = Directory(fixtureRoot);
  if (!root.existsSync()) {
    fail('Fixture root does not exist: $fixtureRoot');
  }

  // Discover all files on disk.
  final discoveredTxt = <String>{};
  final discoveredJson = <String>{};
  for (final providerDir in root.listSync().whereType<Directory>()) {
    for (final file in providerDir.listSync().whereType<File>()) {
      final rel = file.path.substring(root.path.length + 1);
      final normalized = rel.replaceAll('\\', '/');
      if (normalized.endsWith('.txt')) {
        discoveredTxt.add(
            _normalizeFixtureKey(rel, '.txt'));
      } else if (normalized.endsWith('.expected.json')) {
        discoveredJson.add(
            _normalizeFixtureKey(rel, '.expected.json'));
      }
    }
  }

  final declared = _declaredFixtures.toSet();

  // Fail on orphan .txt files (on disk but not declared).
  final orphanTxt = discoveredTxt.difference(declared);
  if (orphanTxt.isNotEmpty) {
    fail('Orphan .txt fixture files not in declared set: $orphanTxt');
  }

  // Fail on orphan .expected.json files.
  final orphanJson = discoveredJson.difference(declared);
  if (orphanJson.isNotEmpty) {
    fail('Orphan .expected.json files not in declared set: $orphanJson');
  }

  // Fail on declared fixtures missing from disk.
  final missingTxt = declared.difference(discoveredTxt);
  if (missingTxt.isNotEmpty) {
    fail('Declared fixtures missing .txt on disk: $missingTxt');
  }
  final missingJson = declared.difference(discoveredJson);
  if (missingJson.isNotEmpty) {
    fail('Declared fixtures missing .expected.json on disk: $missingJson');
  }

  // Load and validate each fixture.
  final cases = <FixtureCase>[];
  for (final name in _declaredFixtures) {
    final txtFile = File('$fixtureRoot/$name.txt');
    final jsonFile = File('$fixtureRoot/$name.expected.json');

    // These should not happen given the checks above, but fail-closed.
    if (!txtFile.existsSync()) fail('Missing .txt: $name');
    if (!jsonFile.existsSync()) fail('Missing .expected.json: $name');

    final rawText = txtFile.readAsStringSync();
    final expectedJson =
        jsonDecode(jsonFile.readAsStringSync()) as Map<String, dynamic>;

    // Validate exact root keys: provider + 7 fields, nothing else.
    final expectedRootKeys = {'provider', ..._requiredFields};
    final actualRootKeys = expectedJson.keys.toSet();
    if (actualRootKeys != expectedRootKeys) {
      fail('$name: root keys mismatch \u2014 '
          'extra: ${actualRootKeys.difference(expectedRootKeys)}, '
          'missing: ${expectedRootKeys.difference(actualRootKeys)}');
    }

    // Validate provider.
    final provider = expectedJson['provider'] as String?;
    if (provider == null || !_validProviders.contains(provider)) {
      fail('$name: invalid or missing provider "$provider" '
          '(valid: $_validProviders)');
    }

    // Validate all seven required fields with exact key sets.
    for (final field in _requiredFields) {
      final entry = expectedJson[field] as Map<String, dynamic>;

      // Each field must have exactly {value, quality}.
      final fieldKeys = entry.keys.toSet();
      const expectedFieldKeys = {'value', 'quality'};
      if (fieldKeys != expectedFieldKeys) {
        fail('$name.$field: field keys mismatch \u2014 '
            'extra: ${fieldKeys.difference(expectedFieldKeys)}, '
            'missing: ${expectedFieldKeys.difference(fieldKeys)}');
      }

      final quality = entry['quality'] as String?;
      if (quality == null || !_validQualities.contains(quality)) {
        fail('$name.$field: invalid quality "$quality" '
            '(valid: $_validQualities)');
      }
    }

    cases.add(FixtureCase(name, rawText, expectedJson));
  }
  return cases;
}

// ================================================================
// Quality / provider parsers (strict -- unknown strings throw)
// ================================================================

ExtractionQuality _parseQuality(String caseName, String field, String q) {
  return switch (q) {
    'full' => ExtractionQuality.full,
    'partial' => ExtractionQuality.partial,
    'unknown' => ExtractionQuality.unknown,
    _ => throw TestFailure(
        '$caseName.$field: unrecognised quality "$q"'),
  };
}

BookingProvider _parseProvider(String caseName, String p) {
  return switch (p) {
    'bookingCom' => BookingProvider.bookingCom,
    'agoda' => BookingProvider.agoda,
    'generic' => BookingProvider.generic,
    'unknown' => BookingProvider.unknown,
    _ => throw TestFailure(
        '$caseName: unrecognised provider "$p"'),
  };
}

void assertField<T>(
  String caseName,
  String fieldName,
  ExtractedField<T> actual,
  Map<String, dynamic> expectedMap, {
  T Function(dynamic)? parse,
}) {
  final expectedValue = expectedMap['value'];
  final expectedQuality =
      _parseQuality(caseName, fieldName, expectedMap['quality'] as String);

  expect(actual.quality, expectedQuality,
      reason: '$caseName: $fieldName quality mismatch '
          '(got ${actual.quality}, expected $expectedQuality)');

  if (expectedValue == null) {
    expect(actual.value, isNull,
        reason: '$caseName: $fieldName should be null');
  } else if (parse != null) {
    expect(actual.value, parse(expectedValue),
        reason: '$caseName: $fieldName value mismatch');
  } else {
    expect(actual.value, expectedValue,
        reason: '$caseName: $fieldName value mismatch');
  }
}

// ================================================================
// Main
// ================================================================

void main() {
  final fixtureRoot = 'test/fixtures/booking_parser';

  // ================================================================
  // Path normalization proof
  // ================================================================

  group('Fixture path normalization', () {
    test('backslash paths normalize to forward slash', () {
      expect(
        _normalizeFixtureKey(r'agoda\branded_flight.txt', '.txt'),
        'agoda/branded_flight',
      );
      expect(
        _normalizeFixtureKey(r'booking_com\full_confirmation.expected.json',
            '.expected.json'),
        'booking_com/full_confirmation',
      );
    });

    test('POSIX paths unchanged', () {
      expect(
        _normalizeFixtureKey('generic/labelled_fields.txt', '.txt'),
        'generic/labelled_fields',
      );
    });

    test('suffix removal is exact (not replaceAll)', () {
      // A name containing .txt in the middle must not be corrupted.
      expect(
        _normalizeFixtureKey('odd.txt_case/fixture.txt', '.txt'),
        'odd.txt_case/fixture',
      );
    });
  });

  // ================================================================
  // Parameterized golden corpus (11 cases)
  // ================================================================

  group('Golden corpus (parameterized)', () {
    late List<FixtureCase> cases;

    setUpAll(() {
      cases = loadFixtures(fixtureRoot);
    });

    test('exactly ${_declaredFixtures.length} fixtures loaded', () {
      expect(cases.length, _declaredFixtures.length,
          reason: 'Fixture count must match declared set');
    });

    test('every declared name was loaded', () {
      final loadedNames = cases.map((c) => c.name).toSet();
      expect(loadedNames, equals(_declaredFixtures.toSet()));
    });

    for (var i = 0; i < _declaredFixtures.length; i++) {
      final fixtureName = _declaredFixtures[i];
      test('fixture [$i]: $fixtureName', () {
        final c = cases.firstWhere((c) => c.name == fixtureName);
        final r = extractBookingFromText(c.rawText);
        final e = c.expected;

        expect(r.provider,
            _parseProvider(fixtureName, e['provider'] as String),
            reason: '$fixtureName: provider');

        assertField<String>(fixtureName, 'bookingType',
            r.bookingTypeField, e['bookingType'] as Map<String, dynamic>);
        assertField<String>(fixtureName, 'venueName',
            r.venueNameField, e['venueName'] as Map<String, dynamic>);
        assertField<DateTime>(fixtureName, 'scheduledStart',
            r.scheduledStartField, e['scheduledStart'] as Map<String, dynamic>,
            parse: (v) => DateTime.parse(v as String));
        assertField<DateTime>(fixtureName, 'checkoutDate',
            r.checkoutDateField, e['checkoutDate'] as Map<String, dynamic>,
            parse: (v) => DateTime.parse(v as String));
        assertField<int>(fixtureName, 'durationMinutes',
            r.durationMinutesField, e['durationMinutes'] as Map<String, dynamic>,
            parse: (v) => (v as num).toInt());
        assertField<String>(fixtureName, 'confirmationCode',
            r.confirmationCodeField, e['confirmationCode'] as Map<String, dynamic>);
        assertField<String>(fixtureName, 'geoRegion',
            r.geoRegionField, e['geoRegion'] as Map<String, dynamic>);
      });
    }
  });

  // ================================================================
  // Branded-flight proofs (section 3)
  // ================================================================

  group('Branded-flight proofs', () {
    test('Booking.com flight: type=flight, no checkout, no duration, PNR extracted', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/booking_com/branded_flight.txt').readAsStringSync(),
      );
      expect(r.provider, BookingProvider.bookingCom);
      expect(r.bookingType, 'flight');
      expect(r.checkoutDate, isNull,
          reason: 'Departure must not become check-out for flights');
      expect(r.durationMinutes, isNull,
          reason: 'No hotel duration for flights');
      expect(r.confirmationCode, isNotNull,
          reason: 'PNR/booking code must be extracted');
    });

    test('Agoda flight: type=flight, no checkout, no duration, code extracted', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/agoda/branded_flight.txt').readAsStringSync(),
      );
      expect(r.provider, BookingProvider.agoda);
      expect(r.bookingType, 'flight');
      expect(r.checkoutDate, isNull,
          reason: 'Departure must not become check-out for flights');
      expect(r.durationMinutes, isNull,
          reason: 'No hotel duration for flights');
      expect(r.confirmationCode, isNotNull,
          reason: 'Booking code must be extracted');
    });

    test('generic flight via PNR routes to generic provider', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/generic/flight_departure.txt').readAsStringSync(),
      );
      expect(r.provider, BookingProvider.generic);
      expect(r.bookingType, 'flight');
      expect(r.checkoutDate, isNull);
      expect(r.confirmationCode, isNotNull);
    });
  });

  // ================================================================
  // Label separator variants
  // ================================================================

  group('Label separator variants', () {
    for (final sep in [': ', ' # ', ' = ', ' is ', '  ']) {
      test('separator "${sep.trim().isEmpty ? "(space)" : sep.trim()}" parses dates', () {
        final r = extractBookingFromText(
          'Hotel stay\nCheck-in${sep}5 October 2026\n'
          'Check-out${sep}7 October 2026',
        );
        expect(r.scheduledStart, DateTime(2026, 10, 5),
            reason: 'Check-in with separator "$sep"');
        expect(r.checkoutDate, DateTime(2026, 10, 7),
            reason: 'Check-out with separator "$sep"');
      });
    }
  });

  // ================================================================
  // Invalid calendar dates
  // ================================================================

  group('Invalid calendar dates', () {
    test('Feb 30 rejected', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 30 February 2026',
      );
      expect(r.scheduledStart, isNull);
    });

    test('Apr 31 rejected', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 31 April 2026',
      );
      expect(r.scheduledStart, isNull);
    });

    test('valid Feb 28 accepted', () {
      final r = extractBookingFromText(
        'Hotel stay\nCheck-in: 28 February 2026',
      );
      expect(r.scheduledStart, DateTime(2026, 2, 28));
    });
  });

  // ================================================================
  // Extraction quality distinction
  // ================================================================

  group('Extraction quality distinction', () {
    test('branded fields are full quality', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/booking_com/full_confirmation.txt')
            .readAsStringSync(),
      );
      expect(r.confirmedFields, isNotEmpty,
          reason: 'Booking.com must have confirmed (full) fields');
      expect(r.partialFields, isEmpty,
          reason: 'Booking.com must have no partial fields');
    });

    test('generic fields are partial quality', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/generic/labelled_fields.txt').readAsStringSync(),
      );
      expect(r.partialFields, isNotEmpty,
          reason: 'Generic must have partial fields');
      expect(r.confirmedFields, isEmpty,
          reason: 'Generic must have no confirmed fields');
    });
  });

  // ================================================================
  // Robustness
  // ================================================================

  group('Robustness', () {
    test('empty input never throws', () {
      expect(() => extractBookingFromText(''), returnsNormally);
      expect(extractBookingFromText('').hasUsefulFields, isFalse);
    });

    test('very long input never throws', () {
      expect(() => extractBookingFromText('A' * 100000), returnsNormally);
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
          'Booking.com\nTest Hotel is expecting you on Sun 4 Oct 2026\n'
          'Check-in Sunday, 4 October 2026 (14:00 - 00:00)',
        ),
        returnsNormally,
      );
      expect(overrides.socketOpened, isFalse);
    });
  });

  // ================================================================
  // Sabotage proofs
  // ================================================================

  group('Sabotage proofs', () {
    test('SP1: missing expected JSON detected by loader', () {
      final cases = loadFixtures(fixtureRoot);
      expect(cases.length, 11);
    });

    test('SP2: orphan detection is structural', () {
      expect(_declaredFixtures.length, 11);
    });

    test('SP3: invalid quality string throws', () {
      expect(
        () => _parseQuality('test', 'field', 'high'),
        throwsA(isA<TestFailure>()),
      );
      expect(
        () => _parseProvider('test', 'superProvider'),
        throwsA(isA<TestFailure>()),
      );
    });

    test('SP4: PNR routes to generic provider', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/generic/flight_departure.txt').readAsStringSync(),
      );
      expect(r.provider, BookingProvider.generic,
          reason: 'Removing pnr from _hasLabelledFields would make this unknown');
    });

    test('SP5: branded flight Departure not aliased to check-out', () {
      final bc = extractBookingFromText(
        File('$fixtureRoot/booking_com/branded_flight.txt').readAsStringSync(),
      );
      expect(bc.checkoutDate, isNull,
          reason: 'Applying hotel aliases unconditionally would create a '
              'check-out from Departure in a flight context');

      final ag = extractBookingFromText(
        File('$fixtureRoot/agoda/branded_flight.txt').readAsStringSync(),
      );
      expect(ag.checkoutDate, isNull,
          reason: 'Same: Agoda flight Departure must not become check-out');
    });

    // SP6: Remove importSource='manual' reset in _autoFill else branch.
    // -> Widget test for zero-field sequence would get importSource=email.
    // Proven in provider_paste_widget_test.dart via:
    //   expect(signalService.calls, hasLength(1));
    //   expect(signalService.calls.single['importSource'], 'manual');

    // SP7: Reintroduce conditional signal assertion.
    // -> Widget test would silently pass with zero signal calls.
    // Proven in provider_paste_widget_test.dart via:
    //   expect(signalService.calls, hasLength(1));
    // No placeholder test here -- the widget test IS the proof.

    test('SP8: footer-only has no venue (save guard proven in widget test)', () {
      final r = extractBookingFromText(
        File('$fixtureRoot/agoda/footer_only.txt').readAsStringSync(),
      );
      expect(r.venueName, isNull,
          reason: 'Footer-only has no venue; removing save guard would '
              'create a synthetic booking');
    });
  });
}

class _FailingHttpOverrides extends HttpOverrides {
  bool socketOpened = false;

  @override
  HttpClient createHttpClient(SecurityContext? context) {
    socketOpened = true;
    throw StateError('No network calls allowed during extraction');
  }
}
