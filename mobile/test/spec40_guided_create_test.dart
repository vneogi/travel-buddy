import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';

/// SPEC-40 Flutter model/contract tests.
///
/// Wizard widget tests require ProviderScope + mock HTTP and are in a
/// separate widget test file. These unit tests prove parsing, backward
/// compat, and payload shape.
void main() {
  // ---------------------------------------------------------------
  // Proof 1: Old and new Home snapshots parse
  // ---------------------------------------------------------------
  group('HomeSnapshot backward compat', () {
    test('old snapshot without create_trip_options parses', () {
      final json = {
        'supported_regions': ['luang_prabang_laos'],
        'supported_corridors': <Map<String, dynamic>>[],
        'trips': <Map<String, dynamic>>[],
        'featured_trip': null,
      };
      final snap = HomeSnapshot.fromJson(json);
      expect(snap.supportedRegions, ['luang_prabang_laos']);
      expect(snap.createTripOptions, isNull);
    });

    test('new snapshot with create_trip_options parses', () {
      final json = {
        'supported_regions': ['luang_prabang_laos'],
        'supported_corridors': <Map<String, dynamic>>[],
        'trips': <Map<String, dynamic>>[],
        'featured_trip': null,
        'create_trip_options': {
          'party_types': [
            {'id': 'solo', 'label': 'Solo'},
            {'id': 'friends', 'label': 'Friends'},
          ],
          'interests': [
            {'id': 'food_markets', 'label': 'Food & markets'},
          ],
          'max_days_by_region': {'luang_prabang_laos': 5},
        },
      };
      final snap = HomeSnapshot.fromJson(json);
      expect(snap.createTripOptions, isNotNull);
      expect(snap.createTripOptions!.partyTypes.length, 2);
      expect(snap.createTripOptions!.interests.length, 1);
      expect(snap.createTripOptions!.maxDaysByRegion['luang_prabang_laos'], 5);
    });

    test('cached JSON round-trips with options', () {
      final json = {
        'supported_regions': ['dubai_uae'],
        'supported_corridors': <Map<String, dynamic>>[],
        'trips': <Map<String, dynamic>>[],
        'featured_trip': null,
        'create_trip_options': {
          'party_types': [
            {'id': 'solo', 'label': 'Solo'},
          ],
          'interests': [
            {'id': 'nature_scenery', 'label': 'Nature & scenery'},
          ],
          'max_days_by_region': {'dubai_uae': 4},
        },
      };
      final snap = HomeSnapshot.fromJson(json);
      final rt = snap.toJson();
      final snap2 = HomeSnapshot.fromJson(rt);
      expect(snap2.createTripOptions!.partyTypes.first.id, 'solo');
      expect(snap2.createTripOptions!.interests.first.id, 'nature_scenery');
      expect(snap2.createTripOptions!.maxDaysByRegion['dubai_uae'], 4);
    });
  });

  // ---------------------------------------------------------------
  // Proof 2: TripState creation context parses
  // ---------------------------------------------------------------
  group('TripState creation context', () {
    test('TripState without creation_context parses (old trips)', () {
      final json = {
        'trip_id': 't1',
        'user_id': 'u1',
        'nodes': <Map<String, dynamic>>[],
      };
      final state = TripState.fromJson(json);
      expect(state.creationContext, isNull);
    });

    test('TripState with creation_context parses', () {
      final json = {
        'trip_id': 't2',
        'user_id': 'u1',
        'geo_region': 'luang_prabang_laos',
        'nodes': <Map<String, dynamic>>[],
        'creation_context': {
          'destination': 'luang_prabang_laos',
          'start_date_local': '2026-10-06',
          'end_date_local': '2026-10-09',
          'interest_ids': ['food_markets', 'arts_crafts'],
        },
      };
      final state = TripState.fromJson(json);
      expect(state.creationContext, isNotNull);
      expect(state.creationContext!.destination, 'luang_prabang_laos');
      expect(state.creationContext!.startDateLocal, '2026-10-06');
      expect(state.creationContext!.endDateLocal, '2026-10-09');
      expect(state.creationContext!.interestIds, ['food_markets', 'arts_crafts']);
    });
  });

  // ---------------------------------------------------------------
  // Proof 3: CreateTripOptions model
  // ---------------------------------------------------------------
  group('CreateTripOptions', () {
    test('parses party types', () {
      final json = {
        'party_types': [
          {'id': 'family_young_kids', 'label': 'Family with young kids'},
        ],
        'interests': <Map<String, dynamic>>[],
        'max_days_by_region': <String, dynamic>{},
      };
      final opts = CreateTripOptions.fromJson(json);
      expect(opts.partyTypes.first.id, 'family_young_kids');
      expect(opts.partyTypes.first.label, 'Family with young kids');
    });

    test('parses interests', () {
      final json = {
        'party_types': <Map<String, dynamic>>[],
        'interests': [
          {'id': 'history_culture', 'label': 'History & culture'},
          {'id': 'wellness_slow', 'label': 'Wellness & slow travel'},
        ],
        'max_days_by_region': <String, dynamic>{},
      };
      final opts = CreateTripOptions.fromJson(json);
      expect(opts.interests.length, 2);
      expect(opts.interests[1].id, 'wellness_slow');
    });

    test('empty JSON defaults gracefully', () {
      final opts = CreateTripOptions.fromJson(<String, dynamic>{});
      expect(opts.partyTypes, isEmpty);
      expect(opts.interests, isEmpty);
      expect(opts.maxDaysByRegion, isEmpty);
    });
  });

  // ---------------------------------------------------------------
  // Proof 4: CreationContext model
  // ---------------------------------------------------------------
  group('CreationContext', () {
    test('parses full context', () {
      final ctx = CreationContext.fromJson({
        'destination': 'vang_vieng_laos',
        'start_date_local': '2026-11-01',
        'end_date_local': '2026-11-03',
        'interest_ids': ['adventure_outdoors'],
      });
      expect(ctx.destination, 'vang_vieng_laos');
      expect(ctx.interestIds, ['adventure_outdoors']);
    });

    test('handles missing fields', () {
      final ctx = CreationContext.fromJson(<String, dynamic>{});
      expect(ctx.destination, isNull);
      expect(ctx.interestIds, isEmpty);
    });
  });

  // ---------------------------------------------------------------
  // Proof 5: Zero interests is allowed
  // ---------------------------------------------------------------
  test('zero interests produces empty list', () {
    final ctx = CreationContext.fromJson({
      'destination': 'dubai_uae',
      'start_date_local': '2026-12-01',
      'end_date_local': '2026-12-02',
      'interest_ids': <String>[],
    });
    expect(ctx.interestIds, isEmpty);
  });

  // ---------------------------------------------------------------
  // Proof 6: Snapshot toJson round-trip preserves structure
  // ---------------------------------------------------------------
  test('HomeSnapshot toJson round-trip preserves supported_regions', () {
    final snap = HomeSnapshot(
      supportedRegions: ['luang_prabang_laos', 'dubai_uae'],
      trips: [],
    );
    final json = snap.toJson();
    final restored = HomeSnapshot.fromJson(json);
    expect(restored.supportedRegions, snap.supportedRegions);
  });
}
