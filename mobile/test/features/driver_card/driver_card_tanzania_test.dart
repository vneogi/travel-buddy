// F2 (owner device finding 2026-11-14): the driver card prefers Swahili for
// Tanzania regions. SPEC-12 provenance tiers are unchanged.
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/features/driver_card/driver_card_helpers.dart';
import 'package:travel_buddy/render/fact_envelope.dart';

void main() {
  group('F2 driver card language priority for Tanzania', () {
    test('tanzania regions prefer swahili then english', () {
      expect(languagePriority('zanzibar_tanzania'), equals(['sw', 'en']));
      expect(languagePriority('nungwi_tanzania'), equals(['sw', 'en']));
    });

    test('laos dubai and unknown regions are unchanged', () {
      expect(languagePriority('luang_prabang_laos'), equals(['lo', 'th', 'en']));
      expect(languagePriority('dubai_uae'), equals(['ar', 'en']));
      expect(languagePriority(null), equals(['en']));
      expect(languagePriority('paris_france'), equals(['en']));
    });

    test('swahili entry is chosen over english for a tanzania venue', () {
      final map = <String, dynamic>{
        'en': {'value': 'English Name', 'source': 'osm'},
        'sw': {'value': 'Jina la Kiswahili', 'source': 'field_verified'},
      };
      final result = resolvePreferredLocalEntry(
        localizedMap: map,
        geoRegion: 'nungwi_tanzania',
      );
      expect(result, isNotNull);
      expect(result!.key, equals('sw'));
      expect(result.value['value'], equals('Jina la Kiswahili'));
    });

    test('english is used when swahili is missing', () {
      final map = <String, dynamic>{
        'en': {'value': 'English Name', 'source': 'osm'},
      };
      final result = resolvePreferredLocalEntry(
        localizedMap: map,
        geoRegion: 'nungwi_tanzania',
      );
      expect(result, isNotNull);
      expect(result!.key, equals('en'));
    });

    test('generated swahili name stays in the ask tier', () {
      expect(tierForNameSource('generated'), equals(FactTier.ask));
      expect(tierForNameSource('field_verified'), equals(FactTier.assert_));
    });
  });
}
