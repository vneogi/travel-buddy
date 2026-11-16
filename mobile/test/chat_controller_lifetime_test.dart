// Chat controller lifetime: prove that ChatScreen must hold a listener on
// itineraryControllerProvider so sends from chat always reach a live
// controller, however the user navigated to chat.
//
// No network. Does NOT override tripEventProvider: the real TripEventService
// and the autoDispose provider lifetime are under test.

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

class _FakeConnectivity extends ConnectivityHelper {
  @override
  Future<bool> checkConnectivity() async => true;
}

const _tripId = 'trip-clt';
const _scope = 'account:clt-test';
int _counter = 0;

TripNode _node({required DateTime start}) => TripNode(
      nodeId: 'n1',
      venueName: 'Test Stop',
      venueId: 'stop-1',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['culture'],
    );

AskResponse _askResponse(String answer) => AskResponse(
      answer: answer,
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.openingHours,
      sourceClass: 'curated_catalog',
    );

AskResponse _whatNowAskResponse() => const AskResponse(
      answer: 'Found 1 option within reach: Wat Si Saket.',
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
            reasonCodes: ['fits_available_window'],
            unknownFields: ['price'],
          ),
        ],
      ),
    );

TripEventResult _result(String msg, {AskResponse? ask, List<TripNode>? nodes}) =>
    TripEventResult(
      message: msg,
      updatedNodes: nodes ?? [],
      routingTier: 'light',
      fromCache: false,
      askResponse: ask,
    );

typedef _Harness = ({
  ProviderContainer container,
  _MockTripRepository repo,
  OfflineDatabase db,
});

Future<_Harness> _buildHarness({
  Future<TripEventResult> Function(Invocation)? sendAnswer,
  Completer<TripEventResult>? completer,
}) async {
  _counter++;
  final dbPath = 'file:clt_$_counter?mode=memory&cache=shared';
  final realDb = OfflineDatabase(testPath: dbPath);
  final repo = _MockTripRepository();
  final now = DateTime.now().toUtc();

  when(() => repo.getTrip(_tripId)).thenAnswer(
    (_) async => TripState(
      tripId: _tripId,
      userId: 'user-1',
      nodes: [_node(start: now.add(const Duration(hours: 1)))],
    ),
  );
  if (completer != null) {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) => completer.future);
  } else if (sendAnswer != null) {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer(sendAnswer);
  }

  return (
    container: ProviderContainer(overrides: [
      tripRepoProvider.overrideWithValue(repo),
      offlineDatabaseProvider.overrideWithValue(realDb),
      identityCacheScopeProvider.overrideWithValue(_scope),
      userStatusProvider.overrideWith(
        (ref) async => const UserStatus(
          userId: 'user-1',
          tier: 'free',
          used: 0,
          remaining: 3,
          max: 3,
        ),
      ),
    ]),
    repo: repo,
    db: realDb,
  );
}

