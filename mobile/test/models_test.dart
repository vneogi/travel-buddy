import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';

void main() {
  group('TripNode.fromJson', () {
    test('parses full node', () {
      final n = TripNode.fromJson({
        'node_id': 'n1',
        'venue_name': 'Zuma',
        'venue_id': 'v9',
        'scheduled_start': '2026-08-05T14:30:00',
        'duration_minutes': 90,
        'is_locked': true,
        'status': 'pending',
        'micro_location': 'DIFC',
        'vibe_tags': ['premium_interiors', 'executive'],
        'lat': 25.21,
        'lng': 55.28,
        'opening_hours': '12:00-00:00',
      });
      expect(n.nodeId, 'n1');
      expect(n.isLocked, true);
      expect(n.status, NodeStatus.pending);
      expect(n.vibeTags, contains('executive'));
      expect(n.scheduledStart, DateTime.parse('2026-08-05T14:30:00'));
    });

    test('applies safe defaults for missing optionals', () {
      final n = TripNode.fromJson({
        'node_id': 'n2',
        'venue_name': 'Cafe',
        'scheduled_start': '2026-08-05T09:00:00',
      });
      expect(n.durationMinutes, 90);
      expect(n.isLocked, false);
      expect(n.status, NodeStatus.pending);
      expect(n.vibeTags, isEmpty);
      expect(n.lat, isNull);
    });

    test('unknown status falls back to pending', () {
      final n = TripNode.fromJson({
        'node_id': 'n3',
        'venue_name': 'X',
        'scheduled_start': '2026-08-05T09:00:00',
        'status': 'bogus',
      });
      expect(n.status, NodeStatus.pending);
    });
  });

  group('TripEventResult.fromJson', () {
    test('parses updated nodes + routing tier + cache flag', () {
      final r = TripEventResult.fromJson({
        'message': 'Done. Heads up: XVA may be closed.',
        'updated_nodes': [
          {
            'node_id': 'n1',
            'venue_name': 'A',
            'scheduled_start': '2026-08-05T09:00:00',
          }
        ],
        'routing_tier_used': 'heavy',
        'from_cache': false,
        'reroutes_remaining': 4,
      });
      expect(r.updatedNodes, hasLength(1));
      expect(r.routingTier, 'heavy');
      expect(r.reroutesRemaining, 4);
    });
  });

  group('UserStatus.fromJson', () {
    test('parses tier + counters', () {
      final u = UserStatus.fromJson({
        'user_id': 'u1',
        'tier': 'free',
        'daily_reroutes_used': 2,
        'daily_reroutes_remaining': 3,
        'max_daily_reroutes': 5,
      });
      expect(u.tier, 'free');
      expect(u.used, 2);
      expect(u.remaining, 3);
      expect(u.max, 5);
    });
  });

  test('HomeSnapshot parses lightweight trips and cache provenance', () {
    final snapshot = HomeSnapshot.fromJson(
      {
        'supported_regions': ['dubai_uae'],
        'trips': [
          {
            'trip_id': 'trip-1',
            'geo_region': 'dubai_uae',
            'starts_at': '2026-10-04T09:00:00Z',
            'ends_at': '2026-10-04T18:00:00Z',
            'node_count': 5,
            'booking_count': 2,
            'updated_at': '2026-08-27T10:00:00Z',
          },
        ],
      },
      fromCache: true,
    );

    expect(snapshot.fromCache, isTrue);
    expect(snapshot.supportedRegions, ['dubai_uae']);
    expect(snapshot.trips.single.tripId, 'trip-1');
    expect(snapshot.trips.single.bookingCount, 2);
  });

  test('EventType wire values match backend contract', () {
    expect(EventType.swapActivity.wire, 'swap_activity');
    expect(EventType.askInfo.wire, 'ask_info');
    expect(EventType.weatherAlert.wire, 'weather_alert');
  });
}
