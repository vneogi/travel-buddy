// SPEC-46 What Now widget tests.
//
// Harness mirrors spec25_durable_threads_widget_test.dart:
//   - unique in-memory OfflineDatabase(testPath:), no initialize()
//   - _FakeConnectivity extends ConnectivityHelper; pass connectivityOverride
//   - mock TripRepository.getTrip; override tripRepoProvider,
//     offlineDatabaseProvider, identityCacheScopeProvider, tripEventProvider
//   - listen itineraryControllerProvider until loading is false
//   - tester.runAsync + _flushFfi; no pumpAndSettle

import 'dart:async';
import 'dart:convert';

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

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

class _MockTripRepository extends Mock implements TripRepository {}

class _MockTripEventService extends Mock implements TripEventService {}

class _FakeConnectivity extends ConnectivityHelper {
  final bool online;
  _FakeConnectivity({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const _scope = 'account:spec46-test';
const _tripId = 'trip-wn';
int _harnessCounter = 0;

TripNode _node({required DateTime start}) => TripNode(
      nodeId: 'n1',
      venueName: 'Context Temple',
      venueId: 'ctx-1',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['quiet', 'culture'],
      geoRegion: 'vientiane_laos',
      microLocation: 'nam_phou_fountain',
      lat: 17.96345,
      lng: 102.61112,
    );

AskResponse _whatNowResponse() => const AskResponse(
      answer: 'Found 2 options within reach: Wat Si Saket, Saffron Cafe.',
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.whatNow,
      sourceClass: 'curated_catalog',
      sourceIds: ['v1', 'v2'],
      whatNow: WhatNowResult(
        locationSource: 'trip_position',
        contextLabel: 'Using your trip position',
        candidates: [
          WhatNowCandidate(
            candidateId: 'what_now:v1',
            venueId: 'v1',
            name: 'Wat Si Saket',
            microLocationDisplay: 'nam_phou_fountain',
            category: 'temple',
            typicalDwellMinutes: 45,
            scheduledStart: '2026-10-02T11:05:00',
            reasonCodes: [
              'fits_available_window',
              'open_for_planned_time',
              'short_walk_from_context',
            ],
            unknownFields: ['price', 'live_crowds', 'traffic'],
          ),
          WhatNowCandidate(
            candidateId: 'what_now:v2',
            venueId: 'v2',
            name: 'Saffron Cafe',
            category: 'cafe',
            typicalDwellMinutes: 30,
            reasonCodes: ['fits_available_window'],
            unknownFields: ['price', 'live_crowds', 'traffic'],
          ),
        ],
      ),
    );

AskResponse _regionAnchorResponse() => const AskResponse(
      answer: 'Found 1 option: Wat Si Saket.',
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.whatNow,
      sourceClass: 'curated_catalog',
      sourceIds: ['v1'],
      whatNow: WhatNowResult(
        locationSource: 'region_anchor',
        contextLabel: 'Browsing in Vientiane',
        candidates: [
          WhatNowCandidate(
            candidateId: 'what_now:v1',
            venueId: 'v1',
            name: 'Wat Si Saket',
            reasonCodes: ['open_for_planned_time'],
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

/// Build harness inside tester.runAsync (FFI I/O).
Future<_Harness> _buildHarness({
  bool online = true,
  TripEventResult? nextResult,
  List<TripNode>? nodes,
}) async {
  final now = DateTime.now().toUtc();
  _harnessCounter++;
  final dbPath =
      'file:spec46_wn_$_harnessCounter?mode=memory&cache=shared';
  final realDb = OfflineDatabase(testPath: dbPath);

  final repo = _MockTripRepository();
  when(() => repo.getTrip(_tripId)).thenAnswer(
    (_) async => TripState(
      tripId: _tripId,
      userId: 'user-1',
      nodes: nodes ?? [_node(start: now.add(const Duration(hours: 1)))],
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

  final container = ProviderContainer(
    overrides: [
      tripRepoProvider.overrideWithValue(repo),
      offlineDatabaseProvider.overrideWithValue(realDb),
      identityCacheScopeProvider.overrideWithValue(_scope),
      tripEventProvider.overrideWithValue(mockService),
    ],
  );

  // Wait for itinerary to load.
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

/// Let FFI futures land, then pump. Polls until [until] matches.
Future<void> _flushFfi(
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

/// Scroll the widget into view, pump the animation forward, then tap.
Future<void> _tapKey(WidgetTester tester, String key) async {
  final finder = find.byKey(Key(key));
  await tester.ensureVisible(finder);
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(finder);
}

/// Tap the What Now entry, then advance the sheet-open animation.
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

TripEventResult _regionAnchorEventResult() => TripEventResult(
      message: '',
      updatedNodes: const [],
      routingTier: 'light',
      fromCache: false,
      askResponse: _regionAnchorResponse(),
    );

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() => registerFallbackValue(EventType.askInfo));

  // =========================================================================
  // 1. Defaults payload is 90 / normal / normal / anything
  // =========================================================================
  testWidgets(
    'defaults payload is 90 / normal / normal / anything',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(nextResult: _whatNowEventResult()),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);

      // Submit without changing chips -> defaults
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester); // drain persist

      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: 'What now?',
            preferences: captureAny(named: 'preferences'),
          )).captured;
      final prefs = captured.first as Map<String, dynamic>;
      expect(prefs['mode'], 'what_now');
      expect(prefs['available_minutes'], 90);
      expect(prefs['energy'], 'normal');
      expect(prefs['walking'], 'normal');
      expect(prefs['intent'], 'anything');

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 2. Chip changes produce the exact preferences map
  // =========================================================================
  testWidgets(
    'chip changes produce the exact preferences map',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(nextResult: _whatNowEventResult()),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);

      await _tapKey(tester, 'what_now_minutes_45');
      await tester.pump();
      await _tapKey(tester, 'what_now_energy_low');
      await tester.pump();
      await _tapKey(tester, 'what_now_walking_short');
      await tester.pump();
      await _tapKey(tester, 'what_now_intent_food');
      await tester.pump();

      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester); // drain persist

      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: 'What now?',
            preferences: captureAny(named: 'preferences'),
          )).captured;
      final prefs = captured.first as Map<String, dynamic>;
      expect(prefs['available_minutes'], 45);
      expect(prefs['energy'], 'low');
      expect(prefs['walking'], 'short');
      expect(prefs['intent'], 'food');

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 3. One submit causes one ask_info
  // =========================================================================
  testWidgets(
    'one submit causes one ask_info',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(nextResult: _whatNowEventResult()),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);

      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester); // drain persist

      verify(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).called(1);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 4. History reload renders WhatNowBubble without a second sendEvent
  // =========================================================================
  testWidgets(
    'history reload renders WhatNowBubble without a second sendEvent',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(nextResult: _whatNowEventResult()),
      );
      if (h == null) fail('harness null');

      // First session
      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));

