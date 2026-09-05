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

    test('offset DateTime is grouped from its fields without conversion', () {
      // Dart DateTime.parse normalizes offset timestamps to UTC, so
      // '2026-10-06T01:30:00+05:30' becomes 2026-10-05T20:00Z (fields
      // show Oct 5, not Oct 6).  The grouping helper reads .year/.month/.day
      // directly -- no toUtc()/toLocal() -- so a local-like DateTime(Oct 6)
      // stays on Oct 6 while a UTC-normalized parse lands on Oct 5.
      //
      // This test verifies the helper never calls toUtc() before grouping:
      // a non-UTC DateTime(Oct 6, 1, 30) keeps its fields intact.
      final localLike = DateTime(2026, 10, 6, 1, 30);
      final nodes = [
        _node('day5', start: DateTime(2026, 10, 5, 18)),
        _node('late', start: localLike),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(2));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[1].date, DateTime(2026, 10, 6));
      // Sabotage proof: .toUtc() on a non-UTC DateTime is NOT identity
      // -- it applies the local timezone offset, so in UTC+N zones
      // 01:30 local could shift to the previous calendar day in UTC.
      // The UTC-parsed variant below already lands on Oct 5 because
      // Dart normalized the offset at parse time.
      final utcParsed = DateTime.parse('2026-10-06T01:30:00+05:30');
      expect(utcParsed.day, 5, reason: 'Dart normalizes offset to UTC');
      final groups2 = groupNodesByCalendarDate([
        _node('day5', start: DateTime(2026, 10, 5, 18)),
        _node('utc', start: utcParsed),
      ]);
      // Both land on Oct 5 because Dart already normalized
      expect(groups2, hasLength(1));
    });
  });
}
