// SPEC-45 operational place details: sourced node fields and actions on
// ActivityDetailScreen. Written without a local Flutter SDK; CI is the first
// compile and run.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/activity_detail/activity_detail_screen.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';

TripNode _activity({
  String id = 'a',
  String name = 'Joma Bakery',
  String? micro = 'nam_phou_fountain',
  String? hours = '07:00-21:00',
  String? slot = 'lunch',
  String? window,
  int minutes = 75,
  String? landmark = 'Opposite the night market',
  List<String> vibes = const ['local', 'coffee'],
  NodeStatus status = NodeStatus.pending,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      venueId: '$id-ref',
      scheduledStart: DateTime(2026, 10, 5, 9),
      durationMinutes: minutes,
      isLocked: false,
      status: status,
      vibeTags: vibes,
      microLocation: micro,
      openingHours: hours,
      slotName: slot,
      timeWindow: window,
      nearestLandmark: landmark,
      geoRegion: 'luang_prabang_laos',
      lat: 19.89,
      lng: 102.13,
    );

TripNode _booking() => TripNode(
      nodeId: 'bk1',
      nodeKind: 'booking',
      bookingType: 'flight',
      venueName: 'LPQ to VTE',
      scheduledStart: DateTime(2026, 10, 6, 14),
      durationMinutes: 60,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

Widget _wrap(Widget child) => MaterialApp(home: child);

void _tallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(1200, 2400);
  tester.view.devicePixelRatio = 2.0;
  addTearDown(tester.view.reset);
}

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockSignalService extends Mock implements SignalService {}

void main() {
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  testWidgets('1. a catalog activity shows each sourced field, no slug', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_wrap(ActivityDetailScreen(node: _activity())));
    expect(find.text('Nam Phou Fountain area'), findsOneWidget);
    expect(find.text('Lunch'), findsOneWidget);
    expect(find.text('75 min'), findsOneWidget);
    expect(find.text('Hours: 07:00-21:00'), findsOneWidget);
    expect(find.text('Landmark: Opposite the night market'), findsOneWidget);
    expect(find.text('local'), findsOneWidget);
    expect(find.text('coffee'), findsOneWidget);
    expect(find.text('nam_phou_fountain'), findsNothing);
    expect(find.textContaining('[BOOKING:'), findsNothing);
    expect(find.text('lunch'), findsNothing);
  });

  testWidgets('2. missing neighbourhood, hours and landmark rows are absent', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_wrap(ActivityDetailScreen(
      node: _activity(micro: null, hours: null, landmark: null),
    )));
    expect(find.byKey(const Key('detail_neighbourhood')), findsNothing);
    expect(find.byKey(const Key('detail_hours')), findsNothing);
    expect(find.byKey(const Key('detail_landmark')), findsNothing);
    expect(find.textContaining('unknown'), findsNothing);
    expect(find.textContaining('Unknown'), findsNothing);
    expect(find.byKey(const Key('detail_dwell')), findsOneWidget);
  });

  testWidgets('3. a window node shows the window label, not a clock time', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_wrap(ActivityDetailScreen(
      node: _activity(slot: 'morning_tour', window: 'morning', minutes: 300),
    )));
    expect(tester.widget<Text>(find.byKey(const Key('detail_slot'))).data, 'Morning');
    expect(find.text('09:00'), findsNothing);
    expect(find.text('morning_tour'), findsNothing);

    await tester.pumpWidget(_wrap(ActivityDetailScreen(
      node: _activity(slot: 'morning_tour', window: 'whole_day', minutes: 480),
    )));
    expect(tester.widget<Text>(find.byKey(const Key('detail_slot'))).data, 'Whole day');
  });

  testWidgets('4. Open in Maps is present and wired', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_wrap(ActivityDetailScreen(node: _activity())));
    final maps = find.byKey(const Key('detail_open_maps'));
    expect(maps, findsOneWidget);
    expect(tester.widget<ButtonStyleButton>(maps).onPressed, isNotNull);
    expect(tester.getSize(maps).height, greaterThanOrEqualTo(44));
  });

  testWidgets('5. Driver card pushes the overflow path with the route trip id',
      (tester) async {
    _tallSurface(tester);
    final node = _activity();
    final router = GoRouter(
      initialLocation: '/trip/trip-9',
      routes: [
        // Mirrors production: the itinerary lives in a ShellRoute and pushes
        // the details screen through a MaterialPageRoute.
        ShellRoute(
          builder: (_, __, child) => Scaffold(body: child),
          routes: [
            GoRoute(
              path: '/trip/:tripId',
              builder: (_, __) => Builder(
                builder: (context) => TextButton(
                  onPressed: () => Navigator.of(context).push(
                    MaterialPageRoute<void>(builder: (_) => ActivityDetailScreen(node: node)),
                  ),
                  child: const Text('open details'),
                ),
              ),
            ),
          ],
        ),
        GoRoute(
          path: '/trip/:tripId/card/:nodeId',
          builder: (_, state) => Scaffold(
            body: Text(
              'card:${state.pathParameters['tripId']}:${state.pathParameters['nodeId']}',
            ),
          ),
        ),
      ],
    );
    addTearDown(router.dispose);
    await tester.pumpWidget(MaterialApp.router(routerConfig: router));
    await tester.pumpAndSettle();
    await tester.tap(find.text('open details'));
    await tester.pumpAndSettle();
    expect(find.byType(ActivityDetailScreen), findsOneWidget);

    await tester.tap(find.byKey(const Key('detail_driver_card')));
    await tester.pumpAndSettle();
    expect(find.text('card:trip-9:a-ref'), findsOneWidget);
  });

  testWidgets('6. Love invokes the parent callback once', (tester) async {
    _tallSurface(tester);
    var loves = 0;
    await tester.pumpWidget(_wrap(ActivityDetailScreen(
      node: _activity(),
      onLoved: () => loves++,
    )));
    final love = find.byKey(const Key('detail_love'));
    expect(love, findsOneWidget);
    expect(find.byIcon(Icons.favorite_border), findsOneWidget);

    await tester.tap(love);
    await tester.pumpAndSettle();
    expect(loves, 1);
    expect(find.byIcon(Icons.favorite), findsOneWidget);

    await tester.tap(love);
    await tester.pumpAndSettle();
    expect(loves, 1);
  });

  testWidgets('7. a locked booking keeps Maps and Driver card only', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_wrap(ActivityDetailScreen(
      node: _booking(),
      onSwap: () {},
      onCancel: () {},
      onMove: () {},
      onLoved: () {},
    )));
    expect(find.text('Locked reservation'), findsOneWidget);
    expect(find.byKey(const Key('detail_open_maps')), findsOneWidget);
    expect(find.byKey(const Key('detail_driver_card')), findsOneWidget);
    expect(find.byKey(const Key('detail_swap')), findsNothing);
    expect(find.byKey(const Key('detail_cancel')), findsNothing);
    expect(find.byKey(const Key('move_detail_bk1')), findsNothing);
    expect(find.byKey(const Key('detail_love')), findsNothing);
    expect(find.byKey(const Key('detail_slot')), findsNothing);
  });

  testWidgets('8. tapping an itinerary card still opens the details screen', (tester) async {
    final database = _MockOfflineDatabase();
    final repository = _MockTripRepository();
    final api = _MockApiClient();
    final signals = _MockSignalService();
    when(() => database.getLovedPlaceRefs(
          identityScope: any(named: 'identityScope'),
          tripId: any(named: 'tripId'),
        )).thenAnswer((_) async => <String>{});
    when(() => database.getNodeOutcomes(
          identityScope: any(named: 'identityScope'),
          tripId: any(named: 'tripId'),
        )).thenAnswer((_) async => <String, NodeOutcome>{});
    when(() => database.cachePlace(any(), any(), identityScope: any(named: 'identityScope')))
        .thenAnswer((_) async {});
    when(() => database.cacheTrip(any(), any(), identityScope: any(named: 'identityScope')))
        .thenAnswer((_) async {});
    when(() => database.getCachedTrip(any(), identityScope: any(named: 'identityScope')))
        .thenAnswer((_) async => null);
    when(() => database.pruneAlertData()).thenAnswer((_) async {});
    when(() => database.getDismissedAlertIds(identityScope: any(named: 'identityScope')))
        .thenAnswer((_) async => <String>{});
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(tripId: 'trip-1', userId: 'user-1', nodes: [_activity()]),
    );
    when(() => api.get(any(), query: any(named: 'query'))).thenAnswer((invocation) async {
      final path = invocation.positionalArguments.first as String;
      if (path.endsWith('/alerts')) {
        return {
          'trip_id': 'trip-1',
          'status': 'unconfigured',
          'alerts': <Object>[],
          'refreshed_at': '2026-08-31T12:00:00.000Z',
        };
      }
      return {
        'user_id': 'user-1',
        'tier': 'free',
        'daily_reroutes_used': 0,
        'daily_reroutes_remaining': 3,
        'max_daily_reroutes': 3,
      };
    });
    final container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repository),
        apiClientProvider.overrideWithValue(api),
        offlineDatabaseProvider.overrideWithValue(database),
        identityCacheScopeProvider.overrideWithValue('account:user-1'),
        signalServiceProvider.overrideWithValue(signals),
      ],
    );
    final loaded = Completer<void>();
    final sub = container.listen(
      itineraryControllerProvider('trip-1'),
      (_, next) {
        if (!next.loading && !loaded.isCompleted) loaded.complete();
      },
      fireImmediately: true,
    );
    await loaded.future;
    addTearDown(() {
      sub.close();
      container.dispose();
    });
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ItineraryScreen(tripId: 'trip-1')),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.text('Joma Bakery').first);
    await tester.pumpAndSettle();
    expect(find.byType(ActivityDetailScreen), findsOneWidget);
    expect(find.byKey(const Key('detail_love')), findsOneWidget);
  });

  testWidgets('9. Move keeps the existing move_detail_<id> key', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_wrap(ActivityDetailScreen(node: _activity(id: 'd1'), onMove: () {})));
    expect(find.byKey(const Key('move_detail_d1')), findsOneWidget);
    expect(find.byKey(const Key('detail_move')), findsNothing);
  });
}
