// SPEC-42 Flutter proofs: span rendering + creationContext wiring.
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';

void main() {
  // -----------------------------------------------------------------------
  // 1. CreateTripOptions: new fields parse and default
  // -----------------------------------------------------------------------
  group('CreateTripOptions SPEC-42 fields', () {
    test('fromJson parses max_auto_populated_days and trip_span_sanity_days',
        () {
      final opts = CreateTripOptions.fromJson({
        'party_types': [],
        'interests': [],
        'max_days_by_region': {'dubai_uae': 4},
        'max_auto_populated_days': 3,
        'trip_span_sanity_days': 60,
      });
      expect(opts.maxAutoPopulatedDays, 3);
      expect(opts.tripSpanSanityDays, 60);
      expect(opts.maxDaysByRegion, {'dubai_uae': 4});
    });

    test('fromJson defaults when fields absent', () {
      final opts = CreateTripOptions.fromJson({
        'party_types': [],
        'interests': [],
      });
      expect(opts.maxAutoPopulatedDays, 5);
      expect(opts.tripSpanSanityDays, 90);
      expect(opts.maxDaysByRegion, isEmpty);
    });
  });

  // -----------------------------------------------------------------------
  // 2. spanAwareDayGroups: ten-day trip renders ten date sections
  // -----------------------------------------------------------------------
  group('spanAwareDayGroups', () {
    test('ten-day single-city trip renders ten date sections', () {
      final day1 = DateTime(2026, 10, 1);
      final day10 = DateTime(2026, 10, 10);

      // Only two nodes, on days 1 and 5
      final nodes = [
        TripNode(
          nodeId: 'n1', tripId: 't1', venueName: 'A',
          scheduledStart: day1.add(const Duration(hours: 9)),
          durationMinutes: 90, geoRegion: 'luang_prabang_laos',
        ),
        TripNode(
          nodeId: 'n2', tripId: 't1', venueName: 'B',
          scheduledStart: DateTime(2026, 10, 5, 9),
          durationMinutes: 90, geoRegion: 'luang_prabang_laos',
        ),
      ];

      final groups = spanAwareDayGroups(
        nodes: nodes,
        startLocal: day1,
        endLocal: day10,
      );
      expect(groups.length, 10);
    });

    test('empty dates have zero nodes', () {
      final groups = spanAwareDayGroups(
        nodes: [
          TripNode(
            nodeId: 'n1', tripId: 't1', venueName: 'A',
            scheduledStart: DateTime(2026, 10, 1, 9),
            durationMinutes: 90, geoRegion: 'luang_prabang_laos',
          ),
        ],
        startLocal: DateTime(2026, 10, 1),
        endLocal: DateTime(2026, 10, 3),
      );
      expect(groups.length, 3);
      expect(groups[0].nodes.length, 1);
      expect(groups[1].nodes.length, 0); // Oct 2: empty
      expect(groups[2].nodes.length, 0); // Oct 3: empty
    });

    test('fully empty valid trip renders its dates', () {
      // Zero nodes, but a valid 5-day span
      final groups = spanAwareDayGroups(
        nodes: [],
        startLocal: DateTime(2026, 10, 1),
        endLocal: DateTime(2026, 10, 5),
      );
      expect(groups.length, 5);
      for (final g in groups) {
        expect(g.nodes, isEmpty);
      }
    });
  });

  // -----------------------------------------------------------------------
  // 3. spanAwareCorridorGroups: corridor segments render every date
  // -----------------------------------------------------------------------
  group('spanAwareCorridorGroups', () {
    test('corridor segments render every segment date including empty ones',
        () {
      // Segment 1: Oct 1-3 (3 days), node only on Oct 1
      // Segment 2: Oct 5-7 (3 days), no nodes at all
      final nodes = [
        TripNode(
          nodeId: 'n1', tripId: 't1', venueName: 'VTE Venue',
          scheduledStart: DateTime(2026, 10, 1, 9),
          durationMinutes: 90, geoRegion: 'vientiane_laos',
        ),
      ];
      final segments = [
        const TripSegment(
          geoRegion: 'vientiane_laos',
          startsOn: '2026-10-01',
          endsOn: '2026-10-03',
        ),
        const TripSegment(
          geoRegion: 'luang_prabang_laos',
          startsOn: '2026-10-05',
          endsOn: '2026-10-07',
        ),
      ];

      final cityGroups = spanAwareCorridorGroups(
        nodes: nodes,
        segments: segments,
      );

      expect(cityGroups.length, 2);
      // Segment 1: 3 days, 1 populated + 2 empty
      expect(cityGroups[0].dayGroups.length, 3);
      expect(cityGroups[0].dayGroups[0].nodes.length, 1);
      expect(cityGroups[0].dayGroups[1].nodes.length, 0);
      expect(cityGroups[0].dayGroups[2].nodes.length, 0);
      // Segment 2: 3 days, all empty
      expect(cityGroups[1].dayGroups.length, 3);
      for (final g in cityGroups[1].dayGroups) {
        expect(g.nodes, isEmpty);
      }
    });
  });

  // -----------------------------------------------------------------------
  // 4. ItineraryState preserves creationContext through copyWith
  // -----------------------------------------------------------------------
  group('ItineraryState creationContext', () {
    test('online TripState creationContext preserved in ItineraryState', () {
      const ctx = CreationContext(
        destination: 'luang_prabang_laos',
        startDateLocal: '2026-10-01',
        endDateLocal: '2026-10-10',
      );
      const state = ItineraryState(creationContext: ctx);
      expect(state.creationContext, isNotNull);
      expect(state.creationContext!.startDateLocal, '2026-10-01');
      expect(state.creationContext!.endDateLocal, '2026-10-10');
    });

    test('copyWith preserves creationContext when not overridden', () {
      const ctx = CreationContext(
        destination: 'dubai_uae',
        startDateLocal: '2026-11-01',
        endDateLocal: '2026-11-05',
      );
      const state = ItineraryState(creationContext: ctx);
      final updated = state.copyWith(loading: false);
      expect(updated.creationContext, isNotNull);
      expect(updated.creationContext!.startDateLocal, '2026-11-01');
    });

    test('copyWith can clear creationContext', () {
      const ctx = CreationContext(
        destination: 'dubai_uae',
        startDateLocal: '2026-11-01',
        endDateLocal: '2026-11-05',
      );
      const state = ItineraryState(creationContext: ctx);
      final cleared = state.copyWith(creationContext: null);
      expect(cleared.creationContext, isNull);
    });

    test('cached TripState round-trips creationContext', () {
      final trip = TripState(
        tripId: 'trip-1',
        userId: 'u1',
        nodes: [],
        geoRegion: 'luang_prabang_laos',
        creationContext: const CreationContext(
          destination: 'luang_prabang_laos',
          startDateLocal: '2026-10-01',
          endDateLocal: '2026-10-10',
        ),
      );
      // Simulate cache round-trip
      final json = trip.toJson();
      final restored = TripState.fromJson(json);
      expect(restored.creationContext, isNotNull);
      expect(restored.creationContext!.startDateLocal, '2026-10-01');
      expect(restored.creationContext!.endDateLocal, '2026-10-10');
    });
  });

  // -----------------------------------------------------------------------
  // 5. nextNode crosses an empty day
  // -----------------------------------------------------------------------
  group('nextNode traversal', () {
    test('nextNode skips empty days to find actual next node', () {
      // Simulate the _TimelineItem list building:
      // Day 1: header, card(n1), Day 2: header, emptyDay, Day 3: header, card(n2)
      // From n1, nextNode should find n2 by skipping headers and emptyDay.
      final day1 = DateTime(2026, 10, 1);
      final day3 = DateTime(2026, 10, 3);

      final n1 = TripNode(
        nodeId: 'n1', tripId: 't1', venueName: 'A',
        scheduledStart: day1.add(const Duration(hours: 9)),
        durationMinutes: 90, geoRegion: 'luang_prabang_laos',
      );
      final n2 = TripNode(
        nodeId: 'n2', tripId: 't1', venueName: 'B',
        scheduledStart: day3.add(const Duration(hours: 9)),
        durationMinutes: 90, geoRegion: 'luang_prabang_laos',
      );

      // Build groups with 3-day span
      final groups = spanAwareDayGroups(
        nodes: [n1, n2],
        startLocal: day1,
        endLocal: day3,
      );
      expect(groups.length, 3);

      // Build flat items like _DateScopedTimeline does
      final items = <Map<String, dynamic>>[];
      for (final g in groups) {
        items.add({'type': 'header', 'date': g.date});
        if (g.nodes.isEmpty) {
          items.add({'type': 'emptyDay'});
        } else {
          for (final node in g.nodes) {
            items.add({'type': 'card', 'node': node});
          }
        }
      }

      // Find n1's index and scan forward
      final n1Index = items.indexWhere(
        (i) => i['type'] == 'card' && (i['node'] as TripNode).nodeId == 'n1',
      );
      expect(n1Index, isNonNegative);

      TripNode? next;
      for (var j = n1Index + 1; j < items.length; j++) {
        final t = items[j]['type'];
        if (t != 'header' && t != 'emptyDay') {
          next = items[j]['node'] as TripNode;
          break;
        }
      }
      expect(next, isNotNull);
      expect(next!.nodeId, 'n2');
    });
  });
}
