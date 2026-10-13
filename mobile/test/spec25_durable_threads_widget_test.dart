// SPEC-25 Phase C: ChatScreen widget tests for durable threads.
//
// These tests combine a real sqflite_ffi OfflineDatabase with mocked
// providers to verify persist round-trip, offline reopen, proposal
// safety, and offline refusal behavior.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';
import 'package:travel_buddy/core/connectivity_helper.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/chat/ask_bubble.dart';
import 'package:travel_buddy/features/chat/chat_screen.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/render/confirm_affordance.dart';

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

const _scope = 'account:widget-test';
const _tripId = 'trip-widget';

TripNode _node({
  String id = 'n1',
  String name = 'Test Venue',
  required DateTime start,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      venueId: 'v-$id',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      geoRegion: 'luang_prabang_laos',
    );

AskResponse _groundedHours() => const AskResponse(
      answer: 'Ban Anou Night Market opens 17:00-23:00.',
      tier: AskTier.assert_,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.openingHours,
      sourceIds: ['lp-v1'],
      sourceClass: 'curated_catalog',
    );

AskResponse _planChangeProposal() => const AskResponse(
      answer: 'I can swap that for Saffron Coffee.',
      tier: AskTier.defer_,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.planChange,
      proposal: AskProposal(
        eventType: ProposalEventType.swapActivity,
        targetNodeId: 'n1',
        summary: 'Swap to Saffron Coffee',
      ),
    );

/// Build a ProviderContainer with real OfflineDatabase and mocked services.
Future<
    ({
      ProviderContainer container,
      _MockTripEventService mockService,
      _FakeConnectivity connectivity,
      OfflineDatabase realDb,
      void Function() closeSubscription,
    })> _buildHarness({
  bool online = true,
  TripEventResult? nextResult,
}) async {
  final now = DateTime.now().toUtc();
  final realDb = OfflineDatabase(testPath: inMemoryDatabasePath);

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

Future<void> _pumpChat(
  WidgetTester tester, {
  required ProviderContainer container,
  required _FakeConnectivity connectivity,
  String? threadId,
}) async {
  await tester.pumpWidget(
    UncontrolledProviderScope(
      container: container,
      child: MaterialApp(
        home: ChatScreen(
          tripId: _tripId,
          connectivityOverride: connectivity,
          threadId: threadId,
        ),
      ),
    ),
  );
  // Pump several frames for initState + _loadThread future.
  await tester.pump();
  await tester.pump();
  await tester.pump();
  await tester.pump();
}

Future<void> _sendMessage(WidgetTester tester, String text) async {
  await tester.enterText(find.byType(TextField), text);
  await tester.tap(find.byIcon(Icons.send_rounded));
  await tester.pump();
  await tester.pump();
  await tester.pump();
  await tester.pump();
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() => registerFallbackValue(EventType.askInfo));

  // =========================================================================
  // 1. Persist round-trip: sendEvent called exactly once.
  // =========================================================================
  testWidgets(
    'persist round-trip: question + answer survive dispose; sendEvent once',
    (tester) async {
      final h = await _buildHarness(
        nextResult: TripEventResult(
          message: '',
          updatedNodes: const [],
          routingTier: 'light',
          fromCache: false,
          askResponse: _groundedHours(),
        ),
      );

      // First session: send a question.
      await _pumpChat(tester,
          container: h.container, connectivity: h.connectivity);
      await _sendMessage(tester, 'What time does it open?');

      expect(find.byType(AskBubble), findsOneWidget);
      expect(find.text(_groundedHours().answer), findsOneWidget);

      // Dispose the widget (simulates leaving Chat).
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();

      // Verify sendEvent was called exactly once.
      verify(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
          )).called(1);

      // Second session: rebuild ChatScreen for the same trip.
      // It should load persisted messages without calling sendEvent.
      await _pumpChat(tester,
          container: h.container, connectivity: h.connectivity);
      await tester.pump();
      await tester.pump();

      // The user question and AskBubble answer should be visible.
      expect(find.text('What time does it open?'), findsOneWidget);
      expect(find.byType(AskBubble), findsOneWidget);
      expect(find.text(_groundedHours().answer), findsOneWidget);

      // No additional sendEvent calls.
      verifyNoMoreInteractions(h.mockService);

      h.closeSubscription();
      h.container.dispose();
      await h.realDb.close();
    },
  );

  // =========================================================================
  // 2. Reopen with network offline: history renders, no crash, no sendEvent.
  // =========================================================================
  testWidgets(
    'offline reopen: history renders without network, no sendEvent',
    (tester) async {
      final h = await _buildHarness(
        nextResult: TripEventResult(
          message: '',
          updatedNodes: const [],
          routingTier: 'light',
          fromCache: false,
          askResponse: _groundedHours(),
        ),
      );

      // First session online: send a question.
      await _pumpChat(tester,
          container: h.container, connectivity: h.connectivity);
      await _sendMessage(tester, 'What time does it open?');
      expect(find.byType(AskBubble), findsOneWidget);

      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();
      reset(h.mockService);

      // Second session: switch connectivity to offline.
      final offlineConn = _FakeConnectivity(online: false);
      await tester.pumpWidget(
        UncontrolledProviderScope(
          container: h.container,
          child: MaterialApp(
            home: ChatScreen(
              tripId: _tripId,
              connectivityOverride: offlineConn,
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump();
      await tester.pump();
      await tester.pump();

      // History still renders.
      expect(find.text('What time does it open?'), findsOneWidget);
      expect(find.byType(AskBubble), findsOneWidget);

      // No sendEvent called during offline reopen.
      verifyZeroInteractions(h.mockService);

      h.closeSubscription();
      h.container.dispose();
      await h.realDb.close();
    },
  );

  // =========================================================================
  // 3. History-loaded proposal has no confirm callback (fromHistory).
  // =========================================================================
  testWidgets(
    'history-loaded proposal renders but confirm does not call sendEvent',
    (tester) async {
      final h = await _buildHarness(
        nextResult: TripEventResult(
          message: '',
          updatedNodes: const [],
          routingTier: 'light',
          fromCache: false,
          askResponse: _planChangeProposal(),
        ),
      );

      // First session: send a question that gets a plan-change proposal.
      await _pumpChat(tester,
          container: h.container, connectivity: h.connectivity);
      await _sendMessage(tester, 'Is there a cafe nearby?');
      expect(find.byType(AskBubble), findsOneWidget);

      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();
      reset(h.mockService);

      // Second session: load from history.
      await _pumpChat(tester,
          container: h.container, connectivity: h.connectivity);
      await tester.pump();
      await tester.pump();

      // Proposal bubble renders.
      expect(find.byType(AskBubble), findsOneWidget);
      expect(find.text(_planChangeProposal().answer), findsOneWidget);

      // ConfirmAffordance should NOT be present (fromHistory disables it).
      expect(find.byType(ConfirmAffordance), findsNothing);

      // No sendEvent.
      verifyZeroInteractions(h.mockService);

      h.closeSubscription();
      h.container.dispose();
      await h.realDb.close();
    },
  );

  // =========================================================================
  // 4. Offline new question shows refusal and writes no assistant row.
  // =========================================================================
  testWidgets(
    'offline question shows refusal; no assistant row persisted',
    (tester) async {
      final h = await _buildHarness(online: false);

      await _pumpChat(tester,
          container: h.container, connectivity: h.connectivity);
      await _sendMessage(tester, 'What time does it open?');

      // Offline refusal shown.
      expect(find.byKey(const Key('ask_offline_refuse')), findsOneWidget);

      // sendEvent never called.
      verifyNever(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
          ));

      // Verify via real DB: user message exists but no assistant row.
      final threads = await h.realDb.listAskThreads(
        identityScope: _scope,
        tripId: _tripId,
      );
      expect(threads, isNotEmpty, reason: 'Thread should exist');
      final threadId = threads.first['thread_id'] as String;
      final msgs = await h.realDb.loadAskMessages(
        threadId: threadId,
        identityScope: _scope,
      );
      expect(msgs.length, 1, reason: 'Only user message persisted');
      expect(msgs.first['role'], 'user');
      expect(
        msgs.where((m) => m['role'] == 'assistant').length,
        0,
        reason: 'Offline refusal must not be persisted as assistant',
      );

      h.closeSubscription();
      h.container.dispose();
      await h.realDb.close();
    },
  );
}
