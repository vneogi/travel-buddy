// SPEC-10 Flutter proofs: hotel dual timestamps, multi-date grouping,
// timeline widget safety with repeated hotel nodes.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

TripNode _node(
  String id, {
  required DateTime start,
  int duration = 90,
  String? name,
  String? geoRegion,
  String nodeKind = 'activity',
  String? bookingType,
  double? lat,
  double? lng,
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
      lat: lat,
      lng: lng,
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
      expect(find.textContaining('18:02'), findsOneWidget);
      expect(find.textContaining('15:00'), findsOneWidget);
      expect(find.text('1 night · checkout 3 Oct'), findsOneWidget);
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
  // 2. Hotel-aware date-grouping proofs
  //    (uses groupNodesByCalendarDateWithHotelStays, NOT the foundational
  //    groupNodesByCalendarDate whose contract is tested separately in
  //    date_scope_test.dart)
  // -----------------------------------------------------------------------
  group('groupNodesByCalendarDateWithHotelStays', () {
    test('check-in Oct 2 / checkout Oct 4 appears on Oct 2 and Oct 3', () {
      final hotel = _node('h-multi',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Multi Night Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      final groups = groupNodesByCalendarDateWithHotelStays([hotel]);
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

      final groups = groupNodesByCalendarDateWithHotelStays([hotel]);
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

      final groups = groupNodesByCalendarDateWithHotelStays([hotel]);
      for (final g in groups) {
        expect(g.nodes.first.nodeId, 'h-same-id');
      }
      // Same object identity — not cloned
      expect(identical(groups[0].nodes.first, groups[1].nodes.first), isTrue);
    });

    test('destination timezone conversion is used', () {
      // 23:30 UTC Oct 2 = 06:30 VTN Oct 3
      // +720 min = 18:30 VTN Oct 3 -> same local day, 1 group
      final hotel = _node('h-tz',
          start: DateTime.utc(2026, 10, 2, 23, 30),
          duration: 720,
          name: 'Late Check-in',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');

      final groups = groupNodesByCalendarDateWithHotelStays([hotel]);
      expect(groups.length, 1);
      expect(groups[0].date, DateTime(2026, 10, 3));
    });

    test('activity grouping remains unchanged', () {
      final activity = _node('a1',
          start: DateTime.utc(2026, 10, 2, 2, 0),
          duration: 90,
          name: 'Morning Temple',
          geoRegion: 'vientiane_laos');

      final groups = groupNodesByCalendarDateWithHotelStays([activity]);
      expect(groups.length, 1);
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

      final groups =
          groupNodesByCalendarDateWithHotelStays([act1, hotel, act2]);
      expect(groups.length, 2);
      expect(groups[0].nodes.map((n) => n.nodeId).toList(),
          containsAll(['a1', 'h-mix']));
      expect(groups[1].nodes.map((n) => n.nodeId).toList(),
          containsAll(['h-mix', 'a2']));
    });
  });

  group('spanAwareCorridorGroups', () {
    test('dateRange extends through hotel checkout morning', () {
      final hotel = _node('hotel-range',
          start: DateTime.utc(2026, 10, 2, 5, 33),
          duration: 2700,
          name: 'Salana boutique Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');
      final groups = spanAwareCorridorGroups(
        nodes: [hotel],
        segments: const [
          TripSegment(
            geoRegion: 'vientiane_laos',
            startsOn: '2026-10-02',
            endsOn: '2026-10-03',
          ),
        ],
      );
      expect(groups.single.dateRange, '2026-10-02 - 2026-10-04');
    });

    test('corridor timeline: one hotel card per night, never two on Oct 3',
        () {
      // 2-night hotel: check-in Oct 2 18:02 VTN, checkout Oct 4 15:00 VTN
      // Hotel covers nights of Oct 2 and Oct 3; checkout Oct 4 is excluded.
      final hotel = _node('hotel-dup-check',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Dhavara Boutique Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');
      final act2 = _node('act-oct2',
          start: DateTime.utc(2026, 10, 2, 2, 0),
          duration: 90,
          name: 'Morning Temple',
          geoRegion: 'vientiane_laos');
      final act3 = _node('act-oct3',
          start: DateTime.utc(2026, 10, 3, 2, 0),
          duration: 90,
          name: 'Lunch Spot',
          geoRegion: 'vientiane_laos');

      final groups = spanAwareCorridorGroups(
        nodes: [act2, hotel, act3],
        segments: const [
          TripSegment(
            geoRegion: 'vientiane_laos',
            startsOn: '2026-10-02',
            endsOn: '2026-10-03',
          ),
        ],
      );
      // The corridor must produce day groups for Oct 2 and Oct 3.
      final cityGroup = groups.single;

      // Assert exactly one hotel card under Oct 2 and exactly one under Oct 3.
      final oct2Group =
          cityGroup.dayGroups.firstWhere((g) => g.date == DateTime(2026, 10, 2));
      final oct3Group =
          cityGroup.dayGroups.firstWhere((g) => g.date == DateTime(2026, 10, 3));
      expect(
          oct2Group.nodes.where((n) => n.nodeId == 'hotel-dup-check').length, 1,
          reason: 'Exactly one hotel card under Oct 2');
      expect(
          oct3Group.nodes.where((n) => n.nodeId == 'hotel-dup-check').length, 1,
          reason: 'Exactly one hotel card under Oct 3');

      // Hotel must NOT appear on Oct 4 (checkout excluded)
      final oct4 = DateTime(2026, 10, 4);
      final hasOct4 = cityGroup.dayGroups.any((g) => g.date == oct4);
      if (hasOct4) {
        final oct4Group =
            cityGroup.dayGroups.firstWhere((g) => g.date == oct4);
        expect(
            oct4Group.nodes.any((n) => n.nodeId == 'hotel-dup-check'), isFalse,
            reason: 'Hotel must not appear on checkout date');
      }

      // City dateRange extends through checkout morning
      expect(cityGroup.dateRange, '2026-10-02 - 2026-10-04');
    });

    test('resolveTimelineGroups with override: one hotel per date', () {
      // Exercise the public helper that _DateScopedTimeline.build calls.
      // With dayGroupsOverride the corridor pre-grouped data passes through.
      final hotel = _node('hotel-resolve',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Resolve Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');
      final act = _node('act-resolve',
          start: DateTime.utc(2026, 10, 3, 2, 0),
          duration: 90,
          name: 'Activity',
          geoRegion: 'vientiane_laos');

      // Get the corridor day groups (correct: 1 hotel per date).
      final corridor = spanAwareCorridorGroups(
        nodes: [hotel, act],
        segments: const [
          TripSegment(
            geoRegion: 'vientiane_laos',
            startsOn: '2026-10-02',
            endsOn: '2026-10-03',
          ),
        ],
      );
      final dayGroups = corridor.single.dayGroups;
      // Simulate the flatten that _buildCitySection does at line 544.
      final flattenedNodes =
          dayGroups.expand((dg) => dg.nodes).toList();

      // WITH dayGroupsOverride (production path): hotel once per date.
      final withOverride = resolveTimelineGroups(
        nodes: flattenedNodes,
        dayGroupsOverride: dayGroups,
        isCorridor: true,
      );
      for (final g in withOverride) {
        final count =
            g.nodes.where((n) => n.nodeId == 'hotel-resolve').length;
        expect(count, lessThanOrEqualTo(1),
            reason: 'With override: max 1 hotel per date');
      }

      // WITHOUT dayGroupsOverride (would be the bug path): duplicates.
      final withoutOverride = resolveTimelineGroups(
        nodes: flattenedNodes,
        isCorridor: true,
      );
      final oct3 = withoutOverride
          .where((g) => g.date == DateTime(2026, 10, 3))
          .toList();
      expect(oct3, isNotEmpty);
      final hotelCountBug =
          oct3.first.nodes.where((n) => n.nodeId == 'hotel-resolve').length;
      expect(hotelCountBug, greaterThan(1),
          reason:
              'Without override the helper re-expands flattened nodes, '
              'duplicating the hotel -- this proves the override is required');
    });
  });

  // -----------------------------------------------------------------------
  // 3. Timeline widget: two-night hotel renders on both dates without
  //    duplicate GlobalKey exceptions.
  // -----------------------------------------------------------------------
  group('Timeline with repeated hotel', () {
    testWidgets('two-night hotel renders twice, no duplicate GlobalKey',
        (tester) async {
      // Hotel: Oct 2 evening -> Oct 4 afternoon VTN (2 covered dates)
      final hotel = _node('hotel-2night',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Two Night Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');
      final act = _node('act-oct3',
          start: DateTime.utc(2026, 10, 3, 2, 0),
          duration: 90,
          name: 'Temple Visit',
          geoRegion: 'vientiane_laos');

      final groups =
          groupNodesByCalendarDateWithHotelStays([hotel, act]);

      // Build a simplified timeline mimicking itinerary_screen logic.
      final items = <Map<String, dynamic>>[];
      for (final group in groups) {
        items.add({'type': 'header', 'date': group.date});
        for (final node in group.nodes) {
          items.add({'type': 'card', 'node': node});
        }
      }

      // Build widgets with the same GlobalKey logic as itinerary_screen.
      final nodeKeys = <String, GlobalKey>{};
      final seenNodeIds = <String>{};
      final widgets = <Widget>[];
      for (var i = 0; i < items.length; i++) {
        final item = items[i];
        if (item['type'] == 'header') {
          widgets.add(Text('Date: ${item['date']}',
              key: ValueKey('header_$i')));
          continue;
        }
        final TripNode node = item['node'];
        final isFirst = seenNodeIds.add(node.nodeId);
        final Key widgetKey;
        if (isFirst) {
          widgetKey =
              nodeKeys.putIfAbsent(node.nodeId, () => GlobalKey());
        } else {
          widgetKey = ValueKey('${node.nodeId}_$i');
        }

        // Find nextNode skipping same node_id
        TripNode? next;
        for (var j = i + 1; j < items.length; j++) {
          if (items[j]['type'] == 'card') {
            final TripNode candidate = items[j]['node'];
            if (candidate.nodeId != node.nodeId) {
              next = candidate;
              break;
            }
          }
        }

        widgets.add(KeyedSubtree(
          key: widgetKey,
          child: ActivityCard(
            node: node,
            nextNode: next,
            isLoved: false,
            isRecordingOutcome: false,
          ),
        ));
      }

      // Pump the widget tree — no duplicate GlobalKey exception expected.
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: SingleChildScrollView(
            child: Column(children: widgets),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // Hotel name renders twice (once per covered date).
      expect(find.text('Two Night Hotel'), findsNWidgets(2));
      // Activity renders once.
      expect(find.text('Temple Visit'), findsOneWidget);
      // Check-in / Check-out labels for each hotel presentation.
      expect(find.text('Check-in'), findsNWidgets(2));
      expect(find.text('Check-out'), findsNWidgets(2));
    });

    test('nextNode skips repeated hotel node_id', () {
      final hotel = _node('h-skip',
          start: DateTime.utc(2026, 10, 2, 11, 2),
          duration: 2698,
          name: 'Skip Hotel',
          geoRegion: 'vientiane_laos',
          nodeKind: 'booking',
          bookingType: 'hotel');
      final act = _node('a-after',
          start: DateTime.utc(2026, 10, 3, 5, 0),
          duration: 60,
          name: 'After Activity',
          geoRegion: 'vientiane_laos');

      final groups =
          groupNodesByCalendarDateWithHotelStays([hotel, act]);
      // Flatten to card items only
      final cards = <TripNode>[];
      for (final g in groups) {
        cards.addAll(g.nodes);
      }
      // Oct 2: hotel; Oct 3: hotel, activity
      // From Oct 2 hotel, nextNode should skip Oct 3 hotel -> activity
      TripNode? nextForFirst;
      for (var j = 1; j < cards.length; j++) {
        if (cards[j].nodeId != cards[0].nodeId) {
          nextForFirst = cards[j];
          break;
        }
      }
      expect(nextForFirst, isNotNull);
      expect(nextForFirst!.nodeId, 'a-after');
    });
  });

  // -----------------------------------------------------------------------
  // 4. TripNode lat/lng round-trip
  // -----------------------------------------------------------------------
  group('TripNode lat/lng round-trip', () {
    test('hotel with lat/lng round-trips through JSON', () {
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
