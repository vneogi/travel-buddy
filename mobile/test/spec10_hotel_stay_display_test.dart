// SPEC-10 Flutter proofs: hotel dual timestamps, multi-date grouping.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/core/destination_tz.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

TripNode _node(
  String id, {
  required DateTime start,
  int duration = 90,
  String? name,
  String? geoRegion,
  String nodeKind = 'activity',
  String? bookingType,
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? id,
      scheduledStart: start,
      durationMinutes: duration,
      isLocked: nodeKind == 'booking',
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: geoRegion,
      nodeKind: nodeKind,
      bookingType: bookingType,
    );

void main() {
  // -----------------------------------------------------------------------
  // 1. Widget test: hotel card shows Check-in + Check-out labels/times
  // -----------------------------------------------------------------------
  group('ActivityCard hotel dual timestamps', () {
    testWidgets('hotel card renders Check-in and Check-out labels',
        (tester) async {
      // 11:02 UTC = 18:02 VTN; duration 1258 min -> checkout 15:00 VTN
      final hotel = _node('h1',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 1258,
          name: 'Dhavara Boutique Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: ActivityCard(
              node: hotel,
              nextNode: null,
              isLoved: false,
              isRecordingOutcome: false,
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Check-in'), findsOneWidget);
      expect(find.text('Check-out'), findsOneWidget);
      // Both times must render
      expect(find.textContaining('18:02'), findsOneWidget);
      expect(find.textContaining('15:00'), findsOneWidget);
    });

    testWidgets('flight card has neither Check-in nor Check-out labels',
        (tester) async {
      final flight = _node('f1',
          start: DateTime.utc(2026, 10, 5, 0, 0),
          duration: 120,
          name: 'VN 921',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'flight');

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: ActivityCard(
              node: flight,
              nextNode: null,
              isLoved: false,
              isRecordingOutcome: false,
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      expect(find.text('Check-in'), findsNothing);
      expect(find.text('Check-out'), findsNothing);
    });
  });

  // -----------------------------------------------------------------------
  // 2. Date-grouping proofs: multi-night hotel coverage
  // -----------------------------------------------------------------------
  group('Multi-date hotel grouping', () {
    test('check-in Oct 2 / checkout Oct 4 appears on Oct 2 and Oct 3', () {
      // 18:02 VTN Oct 2 = 11:02 UTC; checkout 15:00 VTN Oct 4 = 08:00 UTC Oct 4
      // Duration = 44h58m = 2698 min
      final hotel = _node('h-multi',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Multi Night Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      final groups = groupNodesByCalendarDate([hotel]);

      // Must appear on Oct 2 and Oct 3
      expect(groups.length, 2);
      expect(groups[0].date, DateTime(2026, 10, 2));
      expect(groups[1].date, DateTime(2026, 10, 3));
    });

    test('does not appear on checkout date Oct 4', () {
      final hotel = _node('h-multi',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Multi Night Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      final groups = groupNodesByCalendarDate([hotel]);
      final dates = groups.map((g) => g.date).toList();
      expect(dates.contains(DateTime(2026, 10, 4)), isFalse);
    });

    test('both appearances have the same node_id', () {
      final hotel = _node('h-same-id',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Stable ID Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      final groups = groupNodesByCalendarDate([hotel]);
      for (final g in groups) {
        expect(g.nodes.first.nodeId, 'h-same-id');
      }
    });

    test('destination timezone conversion is used', () {
      // 23:30 UTC Oct 2 = 06:30 VTN Oct 3 (next day local)
      // checkout: 23:30 UTC + 720 min (12h) = 11:30 UTC Oct 3 = 18:30 VTN Oct 3
      // So hotel local: check-in Oct 3, checkout Oct 3 -> covers only Oct 3 (same day)
      // Actually checkout is same local day -> only 1 date
      final hotel = _node('h-tz',
          start: DateTime.utc(2026, 10, 2, 23, 30),
          duration: 720,
          name: 'Late Check-in',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      final groups = groupNodesByCalendarDate([hotel]);
      // 23:30 UTC = 06:30 VTN Oct 3; +720min = 18:30 VTN Oct 3 -> same day
      expect(groups.length, 1);
      expect(groups[0].date, DateTime(2026, 10, 3));
    });

    test('activity grouping remains unchanged', () {
      final activity = _node('a1',
          start: DateTime.utc(2026, 10, 2, 2, 0),
          duration: 90,
          name: 'Morning Temple',
          geoRegion: 'vientiane_laos');

      final groups = groupNodesByCalendarDate([activity]);
      expect(groups.length, 1);
      // Still grouped by its scheduledStart date
    });

    test('hotel mixed with activities groups correctly', () {
      final hotel = _node('h-mix',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');
      final act1 = _node('a1',
          start: DateTime.utc(2026, 10, 2, 2, 0),
          duration: 90,
          name: 'Morning',
          geoRegion: 'vientiane_laos');
      final act2 = _node('a2',
          start: DateTime.utc(2026, 10, 3, 2, 0),
          duration: 90,
          name: 'Next Day',
          geoRegion: 'vientiane_laos');

      final groups = groupNodesByCalendarDate([act1, hotel, act2]);
      // Oct 2: act1 + hotel; Oct 3: hotel + act2
      expect(groups.length, 2);
      expect(groups[0].nodes.map((n) => n.nodeId).toList(),
          containsAll(['a1', 'h-mix']));
      expect(groups[1].nodes.map((n) => n.nodeId).toList(),
          containsAll(['h-mix', 'a2']));
    });
  });

  // -----------------------------------------------------------------------
  // 3. TripNode lat/lng round-trip
  // -----------------------------------------------------------------------
  group('TripNode lat/lng round-trip', () {
    test('hotel with lat/lng round-trips through JSON', () {
      final hotel = _node('h2',
          start: DateTime.utc(2026, 10, 2, 11, 0),
          duration: 900,
          name: 'Settha Palace',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      // Manually construct with lat/lng
      final withCoords = TripNode(
        nodeId: 'h2',
        venueName: 'Settha Palace',
        scheduledStart: DateTime.utc(2026, 10, 2, 11, 0),
        durationMinutes: 900,
        isLocked: true,
        status: NodeStatus.pending,
        vibeTags: const [],
        nodeKind: 'booking',
        bookingType: 'hotel',
        lat: 17.9669,
        lng: 102.6135,
        geoRegion: 'vientiane_laos',
      );

      final json = withCoords.toJson();
      expect(json['lat'], closeTo(17.9669, 0.001));
      expect(json['lng'], closeTo(102.6135, 0.001));

      final restored = TripNode.fromJson(json);
      expect(restored.lat, closeTo(17.9669, 0.001));
      expect(restored.lng, closeTo(102.6135, 0.001));
    });
  });
}
