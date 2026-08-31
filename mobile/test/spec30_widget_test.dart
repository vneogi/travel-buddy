import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/chat/chat_screen.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockSignalService extends Mock implements SignalService {}

TripNode _node({
  required String id,
  required String name,
  required DateTime start,
  int durationMinutes = 60,
  bool locked = false,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      venueId: '$id-ref',
      scheduledStart: start,
      durationMinutes: durationMinutes,
      isLocked: locked,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

TripEventResult _result(List<TripNode> nodes) => TripEventResult(
      message: 'Done',
      updatedNodes: nodes,
      routingTier: 'heavy',
      fromCache: false,
    );

void _stubDatabase(
  _MockOfflineDatabase database, {
  Map<String, NodeOutcome> outcomes = const {},
}) {
  when(() => database.getLovedPlaceRefs(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.getNodeOutcomes(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => outcomes);
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

void main() {
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  group('itinerary outcome controls', () {
    testWidgets('elapsed and future cards expose the correct controls',
        (tester) async {
      final now = DateTime.utc(2026, 8, 31, 12);
      final elapsed = _node(
        id: 'elapsed',
        name: 'Elapsed Museum',
        start: now.subtract(const Duration(hours: 2)),
      );
      final future = _node(
        id: 'future',
        name: 'Future Museum',
        start: now.add(const Duration(hours: 2)),
      );

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: ListView(
              children: [
                ActivityCard(
                  node: elapsed,
                  now: now,
                  onTapRecordOutcome: () {},
                ),
                ActivityCard(
                  node: future,
                  now: now,
                  onTapRecordOutcome: () {},
                ),
              ],
            ),
          ),
        ),
      );

      expect(find.text('Did this happen?'), findsOneWidget);
      expect(find.text('Elapsed Museum'), findsOneWidget);
      expect(find.text('Future Museum'), findsOneWidget);
    });

    testWidgets('visited selection displays a textual overlay', (tester) async {
      final harness = await _ItineraryHarness.create(
        _node(
          id: 'elapsed',
          name: 'Museum',
          start: DateTime.now().toUtc().subtract(const Duration(hours: 2)),
        ),
      );
      addTearDown(harness.dispose);
      await harness.pump(tester);

      await tester.tap(find.text('Did this happen?'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Yes, I went'));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 250));

      expect(find.text('Visited'), findsOneWidget);
      expect(harness.node.status, NodeStatus.pending);
    });

    testWidgets('skipped selection requires a reason and displays it',
        (tester) async {
      final harness = await _ItineraryHarness.create(
        _node(
          id: 'elapsed',
          name: 'Museum',
          start: DateTime.now().toUtc().subtract(const Duration(hours: 2)),
        ),
      );
      addTearDown(harness.dispose);
      await harness.pump(tester);

      await tester.tap(find.text('Did this happen?'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('No, I skipped it'));
      await tester.pumpAndSettle();
      expect(find.text('Why are you skipping?'), findsOneWidget);
      await tester.ensureVisible(find.text('Bad weather'));
      await tester.tap(find.text('Bad weather'));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump(const Duration(milliseconds: 250));

      expect(find.text('Skipped: Bad weather'), findsOneWidget);
      expect(harness.node.status, NodeStatus.pending);
    });
  });

  group('cancel-next confirmation', () {
    late _ChatHarness harness;

    tearDown(() => harness.dispose());

    testWidgets('confirmation names the outcome-aware selected venue',
        (tester) async {
      harness = await _ChatHarness.create(acknowledgeFirst: true);
      await harness.pump(tester);

      await harness.send(tester, 'cancel next stop');

      expect(find.text('Cancel this stop?'), findsOneWidget);
      expect(find.textContaining('Second Stop'), findsOneWidget);
      expect(find.textContaining('First Stop'), findsNothing);
      verifyNever(() => harness.repository.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          ));
    });

    testWidgets('Keep it makes zero calls', (tester) async {
      harness = await _ChatHarness.create();
      await harness.pump(tester);
      await harness.send(tester, 'cancel next stop');

      await tester.tap(find.text('Keep it'));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Kept First Stop.'), findsOneWidget);
      verifyNever(() => harness.repository.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          ));
    });

    testWidgets('barrier dismissal makes zero calls', (tester) async {
      harness = await _ChatHarness.create();
      await harness.pump(tester);
      await harness.send(tester, 'cancel next stop');

      await tester.tapAt(const Offset(8, 300));
      await tester.pump(const Duration(milliseconds: 300));

      expect(find.text('Kept First Stop.'), findsOneWidget);
      verifyNever(() => harness.repository.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          ));
    });

    testWidgets('accept makes one call for the displayed node ID',
        (tester) async {
      harness = await _ChatHarness.create(acknowledgeFirst: true);
      when(() => harness.repository.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _result(harness.nodes));
      await harness.pump(tester);
      await harness.send(tester, 'cancel next stop');
      expect(find.textContaining('Second Stop'), findsOneWidget);

      await tester.tap(find.text('Cancel this stop'));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump();

      verify(() => harness.repository.sendEvent(
            tripId: 'trip-1',
            type: EventType.cancelActivity,
            message: 'cancel next stop',
            targetNodeId: 'second',
            preferences: null,
          )).called(1);
    });

    testWidgets('swap next remains immediate and unconfirmed', (tester) async {
      harness = await _ChatHarness.create();
      when(() => harness.repository.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _result(harness.nodes));
      await harness.pump(tester);

      await harness.send(tester, 'swap next stop');
      await tester.pump();

      expect(find.text('Cancel this stop?'), findsNothing);
      verify(() => harness.repository.sendEvent(
            tripId: 'trip-1',
            type: EventType.swapActivity,
            message: 'swap next stop',
            targetNodeId: 'first',
            preferences: null,
          )).called(1);
    });
  });
}

class _ItineraryHarness {
  final TripNode node;
  final ProviderContainer container;
  final void Function() closeSubscription;

  _ItineraryHarness._({
    required this.node,
    required this.container,
    required this.closeSubscription,
  });

  static Future<_ItineraryHarness> create(TripNode node) async {
    final database = _MockOfflineDatabase();
    final signalService = _MockSignalService();
    final repository = _MockTripRepository();
    final api = _MockApiClient();
    _stubDatabase(database);
    when(() => signalService.emitVisitedConfirmedWithResult(
          placeRef: any(named: 'placeRef'),
          tripId: any(named: 'tripId'),
        )).thenAnswer((_) async => true);
    when(() => signalService.emitNodeSkippedWithResult(
          placeRef: any(named: 'placeRef'),
          reason: any(named: 'reason'),
          tripId: any(named: 'tripId'),
        )).thenAnswer((_) async => true);
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: [node],
      ),
    );
    when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
      (invocation) async {
        final path = invocation.positionalArguments.first as String;
        if (path.endsWith('/alerts')) {
          return {
            'trip_id': 'trip-1',
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
    final container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repository),
        apiClientProvider.overrideWithValue(api),
        offlineDatabaseProvider.overrideWithValue(database),
        identityCacheScopeProvider.overrideWithValue('account:user-1'),
        signalServiceProvider.overrideWithValue(signalService),
      ],
    );
    final loaded = Completer<void>();
    final subscription = container.listen(
      itineraryControllerProvider('trip-1'),
      (_, next) {
        if (!next.loading && !loaded.isCompleted) loaded.complete();
      },
      fireImmediately: true,
    );
    await loaded.future;
    return _ItineraryHarness._(
      node: node,
      container: container,
      closeSubscription: subscription.close,
    );
  }

  Future<void> pump(WidgetTester tester) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ItineraryScreen(tripId: 'trip-1')),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  void dispose() {
    closeSubscription();
    container.dispose();
  }
}

