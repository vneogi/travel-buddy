// SPEC-57 slice 1: Arrival armor captain HUD.
//
// Pure helpers use the seed JSON embedded below (no rootBundle). Screen tests
// inject a parsed hub or override arrivalHubsProvider. No network.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/arrival_armor/arrival_armor_screen.dart';
import 'package:travel_buddy/features/arrival_armor/arrival_hubs.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

// Same content as mobile/assets/arrival_hubs.json (section 5 of the brief).
const _seedJson = '''
{
  "hubs": [
    {
      "id": "znz_airport",
      "label": "Zanzibar Airport (ZNZ)",
      "geo_regions": ["zanzibar_tanzania", "nungwi_tanzania"],
      "booking_types": ["flight"],
      "currency": "TZS",
      "fare_band_low": null,
      "fare_band_high": null,
      "hard_ceiling": null,
      "official_option": null,
      "scam_notes": [],
      "surveyed_on": null,
      "source": null
    },
    {
      "id": "stone_town_ferry",
      "label": "Stone Town ferry terminal",
      "geo_regions": ["zanzibar_tanzania", "nungwi_tanzania"],
      "booking_types": ["train"],
      "currency": "TZS",
      "fare_band_low": null,
      "fare_band_high": null,
      "hard_ceiling": null,
      "official_option": null,
      "scam_notes": [],
      "surveyed_on": null,
      "source": null
    }
  ]
}
''';

final _hubs = parseArrivalHubs(_seedJson);
ArrivalHub get _znz => _hubs.firstWhere((h) => h.id == 'znz_airport');

