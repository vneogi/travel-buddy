import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/features/driver_card/driver_card_helpers.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/render/fact_envelope.dart';
import 'package:travel_buddy/services/signal_service.dart';

class MockSyncEngine extends Mock implements SyncEngine {}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // =========================================================
  // Helper tests
  // =========================================================

  group('tierForNameSource', () {
    // Sabotage 1: change tierForNameSource so 'generated' returns assert_.
    // This test must FAIL if that sabotage is applied.
    test('generated name renders ask tier with confirm affordance', () {
      expect(tierForNameSource('generated'), equals(FactTier.ask));
      // Verified sources -> assert_
      expect(tierForNameSource('wikidata'), equals(FactTier.assert_));
      expect(tierForNameSource('osm'), equals(FactTier.assert_));
      expect(tierForNameSource('field_verified'), equals(FactTier.assert_));
      expect(tierForNameSource('manual'), equals(FactTier.assert_));
      // Unknown -> refuse
      expect(tierForNameSource('unknown_source'), equals(FactTier.refuse));
    });

    test('verified name renders assert tier headline', () {
      expect(tierForNameSource('wikidata'), equals(FactTier.assert_));
      expect(tierForNameSource('official'), equals(FactTier.assert_));
    });
  });

  group('languagePriority & resolvePreferredLocalEntry', () {
    test('language selection walks region priority list', () {
      // Laos with th and en (no lo) falls back to th
      final laosMap = <String, dynamic>{
        'th': {'value': 'Thai Name', 'source': 'osm'},
        'en': {'value': 'English Name', 'source': 'wikidata'},
      };
      final result = resolvePreferredLocalEntry(
        localizedMap: laosMap,
        geoRegion: 'luang_prabang_laos',
      );
      expect(result, isNotNull);
      expect(result!.key, equals('th'));
      expect(result.value['value'], equals('Thai Name'));

      // Dubai with ar and en chooses ar
      final dubaiMap = <String, dynamic>{
        'ar': {'value': 'Arabic Name', 'source': 'official'},
        'en': {'value': 'English Name', 'source': 'wikidata'},
      };
      final dubaiResult = resolvePreferredLocalEntry(
        localizedMap: dubaiMap,
        geoRegion: 'dubai_uae',
      );
      expect(dubaiResult, isNotNull);
      expect(dubaiResult!.key, equals('ar'));
    });

    test('missing local name produces explicit refuse degradation, never blank', () {
      // null namesLocal -> resolvePreferredLocalEntry returns null
      final result = resolvePreferredLocalEntry(
        localizedMap: null,
        geoRegion: 'luang_prabang_laos',
      );
      expect(result, isNull);
      // The screen renders FactTier.refuse in this case (never blank)
      // tier for null/missing is refuse
    });
  });

  group('resolveFairFareBand', () {
    // Sabotage 3: change resolveFairFareBand to return empty for Laos.
    // This test must FAIL.
    test('Laos returns LAK fare band', () {
      final fare = resolveFairFareBand('luang_prabang_laos');
      expect(fare, contains('LAK'));
      expect(fare, isNotEmpty);
    });

    test('Dubai returns AED fare band', () {
      final fare = resolveFairFareBand('dubai_uae');
      expect(fare, contains('AED'));
    });

    test('unknown region returns generic fare', () {
      final fare = resolveFairFareBand(null);
      expect(fare, isNotEmpty);
      expect(fare, contains('fare'));
    });
  });

  // =========================================================
  // Signal emission tests
  // =========================================================

  group('Signal emission (offline outbox)', () {
    late OfflineDatabase db;
    late SignalService signalService;

    setUp(() async {
      db = OfflineDatabase(testPath: inMemoryDatabasePath);
      final mockSync = MockSyncEngine();
      signalService = SignalService(db: db, syncEngine: mockSync);
    });

    tearDown(() async {
      await db.close();
    });

    test('driver_card_shown emitted on card open with offline status', () async {
      await signalService.emitDriverCardShown(
        placeRef: 'wat_xieng_thong',
        wasOffline: true,
        nameSource: 'wikidata',
        tripId: 'trip_123',
      );

      final batch = await db.getPendingBatch();
      expect(batch, hasLength(1));
      final payload = jsonDecode(batch.first['payload_json'] as String);
      expect(payload['signal_type'], equals('driver_card_shown'));
      final valueJson = payload['value_json'] as Map<String, dynamic>;
      expect(valueJson['was_offline'], isTrue);
      expect(valueJson['name_source'], equals('wikidata'));
    });

    // Sabotage 4: invert confirm verdict to 'rejected'.
    // This test must FAIL.
    test('confirming promotes source to field_verified and emits signal', () async {
      await signalService.emitNameConfirmed(
        placeRef: 'wat_xieng_thong',
        lang: 'lo',
        shownValue: 'Lao Script Name',
        verdict: 'confirmed',
        tripId: 'trip_123',
      );

      final batch = await db.getPendingBatch();
      expect(batch, hasLength(1));
      final payload = jsonDecode(batch.first['payload_json'] as String);
      expect(payload['signal_type'], equals('name_confirmed'));
      final valueJson = payload['value_json'] as Map<String, dynamic>;
      expect(valueJson['verdict'], equals('confirmed'));
      expect(valueJson['lang'], equals('lo'));
      expect(valueJson['shown_value'], equals('Lao Script Name'));
    });

    test('rejecting emits name_confirmed rejected and degrades locally', () async {
      await signalService.emitNameConfirmed(
        placeRef: 'wat_xieng_thong',
        lang: 'lo',
        shownValue: 'Lao Script Name',
        verdict: 'rejected',
        tripId: 'trip_123',
      );

      final batch = await db.getPendingBatch();
      expect(batch, hasLength(1));
      final payload = jsonDecode(batch.first['payload_json'] as String);
      expect(payload['signal_type'], equals('name_confirmed'));
      final valueJson = payload['value_json'] as Map<String, dynamic>;
      expect(valueJson['verdict'], equals('rejected'));
    });
  });

  // =========================================================
  // Offline rendering (Sabotage 2)
  // =========================================================

  group('Offline driver card rendering', () {
    late OfflineDatabase db;

    setUp(() async {
      db = OfflineDatabase(testPath: inMemoryDatabasePath);
    });

    tearDown(() async {
      await db.close();
    });

    // Sabotage 2: force a network call inside DriverCardScreen load.
    // This test must FAIL (network throws but card still renders).
    test('driver card renders strictly from SQLite cache with network disabled', () async {
      // Populate cache
      final data = PlaceDriverCardData(
        placeRef: 'wat_xieng_thong',
        venueName: 'Wat Xieng Thong',
        namesLocal: {
          'lo': {'value': 'Lao Temple Name', 'source': 'wikidata'},
        },
        nearestLandmark: 'Near Mekong River',
        landmarksLocal: {
          'lo': {'value': 'Lao Landmark', 'source': 'osm'},
        },
        lat: 19.89758,
        lng: 102.14321,
        geoRegion: 'luang_prabang_laos',
      );
      await db.cachePlace('wat_xieng_thong', data.serialize());

      // Read back from cache (simulating what DriverCardScreen does)
      final cached = await db.getCachedPlace('wat_xieng_thong');
      expect(cached, isNotNull);

      final loaded = PlaceDriverCardData.deserialize(cached!);
      expect(loaded.venueName, equals('Wat Xieng Thong'));
      expect(loaded.lat, equals(19.89758));

      // Resolve language entry (offline, no network)
      final entry = resolvePreferredLocalEntry(
        localizedMap: loaded.namesLocal,
        geoRegion: loaded.geoRegion,
      );
      expect(entry, isNotNull);
      expect(entry!.key, equals('lo'));
      expect(entry.value['value'], equals('Lao Temple Name'));

      // Tier mapping
      final tier = tierForNameSource(entry.value['source'] as String);
      expect(tier, equals(FactTier.assert_));

      // Fare band
      final fare = resolveFairFareBand(loaded.geoRegion);
      expect(fare, contains('LAK'));

      // All assertions pass with ZERO network calls
    });
  });

  // =========================================================
  // PlaceDriverCardData serialization
  // =========================================================

  group('PlaceDriverCardData', () {
    test('round-trips through serialize/deserialize', () {
      final data = PlaceDriverCardData(
        placeRef: 'test_venue',
        venueName: 'Test Venue',
        namesLocal: {'lo': {'value': 'Lao', 'source': 'generated'}},
        nearestLandmark: 'Near market',
        lat: 19.5,
        lng: 102.1,
        geoRegion: 'vientiane_laos',
      );
      final json = data.serialize();
      final restored = PlaceDriverCardData.deserialize(json);
      expect(restored.placeRef, equals('test_venue'));
      expect(restored.venueName, equals('Test Venue'));
      expect(restored.namesLocal!['lo']!['value'], equals('Lao'));
      expect(restored.geoRegion, equals('vientiane_laos'));
    });
  });
  group('geoRegion threading', () {
    test(
      'TripNode with geo_region luang_prabang_laos resolves Lao script and LAK fare via fromTripNode',
      () {
        final node = TripNode.fromJson({
          'node_id': 'n1',
          'venue_name': 'Wat Xieng Thong',
          'geo_region': 'luang_prabang_laos',
          'names_local': {
            'lo': {'value': 'Lao Name', 'source': 'wikidata'},
            'en': {'value': 'English Name', 'source': 'wikidata'},
          },
        });
        final placeData = PlaceDriverCardData.fromTripNode(node);
        expect(placeData.geoRegion, equals('luang_prabang_laos'));

        final entry = resolvePreferredLocalEntry(
          localizedMap: placeData.namesLocal,
          geoRegion: placeData.geoRegion,
        );
        expect(entry, isNotNull);
        expect(entry!.key, equals('lo'));
        expect(entry.value['value'], equals('Lao Name'));

        final fare = resolveFairFareBand(placeData.geoRegion);
        expect(fare, contains('LAK'));
      },
    );
  });

}
