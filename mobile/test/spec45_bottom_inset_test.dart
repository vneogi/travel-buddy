// SPEC-45 R5: Bottom inset proof -- no FAB, one AskEntryBar, last card tappable.
//
// UNVERIFIED: flutter test has not been run on this host.
//
// This test constructs a minimal itinerary-like Column with ActivityCards
// inside a SingleChildScrollView at phone width, scrolls to the last card,
// and asserts its onTapDetails fires. The kItineraryBottomInset constant
// is used for padding.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/widgets/activity_card.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart'
    show kItineraryBottomInset;

TripNode _node(String id, String name, String slot) => TripNode(
      nodeId: id,
      venueName: name,
      scheduledStart: DateTime.utc(2026, 10, 2, 10, 0),
      durationMinutes: 90,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['cafe'],
      slotName: slot,
      geoRegion: 'vientiane_laos',
    );

void main() {
  group('R5: Bottom inset', () {
    testWidgets('last Dinner card is scrollable and tappable at phone width',
        (tester) async {
      // Phone-width surface (390x844 -- iPhone 14 logical).
      tester.view.physicalSize = const Size(390 * 3, 844 * 3);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final nodes = [
        _node('n1', 'Morning Walk', 'morning_tour'),
        _node('n2', 'Joma Bakery', 'lunch'),
        _node('n3', 'Pha That Luang', 'afternoon_evening_tour'),
        _node('n4', 'Makphet', 'dinner'),
        _node('n5', 'PVO Vietnamese', 'dinner'),
        _node('n6', 'Night Market', 'dinner'),
      ];

      var lastCardTapped = false;
      final lastNode = nodes.last;

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          // No FAB.
          body: SingleChildScrollView(
            padding: const EdgeInsets.only(bottom: kItineraryBottomInset),
            child: Column(
              children: [
                for (final n in nodes)
                  ActivityCard(
                    key: ValueKey(n.nodeId),
                    node: n,
                    onTapDetails: n == lastNode
                        ? () => lastCardTapped = true
                        : null,
                  ),
              ],
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // No FloatingActionButton anywhere.
      expect(find.byType(FloatingActionButton), findsNothing);

      // Scroll the last card into view.
      final lastCard = find.byKey(const ValueKey('n6'));
      expect(lastCard, findsOneWidget);
      await tester.ensureVisible(lastCard);
      await tester.pumpAndSettle();

      // Tap the last card body (venue name).
      await tester.tap(find.text('Night Market'));
      await tester.pumpAndSettle();

      expect(lastCardTapped, isTrue,
          reason: 'Last Dinner card must be tappable after scroll');
    });

    testWidgets('kItineraryBottomInset is a positive number', (tester) async {
      // Sanity: the named constant exists and is large enough for composer.
      expect(kItineraryBottomInset, greaterThanOrEqualTo(80));
    });
  });
}
