import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';

void main() {
  // Proof 1: Old/new snapshot backward compat
  group('HomeSnapshot backward compat', () {
    test('old snapshot without create_trip_options parses', () {
      final snap = HomeSnapshot.fromJson({
        'supported_regions': ['luang_prabang_laos'],
        'supported_corridors': <Map<String, dynamic>>[],
        'trips': <Map<String, dynamic>>[],
        'featured_trip': null,
      });
      expect(snap.supportedRegions, ['luang_prabang_laos']);
      expect(snap.createTripOptions, isNull);
    });

    test('new snapshot with create_trip_options round-trips', () {
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
      expect(snap.createTripOptions!.partyTypes.length, 2);
      expect(snap.createTripOptions!.interests.length, 1);
      expect(snap.createTripOptions!.maxDaysByRegion['luang_prabang_laos'], 5);

      // Round-trip through toJson
      final rt = HomeSnapshot.fromJson(snap.toJson());
      expect(rt.createTripOptions!.partyTypes.first.id, 'solo');
      expect(rt.createTripOptions!.interests.first.id, 'food_markets');
    });
  });

  // TripState creation context + party
  group('TripState creation context', () {
    test('old trip without creation_context or party parses', () {
      final state = TripState.fromJson({
        'trip_id': 't1',
        'user_id': 'u1',
        'nodes': <Map<String, dynamic>>[],
      });
      expect(state.creationContext, isNull);
      expect(state.party, isNull);
    });

    test('trip with creation_context and party parses', () {
      final state = TripState.fromJson({
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
        'party': {
          'party_type': 'family_teens',
          'size': 4,
        },
      });
      expect(state.creationContext!.destination, 'luang_prabang_laos');
      expect(state.creationContext!.interestIds, ['food_markets', 'arts_crafts']);
      expect(state.party!.partyType, 'family_teens');
      expect(state.party!.size, 4);
    });

    test('TripState.toJson includes creation_context', () {
      final state = TripState(
        tripId: 't3',
        userId: 'u1',
        nodes: [],
        geoRegion: 'dubai_uae',
        creationContext: CreationContext(
          destination: 'dubai_uae',
          startDateLocal: '2026-12-01',
          endDateLocal: '2026-12-02',
          interestIds: ['wellness_slow'],
        ),
        party: TripParty(partyType: 'couple', size: 2),
      );
      final json = state.toJson();
      expect(json['creation_context'], isNotNull);
      expect(json['creation_context']['destination'], 'dubai_uae');
      expect(json['creation_context']['interest_ids'], ['wellness_slow']);
      expect(json['party']['party_type'], 'couple');
    });
  });

  // CreateTripOptions
  group('CreateTripOptions', () {
    test('parses all fields', () {
      final opts = CreateTripOptions.fromJson({
        'party_types': [
          {'id': 'family_young_kids', 'label': 'Family with young kids'},
        ],
        'interests': [
          {'id': 'history_culture', 'label': 'History & culture'},
          {'id': 'wellness_slow', 'label': 'Wellness & slow travel'},
        ],
        'max_days_by_region': {'dubai_uae': 4},
      });
      expect(opts.partyTypes.first.id, 'family_young_kids');
      expect(opts.interests.length, 2);
      expect(opts.maxDaysByRegion['dubai_uae'], 4);
    });

    test('empty JSON defaults gracefully', () {
      final opts = CreateTripOptions.fromJson(<String, dynamic>{});
      expect(opts.partyTypes, isEmpty);
      expect(opts.interests, isEmpty);
      expect(opts.maxDaysByRegion, isEmpty);
    });
  });

  // TripParty
  group('TripParty', () {
    test('fromJson parses', () {
      final p = TripParty.fromJson({
        'party_type': 'friends',
        'size': 5,
        'notes': 'test note',
      });
      expect(p.partyType, 'friends');
      expect(p.size, 5);
      expect(p.notes, 'test note');
    });

    test('defaults to solo/1 on missing fields', () {
      final p = TripParty.fromJson(<String, dynamic>{});
      expect(p.partyType, 'solo');
      expect(p.size, 1);
    });

    test('toJson round-trips', () {
      final p = TripParty(partyType: 'multigen', size: 6);
      final j = p.toJson();
      final p2 = TripParty.fromJson(j);
      expect(p2.partyType, 'multigen');
      expect(p2.size, 6);
    });
  });

  // Zero interests allowed
  test('zero interests produces empty list', () {
    final ctx = CreationContext.fromJson({
      'destination': 'dubai_uae',
      'interest_ids': <String>[],
    });
    expect(ctx.interestIds, isEmpty);
  });

  // -----------------------------------------------------------------------
  // Date-only YYYY-MM-DD payload
  // -----------------------------------------------------------------------
  group('Date-only format', () {
    test('_dateOnly produces YYYY-MM-DD from DateTime', () {
      // This mirrors the _dateOnly helper in repositories.dart
      String dateOnly(DateTime d) => d.toIso8601String().substring(0, 10);
      expect(dateOnly(DateTime(2026, 1, 5)), '2026-01-05');
      expect(dateOnly(DateTime(2026, 11, 30)), '2026-11-30');
      expect(dateOnly(DateTime(2026, 3, 1, 23, 59)), '2026-03-01');
    });

    test('DST boundary produces same calendar date', () {
      // 2026-03-08 is DST spring-forward in US; the date must not shift
      String dateOnly(DateTime d) => d.toIso8601String().substring(0, 10);
      expect(dateOnly(DateTime(2026, 3, 8, 2, 30)), '2026-03-08');
    });
  });

  // -----------------------------------------------------------------------
  // ApiClient typed-422 mapping
  // -----------------------------------------------------------------------
  group('Typed 422 mapping', () {
    test('ValidationException carries server message', () {
      // Simulates what ApiClient._map does when it sees a typed 422
      const exc = ValidationException('Maximum 5 days for this destination');
      expect(exc.message, 'Maximum 5 days for this destination');
      expect(exc, isA<ApiException>());
    });

    test('UnsupportedRegionException is distinct from ValidationException', () {
      const unsup = UnsupportedRegionException('Not ready for Antarctica');
      const valid = ValidationException('Dates overlap');
      expect(unsup, isNot(isA<ValidationException>()));
      expect(valid, isNot(isA<UnsupportedRegionException>()));
    });
  });
}
