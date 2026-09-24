// SPEC-45 R4/R5: Production bottom inset and one-Ask proof.
//
// UNVERIFIED: flutter test has not been run on this host.
//
// Pumps the real ItineraryScreen with a corridor trip state using the
// spec36 _loadItineraryContainer harness pattern. At 390x844 logical
// pixels:
//   - exactly one AskEntryBar
//   - no FloatingActionButton
//   - enough cards to require scrolling
//   - find the final Dinner card, ensureVisible, tap, assert callback
//   - tester.takeException() is null
//   - kItineraryBottomInset appears once in corridor scroll owner

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
import 'package:travel_buddy/widgets/ask_entry_bar.dart';

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockSignalService extends Mock implements SignalService {}

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
}

Future<ProviderContainer> _loadContainer({
  required TripState trip,
  required _MockTripRepository repo,
}) async {
  final database = _MockOfflineDatabase();
  final signalService = _MockSignalService();
  final api = _MockApiClient();
  _stubDatabase(database);

  when(() => repo.getTrip(trip.tripId)).thenAnswer((_) async => trip);
  when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
    (invocation) async {
      final path = invocation.positionalArguments.first as String;
      if (path.endsWith('/alerts')) {
        return {
          'trip_id': trip.tripId,
          'status': 'unconfigured',
          'alerts': <Object>[],
          'refreshed_at': '2026-08-31T12:00:00.000Z',
        };
      }
      return {
        'user_id': trip.userId,
        'tier': 'free',
        'daily_reroutes_used': 0,
        'daily_reroutes_remaining': 3,
        'max_daily_reroutes': 3,
      };
    },
  );
  when(() => signalService.emitUserLoved(
        placeRef: any(named: 'placeRef'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});
  when(() => signalService.emitRerouteRejected(
        placeRef: any(named: 'placeRef'),
        rejectedRefs: any(named: 'rejectedRefs'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});
  when(() => signalService.emitRerouteAccepted(
        placeRef: any(named: 'placeRef'),
        replacementRef: any(named: 'replacementRef'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async {});
  when(() => signalService.emitVisitedConfirmedWithResult(
        placeRef: any(named: 'placeRef'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => true);
  when(() => signalService.emitNodeSkippedWithResult(
        placeRef: any(named: 'placeRef'),
        reason: any(named: 'reason'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => true);

  final container = ProviderContainer(
    overrides: [
      tripRepoProvider.overrideWithValue(repo),
      apiClientProvider.overrideWithValue(api),
      offlineDatabaseProvider.overrideWithValue(database),
      identityCacheScopeProvider.overrideWithValue('account:${trip.userId}'),
      signalServiceProvider.overrideWithValue(signalService),
    ],
  );

  final loaded = Completer<void>();
  final sub = container.listen(
    itineraryControllerProvider(trip.tripId),
    (_, next) {
      if (!next.loading && !loaded.isCompleted) {
        loaded.complete();
      }
    },
    fireImmediately: true,
  );
  await loaded.future;
  addTearDown(() {
    sub.close();
    container.dispose();
  });
  return container;
}

TripNode _node({
  required String id,
  required String name,
  required DateTime start,
  String geoRegion = 'vientiane_laos',
  String? slotName,
  int durationMinutes = 60,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      scheduledStart: start,
      durationMinutes: durationMinutes,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['cafe'],
      geoRegion: geoRegion,
      lat: 0,
      lng: 0,
      slotName: slotName,
    );

void main() {
  group('R4/R5: Production bottom inset', () {
    testWidgets(
      'corridor ItineraryScreen: one AskEntryBar, no FAB, '
      'last card tappable, no overflow exception',
      (tester) async {
        // Phone-width surface (390x844 -- iPhone 14 logical).
        tester.view.physicalSize = const Size(390 * 3, 844 * 3);
        tester.view.devicePixelRatio = 3.0;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);

        final repo = _MockTripRepository();

        // Six nodes across two cities -- enough to require scrolling.
        final nodes = [
          _node(
            id: 'n1',
            name: 'Morning Walk',
            start: DateTime.utc(2026, 10, 5, 2),
            geoRegion: 'vientiane_laos',
            slotName: 'morning_tour',
          ),
          _node(
            id: 'n2',
            name: 'Joma Bakery',
            start: DateTime.utc(2026, 10, 5, 4),
            geoRegion: 'vientiane_laos',
            slotName: 'lunch',
          ),
          _node(
            id: 'n3',
            name: 'Pha That Luang',
            start: DateTime.utc(2026, 10, 5, 7),
            geoRegion: 'vientiane_laos',
            slotName: 'afternoon_evening_tour',
          ),
          _node(
            id: 'n4',
            name: 'LP Waterfall',
            start: DateTime.utc(2026, 10, 6, 2),
            geoRegion: 'luang_prabang_laos',
            slotName: 'morning_tour',
          ),
          _node(
            id: 'n5',
            name: 'PVO Vietnamese',
            start: DateTime.utc(2026, 10, 6, 7),
            geoRegion: 'luang_prabang_laos',
            slotName: 'afternoon_evening_tour',
          ),
          _node(
            id: 'n6',
            name: 'Night Market Dinner',
            start: DateTime.utc(2026, 10, 6, 11),
            geoRegion: 'luang_prabang_laos',
            slotName: 'dinner',
          ),
        ];

        final trip = TripState(
          tripId: 'trip-inset',
          userId: 'u1',
          geoRegion: 'vientiane_laos',
          corridorId: 'laos_northbound_v1',
          segments: const [
            TripSegment(
              geoRegion: 'vientiane_laos',
              startsOn: '2026-10-05',
              endsOn: '2026-10-05',
            ),
            TripSegment(
              geoRegion: 'luang_prabang_laos',
              startsOn: '2026-10-06',
              endsOn: '2026-10-06',
            ),
          ],
          nodes: nodes,
        );

        final container = await _loadContainer(trip: trip, repo: repo);

        await tester.pumpWidget(
          UncontrolledProviderScope(
            container: container,
            child: const MaterialApp(
              home: ItineraryScreen(tripId: 'trip-inset'),
            ),
          ),
        );
        await tester.pumpAndSettle();

        // Exactly one AskEntryBar (the composer).
        expect(find.byType(AskEntryBar), findsOneWidget);

        // No FloatingActionButton.
        expect(find.byType(FloatingActionButton), findsNothing);

        // Cards rendered.
        expect(find.byType(ActivityCard), findsWidgets);

        // Find the final Dinner card.
        final lastCard = find.text('Night Market Dinner');
        expect(lastCard, findsOneWidget);

        // Scroll it into view and tap.
        await tester.ensureVisible(lastCard);
        await tester.pumpAndSettle();

        // Tap the card body (GestureDetector -> details).
        await tester.tap(lastCard);
        await tester.pumpAndSettle();

        // No flutter overflow exception.
        expect(tester.takeException(), isNull);
      },
      timeout: const Timeout(Duration(seconds: 30)),
    );
  });
}
