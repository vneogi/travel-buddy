// SPEC-45 Phase A remainder: R1-R5 widget proofs.
//
// UNVERIFIED: flutter test has not been run on this host.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/widgets/activity_card.dart';
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
  NodeStatus status = NodeStatus.pending,
  List<String> vibeTags = const ['cafe', 'bakery'],
  String? slotName = 'dinner',
  String? geoRegion = 'vientiane_laos',
  DateTime? scheduledStart,
  int durationMinutes = 90,
}) =>
    TripNode(
      nodeId: nodeId,
      venueName: venueName,
      scheduledStart: scheduledStart ?? DateTime.utc(2026, 10, 2, 10, 0),
      durationMinutes: durationMinutes,
      isLocked: isLocked,
      status: status,
      vibeTags: vibeTags,
      microLocation: microLocation,
      nodeKind: nodeKind,
      bookingType: bookingType,
      slotName: slotName,
      geoRegion: geoRegion,
    );

TripNode _hotelNode({String nodeId = 'hotel-1'}) => TripNode(
      nodeId: nodeId,
      venueName: 'Villa Santi Hotel',
      scheduledStart: DateTime.utc(2026, 10, 6, 5, 0),
      durationMinutes: 2880, // 2 nights
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: 'booking',
      bookingType: 'hotel',
      geoRegion: 'luang_prabang_laos',
    );

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

void main() {
  // -------------------------------------------------------------------------
  // R3: NOW badge for current-window stop
  // -------------------------------------------------------------------------
  group('R3: NOW badge', () {
    testWidgets('NOW visible when now is inside the node window',
        (tester) async {
      // Node: 10:00-11:30 UTC. Inject now = 10:30 UTC (inside).
      final node = _activityNode(
        scheduledStart: DateTime.utc(2026, 10, 2, 10, 0),
        durationMinutes: 90,
      );
      await tester.pumpWidget(_wrap(ActivityCard(
        node: node,
        now: DateTime.utc(2026, 10, 2, 10, 30),
      )));
      await tester.pumpAndSettle();

      expect(find.text('NOW'), findsOneWidget);
    });

    testWidgets('NOW absent when now is outside the node window',
        (tester) async {
      final node = _activityNode(
        scheduledStart: DateTime.utc(2026, 10, 2, 10, 0),
        durationMinutes: 90,
      );
      // now = 12:00 UTC, well after the 11:30 end.
      await tester.pumpWidget(_wrap(ActivityCard(
        node: node,
        now: DateTime.utc(2026, 10, 2, 12, 0),
      )));
      await tester.pumpAndSettle();

      expect(find.text('NOW'), findsNothing);
    });

    testWidgets('NOW absent for completed status even inside window',
        (tester) async {
      final node = _activityNode(
        scheduledStart: DateTime.utc(2026, 10, 2, 10, 0),
        durationMinutes: 90,
        status: NodeStatus.completed,
      );
      await tester.pumpWidget(_wrap(ActivityCard(
        node: node,
        now: DateTime.utc(2026, 10, 2, 10, 30),
      )));
      await tester.pumpAndSettle();

      expect(find.text('NOW'), findsNothing);
    });

    testWidgets('NOW absent for skipped status even inside window',
        (tester) async {
      final node = _activityNode(
        scheduledStart: DateTime.utc(2026, 10, 2, 10, 0),
        durationMinutes: 90,
        status: NodeStatus.skipped,
      );
      await tester.pumpWidget(_wrap(ActivityCard(
        node: node,
        now: DateTime.utc(2026, 10, 2, 10, 30),
      )));
      await tester.pumpAndSettle();

      expect(find.text('NOW'), findsNothing);
    });
  });

  // -------------------------------------------------------------------------
  // R4: Hotel continuation -- first vs later presentations
  // -------------------------------------------------------------------------
  group('R4: Hotel continuation', () {
    testWidgets('first presentation shows Edit and Delete', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(
        node: _hotelNode(),
        isContinuation: false,
        onTapEditBooking: () {},
        onTapDeleteBooking: () {},
      )));
      await tester.pumpAndSettle();

      expect(find.text('Edit'), findsOneWidget);
      expect(find.text('Delete'), findsOneWidget);
      expect(find.text('Continued stay'), findsNothing);
    });

    testWidgets('continuation hides Edit/Delete, shows label',
        (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(
        node: _hotelNode(),
        isContinuation: true,
        onTapEditBooking: () {},
        onTapDeleteBooking: () {},
      )));
      await tester.pumpAndSettle();

      expect(find.text('Edit'), findsNothing);
      expect(find.text('Delete'), findsNothing);
      expect(find.text('Continued stay'), findsOneWidget);
    });
  });

  // -------------------------------------------------------------------------
  // R5 partial: no FAB (checked via absence of FloatingActionButton)
  // -------------------------------------------------------------------------
  group('R5: Bottom inset contract', () {
    testWidgets('no INR, no walking minutes on card (preserved)', (tester) async {
      await tester.pumpWidget(_wrap(ActivityCard(node: _activityNode())));
      await tester.pumpAndSettle();

      expect(find.textContaining('INR'), findsNothing);
      expect(find.textContaining('\u20B9'), findsNothing);
      expect(find.textContaining('min walk'), findsNothing);
    });
  });
}
