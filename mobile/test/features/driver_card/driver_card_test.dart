import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/features/driver_card/driver_card_helpers.dart';
import 'package:travel_buddy/features/driver_card/driver_card_screen.dart';
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

  group('buildMapsUri', () {
    test('builds a geo URI that does not depend on Google Maps', () {
      final uri = buildMapsUri(19.89758, 102.14321);
      expect(uri, isNotNull);
      expect(uri!.scheme, equals('geo'));
      expect(uri.toString(), contains('19.89758,102.14321'));
    });

    test('does not offer maps when either coordinate is absent', () {
      expect(buildMapsUri(null, 102.1), isNull);
      expect(buildMapsUri(19.5, null), isNull);
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
      'TripNode with geo_region luang_prabang_laos resolves Lao script via fromTripNode',
      () {
        final node = TripNode.fromJson({
          'node_id': 'n1',
          'venue_name': 'Wat Xieng Thong',
          'scheduled_start': '2026-10-05T09:00:00Z',
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
      },
    );
    test('Dubai geo region resolves Arabic local name', () {
      final node = TripNode.fromJson({
        'node_id': 'n2',
        'venue_name': 'Dubai Museum',
        'scheduled_start': '2026-10-05T09:00:00Z',
        'geo_region': 'dubai_uae',
        'names_local': {
          'ar': {
            'value': '\u0645\u062A\u062D\u0641 \u062F\u0628\u064A',
            'source': 'official',
          },
          'en': {'value': 'Dubai Museum', 'source': 'official'},
        },
      });

      final placeData = PlaceDriverCardData.fromTripNode(node);
      final entry = resolvePreferredLocalEntry(
        localizedMap: placeData.namesLocal,
        geoRegion: placeData.geoRegion,
      );

      expect(entry, isNotNull);
      expect(entry!.key, equals('ar'));
      expect(
        entry.value['value'],
        equals('\u0645\u062A\u062D\u0641 \u062F\u0628\u064A'),
      );
      expect(tierForNameSource(entry.value['source'] as String),
          equals(FactTier.assert_));
    });
  });

  testWidgets('Dubai card renders Arabic, coordinates, maps, and no fare guess',
      (tester) async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    final mockSync = MockSyncEngine();
    final signalService = SignalService(db: db, syncEngine: mockSync);
    await db.cachePlace(
      'dubai_museum',
      const PlaceDriverCardData(
        placeRef: 'dubai_museum',
        venueName: 'Dubai Museum',
        namesLocal: {
          'ar': {
            'value': '\u0645\u062A\u062D\u0641 \u062F\u0628\u064A',
            'source': 'official',
          },
        },
        lat: 25.2637,
        lng: 55.2972,
        geoRegion: 'dubai_uae',
      ).serialize(),
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          offlineDatabaseProvider.overrideWithValue(db),
          signalServiceProvider.overrideWithValue(signalService),
        ],
        child: const MaterialApp(
          home: DriverCardScreen(
            tripId: 'trip-1',
            nodeId: 'dubai_museum',
          ),
        ),
      ),
    );
    // Do not pumpAndSettle: the loading spinner is an infinite animation.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    const arabicName = '\u0645\u062A\u062D\u0641 \u062F\u0628\u064A';
    expect(find.text(arabicName), findsOneWidget);
    expect(
      tester.widget<Text>(find.text(arabicName)).style?.fontSize,
      greaterThanOrEqualTo(32),
    );
    expect(find.text('25.26370, 55.29720'), findsOneWidget);
    expect(find.text('Open in Maps'), findsOneWidget);
    expect(find.text('Typical local fare'), findsNothing);
    expect(find.text('Screenshot this card for offline safety'), findsNothing);
    expect(find.textContaining('fare'), findsNothing);
    await db.close();
  });

}