Future<void> _flush(
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

Future<void> _teardown(WidgetTester tester, _Harness h) async {
  await _flush(tester);
  await tester.pumpWidget(const SizedBox());
  await _flush(tester);
  h.container.dispose();
  await tester.runAsync(() => h.db.close());
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() => registerFallbackValue(EventType.askInfo));

  // 1. ProviderContainer only: demonstrates the bug mechanism.
  test(
    'send through tripEventProvider with no live itinerary listener returns null',
    () async {
      final completer = Completer<TripEventResult>();
      final h = await _buildHarness(completer: completer);
      final future = h.container.read(tripEventProvider).sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: 'Is this place open?',
          );
      await Future<void>.delayed(const Duration(milliseconds: 100));
      completer.complete(
        _result('Open daily.', ask: _askResponse('Open daily.')),
      );
      final result = await future;
      expect(result, isNull);
      h.container.dispose();
      await h.db.close();
    },
  );

  // 2. Chat opened as the app root (no itinerary underneath).
  // The Completer is completed AFTER fake time advances so Riverpod's
  // autoDispose has run on the base (no listener). With the fix, the
  // listener keeps the controller alive and the answer appears.
  testWidgets(
    'chat opened without itinerary shows the server answer, not the generic error',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final completer = Completer<TripEventResult>();
      final h = await tester.runAsync(() => _buildHarness(completer: completer));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(tripId: _tripId, connectivityOverride: _FakeConnectivity()),
        ),
      ));
      await _flush(tester, until: find.byType(TextField));

      await tester.enterText(find.byType(TextField), 'What are the hours?');
      await tester.tap(find.byIcon(Icons.send_rounded));
      await tester.pump();

      // Advance fake time so Riverpod's autoDispose timer fires (if no listener).
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 100)),
      );

      // NOW complete the server response.
      await tester.runAsync(() async {
        completer.complete(
          _result('Open daily 09:00-17:00.',
              ask: _askResponse('Open daily 09:00-17:00.')),
        );
      });
      await _flush(tester, until: find.textContaining('09:00'));

      expect(find.textContaining('09:00-17:00'), findsWidgets);
      expect(find.text('I could not complete that request. Please try again.'),
          findsNothing);

      await _teardown(tester, h);
    },
  );

  // 3. What Now form submit path with Completer-gated reply.
  testWidgets(
    'chat What Now form opened without itinerary shows the What Now result',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final completer = Completer<TripEventResult>();
      final h = await tester.runAsync(() => _buildHarness(completer: completer));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(tripId: _tripId, connectivityOverride: _FakeConnectivity()),
        ),
      ));
      await _flush(tester, until: find.byKey(const Key('what_now_entry')));

      await tester.tap(find.byKey(const Key('what_now_entry')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await _flush(tester, until: find.byKey(const Key('what_now_submit')));

      await tester.tap(find.byKey(const Key('what_now_submit')));
      await tester.pump();

      // Let autoDispose fire on base.
      await tester.pump(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 100)),
      );

      await tester.runAsync(() async {
        completer.complete(
          _result('Found 1 option within reach: Wat Si Saket.',
              ask: _whatNowAskResponse()),
        );
      });
      await _flush(tester, until: find.textContaining('Wat Si Saket'));

      expect(find.textContaining('Wat Si Saket'), findsWidgets);
      expect(find.text('I could not complete that request. Please try again.'),
          findsNothing);

      await _teardown(tester, h);
    },
  );

  // 4. Two sends share one controller instance (instant reply is fine here).
  testWidgets(
    'chat keeps one itinerary controller for its lifetime',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(
            sendAnswer: (_) async =>
                _result('Hi', ask: _askResponse('Hi')),
          ));
      if (h == null) fail('harness null');

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(tripId: _tripId, connectivityOverride: _FakeConnectivity()),
        ),
      ));
      await _flush(tester, until: find.byType(TextField));

      await tester.enterText(find.byType(TextField), 'Hello');
      await tester.tap(find.byIcon(Icons.send_rounded));
      await _flush(tester, until: find.textContaining('Hi'));
      await _flush(tester);

      when(() => h.repo.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async =>
              _result('Next stop at 14:00', ask: _askResponse('Next stop at 14:00')));

      await tester.enterText(find.byType(TextField), 'Next?');
      await tester.tap(find.byIcon(Icons.send_rounded));
      await _flush(tester, until: find.textContaining('14:00'));
      await _flush(tester);

      verify(() => h.repo.getTrip(_tripId)).called(1);

      await _teardown(tester, h);
    },
  );

  // 5. Removing chat disposes the controller.
  testWidgets(
    'closing chat releases the itinerary controller',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      final key = GlobalKey<NavigatorState>();
      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          navigatorKey: key,
          home: ChatScreen(tripId: _tripId, connectivityOverride: _FakeConnectivity()),
        ),
      ));
      await _flush(tester, until: find.byType(TextField));

      key.currentState!.pushReplacement(
        MaterialPageRoute<void>(builder: (_) => const Scaffold()),
      );
      await tester.pumpAndSettle();
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 300)),
      );
      await tester.pump();

      expect(h.container.exists(itineraryControllerProvider(_tripId)), isFalse);

      h.container.dispose();
      await tester.runAsync(() => h.db.close());
    },
  );

  // 6. Pre-existing listener shares the controller with chat.
  testWidgets(
    'chat opened over a live itinerary listener shares that controller',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final now = DateTime.now().toUtc();
      final updatedNode = _node(start: now.add(const Duration(hours: 2)));
      final h = await tester.runAsync(() => _buildHarness(
            sendAnswer: (_) async => _result('Swapped.',
                ask: _askResponse('Swapped.'), nodes: [updatedNode]),
          ));
      if (h == null) fail('harness null');

      final externalSub = h.container.listen(
        itineraryControllerProvider(_tripId),
        (_, __) {},
        fireImmediately: true,
      );
      // Wait for the controller to load.
      for (var i = 0; i < 20; i++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 50)),
        );
        final st = h.container.read(itineraryControllerProvider(_tripId));
        if (!st.loading) break;
      }

      await tester.pumpWidget(UncontrolledProviderScope(
        container: h.container,
        child: MaterialApp(
          home: ChatScreen(tripId: _tripId, connectivityOverride: _FakeConnectivity()),
        ),
      ));
      await _flush(tester, until: find.byType(TextField));

      await tester.enterText(find.byType(TextField), 'Swap next');
      await tester.tap(find.byIcon(Icons.send_rounded));
      await _flush(tester, until: find.textContaining('Swapped'));
      await _flush(tester);

      final state = h.container.read(itineraryControllerProvider(_tripId));
      expect(state.nodes, isNotEmpty);
      expect(state.nodes.first.scheduledStart, updatedNode.scheduledStart);

      verify(() => h.repo.getTrip(_tripId)).called(1);

      externalSub.close();
      await _flush(tester);
      await _teardown(tester, h);
    },
  );
}