      // Verify persisted
      final threads = await tester.runAsync(
        () => h.realDb.listAskThreads(
          identityScope: _scope,
          tripId: _tripId,
        ),
      );
      expect(threads, isNotNull);
      expect(threads!, isNotEmpty);
      final threadId = threads.first['thread_id'] as String;
      final messages = await tester.runAsync(
        () => h.realDb.loadAskMessages(
          threadId: threadId,
          identityScope: _scope,
        ),
      );
      expect(messages!.length, greaterThanOrEqualTo(2));
      final assistantMsg =
          messages.firstWhere((m) => m['role'] == 'assistant');
      final envelope =
          jsonDecode(assistantMsg['envelope_json'] as String);
      expect(envelope['what_now'], isNotNull);
      expect(envelope['what_now']['location_source'], 'trip_position');

      // Dispose and rebuild
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

      // Second session
      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(
        tester,
        until: find.byKey(const Key('what_now_bubble')),
      );
      expect(find.byKey(const Key('what_now_bubble')), findsOneWidget);

      // No sendEvent on history reload
      verifyZeroInteractions(h.mockService);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 5. View details opens display-only UI, no itinerary mutation
  // =========================================================================
  testWidgets(
    'View details opens display-only UI and causes no itinerary mutation',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(nextResult: _whatNowEventResult()),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester); // drain persist

      // Record itinerary state before tapping details
      final itState = h.container.read(
        itineraryControllerProvider(_tripId),
      );
      final nodesBefore = itState.nodes.length;

      expect(find.byKey(const Key('what_now_details_v1')), findsOneWidget);
      await _tapKey(tester, 'what_now_details_v1');
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      // Detail sheet visible
      expect(
        find.byKey(const Key('what_now_detail_sheet_v1')),
        findsOneWidget,
      );

      // Itinerary unchanged
      final itStateAfter = h.container.read(
        itineraryControllerProvider(_tripId),
      );
      expect(itStateAfter.nodes.length, nodesBefore);

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 6. Region anchor: omitted context_node_id, no "near you" / "nearby"
  // =========================================================================
  testWidgets(
    'region anchor: omitted context_node_id, no nearby wording',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(
          nextResult: _regionAnchorEventResult(),
          nodes: const [],
        ),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);

      await _tapKey(tester, 'what_now_submit');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester); // drain persist

      // Preferences must omit context_node_id
      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: 'What now?',
            preferences: captureAny(named: 'preferences'),
          )).captured;
      final prefs = captured.first as Map<String, dynamic>;
      expect(prefs.containsKey('context_node_id'), isFalse);

      // Rendered answer must not say "near you", "nearby", or distance
      expect(
        find.textContaining('nearby', findRichText: true),
        findsNothing,
      );
      expect(
        find.textContaining('near you', findRichText: true),
        findsNothing,
      );

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );

  // =========================================================================
  // 7. Offline submit refuses and enqueues nothing
  // =========================================================================
  testWidgets(
    'offline submit refuses and enqueues nothing',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(
        () => _buildHarness(
          nextResult: _whatNowEventResult(),
          online: false,
        ),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: _tripId,
            connectivityOverride: h.connectivity,
          ),
        ),
      ));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      await _openWhatNowSheet(tester);
      await _tapKey(tester, 'what_now_submit');
      await tester.pump();
      FocusManager.instance.primaryFocus?.unfocus();
      await _flushFfi(tester);

      verifyNever(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          ));

      // SPEC-25: offline refuse shown, thread has user row only
      expect(
        find.byKey(const Key('ask_offline_refuse')),
        findsOneWidget,
      );

      await _flushFfi(tester); // drain user persist

      final threads = await tester.runAsync(
        () => h.realDb.listAskThreads(
          identityScope: _scope,
          tripId: _tripId,
        ),
      );
      expect(threads, isNotNull);
      expect(threads!, isNotEmpty);

      final threadId = threads.first['thread_id'] as String;
      final messages = await tester.runAsync(
        () => h.realDb.loadAskMessages(
          threadId: threadId,
          identityScope: _scope,
        ),
      );
      expect(messages, isNotNull);
      final roles = messages!.map((m) => m['role'] as String).toList();
      expect(roles, equals(['user']));

      h.closeSubscription();
      h.container.dispose();
      await tester.runAsync(() => h.realDb.close());
    },
  );
}
