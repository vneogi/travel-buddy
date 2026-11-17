// SPEC-48 slice 1: NOW / UP NEXT strip on the itinerary.
//
// Fixtures are December 2026 in zanzibar_tanzania (UTC+3). The clock is
// injected through glanceClockProvider.

import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/features/itinerary/now_next_strip.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockSignalService extends Mock implements SignalService {}

const _region = 'zanzibar_tanzania';
const _tripId = 'trip-s48';
const _scope = 'account:spec48-test';

TripNode _node(
  String id,
  DateTime start, {
  int minutes = 60,
  NodeStatus status = NodeStatus.pending,
  String nodeKind = 'activity',
  String? bookingType,
  String? name,
}) =>
    TripNode(
      nodeId: id,
      venueName: name ?? 'Stop $id',
      venueId: 'v-$id',
      scheduledStart: start,
      durationMinutes: minutes,
      isLocked: false,
      status: status,
      vibeTags: const ['culture'],
      geoRegion: _region,
      nodeKind: nodeKind,
      bookingType: bookingType,
    );

final _t0700 = DateTime.utc(2026, 12, 27, 7);
final _now0730 = DateTime.utc(2026, 12, 27, 7, 30);

Widget _stripApp(
  List<TripNode> nodes,
  DateTime Function() clock, {
  ValueChanged<String>? onFocus,
  double textScale = 1.0,
}) =>
    ProviderScope(
      overrides: [glanceClockProvider.overrideWithValue(clock)],
      child: MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: Scaffold(
          body: Column(
            children: [
              NowNextStrip(nodes: nodes, onFocusNode: onFocus ?? (_) {}),
            ],
          ),
        ),
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // -------------------------------------------------------------------------
  // Pure
  // -------------------------------------------------------------------------

  test('picks the in-window stop as now', () {
    final a = _node('a', _t0700);
    final b = _node('b', _t0700.add(const Duration(hours: 2)));
    final stops = glanceStops([a, b], _now0730);
    expect(stops.now?.nodeId, 'a');
    expect(stops.next?.nodeId, 'b');
  });

  test('skipped and completed stops are never now or next', () {
    final done = _node('done', _t0700, status: NodeStatus.completed);
    final skippedLater = _node(
      'skip',
      _t0700.add(const Duration(hours: 1)),
      status: NodeStatus.skipped,
    );
    final completedLater = _node(
      'comp',
      _t0700.add(const Duration(hours: 2)),
      status: NodeStatus.completed,
    );
    final later = _node('later', _t0700.add(const Duration(hours: 3)));
    final stops = glanceStops([done, skippedLater, completedLater, later],
        _now0730);
    expect(stops.now, isNull);
    expect(stops.next?.nodeId, 'later');

    final onlyFiltered = glanceStops([done, skippedLater, completedLater],
        _now0730);
    expect(onlyFiltered.now, isNull);
    expect(onlyFiltered.next, isNull);
  });

  test('hotel stay is never now but check-in can be up next', () {
    final hotelNow = _node(
      'hotel1',
      _t0700.subtract(const Duration(hours: 20)),
      minutes: 48 * 60,
      nodeKind: 'booking',
      bookingType: 'hotel',
    );
    final hotelLater = _node(
      'hotel2',
      _t0700.add(const Duration(hours: 6)),
      minutes: 24 * 60,
      nodeKind: 'booking',
      bookingType: 'hotel',
    );
    final stops = glanceStops([hotelNow, hotelLater], _now0730);
    expect(stops.now, isNull);
    expect(stops.next?.nodeId, 'hotel2');

    // A non-hotel booking in its window can still be now.
    final ferry = _node(
      'ferry',
      _t0700,
      nodeKind: 'booking',
      bookingType: 'transport',
    );
    expect(glanceStops([hotelNow, ferry], _now0730).now?.nodeId, 'ferry');
  });

  test('next is the earliest stop after now from unsorted input', () {
    final late = _node('late', _t0700.add(const Duration(hours: 9)));
    final soon = _node('soon', _t0700.add(const Duration(hours: 2)));
    final mid = _node('mid', _t0700.add(const Duration(hours: 5)));
    final stops = glanceStops([late, mid, soon], _now0730);
    expect(stops.now, isNull);
    expect(stops.next?.nodeId, 'soon');
  });

  test('overlapping windows pick the earliest start as now', () {
    final later = _node('later', _t0700.add(const Duration(minutes: 15)));
    final earlier = _node('earlier', _t0700, minutes: 120);
    final tieA = _node('tieA', _t0700.add(const Duration(minutes: 15)));
    final stops = glanceStops([later, earlier, tieA], _now0730);
    expect(stops.now?.nodeId, 'earlier');
    // Next must start strictly after now; both overlaps started before.
    expect(stops.next, isNull);

    // Ties on start keep original list order.
    final tie = glanceStops([later, tieA], _now0730);
    expect(tie.now?.nodeId, 'later');
  });

  test('after the last stop both are null', () {
    final a = _node('a', _t0700);
    final b = _node('b', _t0700.add(const Duration(hours: 2)));
    final stops = glanceStops([a, b], _t0700.add(const Duration(hours: 5)));
    expect(stops.now, isNull);
    expect(stops.next, isNull);
  });

  test('labels are destination-local', () {
    final current = _node('a', _t0700);
    expect(glanceNowTime(current), 'until 11:00');
    final sameDay = _node('b', DateTime.utc(2026, 12, 27, 12));
    expect(glanceNextTime(sameDay, _now0730), '15:00');
    final nextDay = _node('c', DateTime.utc(2026, 12, 28, 7));
    expect(glanceNextTime(nextDay, _now0730), 'Mon 28 Dec, 10:00');
  });

  // -------------------------------------------------------------------------
  // Widget
  // -------------------------------------------------------------------------

  testWidgets('strip shows NOW and UP NEXT rows with names and times',
      (tester) async {
    final nodes = [
      _node('a', _t0700, name: 'Forodhani Gardens'),
      _node('b', DateTime.utc(2026, 12, 27, 12), name: 'Old Fort'),
    ];
    await tester.pumpWidget(_stripApp(nodes, () => _now0730));

    expect(find.byKey(const Key('glance_strip')), findsOneWidget);
    final nowRow = find.byKey(const Key('glance_now_row'));
    final nextRow = find.byKey(const Key('glance_next_row'));
    expect(nowRow, findsOneWidget);
    expect(nextRow, findsOneWidget);
    expect(
      find.descendant(of: nowRow, matching: find.text('NOW')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: nowRow, matching: find.textContaining('Forodhani')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: nowRow, matching: find.textContaining('until 11:00')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: nextRow, matching: find.text('UP NEXT')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: nextRow, matching: find.textContaining('Old Fort')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: nextRow, matching: find.textContaining('15:00')),
      findsOneWidget,
    );
    // Name and time share one Text.rich, so exact name matches stay free.
    expect(find.text('Forodhani Gardens'), findsNothing);

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('strip is hidden when there is no now and no next',
      (tester) async {
    final nodes = [_node('a', _t0700)];
    await tester.pumpWidget(
      _stripApp(nodes, () => _t0700.add(const Duration(hours: 3))),
    );
    expect(find.byKey(const Key('glance_strip')), findsNothing);
    expect(find.byKey(const Key('glance_now_row')), findsNothing);
    expect(find.byKey(const Key('glance_next_row')), findsNothing);

    await tester.pumpWidget(_stripApp(const [], () => _now0730));
    expect(find.byKey(const Key('glance_strip')), findsNothing);

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('tapping a row reports that node id', (tester) async {
    final tapped = <String>[];
    final nodes = [
      _node('a', _t0700),
      _node('b', DateTime.utc(2026, 12, 27, 12)),
    ];
    await tester.pumpWidget(
      _stripApp(nodes, () => _now0730, onFocus: tapped.add),
    );
    await tester.tap(find.byKey(const Key('glance_now_row')));
    await tester.pump();
    await tester.tap(find.byKey(const Key('glance_next_row')));
    await tester.pump();
    expect(tapped, ['a', 'b']);

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('strip moves on when the clock passes the current stop end',
      (tester) async {
    var clock = _now0730;
    final nodes = [
      _node('a', _t0700, name: 'First Stop'),
      _node('b', DateTime.utc(2026, 12, 27, 9), name: 'Second Stop'),
    ];
    await tester.pumpWidget(_stripApp(nodes, () => clock));
    expect(
      find.descendant(
        of: find.byKey(const Key('glance_now_row')),
        matching: find.textContaining('First Stop'),
      ),
      findsOneWidget,
    );

    // Past the end of the first stop, before the second starts.
    clock = DateTime.utc(2026, 12, 27, 8, 5);
    await tester.pump(const Duration(minutes: 1));
    expect(find.byKey(const Key('glance_now_row')), findsNothing);
    expect(
      find.descendant(
        of: find.byKey(const Key('glance_next_row')),
        matching: find.textContaining('Second Stop'),
      ),
      findsOneWidget,
    );

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('no overflow at 360dp and 2.0 text scale with a long name',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final longName = 'A' * 20 + ' Very Long Venue Name For The Glance Strip';
    expect(longName.length, greaterThanOrEqualTo(60));
    final nodes = [
      _node('a', _t0700, name: longName),
      _node('b', DateTime.utc(2026, 12, 28, 7), name: longName),
    ];
    await tester.pumpWidget(
      _stripApp(nodes, () => _now0730, textScale: 2.0),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    final strip = find.byKey(const Key('glance_strip'));
    expect(tester.getRect(strip).right, lessThanOrEqualTo(360));
    expect(find.byKey(const Key('glance_now_row')).hitTestable(),
        findsOneWidget);
    expect(find.byKey(const Key('glance_next_row')).hitTestable(),
        findsOneWidget);

    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('rows are 44dp buttons with Now and Up next semantics labels',
      (tester) async {
    final handle = tester.ensureSemantics();
    final nodes = [
      _node('a', _t0700, name: 'Forodhani Gardens'),
      _node('b', DateTime.utc(2026, 12, 28, 7), name: 'Old Fort'),
    ];
    await tester.pumpWidget(_stripApp(nodes, () => _now0730));

    final nowRow = find.byKey(const Key('glance_now_row'));
    final nextRow = find.byKey(const Key('glance_next_row'));
    expect(tester.getSize(nowRow).height, greaterThanOrEqualTo(44));
    expect(tester.getSize(nextRow).height, greaterThanOrEqualTo(44));
    expect(
      tester.getSemantics(nowRow),
      containsSemantics(
        label: 'Now: Forodhani Gardens, until 11:00',
        isButton: true,
      ),
    );
    expect(
      tester.getSemantics(nextRow),
      containsSemantics(
        label: 'Up next: Old Fort, Mon 28 Dec, 10:00',
        isButton: true,
      ),
    );

    await tester.pumpWidget(const SizedBox());
    handle.dispose();
  });

  // -------------------------------------------------------------------------
  // Integration
  // -------------------------------------------------------------------------

  testWidgets(
    'itinerary shows the strip from the saved copy when offline',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      tester.view.physicalSize = const Size(800, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final trip = TripState(
        tripId: _tripId,
        userId: 'user-1',
        nodes: [
          _node('a', _t0700, name: 'Forodhani Gardens'),
          _node('b', DateTime.utc(2026, 12, 27, 12), name: 'Old Fort'),
        ],
      );

      final setup = await tester.runAsync(() async {
        final db = OfflineDatabase(
          testPath: 'file:spec48_nn_offline?mode=memory&cache=shared',
        );
        await db.cacheTrip(
          _tripId,
          jsonEncode(trip.toJson()),
          identityScope: _scope,
        );
        final repo = _MockTripRepository();
        when(() => repo.getTrip(_tripId)).thenThrow(const NetworkException());
        // Same stubs as spec45 / spec56 for alerts and user status.
        final api = _MockApiClient();
        when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
          (invocation) async {
            final path = invocation.positionalArguments.first as String;
            if (path.endsWith('/alerts')) {
              return {
                'trip_id': _tripId,
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
          },
        );
        final container = ProviderContainer(overrides: [
          tripRepoProvider.overrideWithValue(repo),
          offlineDatabaseProvider.overrideWithValue(db),
          identityCacheScopeProvider.overrideWithValue(_scope),
          apiClientProvider.overrideWithValue(api),
          signalServiceProvider.overrideWithValue(_MockSignalService()),
          glanceClockProvider.overrideWithValue(() => _now0730),
        ]);
        final loaded = Completer<void>();
        final sub = container.listen(
          itineraryControllerProvider(_tripId),
          (_, next) {
            if (!next.loading && !loaded.isCompleted) loaded.complete();
          },
          fireImmediately: true,
        );
        await loaded.future;
        return (container: container, db: db, sub: sub);
      });
      if (setup == null) fail('setup null');

      expect(
        setup.container.read(itineraryControllerProvider(_tripId)).showingSaved,
        isTrue,
      );

      await tester.pumpWidget(UncontrolledProviderScope(
        container: setup.container,
        child: const MaterialApp(home: ItineraryScreen(tripId: _tripId)),
      ));
      await _flush(tester, until: find.byKey(const Key('glance_now_row')));

      expect(find.byKey(const Key('glance_now_row')), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(const Key('glance_now_row')),
          matching: find.textContaining('Forodhani Gardens'),
        ),
        findsOneWidget,
      );

      // Teardown: close listeners while mounted, dispose, then close the DB.
      setup.sub.close();
      await tester.pumpWidget(const SizedBox());
      await _flush(tester, maxRounds: 4);
      setup.container.dispose();
      await tester.runAsync(() => setup.db.close());
    },
  );
}
