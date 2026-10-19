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
  // SPEC-25 Phase C: Ask thread stubs.
  when(() => database.getMostRecentAskThread(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => null);
  when(() => database.loadAskMessages(
        threadId: any(named: 'threadId'),
        identityScope: any(named: 'identityScope'),
      )).thenAnswer((_) async => <Map<String, dynamic>>[]);
  when(() => database.createAskThread(
        threadId: any(named: 'threadId'),
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
        title: any(named: 'title'),
        createdAt: any(named: 'createdAt'),
      )).thenAnswer((_) async {});
  when(() => database.insertAskMessage(
        messageId: any(named: 'messageId'),
        threadId: any(named: 'threadId'),
        role: any(named: 'role'),
        text: any(named: 'text'),
        envelopeJson: any(named: 'envelopeJson'),
        createdAt: any(named: 'createdAt'),
      )).thenAnswer((_) async {});
  when(() => database.listAskThreads(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <Map<String, dynamic>>[]);
  when(() => database.deleteAskThread(
        threadId: any(named: 'threadId'),
        identityScope: any(named: 'identityScope'),
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

/// Plan-change with empty targetNodeId: confirm must fall back to
/// nextMovableStop (harness node 'n1').
AskResponse _planChangeEmptyTarget() => const AskResponse(
      answer: 'I can swap that activity for you.',
      tier: AskTier.defer_,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.planChange,
      proposal: AskProposal(
        eventType: ProposalEventType.swapActivity,
        targetNodeId: '',
        summary: 'Swap for a museum',
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
  // 8. ChatScreen plan-change confirm with empty target -> fallback to n1.
  // =========================================================================
  group('ChatScreen plan-change confirm', () {
    testWidgets(
      'confirm with empty target falls back to nextMovableStop',
      (tester) async {
        // 'Is there a museum nearby?' classifies as AskIntent.question.
        // Backend returns plan_change with EMPTY targetNodeId.
        final harness = await _ChatHarness.create(
          nextResult: TripEventResult(
            message: '',
            updatedNodes: const [],
            routingTier: 'light',
            fromCache: false,
            askResponse: _planChangeEmptyTarget(),
          ),
        );
        await harness.pump(tester);
        await harness.send(tester, 'Is there a museum nearby?');

        // AskBubble with confirm is present.
        expect(find.byType(ConfirmAffordance), findsOneWidget);

        // Tap Confirm.
        await tester.tap(find.text('Confirm'));
        await tester.pump();
        await tester.pump();

        // Verify both sendEvent calls.
        final captured = verify(() => harness.mockService.sendEvent(
              tripId: captureAny(named: 'tripId'),
              type: captureAny(named: 'type'),
              message: captureAny(named: 'message'),
              targetNodeId: captureAny(named: 'targetNodeId'),
            )).captured;
        // Two calls: first askInfo, second swapActivity (4 args each).
        expect(captured.length, 8);
        // First call: askInfo sends target 'n1' (not null).
        expect(captured[1], EventType.askInfo);
        expect(captured[3], 'n1');
        // Second call: swapActivity, original text, fallback 'n1'.
        expect(captured[5], EventType.swapActivity);
        expect(captured[6], 'Is there a museum nearby?');
        expect(captured[7], 'n1');

        harness.dispose();
      },
    );
  });

  // =========================================================================
  // 9. ChatScreen dismiss: removes proposal entry, no sendEvent.
  // =========================================================================
  group('ChatScreen dismiss', () {
    testWidgets('dismiss removes proposal entry from chat', (tester) async {
      final harness = await _ChatHarness.create(
        nextResult: TripEventResult(
          message: '',
          updatedNodes: const [],
          routingTier: 'light',
          fromCache: false,
          askResponse: _planChangeEmptyTarget(),
        ),
      );
      await harness.pump(tester);
      await harness.send(tester, 'Is there a museum nearby?');

      // Proposal is visible.
      expect(find.byType(ConfirmAffordance), findsOneWidget);
      expect(find.byKey(const Key('ask_plan_change_confirm')), findsOneWidget);

      // Tap dismiss (X icon).
      await tester.tap(find.byIcon(Icons.close));
      await tester.pump();

      // Proposal entry removed from chat.
      expect(find.byType(ConfirmAffordance), findsNothing);
      expect(find.byKey(const Key('ask_plan_change_confirm')), findsNothing);

      // Only the first sendEvent (askInfo) happened; no confirm call.
      verify(() => harness.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
          )).called(1);

      harness.dispose();
    });
  });

  // SPEC-46: WhatNow parse / serialize contract
  group('SPEC-46 what_now contract', () {
    test('WhatNowCandidate round-trips through JSON', () {
      final json = {
        'candidate_id': 'what_now:v1', 'venue_id': 'v1',
        'name': 'Wat Si Saket', 'micro_location_display': 'nam_phou_fountain',
        'category': 'temple', 'typical_dwell_minutes': 45,
        'scheduled_start': '2026-10-02T11:05:00',
        'reason_codes': ['fits_available_window', 'open_for_planned_time'],
        'unknown_fields': ['price', 'live_crowds'],
      };
      final c = WhatNowCandidate.fromJson(json);
      expect(c.candidateId, 'what_now:v1');
      expect(c.venueId, 'v1');
      expect(c.typicalDwellMinutes, 45);
      expect(c.reasonCodes, hasLength(2));
      final out = c.toJson();
      expect(out['candidate_id'], 'what_now:v1');
    });

    test('WhatNowResult round-trips through JSON', () {
      final json = {
        'location_source': 'trip_position',
        'context_label': 'Using your trip position',
        'candidates': [{'candidate_id': 'what_now:v1', 'venue_id': 'v1',
                         'name': 'Wat', 'reason_codes': ['fits_available_window'],
                         'unknown_fields': ['price']}],
      };
      final r = WhatNowResult.fromJson(json);
      expect(r.locationSource, 'trip_position');
      expect(r.candidates, hasLength(1));
      final out = r.toJson();
      expect((out['candidates'] as List).first['venue_id'], 'v1');
    });

    test('AskResponse.whatNow parsed from envelope JSON', () {
      final json = {
        'answer': 'Found 1 option', 'tier': 'hedge', 'path': 'grounded_deterministic', 'intent': 'what_now',
        'what_now': {
          'location_source': 'region_anchor',
          'context_label': 'Browsing in Vientiane',
          'candidates': [{'candidate_id': 'what_now:v1', 'venue_id': 'v1',
                           'name': 'Cafe', 'reason_codes': [],
                           'unknown_fields': ['price']}],
        },
      };
      final resp = AskResponse.fromJson(json);
      expect(resp.intent, AskResponseIntent.whatNow);
      expect(resp.whatNow, isNotNull);
      expect(resp.whatNow!.locationSource, 'region_anchor');
      final out = resp.toJson();
      expect(out['what_now']['location_source'], 'region_anchor');
    });

    test('AskResponse.whatNow null when absent', () {
      final json = {'answer': 'Hello', 'tier': 'hedge', 'path': 'grounded_deterministic', 'intent': 'place_identity'};
      final resp = AskResponse.fromJson(json);
      expect(resp.whatNow, isNull);
      expect(resp.toJson().containsKey('what_now'), isFalse);
    });
  });
}
