// SPEC-42 Flutter proofs: catalog caps removed from UI.
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';

void main() {
  // -----------------------------------------------------------------------
  // CreateTripOptions: new fields parse and default
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
  // spanAwareDayGroups: empty days rendered
  // -----------------------------------------------------------------------
  group('spanAwareDayGroups', () {
    test('fills empty days between populated days', () {
      // Two nodes on day 1 and day 3 of a 5-day span
      final day1 = DateTime(2026, 10, 1);
      final day3 = DateTime(2026, 10, 3);
      final day5 = DateTime(2026, 10, 5);

      final nodes = [
        TripNode(
          nodeId: 'n1',
          tripId: 't1',
          venueName: 'Venue A',
          scheduledStart: day1.add(const Duration(hours: 9)),
          durationMinutes: 90,
          geoRegion: 'luang_prabang_laos',
        ),
        TripNode(
          nodeId: 'n2',
          tripId: 't1',
          venueName: 'Venue B',
          scheduledStart: day3.add(const Duration(hours: 9)),
          durationMinutes: 90,
          geoRegion: 'luang_prabang_laos',
        ),
      ];

      final groups = spanAwareDayGroups(
        nodes: nodes,
        startLocal: day1,
        endLocal: day5,
      );

      // 5 days total
      expect(groups.length, 5);
      // Day 1 has 1 node
      expect(groups[0].nodes.length, 1);
      // Day 2 is empty
      expect(groups[1].nodes.length, 0);
      // Day 3 has 1 node
      expect(groups[2].nodes.length, 1);
      // Day 4, 5 empty
      expect(groups[3].nodes.length, 0);
      expect(groups[4].nodes.length, 0);
    });

    test('single-day span with no nodes returns one empty group', () {
      final day = DateTime(2026, 10, 1);
      final groups = spanAwareDayGroups(
        nodes: [],
        startLocal: day,
        endLocal: day,
      );
      expect(groups.length, 1);
      expect(groups[0].nodes, isEmpty);
      expect(groups[0].date, day);
    });
  });
}
