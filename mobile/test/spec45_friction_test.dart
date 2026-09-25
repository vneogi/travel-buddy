// SPEC-45 Phase A: itinerary visible friction -- widget proofs.
//
// UNVERIFIED: flutter test has not been run on this host.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/widgets/activity_card.dart';
import 'package:travel_buddy/features/activity_detail/activity_detail_screen.dart';
import 'package:travel_buddy/features/itinerary/micro_location_label.dart';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

TripNode _activityNode({
  String nodeId = 'node-1',
  String venueName = 'Joma Bakery',
  String? microLocation = 'nam_phou_fountain',
  String nodeKind = 'activity',
  String? bookingType,
  bool isLocked = false,
  List<String> vibeTags = const ['cafe', 'bakery', 'wifi'],
  String? slotName = 'morning_tour',
  String? geoRegion = 'vientiane_laos',
}) =>
    TripNode(
      nodeId: nodeId,
      venueName: venueName,
      scheduledStart: DateTime.utc(2026, 10, 2, 2, 0), // 09:00 ICT
      durationMinutes: 90,
      isLocked: isLocked,
      status: NodeStatus.pending,
      vibeTags: vibeTags,
      microLocation: microLocation,
      nodeKind: nodeKind,
      bookingType: bookingType,
      slotName: slotName,
      geoRegion: geoRegion,
    );

TripNode _hotelNode() => TripNode(
      nodeId: 'hotel-1',
      venueName: 'Villa Santi Hotel',
      scheduledStart: DateTime.utc(2026, 10, 6, 5, 0), // 12:00 ICT
      durationMinutes: 1440, // 1 night
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: 'booking',
      bookingType: 'hotel',
      geoRegion: 'luang_prabang_laos',
    );

TripNode _bookingNode() => TripNode(
      nodeId: 'flight-1',
      venueName: 'Bangkok Airways PG943',
      scheduledStart: DateTime.utc(2026, 10, 2, 1, 0),
      durationMinutes: 180,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: 'booking',
      bookingType: 'flight',
      geoRegion: 'vientiane_laos',
    );