class _ChatHarness {
  final _MockTripRepository repository;
  final ProviderContainer container;
  final List<TripNode> nodes;
  final void Function() closeSubscription;

  _ChatHarness._({
    required this.repository,
    required this.container,
    required this.nodes,
    required this.closeSubscription,
  });

  static Future<_ChatHarness> create({bool acknowledgeFirst = false}) async {
    final now = DateTime.now().toUtc();
    final nodes = [
      _node(
        id: 'first',
        name: 'First Stop',
        start: now.subtract(const Duration(minutes: 10)),
      ),
      _node(
        id: 'second',
        name: 'Second Stop',
        start: now.add(const Duration(hours: 2)),
      ),
    ];
    final database = _MockOfflineDatabase();
    _stubDatabase(
      database,
      outcomes: acknowledgeFirst
          ? {
              'first': NodeOutcome(
                outcome: NodeOutcome.visited,
                recordedAt: now,
              ),
            }
          : const {},
    );
    final repository = _MockTripRepository();
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: nodes,
      ),
    );
    final container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repository),
        offlineDatabaseProvider.overrideWithValue(database),
        identityCacheScopeProvider.overrideWithValue('account:user-1'),
        userStatusProvider.overrideWith(
          (_) async => const UserStatus(
            userId: 'user-1',
            tier: 'free',
            used: 0,
            remaining: 3,
            max: 3,
          ),
        ),
      ],
    );
    final loaded = Completer<void>();
    final subscription = container.listen(
      itineraryControllerProvider('trip-1'),
      (_, next) {
        if (!next.loading && !loaded.isCompleted) loaded.complete();
      },
      fireImmediately: true,
    );
    await loaded.future;
    return _ChatHarness._(
      repository: repository,
      container: container,
      nodes: nodes,
      closeSubscription: subscription.close,
    );
  }

  Future<void> pump(WidgetTester tester) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: const MaterialApp(home: ChatScreen(tripId: 'trip-1')),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  Future<void> send(WidgetTester tester, String text) async {
    await tester.enterText(find.byType(TextField), text);
    await tester.tap(find.byIcon(Icons.send_rounded));
    await tester.pump();
  }

  void dispose() {
    closeSubscription();
    container.dispose();
  }
}
