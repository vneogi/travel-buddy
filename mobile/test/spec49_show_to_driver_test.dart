// SPEC-49 slice 1: Show-to-driver mode on the Driver Card.
//
// Real in-memory OfflineDatabase(testPath:) with sqflite FFI seeded via
// cachePlace. The card is pushed over a base route so system back can be
// observed. Test data strings are placeholders, not real local names.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/disclaimers.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/driver_card/driver_card_helpers.dart';
import 'package:travel_buddy/features/driver_card/driver_card_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/render/fact_view.dart';
import 'package:travel_buddy/services/signal_service.dart';

class _MockSignalService extends Mock implements SignalService {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

const _scope = 'account:spec49-test';
const _tripId = 'trip-s49';
const _placeRef = 'stone_town_stop';
const _venueName = 'Stone Town Stop';
const _localName = 'Local name sample';
const _localLandmark = 'Local landmark sample';
const _englishLandmark = 'Near the old fort';
const _travelAid = 'Venue information is an offline travel aid.';
int _dbCounter = 0;

const _enterKey = Key('show_to_driver_enter');
const _exitKey = Key('show_to_driver_exit');
const _exitLabel = 'Done -- return to card';

PlaceDriverCardData _place({
  bool localName = true,
  String nameSource = 'generated',
  bool localLandmark = true,
}) =>
    PlaceDriverCardData(
      placeRef: _placeRef,
      venueName: _venueName,
      namesLocal: localName
          ? {
              'sw': {'value': _localName, 'source': nameSource},
            }
          : null,
      nearestLandmark: _englishLandmark,
      landmarksLocal: localLandmark
          ? {
              'sw': {'value': _localLandmark, 'source': 'osm'},
            }
          : null,
      lat: -6.16194,
      lng: 39.18832,
      geoRegion: 'zanzibar_tanzania',
    );

_MockSignalService _signals() {
  final s = _MockSignalService();
  when(() => s.emitDriverCardShown(
        placeRef: any(named: 'placeRef'),
        wasOffline: any(named: 'wasOffline'),
        nameSource: any(named: 'nameSource'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});
  return s;
}

typedef _Harness = ({
  ProviderContainer container,
  OfflineDatabase db,
  GlobalKey<NavigatorState> nav,
});

/// Build inside tester.runAsync. [place] null leaves cache_place empty.
Future<_Harness> _buildHarness({PlaceDriverCardData? place}) async {
  _dbCounter++;
  final db = OfflineDatabase(
    testPath: 'file:spec49_std_$_dbCounter?mode=memory&cache=shared',
  );
  if (place != null) {
    await db.cachePlace(_placeRef, place.serialize(), identityScope: _scope);
  }
  final container = ProviderContainer(overrides: [
    offlineDatabaseProvider.overrideWithValue(db),
    identityCacheScopeProvider.overrideWithValue(_scope),
    signalServiceProvider.overrideWithValue(_signals()),
  ]);
  return (container: container, db: db, nav: GlobalKey<NavigatorState>());
}

Widget _app(_Harness h, {double textScale = 1.0}) => UncontrolledProviderScope(
      container: h.container,
      child: MaterialApp(
        navigatorKey: h.nav,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: const Scaffold(body: Center(child: Text('Base screen'))),
      ),
    );

/// Let FFI futures land, then pump. Polls until [until] matches.
Future<void> _flush(
  WidgetTester tester, {
  Finder? until,
  int maxRounds = 40,
}) async {
  for (var i = 0; i < maxRounds; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();
    if (until != null && tester.any(until)) return;
  }
  if (until != null) {
    expect(until, findsWidgets);
  }
}

/// Push a fresh DriverCardScreen and wait until it has loaded.
Future<void> _openCard(WidgetTester tester, _Harness h) async {
  unawaited(h.nav.currentState!.push(MaterialPageRoute<void>(
    builder: (_) => const DriverCardScreen(tripId: _tripId, nodeId: _placeRef),
  )));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await _flush(
    tester,
    until: find.byWidgetPredicate(
      (w) =>
          (w is OutlinedButton && w.key == _enterKey) ||
          (w is Text && w.data == 'Place not cached'),
    ),
  );
}

Future<void> _tapKey(WidgetTester tester, Key key) async {
  await tester.ensureVisible(find.byKey(key));
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(find.byKey(key));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 100));
}

