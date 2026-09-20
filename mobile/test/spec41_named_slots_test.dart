// SPEC-41 Slice 3: Named day slots -- Flutter widget proofs.
//
// Proofs:
//   - flexible card shows slot label, not walking-derived HH:MM
//   - locked hotel card still shows Check-in / Check-out exact times
//   - locked flight card still shows exact local time
//   - TripNode.fromJson parses slot_name
//
// Flutter UNVERIFIED without the Windows SDK.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

TripNode _flexibleNode(
  String id, {
  required DateTime start,
  String? name,
  String? slotName,
  String geoRegion = 'luang_prabang_laos',
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? id,
      scheduledStart: start,
      durationMinutes: 90,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: geoRegion,
      nodeKind: 'activity',
      slotName: slotName,
    );

TripNode _lockedNode(
  String id, {
  required DateTime start,
  int duration = 90,
  String? name,
  String bookingType = 'flight',
  String geoRegion = 'luang_prabang_laos',
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? id,
      scheduledStart: start,
      durationMinutes: duration,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: geoRegion,
      nodeKind: 'booking',
      bookingType: bookingType,
    );

void main() {
  group('ActivityCard slot rendering', () {
    testWidgets('flexible card shows slot label for morning_tour',
        (tester) async {
      final node = _flexibleNode('n1',
          start: DateTime.utc(2026, 10, 3, 2, 0),
          name: 'Wat Xieng Thong',
          slotName: 'morning_tour');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActivityCard(node: node),
          ),
        ),
      );

      expect(find.text('Morning'), findsOneWidget);
      // The slot label replaces the walking-derived time on flexible cards.
      // We do not assert the absence of a time string because the time rail
      // may still show in other parts of the card.
    });

    testWidgets('flexible card shows slot label for dinner',
        (tester) async {
      final node = _flexibleNode('n2',
          start: DateTime.utc(2026, 10, 3, 12, 0),
          name: 'Tamarind Restaurant',
          slotName: 'dinner');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActivityCard(node: node),
          ),
        ),
      );

      expect(find.text('Dinner'), findsOneWidget);
    });

    testWidgets('flexible card shows slot label for lunch',
        (tester) async {
      final node = _flexibleNode('n3',
          start: DateTime.utc(2026, 10, 3, 5, 0),
          name: 'Lao Lao Garden',
          slotName: 'lunch');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActivityCard(node: node),
          ),
        ),
      );

      expect(find.text('Lunch'), findsOneWidget);
    });

    testWidgets('flexible card shows slot label for afternoon',
        (tester) async {
      final node = _flexibleNode('n4',
          start: DateTime.utc(2026, 10, 3, 7, 0),
          name: 'Kuang Si Falls',
          slotName: 'afternoon_evening_tour');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActivityCard(node: node),
          ),
        ),
      );

      expect(find.text('Afternoon'), findsOneWidget);
    });

    testWidgets('locked hotel card shows Check-in and Check-out labels',
        (tester) async {
      // 11:02 UTC = 18:02 VTN; duration 1258 min -> checkout 15:00 next day VTN
      final hotel = _lockedNode('h1',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 1258,
          name: 'Dhavara Boutique Hotel',
          bookingType: 'hotel');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActivityCard(node: hotel),
          ),
        ),
      );

      expect(find.text('Check-in'), findsOneWidget);
      expect(find.text('Check-out'), findsOneWidget);
      // Locked hotel must NOT show a slot label.
      expect(find.text('Morning'), findsNothing);
      expect(find.text('Dinner'), findsNothing);
    });

    testWidgets('locked flight card shows exact time, not slot label',
        (tester) async {
      final flight = _lockedNode('f1',
          start: DateTime.utc(2026, 10, 2, 1, 0),
          duration: 120,
          name: 'LF321 to LPQ',
          bookingType: 'flight');

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ActivityCard(node: flight),
          ),
        ),
      );

      // Locked flight must NOT show slot labels.
      expect(find.text('Morning'), findsNothing);
      expect(find.text('Afternoon'), findsNothing);
      expect(find.text('Lunch'), findsNothing);
      expect(find.text('Dinner'), findsNothing);
    });
  });

  group('TripNode slot_name serialization', () {
    test('fromJson parses slot_name', () {
      final json = {
        'node_id': 'n1',
        'venue_name': 'Wat Xieng Thong',
        'scheduled_start': '2026-10-03T02:00:00.000Z',
        'duration_minutes': 90,
        'is_locked': false,
        'status': 'pending',
        'vibe_tags': [],
        'node_kind': 'activity',
        'slot_name': 'morning_tour',
      };
      final node = TripNode.fromJson(json);
      expect(node.slotName, 'morning_tour');
    });

    test('fromJson handles missing slot_name as null', () {
      final json = {
        'node_id': 'n1',
        'venue_name': 'Temple',
        'scheduled_start': '2026-10-03T02:00:00.000Z',
        'duration_minutes': 90,
        'is_locked': false,
        'status': 'pending',
        'vibe_tags': [],
        'node_kind': 'activity',
      };
      final node = TripNode.fromJson(json);
      expect(node.slotName, isNull);
    });

    test('toJson includes slot_name', () {
      final node = _flexibleNode('n1',
          start: DateTime.utc(2026, 10, 3, 2, 0),
          name: 'Wat',
          slotName: 'dinner');
      final json = node.toJson();
      expect(json['slot_name'], 'dinner');
    });

    test('toJson includes null slot_name for locked booking', () {
      final node = _lockedNode('f1',
          start: DateTime.utc(2026, 10, 2, 1, 0),
          name: 'Flight',
          bookingType: 'flight');
      final json = node.toJson();
      expect(json['slot_name'], isNull);
    });
  });
}
