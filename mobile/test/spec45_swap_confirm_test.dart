// SPEC-45 R1: Swap sheet select-then-confirm sabotage proof.
//
// UNVERIFIED: flutter test has not been run on this host.
//
// Pumps a SwapSheet with pre-loaded venues, taps one row,
// asserts the sheet stays open and no result was returned, then taps
// Confirm swap and asserts the selected VenueSearchResult is returned.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/swap_sheet/swap_sheet.dart';

/// Minimal fake that only implements swapCandidates.
class _FakeTripRepo implements TripRepository {
  final List<VenueSearchResult> swapResults;
  _FakeTripRepo({required this.swapResults});

  @override
  Future<List<VenueSearchResult>> swapCandidates({
    required String tripId,
    required String targetNodeId,
  }) async =>
      swapResults;

  @override
  noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  group('R1: SwapSheet select-then-confirm', () {
    final venues = [
      const VenueSearchResult(
        venueId: 'v1',
        name: 'Cafe Sinouk',
        description: 'Good coffee',
        microLocation: 'nam_phou_fountain',
        vibeTags: ['cafe'],
      ),
      const VenueSearchResult(
        venueId: 'v2',
        name: 'Makphet',
        description: 'Training restaurant',
        microLocation: 'patuxai_district',
        vibeTags: ['fine_dining'],
      ),
    ];

    testWidgets('tap selects row, sheet stays open, Confirm pops result',
        (tester) async {
      VenueSearchResult? returnedVenue;

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            tripRepoProvider
                .overrideWithValue(_FakeTripRepo(swapResults: venues)),
          ],
          child: MaterialApp(
            home: Scaffold(
              body: Builder(
                builder: (context) => ElevatedButton(
                  child: const Text('Open'),
                  onPressed: () async {
                    final result =
                        await showModalBottomSheet<VenueSearchResult>(
                      context: context,
                      isScrollControlled: true,
                      builder: (_) => SwapSheet(
                        tripId: 'trip-1',
                        targetNodeId: 'node-1',
                        tripState: const TripState(
                          tripId: 'trip-1',
                          userId: 'u1',
                          nodes: [],
                        ),
                      ),
                    );
                    returnedVenue = result;
                  },
                ),
              ),
            ),
          ),
        ),
      );

      // Open the sheet.
      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      // Sheet is visible with both venues.
      expect(find.text('Cafe Sinouk'), findsOneWidget);
      expect(find.text('Makphet'), findsOneWidget);

      // Confirm swap button is disabled (no selection).
      final confirmButton = find.text('Confirm swap');
      expect(confirmButton, findsOneWidget);
      final filledButton = find.ancestor(
        of: confirmButton,
        matching: find.byType(FilledButton),
      );
      expect(
        tester.widget<FilledButton>(filledButton).onPressed,
        isNull,
        reason: 'Confirm swap should be disabled before selection',
      );

      // Tap a venue row.
      await tester.tap(find.text('Cafe Sinouk'));
      await tester.pumpAndSettle();

      // Sheet is still open -- no result returned.
      expect(returnedVenue, isNull,
          reason: 'Tapping a row must not close the sheet');
      expect(find.text('Swap to...'), findsOneWidget,
          reason: 'Sheet header must still be visible');

      // Selected marker: check_circle icon present.
      expect(find.byIcon(Icons.check_circle), findsOneWidget);

      // Confirm swap is now enabled.
      expect(
        tester.widget<FilledButton>(filledButton).onPressed,
        isNotNull,
        reason: 'Confirm swap should be enabled after selection',
      );

      // Tap Confirm swap.
      await tester.tap(confirmButton);
      await tester.pumpAndSettle();

      // Result returned with the correct venue.
      expect(returnedVenue, isNotNull);
      expect(returnedVenue!.venueId, 'v1');
      expect(returnedVenue!.name, 'Cafe Sinouk');
    });
  });
}
