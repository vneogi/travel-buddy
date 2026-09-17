// SPEC-25 Ask envelope: fail-closed parsing, AskBubble rendering, and
// ChatScreen integration. Tests fail if AskBubble is removed, if FactView
// hedge/refuse templates leak back in, or if Chat stops delegating correctly.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
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

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockTripEventService extends Mock implements TripEventService {}

class _FakeConnectivityHelper extends ConnectivityHelper {
  final bool online;
  _FakeConnectivityHelper({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

void _stubDatabase(_MockOfflineDatabase database) {
  when(() => database.getLovedPlaceRefs(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.getNodeOutcomes(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String, NodeOutcome>{});
  when(() => database.cachePlace(any(), any())).thenAnswer((_) async {});
  when(() => database.cacheTrip(any(), any())).thenAnswer((_) async {});
  when(() => database.getCachedTrip(any())).thenAnswer((_) async => null);
  when(() => database.pruneAlertData()).thenAnswer((_) async {});
  when(() => database.getDismissedAlertIds(
        identityScope: any(named: 'identityScope'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.upsertNodeOutcome(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
        nodeId: any(named: 'nodeId'),
        outcome: any(named: 'outcome'),
        reason: any(named: 'reason'),
        recordedAt: any(named: 'recordedAt'),
      )).thenAnswer((_) async {});
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

AskResponse _hours() => const AskResponse(
      answer: 'Ban Anou Night Market hours: Mon 17:00-23:00.',
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.openingHours,
      sourceClass: 'curated_catalog',
    );

AskResponse _dish() => const AskResponse(
      answer: 'Khao Piak Sen is a Lao noodle soup.',
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.dishFact,
      sourceClass: 'curated_catalog',
      foodDisclaimer: 'Menus change; confirm ingredients with the venue.',
    );

AskResponse _refuse() => const AskResponse(
      answer: 'I can only help with trip-related questions.',
      tier: AskTier.refuse,
      path: AskPath.outOfScope,
      intent: AskResponseIntent.outOfScope,
    );

AskResponse _planChange() => const AskResponse(
      answer: 'I can swap that activity for you.',
      tier: AskTier.defer_,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.planChange,
      proposal: AskProposal(
        eventType: ProposalEventType.swapActivity,
        targetNodeId: 'node-42',
        summary: 'Swap Wat Xieng Thong for Kuang Si Falls',
      ),
    );

TripNode _node({
  required String id,
  required String name,
  required DateTime start,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      venueId: '$id-ref',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

/// Chat integration harness: mock sendEvent, injectable connectivity.
class _ChatHarness {
  final ProviderContainer container;
  final _MockTripEventService mockService;
  final _FakeConnectivityHelper connectivity;
  final void Function() _closeSubscription;

  _ChatHarness._({
    required this.container,
    required this.mockService,
    required this.connectivity,
    required void Function() closeSubscription,
  }) : _closeSubscription = closeSubscription;

  static Future<_ChatHarness> create({
    bool online = true,
    TripEventResult? nextResult,
  }) async {
    final now = DateTime.now().toUtc();
    final db = _MockOfflineDatabase();
    _stubDatabase(db);
    final repo = _MockTripRepository();
    when(() => repo.getTrip('test')).thenAnswer(
      (_) async => TripState(
        tripId: 'test',
        userId: 'user-1',
        nodes: [
          _node(
            id: 'n1',
            name: 'Test Stop',
            start: now.add(const Duration(hours: 1)),
          ),
        ],
      ),
    );

    final mockService = _MockTripEventService();
    when(() => mockService.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
        )).thenAnswer((_) async => nextResult);

    final connectivity = _FakeConnectivityHelper(online: online);

    final container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repo),
        offlineDatabaseProvider.overrideWithValue(db),
        identityCacheScopeProvider.overrideWithValue('account:test'),
        tripEventProvider.overrideWithValue(mockService),
      ],
    );

    final loaded = Completer<void>();
    final sub = container.listen(
      itineraryControllerProvider('test'),
      (_, next) {
        if (!next.loading && !loaded.isCompleted) loaded.complete();
      },
      fireImmediately: true,
    );
    await loaded.future;

    return _ChatHarness._(
      container: container,
      mockService: mockService,
      connectivity: connectivity,
      closeSubscription: sub.close,
    );
  }

  Future<void> pump(WidgetTester tester) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(
          home: ChatScreen(
            tripId: 'test',
            connectivityOverride: connectivity,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  Future<void> send(WidgetTester tester, String text) async {
    await tester.enterText(find.byType(TextField), text);
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pump();
    await tester.pump();
    await tester.pump();
  }

  void dispose() {
    _closeSubscription();
    container.dispose();
  }
}

void main() {
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  // =========================================================================
  // 1. Fail-closed parsing: missing/unknown path, intent, tier, event_type.
  // =========================================================================
  group('AskResponse.fromJson fail-closed', () {
    test('missing path throws', () {
      expect(
        () => AskResponse.fromJson({
          'answer': 'x',
          'tier': 'hedge',
          'intent': 'opening_hours',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('empty intent throws', () {
      expect(
        () => AskResponse.fromJson({
          'answer': 'x',
          'tier': 'hedge',
          'path': 'grounded_deterministic',
          'intent': '',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('missing tier throws', () {
      expect(
        () => AskResponse.fromJson({
          'answer': 'x',
          'path': 'grounded_deterministic',
          'intent': 'opening_hours',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('unknown path throws', () {
      expect(
        () => AskPath.fromWire('totally_unknown'),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('unknown intent throws', () {
      expect(
        () => AskResponseIntent.fromWire('made_up'),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('unknown proposal event_type throws', () {
      expect(
        () => ProposalEventType.fromWire('teleport'),
        throwsA(isA<ArgumentError>()),
      );
    });
  });

  // =========================================================================
  // 2. AskBubble: answer verbatim, no hedge template, caption, no disclaimer.
  // =========================================================================
  group('AskBubble hours', () {
    testWidgets('shows answer text without hedge template', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _hours())));
      expect(find.text(_hours().answer), findsOneWidget);
      expect(find.textContaining('Travellers usually say'), findsNothing);
      expect(find.byKey(const Key('ask_fact_view')), findsOneWidget);
      expect(find.text('curated_catalog'), findsOneWidget);
      expect(find.textContaining('Menus change'), findsNothing);
    });
  });

  // =========================================================================
  // 3. Dish disclaimer gated on intent.
  // =========================================================================
  group('AskBubble dish disclaimer', () {
    testWidgets('dish_fact shows food_disclaimer', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _dish())));
      expect(find.text(_dish().answer), findsOneWidget);
      expect(
        find.text('Menus change; confirm ingredients with the venue.'),
        findsOneWidget,
      );
    });

    testWidgets('hours fixture does NOT show disclaimer', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _hours())));
      expect(find.textContaining('Menus change'), findsNothing);
    });
  });

  // =========================================================================
  // 4. Refuse: backend answer visible, no generic copy.
  // =========================================================================
  group('AskBubble refuse', () {
    testWidgets('shows backend answer, not generic refuse', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _refuse())));
      expect(find.text(_refuse().answer), findsOneWidget);
      expect(find.text('Information not available'), findsNothing);
    });
  });

  // =========================================================================
  // 5. Plan-change AskBubble: ConfirmAffordance, dismiss, no-proposal.
  // =========================================================================
  group('AskBubble plan-change', () {
    testWidgets('confirm affordance present and tappable', (tester) async {
      var confirmed = false;
      await tester.pumpWidget(_wrap(
        AskBubble(
          askResponse: _planChange(),
          onConfirm: () => confirmed = true,
        ),
      ));
      expect(
        find.byKey(const Key('ask_plan_change_confirm')),
        findsOneWidget,
      );
      expect(find.byType(ConfirmAffordance), findsOneWidget);
      await tester.tap(find.text('Confirm'));
      expect(confirmed, isTrue);
    });

    testWidgets('dismiss does not fire onConfirm', (tester) async {
      var confirmed = false;
      await tester.pumpWidget(_wrap(
        AskBubble(
          askResponse: _planChange(),
          onConfirm: () => confirmed = true,
          onDismiss: () {},
        ),
      ));
      await tester.tap(find.byIcon(Icons.close));
      expect(confirmed, isFalse);
    });

    testWidgets('plan_change without proposal has no confirm', (tester) async {
      const noProposal = AskResponse(
        answer: 'Which activity do you mean?',
        tier: AskTier.defer_,
        path: AskPath.groundedDeterministic,
        intent: AskResponseIntent.planChange,
      );
      await tester.pumpWidget(
        _wrap(const AskBubble(askResponse: noProposal)),
      );
      expect(find.byType(ConfirmAffordance), findsNothing);
      expect(find.text('Which activity do you mean?'), findsOneWidget);
    });
  });

  // =========================================================================
  // 6. ChatScreen: ask_info -> AskBubble in tree.
  // =========================================================================
  group('ChatScreen ask_info', () {
    testWidgets('ask_info renders AskBubble with answer', (tester) async {
      final harness = await _ChatHarness.create(
        nextResult: TripEventResult(
          message: '',
          updatedNodes: const [],
          routingTier: 'light',
          fromCache: false,
          askResponse: _hours(),
        ),
      );
      await harness.pump(tester);
      await harness.send(tester, 'What time does it open?');

      expect(find.byType(AskBubble), findsOneWidget);
      expect(find.text(_hours().answer), findsOneWidget);
      expect(find.byKey(const Key('ask_fact_view')), findsOneWidget);

      harness.dispose();
    });

    testWidgets('ask_info + null envelope shows failure copy', (tester) async {
      final harness = await _ChatHarness.create(
        nextResult: const TripEventResult(
          message: 'stale fallback',
          updatedNodes: [],
          routingTier: 'light',
          fromCache: false,
          // askResponse intentionally null
        ),
      );
      await harness.pump(tester);
      await harness.send(tester, 'What time does it open?');

      expect(find.byType(AskBubble), findsNothing);
      expect(find.textContaining('could not complete'), findsOneWidget);
      // Must NOT show result.message as a successful fact.
      expect(find.text('stale fallback'), findsNothing);

      harness.dispose();
    });
  });

  // =========================================================================
  // 7. ChatScreen offline: sendEvent NOT called, refuse widget shown.
  // =========================================================================
  group('ChatScreen offline', () {
    testWidgets('offline blocks sendEvent and shows refuse', (tester) async {
      final harness = await _ChatHarness.create(online: false);
      await harness.pump(tester);
      await harness.send(tester, 'What time does it open?');

      expect(find.byKey(const Key('ask_offline_refuse')), findsOneWidget);
      verifyNever(() => harness.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
          ));

      harness.dispose();
    });
  });

  // =========================================================================
  // 8. ChatScreen plan-change confirm: sendEvent with correct args.
  // =========================================================================
  group('ChatScreen plan-change confirm', () {
    testWidgets(
      'confirm sends EventType.swapActivity with original text and targetNodeId',
      (tester) async {
        final harness = await _ChatHarness.create(
          nextResult: TripEventResult(
            message: '',
            updatedNodes: const [],
            routingTier: 'light',
            fromCache: false,
            askResponse: _planChange(),
          ),
        );
        await harness.pump(tester);
        await harness.send(tester, 'replace next stop with a museum');

        // AskBubble with confirm is present.
        expect(find.byType(ConfirmAffordance), findsOneWidget);

        // Tap Confirm.
        await tester.tap(find.text('Confirm'));
        await tester.pump();
        await tester.pump();

        // Verify second sendEvent used the original text, not proposal.summary.
        final captured = verify(() => harness.mockService.sendEvent(
              tripId: captureAny(named: 'tripId'),
              type: captureAny(named: 'type'),
              message: captureAny(named: 'message'),
              targetNodeId: captureAny(named: 'targetNodeId'),
            )).captured;
        // Two calls: first askInfo, second swapActivity.
        expect(captured.length, 8); // 4 named args x 2 calls
        // Second call (indices 4-7): type, message, targetNodeId.
        expect(captured[5], EventType.swapActivity);
        expect(captured[6], 'replace next stop with a museum');
        expect(captured[7], 'node-42');

        harness.dispose();
      },
    );
  });
}
