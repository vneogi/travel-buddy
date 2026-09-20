// SPEC-42 Flutter proofs: span rendering + creationContext wiring.
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';

// Same helper used by date_scope_test.dart.
TripNode _node(
  String id, {
  required DateTime start,
  int duration = 90,
  String? name,
  String? geoRegion,
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? id,
      scheduledStart: start,
      durationMinutes: duration,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: geoRegion,
    );

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

      final nodes = [
        _node('n1',
            start: day1.add(const Duration(hours: 9)),
            geoRegion: 'luang_prabang_laos'),
        _node('n2',
            start: DateTime(2026, 10, 5, 9),
            geoRegion: 'luang_prabang_laos'),
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
          _node('n1',
              start: DateTime(2026, 10, 1, 9),
              geoRegion: 'luang_prabang_laos'),
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
      final nodes = [
        _node('n1',
            start: DateTime(2026, 10, 1, 9),
            name: 'VTE Venue',
            geoRegion: 'vientiane_laos'),
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
      expect(cityGroups[0].dayGroups.length, 3);
      expect(cityGroups[0].dayGroups[0].nodes.length, 1);
      expect(cityGroups[0].dayGroups[1].nodes.length, 0);
      expect(cityGroups[0].dayGroups[2].nodes.length, 0);
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
      final day1 = DateTime(2026, 10, 1);
      final day3 = DateTime(2026, 10, 3);

      final n1 = _node('n1',
          start: day1.add(const Duration(hours: 9)),
          geoRegion: 'luang_prabang_laos');
      final n2 = _node('n2',
          start: day3.add(const Duration(hours: 9)),
          geoRegion: 'luang_prabang_laos');

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