TripNode _node(
  String id, {
  required DateTime start,
  String nodeKind = 'booking',
  String? bookingType,
  String? geoRegion = 'zanzibar_tanzania',
  String? venueId,
  String? name,
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? 'Venue $id',
      venueId: venueId,
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: nodeKind == 'booking',
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: geoRegion,
      nodeKind: nodeKind,
      bookingType: bookingType,
    );

final _flightStart = DateTime.utc(2026, 12, 26, 10);
TripNode get _flight =>
    _node('flight-1', start: _flightStart, bookingType: 'flight', name: 'Arrival flight');

Widget _screenApp(ArrivalHub hub, {String? hotelRef}) => ProviderScope(
      child: MaterialApp(
        home: ArrivalArmorScreen(
          tripId: 't1',
          hubId: hub.id,
          hotelRef: hotelRef,
          hub: hub,
        ),
      ),
    );

Widget _routedApp(String location) {
  final router = GoRouter(
    initialLocation: location,
    routes: [
      GoRoute(
        path: '/trip/:tripId/arrival/:hubId',
        builder: (_, state) => ArrivalArmorScreen(
          tripId: state.pathParameters['tripId']!,
          hubId: state.pathParameters['hubId']!,
          hotelRef: state.uri.queryParameters['hotel'],
        ),
      ),
      GoRoute(
        path: '/trip/:tripId/card/:nodeId',
        builder: (_, state) =>
            Scaffold(body: Text('card ${state.pathParameters['nodeId']}')),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      arrivalHubsProvider.overrideWith((ref) async => parseArrivalHubs(_seedJson)),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

void main() {
  // -------------------------------------------------------------- helpers

  test('hubForBooking matches flight in zanzibar_tanzania to znz_airport', () {
    final hub = hubForBooking(
      geoRegion: 'zanzibar_tanzania',
      bookingType: 'flight',
      hubs: _hubs,
    );
    expect(hub?.id, 'znz_airport');
    expect(
      hubForBooking(geoRegion: 'nungwi_tanzania', bookingType: 'flight', hubs: _hubs)?.id,
      'znz_airport',
    );
    // The seed carries no money or scam data.
    for (final h in _hubs) {
      expect(h.fareBandLow, isNull);
      expect(h.fareBandHigh, isNull);
      expect(h.hardCeiling, isNull);
      expect(h.officialOption, isNull);
      expect(h.scamNotes, isEmpty);
      expect(h.surveyedOn, isNull);
      expect(h.source, isNull);
    }
  });

  test('hubForBooking returns null for hotel booking', () {
    expect(
      hubForBooking(geoRegion: 'zanzibar_tanzania', bookingType: 'hotel', hubs: _hubs),
      isNull,
    );
    expect(
      hubForBooking(geoRegion: 'zanzibar_tanzania', bookingType: null, hubs: _hubs),
      isNull,
    );
  });

  test('hubForBooking returns null for unknown region', () {
    expect(
      hubForBooking(geoRegion: 'vientiane_laos', bookingType: 'flight', hubs: _hubs),
      isNull,
    );
    expect(hubForBooking(geoRegion: null, bookingType: 'flight', hubs: _hubs), isNull);
  });

  test('nextHotelDestination picks earliest hotel on or after flight', () {
    final nodes = [
      _flight,
      _node('h-before', start: _flightStart.subtract(const Duration(days: 1)), bookingType: 'hotel'),
      _node('h-late', start: DateTime.utc(2026, 12, 28, 14), bookingType: 'hotel'),
      _node('h-nungwi',
          start: DateTime.utc(2026, 12, 26, 14),
          bookingType: 'hotel',
          geoRegion: 'nungwi_tanzania'),
      _node('h-stone',
          start: DateTime.utc(2026, 12, 26, 14),
          bookingType: 'hotel',
          venueId: 'stone-town-hotel'),
      _node('act', start: DateTime.utc(2026, 12, 26, 12), nodeKind: 'activity'),
    ];
    final hotel = nextHotelDestination(from: _flight, nodes: nodes);
    // Same start as h-nungwi; the flight's region wins the tie.
    expect(hotel?.nodeId, 'h-stone');

    // Without a region preference, ties break on nodeId.
    final noRegion = _node('f2', start: _flightStart, bookingType: 'flight', geoRegion: null);
    expect(nextHotelDestination(from: noRegion, nodes: nodes)?.nodeId, 'h-nungwi');

    // A hotel starting exactly at the flight start counts (on or after).
    final same = _node('h-same', start: _flightStart, bookingType: 'hotel');
    expect(nextHotelDestination(from: _flight, nodes: [...nodes, same])?.nodeId, 'h-same');
  });

  test('nextHotelDestination returns null when no hotel', () {
    expect(nextHotelDestination(from: _flight, nodes: [_flight]), isNull);
    final onlyEarlier = [
      _flight,
      _node('h-before', start: _flightStart.subtract(const Duration(hours: 1)), bookingType: 'hotel'),
      _node('tour', start: DateTime.utc(2026, 12, 27, 9), bookingType: 'tour'),
    ];
    expect(nextHotelDestination(from: _flight, nodes: onlyEarlier), isNull);
  });

  // --------------------------------------------------------------- screen

  testWidgets('screen omits fare and scam when asset fields are null', (tester) async {
    await tester.pumpWidget(_screenApp(_znz));
    expect(find.text('Arrival armor'), findsOneWidget);
    expect(find.text('Zanzibar Airport (ZNZ)'), findsOneWidget);
    expect(find.text('Fair fare guide'), findsNothing);
    expect(find.text('Official option'), findsNothing);
    expect(find.text(kArrivalFareCaption), findsNothing);
    expect(find.textContaining('Walk-away above'), findsNothing);
    expect(find.textContaining('Source:'), findsNothing);
    expect(find.text('Watch for'), findsNothing);
    expect(find.textContaining('TZS'), findsNothing);

    // Control: a hub with test-only values does render both blocks, so the
    // omission above is driven by the null seed fields, not by the layout.
    const control = ArrivalHub(
      id: 'test_hub',
      label: 'Test hub',
      currency: 'TZS',
      fareBandLow: 1,
      fareBandHigh: 2,
      hardCeiling: 3,
      officialOption: 'Test official option',
      scamNotes: ['Test note', '  '],
      surveyedOn: '2026-01-01',
      source: 'test fixture',
    );
    await tester.pumpWidget(_screenApp(control));
    expect(find.text('Fair fare guide'), findsOneWidget);
    expect(find.text('1 - 2 TZS'), findsOneWidget);
    expect(find.text('Walk-away above 3 TZS'), findsOneWidget);
    expect(find.text('Official option'), findsOneWidget);
    expect(find.text(kArrivalFareCaption), findsOneWidget);
    expect(find.text('Source: test fixture (2026-01-01)'), findsOneWidget);
    expect(find.text('Watch for'), findsOneWidget);
    expect(find.text('- Test note'), findsOneWidget);
    expect(find.text(kArrivalEmptyHub), findsNothing);
  });

  testWidgets('screen shows empty-hub calm line when no fare and no scam', (tester) async {
    await tester.pumpWidget(_screenApp(_znz));
    expect(find.text('No verified fare or tip sheet for this hub yet.'), findsOneWidget);
  });

  testWidgets('screen shows Open driver card when hotel query set', (tester) async {
    await tester.pumpWidget(_routedApp('/trip/t1/arrival/znz_airport?hotel=stone-town-hotel'));
    await tester.pumpAndSettle();
    expect(find.text('Zanzibar Airport (ZNZ)'), findsOneWidget);
    final button = find.byKey(const Key('arrival_open_driver_card'));
    expect(button, findsOneWidget);
    expect(find.text('Open driver card for hotel'), findsOneWidget);
    expect(tester.getSize(button).height, greaterThanOrEqualTo(48));

    await tester.tap(button);
    await tester.pumpAndSettle();
    expect(find.text('card stone-town-hotel'), findsOneWidget);
  });

  testWidgets('screen omits Open driver card when hotel query absent', (tester) async {
    await tester.pumpWidget(_routedApp('/trip/t1/arrival/znz_airport'));
    await tester.pumpAndSettle();
    expect(find.text('Zanzibar Airport (ZNZ)'), findsOneWidget);
    expect(find.byKey(const Key('arrival_open_driver_card')), findsNothing);
    expect(find.text('Open driver card for hotel'), findsNothing);
    expect(find.byType(FilledButton), findsNothing);

    await tester.pumpWidget(_routedApp('/trip/t1/arrival/znz_airport?hotel='));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('arrival_open_driver_card')), findsNothing);
  });

  // -------------------------------------------------------------- overflow

  testWidgets('overflow offers Arrival armor for matching flight only', (tester) async {
    final hotel = _node('h-stone',
        start: DateTime.utc(2026, 12, 26, 14), bookingType: 'hotel', venueId: 'stone-town-hotel');
    final nodes = [_flight, hotel];

    Widget cardApp(TripNode node) {
      final router = GoRouter(
        initialLocation: '/trip/t1',
        routes: [
          GoRoute(
            path: '/trip/:tripId',
            builder: (_, __) => Scaffold(
              body: SingleChildScrollView(
                child: ActivityCard(node: node, arrivalHubs: _hubs, tripNodes: nodes),
              ),
            ),
            routes: [
              GoRoute(
                path: 'arrival/:hubId',
                builder: (_, state) => Scaffold(
                  body: Text(
                    'arrival ${state.pathParameters['hubId']} '
                    'hotel ${state.uri.queryParameters['hotel']}',
                  ),
                ),
              ),
            ],
          ),
        ],
      );
      return MaterialApp.router(routerConfig: router);
    }

    // Flight in a mapped region: the item is offered and pushes the hub route.
    await tester.pumpWidget(cardApp(_flight));
    await tester.tap(find.byTooltip('More actions'));
    await tester.pumpAndSettle();
    expect(find.text('Arrival armor'), findsOneWidget);
    await tester.tap(find.text('Arrival armor'));
    await tester.pumpAndSettle();
    expect(find.text('arrival znz_airport hotel stone-town-hotel'), findsOneWidget);

    // Hotel booking: no Arrival armor, Driver card still offered.
    await tester.pumpWidget(cardApp(hotel));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('More actions'));
    await tester.pumpAndSettle();
    expect(find.text('Arrival armor'), findsNothing);
    expect(find.text('Driver card'), findsOneWidget);

    // Flight in an unmapped region: no Arrival armor.
    final laosFlight =
        _node('f-laos', start: _flightStart, bookingType: 'flight', geoRegion: 'vientiane_laos');
    await tester.pumpWidget(cardApp(laosFlight));
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('More actions'));
    await tester.pumpAndSettle();
    expect(find.text('Arrival armor'), findsNothing);
  });
}
