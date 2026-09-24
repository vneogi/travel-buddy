// SPEC G0 field-fix -- Flutter swap slot proofs.
//
// D4: Mixed stub (food + hospital).  Hospital IS visible -- documents
//     that the sheet trusts swapCandidates.  Infrastructure exclusion
//     is proven by Python P5 (server-side filter).
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

// Food venue.
const _food = VenueSearchResult(
  venueId: 'food-1',
  name: 'Organic Mulberry Farm Cafe',
  description: 'Farm-to-table organic cafe',
  microLocation: 'riverside',
  vibeTags: ['authentic'],
  isSponsored: false,
);

// Infrastructure venue -- the sheet renders whatever the server sends.
const _hospital = VenueSearchResult(
  venueId: 'infra-1',
  name: 'Vang Vieng Hospital',
  description: 'Hospital',
  microLocation: 'centre',
  vibeTags: [],
  isSponsored: false,
);

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
  group('SwapSheet trust contract', () {
    late _MockTripRepository repo;

    setUp(() {
      repo = _MockTripRepository();
    });

    testWidgets('mixed list: food AND hospital both visible (sheet trusts server)',
        (tester) async {
      when(() => repo.swapCandidates(
            tripId: any(named: 'tripId'),
            targetNodeId: any(named: 'targetNodeId'),
          )).thenAnswer((_) async => [_food, _hospital]);

      await tester.pumpWidget(
        _wrapSwapSheet(repo: repo, tripState: _minimalTrip()),
      );
      await tester.pumpAndSettle();

      // Both names rendered -- sheet does not client-side filter.
      expect(find.text('Organic Mulberry Farm Cafe'), findsOneWidget);
      expect(find.text('Vang Vieng Hospital'), findsOneWidget);
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

      expect(
        find.text('No alternative venues found nearby.'),
        findsOneWidget,
      );
    });
  });
}
