// SPEC-56 slice 1: honest offline status on the itinerary.
//
// Real in-memory OfflineDatabase(testPath:) with sqflite FFI, a real
// ItineraryController and a mocked TripRepository. Teardown closes harness
// listeners while the widget is mounted, then disposes the container.

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
import 'package:travel_buddy/features/itinerary/offline_readiness.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/theme/colors.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockSignalService extends Mock implements SignalService {}

const _scope = 'account:spec56-test';
const _otherScope = 'account:spec56-other';
const _tripId = 'trip-s56';
int _dbCounter = 0;

OfflineDatabase _newDb() {
  _dbCounter++;
  return OfflineDatabase(
    testPath: 'file:spec56_or_$_dbCounter?mode=memory&cache=shared',
  );
}

TripNode _node(String id, String venueId, DateTime start) => TripNode(
      nodeId: id,
      venueName: 'Venue $venueId',
      venueId: venueId,
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['culture'],
    );

TripState _trip() {
  final now = DateTime.now().toUtc();
  return TripState(
    tripId: _tripId,
    userId: 'user-1',
    nodes: [
      _node('n1', 'v1', now.add(const Duration(hours: 1))),
      _node('n2', 'v2', now.add(const Duration(hours: 3))),
      _node('n3', 'v3', now.add(const Duration(hours: 5))),
    ],
  );
}

Future<void> _setTripCachedAt(OfflineDatabase db, DateTime atUtc) async {
  final raw = await db.db;
  await raw.update(
    'cache_trip',
    {'cached_at': atUtc.toUtc().toIso8601String()},
    where: 'identity_scope = ? AND trip_id = ?',
    whereArgs: [_scope, _tripId],
  );
}

Future<void> _deleteTripRow(OfflineDatabase db) async {
  final raw = await db.db;
  await raw.delete(
    'cache_trip',
    where: 'identity_scope = ? AND trip_id = ?',
    whereArgs: [_scope, _tripId],
  );
}

Future<void> _deletePlace(OfflineDatabase db, String ref) async {
  final raw = await db.db;
  await raw.delete(
    'cache_place',
    where: 'identity_scope = ? AND place_ref = ?',
    whereArgs: [_scope, ref],
  );
}

typedef _Harness = ({
  ProviderContainer container,
  OfflineDatabase db,
  void Function() closeSubscription,
});

/// Build inside tester.runAsync. [online] false makes getTrip throw a
/// NetworkException. [savedAge] pre-seeds the trip row that old.
Future<_Harness> _buildHarness({
  bool online = true,
  Duration? savedAge,
  bool fullScreen = false,
}) async {
  final db = _newDb();
  final trip = _trip();
  if (savedAge != null) {
    await db.cacheTrip(
      _tripId,
      jsonEncode(trip.toJson()),
      identityScope: _scope,
    );
    await _setTripCachedAt(db, DateTime.now().toUtc().subtract(savedAge));
  }

  final repo = _MockTripRepository();
  if (online) {
    when(() => repo.getTrip(_tripId)).thenAnswer((_) async => trip);
  } else {
    when(() => repo.getTrip(_tripId)).thenThrow(const NetworkException());
  }

  final overrides = <Override>[
    tripRepoProvider.overrideWithValue(repo),
    offlineDatabaseProvider.overrideWithValue(db),
    identityCacheScopeProvider.overrideWithValue(_scope),
  ];
  if (fullScreen) {
    // Same stubs as spec45_bottom_inset_test.dart for alerts / user status.
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
    overrides
      ..add(apiClientProvider.overrideWithValue(api))
      ..add(signalServiceProvider.overrideWithValue(_MockSignalService()));
  }

  final container = ProviderContainer(overrides: overrides);
  final loaded = Completer<void>();
  final sub = container.listen(
    itineraryControllerProvider(_tripId),
    (_, next) {
      if (!next.loading && !loaded.isCompleted) loaded.complete();
    },
    fireImmediately: true,
  );
  await loaded.future;
  return (container: container, db: db, closeSubscription: sub.close);
}

