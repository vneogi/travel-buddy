import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/core/api_client.dart';
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

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockSignalService extends Mock implements SignalService {}

TripNode _node({
  required String id,
  required String name,
  required DateTime start,
  int durationMinutes = 60,
  bool locked = false,
  String nodeKind = 'activity',
  String? bookingType,
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
      nodeKind: nodeKind,
      bookingType: bookingType,
    );

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

/// Reusable harness for ItineraryScreen widget tests.
class _Harness {
  final ProviderContainer container;
  final void Function() closeSubscription;

  _Harness._({required this.container, required this.closeSubscription});

  static Future<_Harness> create(List<TripNode> nodes) async {
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
    when(() => signalService.emitUserLoved(
          placeRef: any(named: 'placeRef'),
          tripId: any(named: 'tripId'),
        )).thenAnswer((_) async {});
    when(() => repository.getTrip('trip-1')).thenAnswer(
      (_) async => TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        nodes: nodes,
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
    return _Harness._(
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

void main() {
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  group('SPEC-31 date-scoped itinerary', () {
    setUp(() {
      final binding = TestWidgetsFlutterBinding.ensureInitialized();
      binding.setSurfaceSize(const Size(800, 600));
    });
    tearDown(() {
      final binding = TestWidgetsFlutterBinding.ensureInitialized();
      binding.setSurfaceSize(null);
    });

    testWidgets('AppBar says Your Trip', (tester) async {
      final harness = await _Harness.create([
        _node(id: 'a', name: 'Museum', start: DateTime(2026, 10, 5, 9)),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      expect(find.text('Your Trip'), findsOneWidget);
    });

    testWidgets('two dates render two headers and all cards', (tester) async {
      final harness = await _Harness.create([
        _node(id: 'a', name: 'Morning Market', start: DateTime(2026, 10, 5, 9)),
        _node(id: 'b', name: 'Lunch Spot', start: DateTime(2026, 10, 5, 12)),
        _node(id: 'c', name: 'Temple Visit', start: DateTime(2026, 10, 6, 10)),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      // Date headers include year
      expect(
        find.text('Monday, 5 October 2026'),
        findsOneWidget,
      );
      expect(
        find.text('Tuesday, 6 October 2026'),
        findsOneWidget,
      );
      // All cards present
      expect(find.text('Morning Market'), findsOneWidget);
      expect(find.text('Lunch Spot'), findsOneWidget);
      expect(find.text('Temple Visit'), findsOneWidget);
    });

    testWidgets('date header includes year (New Year boundary)', (tester) async {
      final harness = await _Harness.create([
        _node(id: 'nye', name: 'NYE Party', start: DateTime(2026, 12, 31, 22)),
        _node(id: 'nyd', name: 'Brunch', start: DateTime(2027, 1, 1, 10)),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      expect(find.text('Thursday, 31 December 2026'), findsOneWidget);
      expect(find.text('Friday, 1 January 2027'), findsOneWidget);
    });

    testWidgets('ActivityCard keys survive: love updates the intended node',
        (tester) async {
      final harness = await _Harness.create([
        _node(id: 'a', name: 'Market', start: DateTime(2026, 10, 5, 9)),
        _node(id: 'b', name: 'Temple', start: DateTime(2026, 10, 6, 10)),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      // Both cards present
      expect(find.byType(ActivityCard), findsNWidgets(2));

      // Tap the heart on the first card
      final heartButtons = find.byIcon(Icons.favorite_border);
      expect(heartButtons, findsWidgets);
      await tester.tap(heartButtons.first);
      await tester.pump();

      // Verify that the signal service was called for the first node
      final signalService = harness.container.read(signalServiceProvider);
      verify(() => signalService.emitUserLoved(
            placeRef: 'a-ref',
            tripId: 'trip-1',
          )).called(1);
    });

    testWidgets(
        'last node of one date receives first node of next date as nextNode',
        (tester) async {
      final harness = await _Harness.create([
        _node(id: 'a', name: 'Market', start: DateTime(2026, 10, 5, 9)),
        _node(id: 'b', name: 'Temple', start: DateTime(2026, 10, 6, 10)),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      // Both ActivityCards should be present. The first card (Market)
      // should have nextNode pointing to Temple (cross-date boundary).
      final cards = tester.widgetList<ActivityCard>(find.byType(ActivityCard));
      final firstCard = cards.first;
      expect(firstCard.node.nodeId, 'a');
      expect(firstCard.nextNode, isNotNull);
      expect(firstCard.nextNode!.nodeId, 'b');
    });

    testWidgets('no RenderFlex overflow at 800x600 with two date groups',
        (tester) async {
      final harness = await _Harness.create([
        _node(id: 'a', name: 'Cafe', start: DateTime(2026, 10, 5, 9)),
        _node(id: 'b', name: 'Museum', start: DateTime(2026, 10, 5, 14)),
        _node(id: 'c', name: 'Park', start: DateTime(2026, 10, 6, 10)),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      // The test framework reports RenderFlex overflows as test failures.
      // If we get here without a failure, layout is clean.
      expect(find.byType(ActivityCard), findsNWidgets(3));
    });

    testWidgets('SPEC-30 outcome wiring still reaches the correct node',
        (tester) async {
      final now = DateTime(2026, 10, 5, 12);
      final harness = await _Harness.create([
        _node(
          id: 'elapsed',
          name: 'Morning Tour',
          start: now.subtract(const Duration(hours: 2)),
        ),
        _node(
          id: 'future',
          name: 'Dinner',
          start: now.add(const Duration(hours: 5)),
        ),
      ]);
      addTearDown(harness.dispose);
      await harness.pump(tester);

      // Two cards under the same date header
      expect(find.byType(ActivityCard), findsNWidgets(2));

      // The elapsed node should show "Did this happen?"
      expect(find.text('Did this happen?'), findsOneWidget);

      // Tap "Did this happen?" -> opens outcome sheet
      await tester.tap(find.text('Did this happen?'));
      await tester.pumpAndSettle();

      // Tap "Yes, I went" -> records visited
      await tester.tap(find.text('Yes, I went'));
      await tester.pumpAndSettle();

      // Verify signal was emitted for the elapsed node, not the future one
      final signalService = harness.container.read(signalServiceProvider);
      verify(() => signalService.emitVisitedConfirmedWithResult(
            placeRef: 'elapsed-ref',
            tripId: 'trip-1',
          )).called(1);

      // Verify persistence was called for the elapsed node
      final db = harness.container.read(offlineDatabaseProvider);
      verify(() => db.upsertNodeOutcome(
            identityScope: any(named: 'identityScope'),
            tripId: 'trip-1',
            nodeId: 'elapsed',
            outcome: any(named: 'outcome'),
            reason: any(named: 'reason'),
            recordedAt: any(named: 'recordedAt'),
          )).called(1);

      // The future node should NOT have had its outcome recorded
      verifyNever(() => signalService.emitVisitedConfirmedWithResult(
            placeRef: 'future-ref',
            tripId: 'trip-1',
          ));
    });
  });
}
