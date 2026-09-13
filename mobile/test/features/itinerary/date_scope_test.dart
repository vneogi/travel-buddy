import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';

TripNode _node(
  String id, {
  required DateTime start,
  int duration = 90,
  String nodeKind = 'activity',
  String? bookingType,
  String? name,
  String? geoRegion,
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? id,
      scheduledStart: start,
      durationMinutes: duration,
      isLocked: nodeKind == 'booking',
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: nodeKind,
      bookingType: bookingType,
      geoRegion: geoRegion,
    );

void main() {
  // -----------------------------------------------------------
  // groupNodesByCalendarDate
  // -----------------------------------------------------------
  group('groupNodesByCalendarDate', () {
    test('one calendar date produces one group', () {
      final nodes = [
        _node('a', start: DateTime(2026, 10, 5, 9)),
        _node('b', start: DateTime(2026, 10, 5, 14)),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(1));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[0].nodes.map((n) => n.nodeId), ['a', 'b']);
    });

    test('multiple dates produce ordered groups', () {
      final nodes = [
        _node('d1a', start: DateTime(2026, 10, 5, 9)),
        _node('d1b', start: DateTime(2026, 10, 5, 14)),
        _node('d2a', start: DateTime(2026, 10, 6, 10)),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(2));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[1].date, DateTime(2026, 10, 6));
    });

    test('nodes within a date preserve input order', () {
      final nodes = [
        _node('z', start: DateTime(2026, 10, 5, 15)),
        _node('a', start: DateTime(2026, 10, 5, 9)),
        _node('m', start: DateTime(2026, 10, 5, 12)),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups[0].nodes.map((n) => n.nodeId), ['z', 'a', 'm']);
    });

    test('input list is not mutated', () {
      final nodes = [
        _node('a', start: DateTime(2026, 10, 5, 9)),
        _node('b', start: DateTime(2026, 10, 6, 9)),
      ];
      final copy = List<TripNode>.of(nodes);
      groupNodesByCalendarDate(nodes);
      expect(nodes.length, copy.length);
      for (var i = 0; i < nodes.length; i++) {
        expect(identical(nodes[i], copy[i]), isTrue);
      }
    });

    test('Dec 31 and Jan 1 remain separate groups', () {
      final nodes = [
        _node('nye', start: DateTime(2026, 12, 31, 22)),
        _node('nyd', start: DateTime(2027, 1, 1, 10)),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(2));
      expect(groups[0].date, DateTime(2026, 12, 31));
      expect(groups[1].date, DateTime(2027, 1, 1));
    });

    test('non-contiguous same date produces separate groups (A/B/A)', () {
      final nodes = [
        _node('a1', start: DateTime(2026, 10, 5, 9)),
        _node('b1', start: DateTime(2026, 10, 6, 10)),
        _node('a2', start: DateTime(2026, 10, 5, 15)),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(3));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[0].nodes.map((n) => n.nodeId), ['a1']);
      expect(groups[1].date, DateTime(2026, 10, 6));
      expect(groups[1].nodes.map((n) => n.nodeId), ['b1']);
      expect(groups[2].date, DateTime(2026, 10, 5));
      expect(groups[2].nodes.map((n) => n.nodeId), ['a2']);
    });

    test('destination-local conversion groups by local date', () {
      // A Vientiane node at 22:00 UTC on Oct 5 is 05:00 ICT on Oct 6.
      // With geoRegion set, grouping uses destination-local, so it should
      // land on Oct 6, not Oct 5.
      final nodes = [
        _node('day5', start: DateTime.utc(2026, 10, 5, 10), geoRegion: 'vientiane_laos'),
        _node('day6', start: DateTime.utc(2026, 10, 5, 22), geoRegion: 'vientiane_laos'),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      // 10:00 UTC = 17:00 ICT Oct 5, 22:00 UTC = 05:00 ICT Oct 6
      expect(groups, hasLength(2));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[0].nodes.map((n) => n.nodeId), ['day5']);
      expect(groups[1].date, DateTime(2026, 10, 6));
      expect(groups[1].nodes.map((n) => n.nodeId), ['day6']);
    });

    test('null geoRegion falls back without crash', () {
      // Nodes without geoRegion fall back to .toLocal() in destination_tz.
      // On CI (UTC) this is identity, so fields are preserved.
      final nodes = [
        _node('a', start: DateTime.utc(2026, 10, 5, 18)),
        _node('b', start: DateTime.utc(2026, 10, 6, 1)),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(2));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[1].date, DateTime(2026, 10, 6));
    });
  });
}