Widget _rowApp(_Harness h, {double textScale = 1.0}) =>
    UncontrolledProviderScope(
      container: h.container,
      child: MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: const Scaffold(
          body: Column(children: [OfflineStatusRow(tripId: _tripId)]),
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

const _rowKey = Key('offline_status_row');
const _sheetKey = Key('offline_status_sheet');
const _checkKey = Key('offline_status_check_again');

/// Re-read status the way "Check again" or app resume would.
Future<void> _reread(WidgetTester tester, _Harness h, {Finder? until}) async {
  h.container.invalidate(tripCacheStatusProvider(_tripId));
  await _flush(tester, until: until);
}

Future<void> _openSheet(WidgetTester tester) async {
  await tester.tap(find.byKey(_rowKey));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  await _flush(tester, until: find.byKey(_sheetKey));
}

List<String> _texts(WidgetTester tester, Finder scope) => tester
    .widgetList<Text>(find.descendant(of: scope, matching: find.byType(Text)))
    .map((t) => t.data ?? t.textSpan?.toPlainText() ?? '')
    .toList();

Future<void> _teardown(WidgetTester tester, _Harness h) async {
  h.closeSubscription();
  await tester.pumpWidget(const SizedBox());
  await _flush(tester, maxRounds: 4);
  h.container.dispose();
  await tester.runAsync(() => h.db.close());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // -------------------------------------------------------------------------
  // DB and helper
  // -------------------------------------------------------------------------

  test('status is null when the trip is not cached', () async {
    final db = _newDb();
    final status = await db.getTripCacheStatus(
      _tripId,
      identityScope: _scope,
      placeRefs: const ['v1'],
    );
    expect(status, isNull);
    await db.close();
  });

  test('status reads cached_at and counts only this identity\'s places',
      () async {
    final db = _newDb();
    await db.cacheTrip(_tripId, '{}', identityScope: _scope);
    final at = DateTime.utc(2026, 10, 2, 9, 30);
    await _setTripCachedAt(db, at);
    await db.cachePlace('v1', '{}', identityScope: _scope);
    await db.cachePlace('v2', '{}', identityScope: _scope);
    // Same refs for another identity must not be counted.
    for (final ref in ['v1', 'v2', 'v3']) {
      await db.cachePlace(ref, '{}', identityScope: _otherScope);
    }

    final status = await db.getTripCacheStatus(
      _tripId,
      identityScope: _scope,
      placeRefs: const ['v1', 'v2', 'v3'],
    );
    expect(status, isNotNull);
    expect(status!.cachedAt, at);
    expect(status.placesCached, 2);
    await db.close();
  });

  test('unusable identity scope returns null', () async {
    final db = _newDb();
    await db.cacheTrip(_tripId, '{}', identityScope: _scope);
    for (final bad in ['', 'account:', 'anonymous:']) {
      final status = await db.getTripCacheStatus(
        _tripId,
        identityScope: bad,
        placeRefs: const ['v1'],
      );
      expect(status, isNull, reason: 'scope "$bad"');
    }
    await db.close();
  });

  test('empty refs count zero and duplicate refs count once', () async {
    final db = _newDb();
    await db.cacheTrip(_tripId, '{}', identityScope: _scope);
    await db.cachePlace('v1', '{}', identityScope: _scope);

    final empty = await db.getTripCacheStatus(
      _tripId,
      identityScope: _scope,
      placeRefs: const [],
    );
    expect(empty!.placesCached, 0);

    final dupes = await db.getTripCacheStatus(
      _tripId,
      identityScope: _scope,
      placeRefs: const ['v1', 'v1', 'v1'],
    );
    expect(dupes!.placesCached, 1);
    await db.close();
  });

  test('savedAgeLabel matches Home wording', () {
    final now = DateTime.utc(2026, 10, 2, 12);
    expect(
      savedAgeLabel(now.subtract(const Duration(seconds: 30)), nowUtc: now),
      'just now',
    );
    expect(
      savedAgeLabel(now.subtract(const Duration(minutes: 5)), nowUtc: now),
      '5m ago',
    );
    expect(
      savedAgeLabel(now.subtract(const Duration(hours: 3)), nowUtc: now),
      '3h ago',
    );
    expect(
      savedAgeLabel(now.subtract(const Duration(days: 2)), nowUtc: now),
      '2d ago',
    );
  });

  // -------------------------------------------------------------------------
  // Widget
  // -------------------------------------------------------------------------

  testWidgets(
    'online load shows Saved on this device',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_rowApp(h));
      await _flush(tester, until: find.byKey(_rowKey));
      // cacheTrip is fire-and-forget; re-read once it has landed, as the
      // "Check again" button would.
      await _flush(tester, maxRounds: 4);
      await _reread(
        tester,
        h,
        until: find.text('Saved on this device (just now)'),
      );
      expect(find.text('Saved on this device (just now)'), findsOneWidget);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'failed load with a saved copy shows Offline showing saved trip',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(online: false, savedAge: const Duration(hours: 2)),
      );
      if (h == null) fail('harness null');

      expect(
        h.container.read(itineraryControllerProvider(_tripId)).showingSaved,
        isTrue,
      );

      await tester.pumpWidget(_rowApp(h));
      await _flush(
        tester,
        until: find.text('Offline: showing saved trip (saved 2h ago)'),
      );
      expect(
        find.text('Offline: showing saved trip (saved 2h ago)'),
        findsOneWidget,
      );
      expect(
        find.textContaining('Offline: showing saved itinerary'),
        findsNothing,
      );
      expect(
        h.container.read(itineraryControllerProvider(_tripId)).banner,
        isNull,
      );

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'no saved copy shows Not saved on this device yet',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_rowApp(h));
      await _flush(tester, until: find.byKey(_rowKey));
      // Load succeeded online, so load() wrote the trip row. To model "the
      // trip row is absent" without changing load(), let that write land
      // and then delete the row before re-reading.
      await _flush(tester, maxRounds: 4);
      await tester.runAsync(() => _deleteTripRow(h.db));
      await _reread(tester, h, until: find.text('Not saved on this device yet'));
      expect(find.text('Not saved on this device yet'), findsOneWidget);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'stale saved copy shows the stale note',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(online: false, savedAge: const Duration(days: 2)),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(_rowApp(h));
      final rowText = find.text('Offline: showing saved trip (saved 2d ago)');
      await _flush(tester, until: rowText);
      expect(tester.widget<Text>(rowText).style?.color, AppColors.warning);

      await _openSheet(tester);
      expect(find.text(kOfflineStaleNote), findsOneWidget);
      expect(find.text(kOfflineFootnote), findsOneWidget);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'sheet lists itinerary time and driver card counts',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_rowApp(h));
      await _flush(tester, until: find.byKey(_rowKey));
      // load() pre-caches every stop's driver card, so drop the third one
      // to get 2 of 3 saved.
      await _flush(tester, maxRounds: 4);
      await tester.runAsync(() => _deletePlace(h.db, 'v3'));

      await _openSheet(tester);
      await tester.tap(find.byKey(_checkKey));
      await _flush(tester, until: find.text('Driver cards: 2 of 3 stops saved'));
      expect(find.textContaining('Itinerary: saved '), findsOneWidget);
      expect(find.text('Driver cards: 2 of 3 stops saved'), findsOneWidget);
      expect(find.text(kOfflineStaleNote), findsNothing);
      expect(find.text(kOfflineFootnote), findsOneWidget);
      expect(find.text('Check again'), findsOneWidget);

      await tester.runAsync(
        () => h.db.cachePlace('v3', '{}', identityScope: _scope),
      );
      await tester.tap(find.byKey(_checkKey));
      await _flush(tester, until: find.text('Driver cards: 3 of 3 stops saved'));
      expect(find.text('Driver cards: 3 of 3 stops saved'), findsOneWidget);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'no overclaiming words in row or sheet',
    timeout: const Timeout(Duration(seconds: 60)),
    (tester) async {
      const banned = [
        '100%',
        'ready',
        'fully',
        'downloaded',
        'complete',
        'outbox',
        'signal',
      ];
      final scenarios = <String, Future<_Harness> Function()>{
        'online saved': () => _buildHarness(),
        'offline 2h': () =>
            _buildHarness(online: false, savedAge: const Duration(hours: 2)),
        'not saved': () => _buildHarness(),
        'offline stale': () =>
            _buildHarness(online: false, savedAge: const Duration(days: 2)),
      };

      for (final entry in scenarios.entries) {
        final h = await tester.runAsync(entry.value);
        if (h == null) fail('harness null');
        await tester.pumpWidget(_rowApp(h));
        await _flush(tester, until: find.byKey(_rowKey));
        await _flush(tester, maxRounds: 4);
        if (entry.key == 'not saved') {
          await tester.runAsync(() => _deleteTripRow(h.db));
        }
        await _reread(tester, h, until: find.byKey(_rowKey));

        final seen = <String>[..._texts(tester, find.byKey(_rowKey))];
        await _openSheet(tester);
        seen.addAll(_texts(tester, find.byKey(_sheetKey)));
        expect(seen, isNotEmpty, reason: entry.key);

        for (final text in seen) {
          final lower = text.toLowerCase();
          for (final word in banned) {
            expect(
              lower.contains(word),
              isFalse,
              reason: '${entry.key}: "$text" contains "$word"',
            );
          }
        }
        await _teardown(tester, h);
      }
    },
  );

  testWidgets(
    'app resume re-reads status',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_rowApp(h));
      await _flush(tester, until: find.byKey(_rowKey));
      await _flush(tester, maxRounds: 4);
      await tester.runAsync(() => _deletePlace(h.db, 'v3'));
      await _reread(tester, h);

      await _openSheet(tester);
      await _flush(tester, until: find.text('Driver cards: 2 of 3 stops saved'));

      await tester.runAsync(
        () => h.db.cachePlace('v3', '{}', identityScope: _scope),
      );
      // No tap: only the lifecycle change may trigger the re-read.
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await _flush(tester, until: find.text('Driver cards: 3 of 3 stops saved'));
      expect(find.text('Driver cards: 3 of 3 stops saved'), findsOneWidget);

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'itinerary screen shows the status row',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      tester.view.physicalSize = const Size(800, 2000);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final h = await tester.runAsync(() => _buildHarness(fullScreen: true));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: const MaterialApp(home: ItineraryScreen(tripId: _tripId)),
      ));
      await _flush(tester, until: find.byKey(_rowKey));
      await _flush(tester, until: find.byType(ActivityCard));

      expect(find.byKey(_rowKey), findsOneWidget);
      final rowTop = tester.getTopLeft(find.byKey(_rowKey)).dy;
      final firstCardTop = tester.getTopLeft(find.byType(ActivityCard).first).dy;
      expect(rowTop, lessThan(firstCardTop));
      // The row adds no scrollable of its own.
      expect(
        find.descendant(
          of: find.byKey(_rowKey),
          matching: find.byType(Scrollable),
        ),
        findsNothing,
      );

      await _teardown(tester, h);
    },
  );

  testWidgets(
    'row fits at 360dp and 2.0 text scale',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final h = await tester.runAsync(
        () => _buildHarness(online: false, savedAge: const Duration(hours: 2)),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(_rowApp(h, textScale: 2.0));
      final rowText = find.text('Offline: showing saved trip (saved 2h ago)');
      await _flush(tester, until: rowText);

      expect(tester.takeException(), isNull);
      final rect = tester.getRect(rowText);
      expect(rect.right, lessThanOrEqualTo(360));
      expect(rect.left, greaterThanOrEqualTo(0));
      expect(rowText.hitTestable(), findsOneWidget);
      expect(tester.getSize(find.byKey(_rowKey)).height, greaterThanOrEqualTo(44));

      await _teardown(tester, h);
    },
  );
}