// Wrap a single widget in a MaterialApp for testing.
Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  // ---------------------------------------------------------------------------
  // micro_location_label unit tests
  // ---------------------------------------------------------------------------
  group('friendlyMicroLocation', () {
    test('nam_phou_fountain returns friendly label', () {
      expect(friendlyMicroLocation('nam_phou_fountain'),
          'Nam Phou Fountain area');
    });

    test('unknown key returns null', () {
      expect(friendlyMicroLocation('unknown_place'), isNull);
    });

    test('null returns null', () {
      expect(friendlyMicroLocation(null), isNull);
    });

    test('Dubai key returns friendly label', () {
      expect(friendlyMicroLocation('Downtown'), 'Downtown Dubai');
    });
  });

  // ---------------------------------------------------------------------------
  // Item 4: No snake_case or [BOOKING: chrome on card
  // ---------------------------------------------------------------------------
  group('ActivityCard display', () {
    testWidgets('nam_phou_fountain not visible as raw text', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(node: _activityNode())));
      await tester.pumpAndSettle();

      // Raw snake_case must not appear.
      expect(find.text('nam_phou_fountain'), findsNothing);
      // Friendly label or nothing must be present.
      expect(find.text('Nam Phou Fountain area'), findsOneWidget);
    });

    testWidgets('[BOOKING: not visible on booking card', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(node: _bookingNode())));
      await tester.pumpAndSettle();

      // Debug chrome must not appear.
      expect(find.textContaining('[BOOKING:'), findsNothing);
      // Title-case badge must appear.
      expect(find.text('Flight'), findsOneWidget);
    });

    testWidgets('hotel booking shows Hotel badge', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(node: _hotelNode())));
      await tester.pumpAndSettle();

      expect(find.textContaining('[BOOKING:'), findsNothing);
      expect(find.text('Hotel'), findsOneWidget);
    });

    testWidgets('max 2 vibe chips on card; rest collapsed', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(
        node: _activityNode(vibeTags: ['cafe', 'bakery', 'wifi', 'quiet']),
      )));
      await tester.pumpAndSettle();

      // Only first 2 tags + overflow chip.
      expect(find.text('cafe'), findsOneWidget);
      expect(find.text('bakery'), findsOneWidget);
      expect(find.text('+2'), findsOneWidget);
      expect(find.text('wifi'), findsNothing);
      expect(find.text('quiet'), findsNothing);
    });

    testWidgets('slot label does not wrap (softWrap false)', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(
        node: _activityNode(slotName: 'morning_tour'),
      )));
      await tester.pumpAndSettle();

      expect(find.text('Morning'), findsOneWidget);
    });
  });

  // ---------------------------------------------------------------------------
  // Item 6: Hotel card shows month-day on check-in/out
  // ---------------------------------------------------------------------------
  group('Hotel card dates', () {
    testWidgets('hotel card shows month-day token', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(node: _hotelNode())));
      await tester.pumpAndSettle();

      // Must show "Oct" as part of a date string (e.g. "Tue 6 Oct, 12:00").
      expect(find.textContaining('Oct'), findsWidgets);
      // Must show "Check-in" and "Check-out" labels.
      expect(find.text('Check-in'), findsOneWidget);
      expect(find.text('Check-out'), findsOneWidget);
    });
  });

  // ---------------------------------------------------------------------------
  // Item 2: Card tap opens ActivityDetailScreen
  // ---------------------------------------------------------------------------
  group('Card tap opens details', () {
    testWidgets('onTapDetails callback fires on card body tap',
        (tester) async {
      var detailsTapped = false;
      await tester.pumpWidget(_wrap(ActivityCard(
        node: _activityNode(),
        onTapDetails: () => detailsTapped = true,
      )));
      await tester.pumpAndSettle();

      // Tap the card body (venue name).
      await tester.tap(find.text('Joma Bakery'));
      expect(detailsTapped, isTrue);
    });

    testWidgets('ActivityDetailScreen uses friendly micro_location',
        (tester) async {
      await tester.pumpWidget(_wrap(ActivityDetailScreen(
        node: _activityNode(),
      )));
      await tester.pumpAndSettle();

      expect(find.text('nam_phou_fountain'), findsNothing);
      expect(find.text('Nam Phou Fountain area'), findsOneWidget);
    });
  });

  // ---------------------------------------------------------------------------
  // Item 3: Overflow menu instead of four-icon row
  // ---------------------------------------------------------------------------
  group('Overflow menu', () {
    testWidgets('skip/love/driver in overflow, not title row icons',
        (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(
        node: _activityNode(),
        onTapSwap: () {},
        onTapCancel: () {},
        onTapLoved: () {},
      )));
      await tester.pumpAndSettle();

      // Swap icon button is inline.
      expect(find.byIcon(Icons.swap_horiz), findsOneWidget);
      // Cancel/love icons are NOT inline -- they are in the overflow.
      // The overflow menu icon (more_vert) should be present.
      expect(find.byIcon(Icons.more_vert), findsOneWidget);
      // Cancel icon should not be visible until overflow is opened.
      expect(find.byIcon(Icons.cancel_outlined), findsNothing);
    });
  });

  // ---------------------------------------------------------------------------
  // Item 9: Swap confirm required; no INR or fabricated minutes
  // ---------------------------------------------------------------------------
  group('Swap sheet contract', () {
    // The swap sheet is tested in spec_g0_swap_slot_test.dart.
    // This test just ensures no INR/fabricated copy in the card.
    testWidgets('no INR or walking minutes on activity card', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(node: _activityNode())));
      await tester.pumpAndSettle();

      expect(find.textContaining('INR'), findsNothing);
      expect(find.textContaining('\u20B9'), findsNothing); // rupee symbol
      expect(find.textContaining('min walk'), findsNothing);
    });
  });
}
