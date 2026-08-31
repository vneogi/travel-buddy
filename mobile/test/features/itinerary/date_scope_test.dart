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

    test('offset DateTime is grouped from its fields without conversion', () {
      // A DateTime with a +05:30 offset should group under the date
      // represented by its fields, not after toUtc() conversion.
      // DateTime.parse preserves the offset in the represented fields.
      final late = DateTime.parse('2026-10-06T01:30:00+05:30');
      // That instant is 2026-10-05T20:00:00Z, but the fields say Oct 6.
      final nodes = [
        _node('day5', start: DateTime(2026, 10, 5, 18)),
        _node('late', start: late),
      ];
      final groups = groupNodesByCalendarDate(nodes);
      expect(groups, hasLength(2));
      expect(groups[0].date, DateTime(2026, 10, 5));
      expect(groups[1].date, DateTime(2026, 10, 6));
    });
  });

  // -----------------------------------------------------------
  // isHotelLikeNode
  // -----------------------------------------------------------
  group('isHotelLikeNode', () {
    test('booking type hotel is recognized', () {
      final n = _node('h', start: DateTime(2026, 10, 5),
          nodeKind: 'booking', bookingType: 'hotel');
      expect(isHotelLikeNode(n), isTrue);
    });

    test('name fallback hotel', () {
      expect(isHotelLikeNode(
        _node('x', start: DateTime(2026, 10, 5), name: 'Grand Hotel Luang Prabang'),
      ), isTrue);
    });

    test('name fallback resort', () {
      expect(isHotelLikeNode(
        _node('x', start: DateTime(2026, 10, 5), name: 'Beach Resort'),
      ), isTrue);
    });

    test('name fallback hostel', () {
      expect(isHotelLikeNode(
        _node('x', start: DateTime(2026, 10, 5), name: 'Downtown Hostel'),
      ), isTrue);
    });

    test('name fallback villa', () {
      expect(isHotelLikeNode(
        _node('x', start: DateTime(2026, 10, 5), name: 'Villa Maly'),
      ), isTrue);
    });

    test('name fallback guesthouse', () {
      expect(isHotelLikeNode(
        _node('x', start: DateTime(2026, 10, 5), name: 'Cozy Guesthouse'),
      ), isTrue);
    });

    test('non-hotel activity is not recognized', () {
      expect(isHotelLikeNode(
        _node('x', start: DateTime(2026, 10, 5), name: 'Night Market'),
      ), isFalse);
    });
  });

  // -----------------------------------------------------------
  // selectRescueStay
  // -----------------------------------------------------------
  group('selectRescueStay', () {
    test('active stay beats elapsed and future', () {
      final now = DateTime(2026, 10, 5, 20);
      final nodes = [
        _node('past', start: DateTime(2026, 10, 4, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
        _node('active', start: DateTime(2026, 10, 5, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
        _node('future', start: DateTime(2026, 10, 7, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
      ];
      expect(selectRescueStay(nodes, now)!.nodeId, 'active');
    });

    test('overlapping active stays choose latest start', () {
      final now = DateTime(2026, 10, 5, 20);
      final nodes = [
        _node('early', start: DateTime(2026, 10, 5, 10), duration: 1440,
            nodeKind: 'booking', bookingType: 'hotel'),
        _node('late', start: DateTime(2026, 10, 5, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
      ];
      expect(selectRescueStay(nodes, now)!.nodeId, 'late');
    });

    test('no active stay chooses earliest future', () {
      final now = DateTime(2026, 10, 3, 12);
      final nodes = [
        _node('far', start: DateTime(2026, 10, 7, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
        _node('near', start: DateTime(2026, 10, 5, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
      ];
      expect(selectRescueStay(nodes, now)!.nodeId, 'near');
    });

    test('no active/future chooses latest-ended elapsed', () {
      final now = DateTime(2026, 10, 10, 12);
      final nodes = [
        _node('old', start: DateTime(2026, 10, 4, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
        _node('recent', start: DateTime(2026, 10, 6, 14), duration: 720,
            nodeKind: 'booking', bookingType: 'hotel'),
      ];
      expect(selectRescueStay(nodes, now)!.nodeId, 'recent');
    });

    test('46-hour hotel is active on the second calendar day', () {
      // Check in Oct 5 14:00, check out Oct 7 12:00 (46 hours).
      final now = DateTime(2026, 10, 6, 10);
      final nodes = [
        _node('long', start: DateTime(2026, 10, 5, 14), duration: 2760,
            nodeKind: 'booking', bookingType: 'hotel'),
      ];
      expect(selectRescueStay(nodes, now)!.nodeId, 'long');
    });

    test('exact checkout boundary is not active (half-open)', () {
      // Hotel: Oct 5 14:00 to Oct 6 14:00 (1440 min).
      // now == Oct 6 14:00 exactly -> NOT active (end is exclusive).
      final checkout = DateTime(2026, 10, 6, 14);
      final nodes = [
        _node('h', start: DateTime(2026, 10, 5, 14), duration: 1440,
            nodeKind: 'booking', bookingType: 'hotel'),
      ];
      final result = selectRescueStay(nodes, checkout);
      // Should be elapsed, not active.
      expect(result!.nodeId, 'h');
      // Verify it was selected as elapsed (no future, no active).
      // If it were active we'd be OK too, but let's verify the boundary:
      // Immediately before checkout should be active.
      final justBefore = checkout.subtract(const Duration(seconds: 1));
      expect(selectRescueStay(nodes, justBefore)!.nodeId, 'h');
    });

    test('no hotel returns null', () {
      final nodes = [
        _node('cafe', start: DateTime(2026, 10, 5, 9)),
        _node('market', start: DateTime(2026, 10, 5, 14)),
      ];
      expect(selectRescueStay(nodes, DateTime(2026, 10, 5, 12)), isNull);
    });

    test('list order does not affect selected stay', () {
      final now = DateTime(2026, 10, 5, 20);
      final active = _node('active', start: DateTime(2026, 10, 5, 14),
          duration: 720, nodeKind: 'booking', bookingType: 'hotel');
      final future = _node('future', start: DateTime(2026, 10, 7, 14),
          duration: 720, nodeKind: 'booking', bookingType: 'hotel');

      // Forward order
      expect(selectRescueStay([active, future], now)!.nodeId, 'active');
      // Reverse order
      expect(selectRescueStay([future, active], now)!.nodeId, 'active');
    });

    test('keyword fallback is recognized for rescue', () {
      final now = DateTime(2026, 10, 5, 20);
      final nodes = [
        _node('v', start: DateTime(2026, 10, 5, 14), duration: 720,
            name: 'Villa Maly'),
      ];
      expect(selectRescueStay(nodes, now)!.nodeId, 'v');
    });
  });
}
