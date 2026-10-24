// SPEC-42 trip-private uncatalogued Add widget tests.
//
// Harness rules: unique in-memory OfflineDatabase(testPath:), tester.runAsync,
// _flushFfi, no pumpAndSettle, no physicalSize. Sheet open/close uses pump()
// plus a timed pump; ensureVisible before taps; drain FFI before dispose.

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
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockSignalService extends Mock implements SignalService {}

class _FakeConnectivity extends ConnectivityHelper {
  final bool online;
  _FakeConnectivity({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

const _tripId = 'trip-uca';
const _region = 'vientiane_laos';
int _harnessCounter = 0;

DateTime _ictDay(int offset) {
  final ict = DateTime.now().toUtc().add(const Duration(hours: 7));
  return DateTime.utc(ict.year, ict.month, ict.day + offset);
}

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

DateTime _at(DateTime day, int hour) =>
    DateTime.utc(day.year, day.month, day.day, hour).subtract(const Duration(hours: 7));

final _populated = _iso(_ictDay(1));
final _empty = _iso(_ictDay(2));

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

TripState _trip() => TripState(
      tripId: _tripId,
      userId: 'user-dadd',
      geoRegion: _region,
      nodes: [
        _flex('temple', 'Wat Si Saket', _at(_ictDay(1), 9), 'morning_tour'),
        _flex('lunch', 'Khop Chai Deu', _at(_ictDay(1), 12), 'lunch'),
      ],
      creationContext: CreationContext(
        destination: _region,
        startDateLocal: _iso(_ictDay(1)),
        endDateLocal: _iso(_ictDay(2)),
      ),
    );

AddCandidatesResult _cands() => AddCandidatesResult(
      targetDate: _empty,
      targetSlot: 'dinner',
      geoRegion: _region,
      candidates: [
        AddCandidate(
          venueId: 'v-noodle',
          name: 'Noodle House',
          category: 'restaurant',
          microLocation: 'Riverside',
          plannedStart: '${_empty}T17:00:00+07:00',
          typicalDwellMinutes: 60,
        ),
      ],
    );

typedef _Harness = ({
  ProviderContainer container,
  _MockTripRepository repo,
  OfflineDatabase db,
  void Function() closeSubscription,
});

Future<_Harness> _buildHarness() async {
  _harnessCounter++;
  final db = OfflineDatabase(
    testPath: 'file:spec42_uca_$_harnessCounter?mode=memory&cache=shared',
  );
  final repo = _MockTripRepository();
  when(() => repo.getTrip(_tripId)).thenAnswer((_) async => _trip());
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
      'user_id': 'user-dadd',
      'tier': 'free',
      'daily_reroutes_used': 0,
      'daily_reroutes_remaining': 3,
      'max_daily_reroutes': 3,
    };
  });
  final container = ProviderContainer(overrides: [
    tripRepoProvider.overrideWithValue(repo),
    apiClientProvider.overrideWithValue(api),
    offlineDatabaseProvider.overrideWithValue(db),
    identityCacheScopeProvider.overrideWithValue('account:user-dadd'),
    signalServiceProvider.overrideWithValue(_MockSignalService()),
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

Future<void> _tapKey(WidgetTester tester, String key) async {
  final f = find.byKey(Key(key));
  await tester.ensureVisible(f);
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(f);
}

Future<void> _settle(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
}

Future<void> _pumpScreen(WidgetTester tester, _Harness h, {bool online = true}) async {
  await tester.pumpWidget(UncontrolledProviderScope(
    container: h.container,
    child: MaterialApp(
      home: ItineraryScreen(
        tripId: _tripId,
        connectivityOverride: _FakeConnectivity(online: online),
      ),
    ),
  ));
  await _flushFfi(tester, until: find.byKey(Key('empty_day_add_$_empty')));
}

Future<void> _openAndPickDinner(WidgetTester tester) async {
  await _tapKey(tester, 'empty_day_add_$_empty');
  await _settle(tester);
  expect(find.byKey(const Key('direct_add_sheet_v1')), findsOneWidget);
  await _tapKey(tester, 'direct_add_slot_dinner');
  await _flushFfi(tester, maxRounds: 6);
}

void _stubCandidates(_MockTripRepository repo, AddCandidatesResult r) {
  when(() => repo.addCandidates(
        tripId: any(named: 'tripId'),
        targetDate: any(named: 'targetDate'),
        targetSlot: any(named: 'targetSlot'),
      )).thenAnswer((_) async => r);
}

void _verifyNoSend(_MockTripRepository repo) {
  verifyNever(() => repo.sendEvent(
        tripId: any(named: 'tripId'),
        type: any(named: 'type'),
        message: any(named: 'message'),
        targetNodeId: any(named: 'targetNodeId'),
        preferences: any(named: 'preferences'),
      ));
}

Future<void> _teardown(WidgetTester tester, _Harness h) async {
  await _flushFfi(tester, maxRounds: 4);
  h.closeSubscription();
  h.container.dispose();
  await tester.runAsync(() => h.db.close());
}

void _stubSend(_MockTripRepository repo, List<TripNode> nodes) {
  when(() => repo.sendEvent(
        tripId: any(named: 'tripId'),
        type: any(named: 'type'),
        message: any(named: 'message'),
        targetNodeId: any(named: 'targetNodeId'),
        preferences: any(named: 'preferences'),
      )).thenAnswer((_) async => TripEventResult(
        message: 'Added.',
        updatedNodes: nodes,
        routingTier: 'light',
        fromCache: false,
      ));
}

Future<void> _openPrivateForm(WidgetTester tester) async {
  await _openAndPickDinner(tester);
  await _tapKey(tester, 'uncatalogued_add_open');
  await tester.pump();
  expect(find.byKey(const Key('uncatalogued_add_form')), findsOneWidget);
}

Future<void> _fillPrivateForm(WidgetTester tester) async {
  final name = find.byKey(const Key('uncatalogued_add_name'));
  await tester.ensureVisible(name);
  await tester.enterText(name, '  Papao   viewpoint ');
  await tester.pump();
  await _tapKey(tester, 'uncatalogued_add_dwell_45');
  await tester.pump();
  final micro = find.byKey(const Key('uncatalogued_add_micro'));
  await tester.ensureVisible(micro);
  await tester.enterText(micro, 'east bank');
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() => registerFallbackValue(EventType.addActivity));

  testWidgets('uncatalogued action is reachable from the empty-day sheet',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    await _pumpScreen(tester, h);
    expect(find.byKey(Key('empty_day_add_$_populated')), findsNothing);
    await _openPrivateForm(tester);
    expect(find.byKey(const Key('uncatalogued_add_dwell_15')), findsOneWidget);
    expect(find.byKey(const Key('uncatalogued_add_dwell_120')), findsOneWidget);
    // Confirm stays disabled until name + dwell are given.
    final confirm = tester.widget<ElevatedButton>(
        find.byKey(const Key('uncatalogued_add_confirm')));
    expect(confirm.onPressed, isNull);
    await _tapKey(tester, 'uncatalogued_add_cancel');
    await _settle(tester);
    await _teardown(tester, h);
  });

  testWidgets('confirm sends one add_activity with exact uncatalogued_add preferences',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    final added = TripNode(
      nodeId: 'priv-1',
      venueName: 'Papao viewpoint',
      scheduledStart: _at(_ictDay(2), 17),
      durationMinutes: 45,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: _region,
      slotName: 'dinner',
      placeSource: 'trip_private',
    );
    _stubSend(h.repo, [...before, added]);

    await _pumpScreen(tester, h);
    await _openPrivateForm(tester);
    await _fillPrivateForm(tester);
    final copy = find.byKey(const Key('uncatalogued_add_confirm_copy'));
    expect(copy, findsOneWidget);
    final text = (tester.widget<Text>(copy)).data!;
    expect(text, contains('Papao viewpoint'));
    expect(text, contains(_empty));
    expect(text, contains('Dinner'));
    expect(text, contains('45 min'));
    expect(text, contains('only on this trip'));

    await _tapKey(tester, 'uncatalogued_add_confirm');
    await _settle(tester);
    await _flushFfi(tester, maxRounds: 10);

    final captured = verify(() => h.repo.sendEvent(
          tripId: _tripId,
          type: EventType.addActivity,
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: captureAny(named: 'preferences'),
        )).captured;
    expect(captured, hasLength(1));
    expect(captured.single, {
      'mode': 'uncatalogued_add',
      'name': 'Papao viewpoint',
      'target_date': _empty,
      'target_slot': 'dinner',
      'typical_dwell_minutes': 45,
      'micro_location': 'east bank',
    });
    final sent = captured.single as Map;
    expect(sent.containsKey('venue_id'), isFalse);
    expect(sent.containsKey('scheduled_start'), isFalse);

    expect(find.byKey(Key('empty_day_add_$_empty')), findsNothing);
    expect(find.text('Papao viewpoint'), findsWidgets);
    expect(find.byKey(const Key('trip_private_badge_priv-1')), findsOneWidget);
    expect(
      find.byWidgetPredicate((w) => w is ActivityCard && w.node.nodeId == 'priv-1'),
      findsOneWidget,
    );
    await _teardown(tester, h);
  });

