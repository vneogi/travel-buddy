// SPEC-42 thin typed Move widget tests.
//
// Harness rules (What Now / Ask-to-Add lessons):
//   - unique in-memory OfflineDatabase(testPath:) + tester.runAsync + _flushFfi
//   - no pumpAndSettle, no physicalSize
//   - sheet/menu open = pump() + pump(500ms); ensureVisible before taps
//   - drain FFI before container.dispose()

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/connectivity_helper.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/activity_detail/activity_detail_screen.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockSignalService extends Mock implements SignalService {}

class _FakeConnectivity extends ConnectivityHelper {
  bool online;
  _FakeConnectivity({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

const _tripId = 'trip-move';
const _region = 'vientiane_laos';
int _harnessCounter = 0;

/// Destination-local (ICT, UTC+7) calendar day [offset] days from today.
DateTime _ictDay(int offset) {
  final ict = DateTime.now().toUtc().add(const Duration(hours: 7));
  return DateTime.utc(ict.year, ict.month, ict.day + offset);
}

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// UTC instant for ICT wall time [hour] on [day].
DateTime _at(DateTime day, int hour) =>
    DateTime.utc(day.year, day.month, day.day, hour).subtract(const Duration(hours: 7));

TripNode _flex(String id, String name, DateTime start, String slot) => TripNode(
      nodeId: id,
      venueName: name,
      venueId: 'v-$id',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: _region,
      slotName: slot,
    );

TripNode _locked(String id) => TripNode(
      nodeId: id,
      venueName: 'Booked Tour',
      scheduledStart: _at(_ictDay(1), 15),
      durationMinutes: 60,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: _region,
      nodeKind: 'booking',
      bookingType: 'tour',
    );

TripState _trip() {
  final day = _ictDay(1);
  return TripState(
    tripId: _tripId,
    userId: 'user-move',
    geoRegion: _region,
    nodes: [
      _flex('temple', 'Wat Si Saket', _at(day, 9), 'morning_tour'),
      _flex('lunch', 'Khop Chai Deu', _at(day, 12), 'lunch'),
    ],
    creationContext: CreationContext(
      destination: _region,
      startDateLocal: _iso(_ictDay(0)),
      endDateLocal: _iso(_ictDay(2)),
    ),
  );
}

typedef _Harness = ({
  ProviderContainer container,
  _MockTripRepository repo,
  OfflineDatabase db,
  void Function() closeSubscription,
});

Future<_Harness> _buildHarness() async {
  _harnessCounter++;
  final db = OfflineDatabase(
    testPath: 'file:spec42_move_$_harnessCounter?mode=memory&cache=shared',
  );
  final trip = _trip();
  final repo = _MockTripRepository();
  when(() => repo.getTrip(_tripId)).thenAnswer((_) async => trip);

  final api = _MockApiClient();
  when(() => api.get(any(), query: any(named: 'query'))).thenAnswer((inv) async {
    final path = inv.positionalArguments.first as String;
    if (path.endsWith('/alerts')) {
      return {
        'trip_id': _tripId,
        'status': 'unconfigured',
        'alerts': <Object>[],
        'refreshed_at': '2026-08-31T12:00:00.000Z',
      };
    }
    return {
      'user_id': 'user-move',
      'tier': 'free',
      'daily_reroutes_used': 0,
      'daily_reroutes_remaining': 3,
      'max_daily_reroutes': 3,
    };
  });

  final signals = _MockSignalService();

  final container = ProviderContainer(overrides: [
    tripRepoProvider.overrideWithValue(repo),
    apiClientProvider.overrideWithValue(api),
    offlineDatabaseProvider.overrideWithValue(db),
    identityCacheScopeProvider.overrideWithValue('account:user-move'),
    signalServiceProvider.overrideWithValue(signals),
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
  return (container: container, repo: repo, db: db, closeSubscription: sub.close);
}

Future<void> _flushFfi(WidgetTester tester, {Finder? until, int maxRounds = 40}) async {
  for (var i = 0; i < maxRounds; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await tester.pump();
    if (until != null && tester.any(until)) return;
  }
  if (until != null) expect(until, findsWidgets);
}

Future<void> _tap(WidgetTester tester, Finder finder) async {
  await tester.ensureVisible(finder);
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(finder);
}

Future<void> _tapKey(WidgetTester tester, String key) => _tap(tester, find.byKey(Key(key)));

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

Finder _overflowFor(String nodeId) => find.descendant(
      of: find.byWidgetPredicate((w) => w is ActivityCard && w.node.nodeId == nodeId),
      matching: find.byTooltip('More actions'),
    );

Future<void> _pumpScreen(WidgetTester tester, _Harness h, _FakeConnectivity c) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: h.container,
    child: MaterialApp(
      home: ItineraryScreen(tripId: _tripId, connectivityOverride: c),
    ),
  ));
  await _flushFfi(tester, until: _overflowFor('lunch'));
}

/// Open lunch overflow -> Move -> pick tomorrow+0 dinner.
Future<void> _pickLunchToDinner(WidgetTester tester) async {
  await _tap(tester, _overflowFor('lunch'));
  await _settle(tester);
  await _tapKey(tester, 'move_menu_lunch');
  await _settle(tester);
  expect(find.byKey(const Key('move_sheet_v1')), findsOneWidget);
  await _tapKey(tester, 'move_date_${_iso(_ictDay(1))}');
  await tester.pump();
  await _tapKey(tester, 'move_slot_dinner');
  await tester.pump();
}

Future<void> _teardown(WidgetTester tester, _Harness h) async {
  await _flushFfi(tester, maxRounds: 4);
  h.closeSubscription();
  h.container.dispose();
  await tester.runAsync(() => h.db.close());
}

void _stubSend(_MockTripRepository repo, Future<TripEventResult> Function() answer) {
  when(() => repo.sendEvent(
        tripId: any(named: 'tripId'),
        type: any(named: 'type'),
        message: any(named: 'message'),
        targetNodeId: any(named: 'targetNodeId'),
        preferences: any(named: 'preferences'),
      )).thenAnswer((_) => answer());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() {
    registerFallbackValue(EventType.moveActivity);
  });

  testWidgets('unlocked card overflow shows Move', (tester) async {
    var moves = 0;
    await tester.pumpWidget(MaterialApp(
      home: Scaffold(
        body: ActivityCard(
          node: _flex('n1', 'Wat Si Saket', _at(_ictDay(1), 9), 'morning_tour'),
          onTapMove: () => moves++,
        ),
      ),
    ));
    await _tap(tester, find.byTooltip('More actions'));
    await _settle(tester);
    expect(find.byKey(const Key('move_menu_n1')), findsOneWidget);
    await _tapKey(tester, 'move_menu_n1');
    await _settle(tester);
    expect(moves, 1);
  });

  testWidgets('locked and booking cards have no Move', (tester) async {
    final booking = _locked('bk1');
    final lockedFlex = TripNode(
      nodeId: 'lk1',
      venueName: 'Locked stop',
      scheduledStart: _at(_ictDay(1), 9),
      durationMinutes: 60,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: _region,
    );
    for (final n in [booking, lockedFlex]) {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: ActivityCard(node: n, onTapMove: () {})),
      ));
      await _tap(tester, find.byTooltip('More actions'));
      await _settle(tester);
      expect(find.byKey(Key('move_menu_${n.nodeId}')), findsNothing);
      await tester.tapAt(const Offset(5, 5));
      await _settle(tester);
    }
    await tester.pumpWidget(MaterialApp(
      home: ActivityDetailScreen(node: booking, onMove: () {}),
    ));
    expect(find.byKey(const Key('move_detail_bk1')), findsNothing);
    await tester.pumpWidget(MaterialApp(
      home: ActivityDetailScreen(
        node: _flex('d1', 'Temple', _at(_ictDay(1), 9), 'morning_tour'),
        onMove: () {},
      ),
    ));
    expect(find.byKey(const Key('move_detail_d1')), findsOneWidget);
  });

  testWidgets('confirm sends one move_activity with exact preferences',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    final temple = before.firstWhere((n) => n.nodeId == 'temple');
    final lunch = before.firstWhere((n) => n.nodeId == 'lunch');
    final movedLunch = TripNode(
      nodeId: lunch.nodeId,
      venueName: lunch.venueName,
      venueId: lunch.venueId,
      scheduledStart: _at(_ictDay(1), 17),
      durationMinutes: lunch.durationMinutes,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: _region,
      slotName: 'dinner',
    );
    _stubSend(h.repo, () async => TripEventResult(
          message: 'Moved Khop Chai Deu.',
          updatedNodes: [temple, movedLunch],
          routingTier: 'light',
          fromCache: false,
        ));

    await _pumpScreen(tester, h, _FakeConnectivity());
    await _pickLunchToDinner(tester);
    expect(find.byKey(const Key('move_confirm_copy')), findsOneWidget);
    expect(find.textContaining('Khop Chai Deu'), findsWidgets);
    await _tapKey(tester, 'move_confirm');
    await _flushFfi(tester, maxRounds: 10);

    final captured = verify(() => h.repo.sendEvent(
          tripId: _tripId,
          type: EventType.moveActivity,
          message: any(named: 'message'),
          targetNodeId: 'lunch',
          preferences: captureAny(named: 'preferences'),
        )).captured;
    expect(captured, hasLength(1));
    expect(captured.single, {
      'mode': 'move',
      'target_date': _iso(_ictDay(1)),
      'target_slot': 'dinner',
    });

    final after = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    final afterLunch = after.firstWhere((n) => n.nodeId == 'lunch');
    expect(afterLunch.slotName, 'dinner');
    expect(after.firstWhere((n) => n.nodeId == 'temple').scheduledStart,
        temple.scheduledStart);
    expect(find.textContaining('Dinner'), findsWidgets);

    await _teardown(tester, h);
  });

  testWidgets('cancel sends nothing', timeout: const Timeout(Duration(seconds: 30)),
      (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    await _pumpScreen(tester, h, _FakeConnectivity());
    await _pickLunchToDinner(tester);
    await _tapKey(tester, 'move_cancel');
    await _settle(tester); // advance the sheet's reverse animation
    await _flushFfi(tester, maxRounds: 6);
    expect(find.byKey(const Key('move_sheet_v1')), findsNothing);
    verifyNever(() => h.repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        ));
    await _teardown(tester, h);
  });

  testWidgets('server refusal does not locally move the card',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    _stubSend(h.repo, () async =>
        throw const ValidationException('That slot already has an activity. Nothing was moved.'));

    await _pumpScreen(tester, h, _FakeConnectivity());
    await _pickLunchToDinner(tester);
    await _tapKey(tester, 'move_confirm');
    await _flushFfi(tester, until: find.textContaining('already has an activity'));

    final after = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    expect(after.map((n) => '${n.nodeId}|${n.scheduledStart}|${n.slotName}').toList(),
        before.map((n) => '${n.nodeId}|${n.scheduledStart}|${n.slotName}').toList());
    await _teardown(tester, h);
  });

  testWidgets('offline confirm refuses and enqueues nothing',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    final offline = _FakeConnectivity(online: false);

    await _pumpScreen(tester, h, offline);
    await _pickLunchToDinner(tester);
    await _tapKey(tester, 'move_confirm');
    await _flushFfi(tester, until: find.textContaining('Not available offline'));

    verifyNever(() => h.repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        ));
    final pending = await tester.runAsync(() => h.db.getPendingBatch());
    expect(pending ?? const [], isEmpty);
    final after = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    expect(after.map((n) => n.scheduledStart).toList(),
        before.map((n) => n.scheduledStart).toList());
    await _teardown(tester, h);
  });

  test('EventType.moveActivity wire round-trip', () {
    expect(EventType.moveActivity.wire, 'move_activity');
    expect(EventType.values.where((e) => e.wire == 'move_activity'), hasLength(1));
  });
}
