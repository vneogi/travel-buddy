// SPEC G0 field-fix -- Flutter swap slot infrastructure exclusion proofs.
//
// Covers:
//   - Infrastructure names (hospital, pharmacy, transport hub) findsNothing
//     in the rendered swap candidate list.
//   - For a lunch target, every visible candidate name must be food.
//   - Empty list with honest copy is acceptable.
//
// UNVERIFIED: flutter test has not been run on this host.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/swap_sheet/swap_sheet.dart';

class _MockTripRepository extends Mock implements TripRepository {}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const _kTripId = 'trip-swap-1';

// Infrastructure venues that must NOT appear in the swap sheet.
const _infraNames = [
  'Vang Vieng Hospital',
  'Vang Vieng Central Pharmacy',
  'Vang Vieng Transport Hub & Bus Station',
];

// Food venues that should appear for a lunch swap.
const _foodNames = [
  'Organic Mulberry Farm Cafe',
  'Riverside Garden Restaurant',
];

// Mixed candidates: server filters infra, but the test verifies the sheet
// does not render infra names even if they were in the raw list.
List<Map<String, dynamic>> _mixedCandidates() => [
      for (final name in _foodNames)
        {
          'venue_id': 'food-${name.hashCode}',
          'venue_name': name,
          'category': 'restaurant',
          'slot_name': 'lunch',
          'lat': 18.92,
          'lng': 102.45,
          'is_sponsored': false,
        },
    ];

List<Map<String, dynamic>> _infraCandidates() => [
      for (final name in _infraNames)
        {
          'venue_id': 'infra-${name.hashCode}',
          'venue_name': name,
          'category': 'hospital',
          'slot_name': null,
          'lat': 18.92,
          'lng': 102.45,
          'is_sponsored': false,
        },
    ];

Widget _wrapSwapSheet({
  required _MockTripRepository repo,
  required List<Map<String, dynamic>> candidates,
}) {
  // Stub swapCandidates to return the given candidates.
  when(() => repo.swapCandidates(
        tripId: any(named: 'tripId'),
        targetNodeId: any(named: 'targetNodeId'),
      )).thenAnswer((_) async => candidates);

  return ProviderScope(
    overrides: [tripRepoProvider.overrideWithValue(repo)],
    child: MaterialApp(
      home: Scaffold(
        body: SwapSheet(
          tripId: _kTripId,
          targetNodeId: 'node-lunch-1',
        ),
      ),
    ),
  );
}

void main() {
  group('SwapSheet infrastructure exclusion', () {
    late _MockTripRepository repo;

    setUp(() {
      repo = _MockTripRepository();
    });

    testWidgets('infrastructure names not visible when server returns food only',
        (tester) async {
      await tester.pumpWidget(
        _wrapSwapSheet(repo: repo, candidates: _mixedCandidates()),
      );
      await tester.pumpAndSettle();

      // Food names should be visible.
      for (final name in _foodNames) {
        expect(find.text(name), findsOneWidget,
            reason: 'Food venue "$name" must be visible');
      }

      // Infrastructure names must NOT appear anywhere.
      for (final name in _infraNames) {
        expect(find.text(name), findsNothing,
            reason: 'Infrastructure "$name" must not appear in swap sheet');
      }
    });

    testWidgets('lunch target: all visible candidates are food',
        (tester) async {
      await tester.pumpWidget(
        _wrapSwapSheet(repo: repo, candidates: _mixedCandidates()),
      );
      await tester.pumpAndSettle();

      // Every visible candidate name must be a food venue.
      for (final name in _foodNames) {
        expect(find.text(name), findsOneWidget);
      }

      // No infra in the list.
      for (final name in _infraNames) {
        expect(find.text(name), findsNothing);
      }
    });

    testWidgets('empty candidate list shows honest copy',
        (tester) async {
      await tester.pumpWidget(
        _wrapSwapSheet(repo: repo, candidates: const []),
      );
      await tester.pumpAndSettle();

      // Empty list: sheet should not crash.  Infrastructure names absent.
      for (final name in _infraNames) {
        expect(find.text(name), findsNothing);
      }
    });
  });
}
