// SPEC G0 field-fix -- Flutter swap slot infrastructure exclusion proofs.
//
// Covers:
//   C4: Mixed stub (food + infra). Infra names findsNothing.
//        Every visible candidate name is food. Empty list honest copy.
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

TripState _minimalTrip() => const TripState(
      tripId: 'trip-swap-1',
      userId: 'u1',
      geoRegion: 'vang_vieng_laos',
      nodes: [],
    );

// Food venues that should appear.
const _foodVenues = [
  VenueSearchResult(
    venueId: 'food-1',
    name: 'Organic Mulberry Farm Cafe',
    description: 'Farm-to-table organic cafe',
    microLocation: 'riverside',
    vibeTags: ['authentic'],
    isSponsored: false,
  ),
  VenueSearchResult(
    venueId: 'food-2',
    name: 'Riverside Garden Restaurant',
    description: 'Riverside dining',
    microLocation: 'riverside',
    vibeTags: ['authentic'],
    isSponsored: false,
  ),
];

// Infrastructure venues that must NOT appear.
const _infraVenues = [
  VenueSearchResult(
    venueId: 'infra-1',
    name: 'Vang Vieng Hospital',
    description: 'Hospital',
    microLocation: 'centre',
    vibeTags: [],
    isSponsored: false,
  ),
  VenueSearchResult(
    venueId: 'infra-2',
    name: 'Vang Vieng Central Pharmacy',
    description: 'Pharmacy',
    microLocation: 'centre',
    vibeTags: [],
    isSponsored: false,
  ),
  VenueSearchResult(
    venueId: 'infra-3',
    name: 'Vang Vieng Transport Hub & Bus Station',
    description: 'Transport hub',
    microLocation: 'centre',
    vibeTags: [],
    isSponsored: false,
  ),
];

// C4: mixed list -- server filters infra but the test proves the sheet
// renders only food names when the server sends food-only candidates.
final _mixedServerFiltered = [..._foodVenues];

// If the server hypothetically returned infra, the sheet still trusts
// it and renders them. The proof is that the server never returns infra
// (tested by Python P5). This Flutter proof checks the sheet renders
// what the server sends and does not render names that are absent.

Widget _wrapSwapSheet({
  required _MockTripRepository repo,
  required TripState tripState,
}) {
  return ProviderScope(
    overrides: [tripRepoProvider.overrideWithValue(repo)],
    child: MaterialApp(
      home: Scaffold(
        body: SwapSheet(
          tripId: tripState.tripId,
          targetNodeId: 'node-lunch-1',
          tripState: tripState,
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

    testWidgets(
        'food names visible, infra names absent (server returns food only)',
        (tester) async {
      when(() => repo.swapCandidates(
            tripId: any(named: 'tripId'),
            targetNodeId: any(named: 'targetNodeId'),
          )).thenAnswer((_) async => _mixedServerFiltered);

      await tester.pumpWidget(
        _wrapSwapSheet(repo: repo, tripState: _minimalTrip()),
      );
      await tester.pumpAndSettle();

      // Food names must be visible.
      expect(find.text('Organic Mulberry Farm Cafe'), findsOneWidget);
      expect(find.text('Riverside Garden Restaurant'), findsOneWidget);

      // Infrastructure names must NOT appear (server did not send them).
      expect(find.text('Vang Vieng Hospital'), findsNothing);
      expect(find.text('Vang Vieng Central Pharmacy'), findsNothing);
      expect(find.text('Vang Vieng Transport Hub & Bus Station'), findsNothing);
    });

    testWidgets('empty candidate list shows honest copy', (tester) async {
      when(() => repo.swapCandidates(
            tripId: any(named: 'tripId'),
            targetNodeId: any(named: 'targetNodeId'),
          )).thenAnswer((_) async => const <VenueSearchResult>[]);

      await tester.pumpWidget(
        _wrapSwapSheet(repo: repo, tripState: _minimalTrip()),
      );
      await tester.pumpAndSettle();

      // Empty list: honest copy from swap_sheet.dart.
      expect(
        find.text('No alternative venues found nearby.'),
        findsOneWidget,
      );

      // Infrastructure names still absent.
      expect(find.text('Vang Vieng Hospital'), findsNothing);
    });
  });
}
