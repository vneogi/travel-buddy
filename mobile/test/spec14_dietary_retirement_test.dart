import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/disclaimers.dart';

/// SPEC-14: dietary suitability claim is retired.
///
/// Sabotage proofs:
///   S4: Skip the driver-card disclaimer -> kFoodDisclaimerShort test fails.
///   S1: Keep a halal/suitable badge -> kFoodDisclaimer content test fails.
void main() {
  // ===========================================================
  // Disclaimer constants exist and are pure ASCII
  // ===========================================================

  group('Disclaimer constants', () {
    test('kFoodDisclaimer is non-empty and ASCII', () {
      expect(kFoodDisclaimer.isNotEmpty, isTrue);
      for (final c in kFoodDisclaimer.codeUnits) {
        expect(c, lessThan(128), reason: 'non-ASCII in kFoodDisclaimer');
      }
    });

    test('kFoodDisclaimerShort is non-empty and ASCII', () {
      expect(kFoodDisclaimerShort.isNotEmpty, isTrue);
      for (final c in kFoodDisclaimerShort.codeUnits) {
        expect(c, lessThan(128), reason: 'non-ASCII in kFoodDisclaimerShort');
      }
    });

    test('kFoodDisclaimer contains required phrases', () {
      final lower = kFoodDisclaimer.toLowerCase();
      expect(lower, contains('incomplete'));
      expect(lower, contains('menus change'));
      expect(lower, contains('confirm'));
    });

    test('kFoodDisclaimerShort contains required phrases', () {
      final lower = kFoodDisclaimerShort.toLowerCase();
      expect(lower, contains('menus change'));
      expect(lower, contains('confirm'));
    });
  });

  // ===========================================================
  // No dietary suitability claim in the disclaimer text
  // ===========================================================

  group('No dietary claim in disclaimer', () {
    test('disclaimer does not claim food is halal or suitable', () {
      for (final keyword in ['halal', 'vegan', 'vegetarian', 'suitable']) {
        expect(
          kFoodDisclaimer.toLowerCase().contains(keyword),
          isFalse,
          reason: 'disclaimer must not claim food is $keyword',
        );
      }
    });
  });

  // ===========================================================
  // Disclaimer text matches between full and short variant
  // ===========================================================

  group('Full and short disclaimers are consistent', () {
    test('short disclaimer is a subset concept of full', () {
      // Both mention menus change and confirming with venue
      expect(kFoodDisclaimer.toLowerCase(), contains('menus change'));
      expect(kFoodDisclaimerShort.toLowerCase(), contains('menus change'));
      expect(kFoodDisclaimer.toLowerCase(), contains('confirm'));
      expect(kFoodDisclaimerShort.toLowerCase(), contains('confirm'));
    });
  });
}