  testWidgets('cancel sends nothing', timeout: const Timeout(Duration(seconds: 30)),
      (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    await _pumpScreen(tester, h);
    await _openPrivateForm(tester);
    await _fillPrivateForm(tester);
    await _tapKey(tester, 'uncatalogued_add_cancel');
    await _settle(tester);
    await _flushFfi(tester, maxRounds: 6);
    expect(find.byKey(const Key('direct_add_sheet_v1')), findsNothing);
    _verifyNoSend(h.repo);
    expect(find.byKey(Key('empty_day_add_$_empty')), findsOneWidget);
    await _teardown(tester, h);
  });

  testWidgets('server 422 leaves the date empty and shows the message',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    when(() => h.repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) async => throw const ValidationException(
        'That place is in the catalog. Pick it from the list instead.'));
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;

    await _pumpScreen(tester, h);
    await _openPrivateForm(tester);
    await _fillPrivateForm(tester);
    await _tapKey(tester, 'uncatalogued_add_confirm');
    await _settle(tester);
    await _flushFfi(tester, until: find.textContaining('Pick it from the list'));

    final after = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    expect(after.map((n) => n.nodeId).toList(), before.map((n) => n.nodeId).toList());
    expect(find.byKey(Key('empty_day_add_$_empty')), findsOneWidget);
    await _teardown(tester, h);
  });

  testWidgets('offline empty-day tap opens nothing and queues nothing',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    await _pumpScreen(tester, h, online: false);
    await _tapKey(tester, 'empty_day_add_$_empty');
    await _settle(tester);
    await _flushFfi(tester, until: find.textContaining('Not available offline'));
    expect(find.byKey(const Key('direct_add_sheet_v1')), findsNothing);
    expect(find.byKey(const Key('uncatalogued_add_open')), findsNothing);
    verifyNever(() => h.repo.addCandidates(
          tripId: any(named: 'tripId'),
          targetDate: any(named: 'targetDate'),
          targetSlot: any(named: 'targetSlot'),
        ));
    _verifyNoSend(h.repo);
    final pending = await tester.runAsync(() => h.db.getPendingBatch());
    expect(pending ?? const [], isEmpty);
    await _teardown(tester, h);
  });

  testWidgets('existing catalog direct_add confirm still works',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    _stubSend(h.repo, [
      ...before,
      TripNode(
        nodeId: 'new-1',
        venueName: 'Noodle House',
        venueId: 'v-noodle',
        scheduledStart: _at(_ictDay(2), 17),
        durationMinutes: 60,
        isLocked: false,
        status: NodeStatus.pending,
        vibeTags: const [],
        geoRegion: _region,
        slotName: 'dinner',
      ),
    ]);
    await _pumpScreen(tester, h);
    await _openAndPickDinner(tester);
    await _tapKey(tester, 'direct_add_candidate_v-noodle');
    await tester.pump();
    await _tapKey(tester, 'direct_add_confirm');
    await _settle(tester);
    await _flushFfi(tester, maxRounds: 10);
    final captured = verify(() => h.repo.sendEvent(
          tripId: _tripId,
          type: EventType.addActivity,
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: captureAny(named: 'preferences'),
        )).captured;
    expect(captured.single, {
      'mode': 'direct_add',
      'venue_id': 'v-noodle',
      'target_date': _empty,
      'target_slot': 'dinner',
    });
    expect(find.byKey(const Key('trip_private_badge_new-1')), findsNothing);
    await _teardown(tester, h);
  });

  test('TripNode place_source defaults to catalog and round-trips', () {
    final old = TripNode.fromJson({
      'node_id': 'n',
      'venue_name': 'X',
      'scheduled_start': '2026-10-13T10:00:00Z',
    });
    expect(old.placeSource, 'catalog');
    expect(old.isTripPrivate, isFalse);
    final priv = TripNode.fromJson({...old.toJson(), 'place_source': 'trip_private'});
    expect(priv.isTripPrivate, isTrue);
    expect(TripNode.fromJson(priv.toJson()).placeSource, 'trip_private');
  });
}