Future<void> _teardown(WidgetTester tester, _Harness h) async {
  await tester.pumpWidget(const SizedBox());
  await _flush(tester, maxRounds: 2);
  h.container.dispose();
  await tester.runAsync(() => h.db.close());
}

void _expectNormalCard() {
  expect(find.byKey(_enterKey), findsOneWidget);
  expect(find.byKey(_exitKey), findsNothing);
  expect(find.text('Driver Card'), findsOneWidget);
  expect(find.text('Open in Maps'), findsOneWidget);
}

void _expectHandoff() {
  expect(find.byKey(_exitKey), findsOneWidget);
  expect(find.byKey(_enterKey), findsNothing);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  testWidgets(
    'enter control visible when place is cached',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);

      expect(find.byKey(_enterKey), findsOneWidget);
      expect(find.text('Show to driver'), findsOneWidget);
      expect(
        tester.widget<OutlinedButton>(find.byKey(_enterKey)).onPressed,
        isNotNull,
      );

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'enter control absent when place is not cached',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);

      expect(find.text('Place not cached'), findsOneWidget);
      expect(find.byKey(_enterKey), findsNothing);
      expect(find.text('Show to driver'), findsNothing);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'tapping Show to driver hides maps confirm and disclaimers',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      // Source "generated" is the ask tier, so FactView confirm/dismiss
      // are on the normal card.
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);

      expect(find.byType(FactView), findsOneWidget);
      expect(find.text('Open in Maps'), findsOneWidget);
      expect(find.text(_travelAid), findsOneWidget);

      await _tapKey(tester, _enterKey);
      _expectHandoff();
      expect(find.text('Open in Maps'), findsNothing);
      expect(find.byType(FactView), findsNothing);
      expect(find.text('-6.16194, 39.18832'), findsNothing);
      expect(find.text(_travelAid), findsNothing);
      expect(find.text(kFoodDisclaimerShort), findsNothing);
      expect(find.text('Driver Card'), findsNothing);
      expect(find.byType(AppBar), findsNothing);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'show-to-driver shows destination name at display size',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);
      await _tapKey(tester, _enterKey);

      final name = find.byKey(const Key('show_to_driver_name'));
      expect(name, findsOneWidget);
      expect(tester.widget<Text>(name).data, _localName);
      expect(
        tester.widget<Text>(name).style?.fontSize,
        greaterThanOrEqualTo(32),
      );
      expect(find.byKey(_exitKey), findsOneWidget);
      expect(find.text(_exitLabel), findsOneWidget);

      await _teardown(tester, h);

      // Without a usable local name the English venue name is shown.
      final h2 = await tester.runAsync(
        () => _buildHarness(place: _place(localName: false)),
      );
      if (h2 == null) fail('harness null');
      await tester.pumpWidget(_app(h2));
      await _openCard(tester, h2);
      await _tapKey(tester, _enterKey);
      expect(tester.widget<Text>(name).data, _venueName);
      expect(
        tester.widget<Text>(name).style?.fontSize,
        greaterThanOrEqualTo(32),
      );
      await _teardown(tester, h2);
    },
  );

  testWidgets(
    'landmark shown only when cached landmark exists',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      // With a resolved local landmark.
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);
      await _tapKey(tester, _enterKey);
      expect(find.text('Landmark'), findsOneWidget);
      expect(find.text(_localLandmark), findsOneWidget);
      // The English nearestLandmark is never shown in hand-off mode.
      expect(find.text(_englishLandmark), findsNothing);
      await _teardown(tester, h);

      // Without one: nothing in its place.
      final h2 = await tester.runAsync(
        () => _buildHarness(place: _place(localLandmark: false)),
      );
      if (h2 == null) fail('harness null');
      await tester.pumpWidget(_app(h2));
      await _openCard(tester, h2);
      // Normal card still shows nearestLandmark unchanged.
      expect(find.text(_englishLandmark), findsOneWidget);
      await _tapKey(tester, _enterKey);
      expect(find.text('Landmark'), findsNothing);
      expect(find.byKey(const Key('show_to_driver_landmark')), findsNothing);
      expect(find.text(_englishLandmark), findsNothing);
      expect(find.textContaining('not available'), findsNothing);
      await _teardown(tester, h2);
    },
  );

  testWidgets(
    'Done exit returns to the normal card',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);
      await _tapKey(tester, _enterKey);
      _expectHandoff();

      await _tapKey(tester, _exitKey);
      _expectNormalCard();

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'system back while in mode exits mode not the route',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);
      await _tapKey(tester, _enterKey);
      _expectHandoff();

      await tester.binding.handlePopRoute();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      _expectNormalCard();
      expect(find.text('Base screen'), findsNothing);

      // With the mode off, back pops the route normally.
      await tester.binding.handlePopRoute();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Base screen'), findsOneWidget);
      expect(find.text('Driver Card'), findsNothing);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'opening the screen always starts with mode off',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);
      _expectNormalCard();
      await _tapKey(tester, _enterKey);
      _expectHandoff();

      // Leave the route while the mode is on, then open a fresh screen.
      h.nav.currentState!.pop();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Base screen'), findsOneWidget);

      await _openCard(tester, h);
      _expectNormalCard();

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'works offline from cache only',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final db = _MockOfflineDatabase();
      final repo = _MockTripRepository();
      final api = _MockApiClient();
      when(() => db.getCachedPlace(
            _placeRef,
            identityScope: any(named: 'identityScope'),
          )).thenAnswer((_) async => _place().serialize());

      await tester.pumpWidget(ProviderScope(
        overrides: [
          offlineDatabaseProvider.overrideWithValue(db),
          identityCacheScopeProvider.overrideWithValue(_scope),
          signalServiceProvider.overrideWithValue(_signals()),
          tripRepoProvider.overrideWithValue(repo),
          apiClientProvider.overrideWithValue(api),
        ],
        child: const MaterialApp(
          home: DriverCardScreen(tripId: _tripId, nodeId: _placeRef),
        ),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.byKey(_enterKey), findsOneWidget);

      await _tapKey(tester, _enterKey);
      _expectHandoff();
      await _tapKey(tester, _exitKey);

      verify(() => db.getCachedPlace(_placeRef, identityScope: _scope))
          .called(1);
      verifyZeroInteractions(repo);
      verifyZeroInteractions(api);

      await tester.pumpWidget(const SizedBox.shrink());
    },
  );

  testWidgets(
    'no overflow at 360dp and 2.0 text scale',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h, textScale: 2.0));
      await _openCard(tester, h);

      // Mode off.
      expect(tester.takeException(), isNull);
      expect(find.byKey(_enterKey), findsOneWidget);

      // Mode on.
      await _tapKey(tester, _enterKey);
      expect(tester.takeException(), isNull);
      final name = find.byKey(const Key('show_to_driver_name'));
      expect(tester.getRect(name).right, lessThanOrEqualTo(360));
      expect(tester.widget<Text>(name).overflow, isNot(TextOverflow.ellipsis));
      expect(find.byKey(_exitKey).hitTestable(), findsOneWidget);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'enter and exit meet 44dp / 48dp min heights and button semantics',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final handle = tester.ensureSemantics();
      final h = await tester.runAsync(() => _buildHarness(place: _place()));
      if (h == null) fail('harness null');
      await tester.pumpWidget(_app(h));
      await _openCard(tester, h);

      expect(
        tester.getSize(find.byKey(_enterKey)).height,
        greaterThanOrEqualTo(44),
      );
      expect(
        tester.getSemantics(find.byKey(_enterKey)),
        containsSemantics(label: 'Show to driver', isButton: true),
      );

      await _tapKey(tester, _enterKey);
      expect(
        tester.getSize(find.byKey(_exitKey)).height,
        greaterThanOrEqualTo(48),
      );
      expect(
        tester.getSemantics(find.byKey(_exitKey)),
        containsSemantics(label: _exitLabel, isButton: true),
      );

      await _teardown(tester, h);
      handle.dispose();
    },
  );
}
