// SPEC-36: Flutter corridor proof and sabotage tests.
//
// Proof 12-20 + sabotage proofs.
// These are pure-Dart unit tests for model parsing, corridor grouping,
// and widget construction. They do not require a running server.
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';

void main() {
  // -- Helpers ---------------------------------------------------------------

  TripNode _node({
    required String name,
    required String geoRegion,
    required DateTime scheduledStart,
    int durationMinutes = 60,
  }) =>
      TripNode(
        nodeId: name,
        venueName: name,
        scheduledStart: scheduledStart,
        durationMinutes: durationMinutes,
        isLocked: false,
        status: 'pending',
        geoRegion: geoRegion,
        lat: 0,
        lng: 0,
      );

  TripSegment _seg(String region, String start, String end) => TripSegment(
        geoRegion: region,
        startsOn: start,
        endsOn: end,
      );

  // -- Proof 12: SupportedCorridor round-trips JSON --------------------------

  test('P12: SupportedCorridor.fromJson round-trips', () {
    final json = {
      'corridor_id': 'laos_northbound_v1',
      'display_name': 'Vientiane to Luang Prabang',
      'geo_regions': ['vientiane_laos', 'vang_vieng_laos', 'luang_prabang_laos'],
      'max_days': 7,
      'max_days_per_segment': 3,
    };
    final c = SupportedCorridor.fromJson(json);
    expect(c.corridorId, 'laos_northbound_v1');
    expect(c.geoRegions, hasLength(3));
    expect(c.maxDays, 7);
    final out = c.toJson();
    expect(out['corridor_id'], 'laos_northbound_v1');
  });

  // -- Proof 13: TripSegment round-trips JSON --------------------------------

  test('P13: TripSegment.fromJson round-trips', () {
    final json = {
      'geo_region': 'vientiane_laos',
      'starts_on': '2026-10-02',
      'ends_on': '2026-10-03',
    };
    final s = TripSegment.fromJson(json);
    expect(s.geoRegion, 'vientiane_laos');
    expect(s.startsOn, '2026-10-02');
    final out = s.toJson();
    expect(out['starts_on'], '2026-10-02');
  });

  // -- Proof 14: TripState parses corridor_id + segments ---------------------

  test('P14: TripState parses corridor_id and segments', () {
    final json = {
      'trip_id': 'test-trip-1',
      'user_id': 'u1',
      'nodes': <Map<String, dynamic>>[],
      'corridor_id': 'laos_northbound_v1',
      'segments': [
        {'geo_region': 'vientiane_laos', 'starts_on': '2026-10-02', 'ends_on': '2026-10-03'},
        {'geo_region': 'vang_vieng_laos', 'starts_on': '2026-10-04', 'ends_on': '2026-10-05'},
      ],
    };
    final ts = TripState.fromJson(json);
    expect(ts.corridorId, 'laos_northbound_v1');
    expect(ts.segments, hasLength(2));
    expect(ts.segments.first.geoRegion, 'vientiane_laos');
  });

  // -- Proof 15: corridor grouping preserves segment order -------------------

  test('P15: groupNodesByCorridor preserves segment order', () {
    final segments = [
      _seg('vientiane_laos', '2026-10-02', '2026-10-02'),
      _seg('vang_vieng_laos', '2026-10-03', '2026-10-03'),
      _seg('luang_prabang_laos', '2026-10-04', '2026-10-04'),
    ];
    final nodes = [
      _node(name: 'LP1', geoRegion: 'luang_prabang_laos',
            scheduledStart: DateTime.utc(2026, 10, 4, 2)),
      _node(name: 'VTE1', geoRegion: 'vientiane_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
      _node(name: 'VV1', geoRegion: 'vang_vieng_laos',
            scheduledStart: DateTime.utc(2026, 10, 3, 2)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: segments);
    expect(groups, hasLength(3));
    expect(groups[0].geoRegion, 'vientiane_laos');
    expect(groups[1].geoRegion, 'vang_vieng_laos');
    expect(groups[2].geoRegion, 'luang_prabang_laos');
    expect(groups[0].dayGroups.expand((dg) => dg.nodes).first.venueName, 'VTE1');
    expect(groups[2].dayGroups.expand((dg) => dg.nodes).first.venueName, 'LP1');
  });

  // -- Proof 16: unknown region nodes go to "Other stops" --------------------

  test('P16: unknown region nodes go to Other stops', () {
    final segments = [
      _seg('vientiane_laos', '2026-10-02', '2026-10-02'),
    ];
    final nodes = [
      _node(name: 'VTE1', geoRegion: 'vientiane_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
      _node(name: 'Mystery', geoRegion: 'unknown_region',
            scheduledStart: DateTime.utc(2026, 10, 2, 4)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: segments);
    expect(groups.last.displayName, 'Other stops');
    expect(groups.last.dayGroups.expand((dg) => dg.nodes).first.venueName,
        'Mystery');
  });

  // -- Proof 17: display names resolve correctly -----------------------------

  test('P17: display names are human-readable', () {
    final segments = [
      _seg('luang_prabang_laos', '2026-10-06', '2026-10-08'),
    ];
    final nodes = [
      _node(name: 'T1', geoRegion: 'luang_prabang_laos',
            scheduledStart: DateTime.utc(2026, 10, 6, 2)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: segments);
    expect(groups.first.displayName, 'Luang Prabang');
    expect(groups.first.dateRange, '2026-10-06 - 2026-10-08');
  });

  // -- Proof 18: HomeSnapshot parses supported_corridors ---------------------

  test('P18: HomeSnapshot parses supported_corridors', () {
    final json = {
      'supported_regions': ['dubai_uae'],
      'supported_corridors': [
        {
          'corridor_id': 'laos_northbound_v1',
          'display_name': 'Vientiane to Luang Prabang',
          'geo_regions': ['vientiane_laos', 'vang_vieng_laos', 'luang_prabang_laos'],
          'max_days': 7,
          'max_days_per_segment': 3,
        }
      ],
      'trips': <Map<String, dynamic>>[],
    };
    final snap = HomeSnapshot.fromJson(json);
    expect(snap.supportedCorridors, hasLength(1));
    expect(snap.supportedCorridors.first.corridorId, 'laos_northbound_v1');
  });

  // -- Proof 19: TripSummary parses corridor_id ------------------------------

  test('P19: TripSummary parses corridor_id', () {
    final json = {
      'trip_id': 't1',
      'geo_region': 'vientiane_laos',
      'node_count': 28,
      'booking_count': 0,
      'updated_at': '2026-10-02T00:00:00Z',
      'corridor_id': 'laos_northbound_v1',
    };
    final ts = TripSummary.fromJson(json);
    expect(ts.corridorId, 'laos_northbound_v1');
  });

  // -- Proof 20: FeaturedTrip parses corridor_id -----------------------------

  test('P20: FeaturedTrip parses corridor_id', () {
    final json = {
      'trip_id': 't1',
      'geo_region': 'vientiane_laos',
      'is_active': true,
      'corridor_id': 'laos_northbound_v1',
    };
    final ft = FeaturedTrip.fromJson(json);
    expect(ft.corridorId, 'laos_northbound_v1');
  });

  // -- Proof: isPast on CorridorCityGroup ------------------------------------

  test('CorridorCityGroup.isPast is true when all nodes ended', () {
    final pastNode = _node(
      name: 'Past',
      geoRegion: 'vientiane_laos',
      scheduledStart: DateTime.utc(2020, 1, 1, 9),
      durationMinutes: 60,
    );
    final group = CorridorCityGroup(
      geoRegion: 'vientiane_laos',
      displayName: 'Vientiane',
      dateRange: '2020-01-01 - 2020-01-01',
      dayGroups: groupNodesByCalendarDate([pastNode]),
    );
    expect(group.isPast(DateTime.now().toUtc()), isTrue);
  });

  test('CorridorCityGroup.isPast is false when a node is future', () {
    final futureNode = _node(
      name: 'Future',
      geoRegion: 'vientiane_laos',
      scheduledStart: DateTime.utc(2099, 1, 1, 9),
      durationMinutes: 60,
    );
    final group = CorridorCityGroup(
      geoRegion: 'vientiane_laos',
      displayName: 'Vientiane',
      dateRange: '2099-01-01 - 2099-01-01',
      dayGroups: groupNodesByCalendarDate([futureNode]),
    );
    expect(group.isPast(DateTime.now().toUtc()), isFalse);
  });

  // -- Backward compatibility: no segments -> single-city grouping -----------

  test('Single-city trip with empty segments: groupNodesByCorridor returns only Other', () {
    final nodes = [
      _node(name: 'A', geoRegion: 'dubai_uae',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
    ];
    final groups = groupNodesByCorridor(nodes: nodes, segments: []);
    expect(groups, hasLength(1));
    expect(groups.first.displayName, 'Other stops');
  });

  // -- Sabotage proof S5: date-only grouping loses city order ----------------

  test('S5: groupNodesByCalendarDate does NOT preserve city order', () {
    // This is the WRONG approach for corridors: date-only grouping
    // mixes cities. The corridor grouper separates by city FIRST.
    final nodes = [
      _node(name: 'LP', geoRegion: 'luang_prabang_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 2)),
      _node(name: 'VTE', geoRegion: 'vientiane_laos',
            scheduledStart: DateTime.utc(2026, 10, 2, 4)),
    ];
    // Date-only: both land in same day group (no city separation)
    final dayGroups = groupNodesByCalendarDate(nodes);
    expect(dayGroups, hasLength(1)); // Same day -> merged
    expect(dayGroups.first.nodes, hasLength(2)); // Both mixed together
  });

  // -- Sabotage proof S7: repository must NOT send both start_date and segments

  test('S7: TripSegment.toJson shape does not include start_date', () {
    final seg = TripSegment(
      geoRegion: 'vientiane_laos',
      startsOn: '2026-10-02',
      endsOn: '2026-10-03',
    );
    final json = seg.toJson();
    expect(json.containsKey('start_date'), isFalse);
    expect(json.containsKey('geo_region'), isTrue);
    expect(json.containsKey('starts_on'), isTrue);
    expect(json.containsKey('ends_on'), isTrue);
  });
}
