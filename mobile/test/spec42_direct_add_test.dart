// SPEC-42 empty-day catalog Add widget tests.
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

const _tripId = 'trip-dadd';
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
    testPath: 'file:spec42_dadd_$_harnessCounter?mode=memory&cache=shared',
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

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() => registerFallbackValue(EventType.addActivity));

  testWidgets('empty date renders keyed Add activity; populated date does not',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    await _pumpScreen(tester, h);
    expect(find.byKey(Key('empty_day_add_$_empty')), findsOneWidget);
    expect(find.byKey(Key('empty_day_add_$_populated')), findsNothing);
    expect(find.text('Open day'), findsOneWidget);
    await _teardown(tester, h);
  });

  testWidgets('slot selection calls add_candidates with exact date/slot',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    await _pumpScreen(tester, h);
    await _openAndPickDinner(tester);
    verify(() => h.repo.addCandidates(
          tripId: _tripId,
          targetDate: _empty,
          targetSlot: 'dinner',
        )).called(1);
    expect(find.byKey(const Key('direct_add_candidate_v-noodle')), findsOneWidget);
    await _tapKey(tester, 'direct_add_cancel');
    await _settle(tester);
    await _teardown(tester, h);
  });

  testWidgets('typed empty result shows server refusal copy',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(
      h.repo,
      AddCandidatesResult(
        targetDate: _empty,
        targetSlot: 'dinner',
        geoRegion: _region,
        refusalCode: 'hours',
        refusalCopy: 'Nothing that fits is open in that slot on this day.',
      ),
    );
    await _pumpScreen(tester, h);
    await _openAndPickDinner(tester);
    expect(find.byKey(const Key('direct_add_refusal')), findsOneWidget);
    expect(find.text('Nothing that fits is open in that slot on this day.'), findsOneWidget);
    await _tapKey(tester, 'direct_add_cancel');
    await _settle(tester);
    _verifyNoSend(h.repo);
    await _teardown(tester, h);
  });

  testWidgets('confirm sends one add_activity with exact direct_add preferences',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    final added = TripNode(
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
    );
    when(() => h.repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) async => TripEventResult(
          message: 'Added Noodle House.',
          updatedNodes: [...before, added],
          routingTier: 'light',
          fromCache: false,
        ));

    await _pumpScreen(tester, h);
    await _openAndPickDinner(tester);
    await _tapKey(tester, 'direct_add_candidate_v-noodle');
    await tester.pump();
    expect(find.byKey(const Key('direct_add_confirm_copy')), findsOneWidget);
    expect(find.textContaining('17:00'), findsWidgets);
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
    expect(captured, hasLength(1));
    expect(captured.single, {
      'mode': 'direct_add',
      'venue_id': 'v-noodle',
      'target_date': _empty,
      'target_slot': 'dinner',
    });

    final after = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    expect(after.length, before.length + 1);
    for (final n in before) {
      final m = after.firstWhere((x) => x.nodeId == n.nodeId);
      expect(m.scheduledStart, n.scheduledStart);
      expect(m.slotName, n.slotName);
    }
    expect(find.byKey(Key('empty_day_add_$_empty')), findsNothing);
    expect(
      find.byWidgetPredicate((w) => w is ActivityCard && w.node.nodeId == 'new-1'),
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
    await _openAndPickDinner(tester);
    await _tapKey(tester, 'direct_add_candidate_v-noodle');
    await tester.pump();
    await _tapKey(tester, 'direct_add_cancel');
    await _settle(tester);
    await _flushFfi(tester, maxRounds: 6);
    expect(find.byKey(const Key('direct_add_sheet_v1')), findsNothing);
    _verifyNoSend(h.repo);
    await _teardown(tester, h);
  });

  testWidgets('server refusal leaves the date empty and shows its message',
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
        )).thenAnswer((_) async =>
        throw const ValidationException('That slot already has an activity on this day.'));
    final before = h.container.read(itineraryControllerProvider(_tripId)).nodes;

    await _pumpScreen(tester, h);
    await _openAndPickDinner(tester);
    await _tapKey(tester, 'direct_add_candidate_v-noodle');
    await tester.pump();
    await _tapKey(tester, 'direct_add_confirm');
    await _settle(tester);
    await _flushFfi(tester, until: find.textContaining('already has an activity'));

    final after = h.container.read(itineraryControllerProvider(_tripId)).nodes;
    expect(after.map((n) => n.nodeId).toList(), before.map((n) => n.nodeId).toList());
    expect(find.byKey(Key('empty_day_add_$_empty')), findsOneWidget);
    await _teardown(tester, h);
  });

  testWidgets('offline tap opens nothing, sends nothing, shows offline copy',
      timeout: const Timeout(Duration(seconds: 30)), (tester) async {
    final h = await tester.runAsync(_buildHarness);
    if (h == null) fail('harness null');
    _stubCandidates(h.repo, _cands());
    await _pumpScreen(tester, h, online: false);
    await _tapKey(tester, 'empty_day_add_$_empty');
    await _settle(tester);
    await _flushFfi(tester, until: find.textContaining('Not available offline'));

    expect(find.byKey(const Key('direct_add_sheet_v1')), findsNothing);
    verifyNever(() => h.repo.addCandidates(
          tripId: any(named: 'tripId'),
          targetDate: any(named: 'targetDate'),
          targetSlot: any(named: 'targetSlot'),
        ));
    _verifyNoSend(h.repo);
    final pending = await tester.runAsync(() => h.db.getPendingBatch());
    expect(pending ?? const [], isEmpty);
    expect(h.container.read(itineraryControllerProvider(_tripId)).nodes, hasLength(2));
    await _teardown(tester, h);
  });

  test('AddCandidatesResult parses the closed DTO', () {
    final r = AddCandidatesResult.fromJson({
      'target_date': '2026-10-13',
      'target_slot': 'dinner',
      'geo_region': _region,
      'candidates': [
        {
          'venue_id': 'v1',
          'name': 'Example',
          'category': 'restaurant',
          'micro_location': 'Riverside',
          'vibe_tags': ['local'],
          'planned_start': '2026-10-13T17:00:00+07:00',
          'typical_dwell_minutes': 60,
        }
      ],
      'refusal_code': null,
      'refusal_copy': null,
    });
    expect(r.candidates.single.venueId, 'v1');
    expect(r.candidates.single.typicalDwellMinutes, 60);
    expect(r.refusalCode, isNull);
  });
}
