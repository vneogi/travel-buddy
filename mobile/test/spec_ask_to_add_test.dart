// Ask-to-Add widget tests.
// Harness mirrors spec46_what_now_test.dart / spec25_durable_threads_widget_test.dart.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/core/connectivity_helper.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/chat/chat_screen.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';

class _MockTripRepository extends Mock implements TripRepository {}
class _MockTripEventService extends Mock implements TripEventService {}

class _FakeConnectivity extends ConnectivityHelper {
  bool online;
  _FakeConnectivity({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

const _scope = 'account:ask-to-add-test';
const _tripId = 'trip-ata';
int _harnessCounter = 0;

TripNode _node({required DateTime start}) => TripNode(
      nodeId: 'n1',
      venueName: 'Context Temple',
      venueId: 'ctx-1',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['quiet'],
      geoRegion: 'vientiane_laos',
    );

AskResponse _whatNowResponse() => const AskResponse(
      answer: 'Found 1 option: Wat Si Saket.',
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.whatNow,
      sourceClass: 'curated_catalog',
      sourceIds: ['v1'],
      whatNow: WhatNowResult(
        locationSource: 'trip_position',
        contextLabel: 'Using your trip position',
        candidates: [
          WhatNowCandidate(
            candidateId: 'what_now:v1',
            venueId: 'v1',
            name: 'Wat Si Saket',
            category: 'temple',
            typicalDwellMinutes: 45,
            scheduledStart: '2026-10-02T11:05:00',
            reasonCodes: ['fits_available_window'],
            unknownFields: ['price'],
          ),
        ],
      ),
    );

typedef _Harness = ({
  ProviderContainer container,
  _MockTripEventService mockService,
  _FakeConnectivity connectivity,
  OfflineDatabase realDb,
  void Function() closeSubscription,
});

Future<_Harness> _buildHarness({
  bool online = true,
  TripEventResult? nextResult,
}) async {
  final now = DateTime.now().toUtc();
  _harnessCounter++;
  final dbPath = 'file:spec_ata_$_harnessCounter?mode=memory&cache=shared';
  final realDb = OfflineDatabase(testPath: dbPath);

  final repo = _MockTripRepository();
  when(() => repo.getTrip(_tripId)).thenAnswer(
    (_) async => TripState(
      tripId: _tripId,
      userId: 'user-1',
      nodes: [_node(start: now.add(const Duration(hours: 1)))],
    ),
  );

  final mockService = _MockTripEventService();
  when(() => mockService.sendEvent(
        tripId: any(named: 'tripId'),
        type: any(named: 'type'),
        message: any(named: 'message'),
        targetNodeId: any(named: 'targetNodeId'),
        preferences: any(named: 'preferences'),
      )).thenAnswer((_) async => nextResult);

  final connectivity = _FakeConnectivity(online: online);

  final container = ProviderContainer(overrides: [
    tripRepoProvider.overrideWithValue(repo),
    offlineDatabaseProvider.overrideWithValue(realDb),
    identityCacheScopeProvider.overrideWithValue(_scope),
    tripEventProvider.overrideWithValue(mockService),
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

  return (
    container: container,
    mockService: mockService,
    connectivity: connectivity,
    realDb: realDb,
    closeSubscription: sub.close,
  );
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
  final finder = find.byKey(Key(key));
  await tester.ensureVisible(finder);
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(finder);
}

Future<void> _openWhatNowSheet(WidgetTester tester) async {
  await tester.tap(find.byKey(const Key('what_now_entry')));
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 500));
  expect(find.byKey(const Key('what_now_submit')), findsOneWidget);
}

TripEventResult _whatNowEventResult() => TripEventResult(
      message: '',
      updatedNodes: const [],
      routingTier: 'light',
      fromCache: false,
      askResponse: _whatNowResponse(),
    );

TripEventResult _addSuccessResult() => const TripEventResult(
      message: 'Added Wat Si Saket to your plan.',
      updatedNodes: [],
      routingTier: 'light',
      fromCache: false,
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() {
    registerFallbackValue(EventType.askInfo);
    registerFallbackValue(EventType.addActivity);
  });

  // =========================================================================
  // 1. Live card shows Add to plan
  // =========================================================================
  testWidgets('live card shows Add to plan button', timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(nextResult: _whatNowEventResult()));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: h.connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));
      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester);

      expect(find.byKey(const Key('what_now_add_v1')), findsOneWidget);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 2. Confirm sends one add_activity with exact preferences
  // =========================================================================
  testWidgets('confirm sends add_activity with preferences', timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      // First sendEvent returns what_now, second returns add success
      var callCount = 0;
      final h = await tester.runAsync(() => _buildHarness(nextResult: _whatNowEventResult()));
      if (h == null) fail('harness null');

      // After what_now loads, reconfigure mock for add_activity
      when(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: EventType.addActivity,
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _addSuccessResult());

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: h.connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));
      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester);

      // Tap Add to plan
      await _tapKey(tester, 'what_now_add_v1');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Confirm dialog
      expect(find.byKey(const Key('ask_to_add_confirm_dialog')), findsOneWidget);
      await tester.tap(find.byKey(const Key('ask_to_add_confirm')));
      await _flushFfi(tester);

      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.addActivity,
            message: any(named: 'message'),
            preferences: captureAny(named: 'preferences'),
          )).captured;
      expect(captured, isNotEmpty);
      final prefs = captured.first as Map<String, dynamic>;
      expect(prefs['mode'], 'ask_to_add');
      expect(prefs['venue_id'], 'v1');
      expect(prefs['candidate_id'], 'what_now:v1');

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 3. Cancel sends nothing
  // =========================================================================
  testWidgets('cancel sends nothing', timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(nextResult: _whatNowEventResult()));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: h.connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));
      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester);

      // Reset mock to track only add_activity
      reset(h.mockService);
      when(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _addSuccessResult());

      await _tapKey(tester, 'what_now_add_v1');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byKey(const Key('ask_to_add_cancel')), findsOneWidget);
      await tester.tap(find.byKey(const Key('ask_to_add_cancel')));
      await tester.pump();
      await _flushFfi(tester);

      verifyZeroInteractions(h.mockService);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 4. History card has no Add to plan
  // =========================================================================
  testWidgets('history card has no Add to plan', timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(nextResult: _whatNowEventResult()));
      if (h == null) fail('harness null');

      // First session: submit what now
      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: h.connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));
      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester);

      // Dispose and rebuild (history reload)
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();
      reset(h.mockService);
      when(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _whatNowEventResult());

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: h.connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));

      // History card: no Add to plan button
      expect(find.byKey(const Key('what_now_add_v1')), findsNothing);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 5. Offline confirm refuses and enqueues nothing
  // =========================================================================
  testWidgets('offline confirm refuses and enqueues nothing', timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      // Online for what_now, then goes offline for add
      final connectivity = _FakeConnectivity(online: true);
      final h = await tester.runAsync(() => _buildHarness(nextResult: _whatNowEventResult()));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));
      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester);

      // Go offline
      connectivity.online = false;

      reset(h.mockService);
      when(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _addSuccessResult());

      await _tapKey(tester, 'what_now_add_v1');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.tap(find.byKey(const Key('ask_to_add_confirm')));
      await _flushFfi(tester);

      expect(find.byKey(const Key('ask_offline_refuse')), findsOneWidget);
      verifyZeroInteractions(h.mockService);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 6. View details still does not mutate
  // =========================================================================
  testWidgets('View details does not mutate itinerary', timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(nextResult: _whatNowEventResult()));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(home: ChatScreen(tripId: _tripId, connectivityOverride: h.connectivity)),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));
      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester);

      final nodesBefore = h.container.read(itineraryControllerProvider(_tripId)).nodes.length;

      await tester.tap(find.byKey(const Key('what_now_details_v1')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(find.byKey(const Key('what_now_detail_sheet_v1')), findsOneWidget);
      expect(h.container.read(itineraryControllerProvider(_tripId)).nodes.length, nodesBefore);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );
}
