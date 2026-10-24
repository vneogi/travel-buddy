import 'dart:async';
import 'dart:convert';

import 'package:connectivity_plus/connectivity_plus.dart';
import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:travel_buddy/core/anon_session.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/profile/profile_screen.dart';
import 'package:travel_buddy/features/profile/sign_out_controller.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';

class _MockSyncEngine extends Mock implements SyncEngine {}

class _MockTripRepository extends Mock implements TripRepository {}

class _FakeAnonAuth implements AnonAuth {
  bool _hasSession;
  String? _accessToken;
  final List<String> events;
  final bool signInFails;
  int signInCalls = 0;
  int signOutCalls = 0;

  _FakeAnonAuth({
    required String accessToken,
    List<String>? events,
    this.signInFails = false,
  })  : _hasSession = true,
        _accessToken = accessToken,
        events = events ?? <String>[];

  @override
  bool get hasSession => _hasSession;

  String? get accessToken => _hasSession ? _accessToken : null;

  @override
  Future<void> signInAnonymously() async {
    events.add('auth.signIn');
    signInCalls++;
    if (signInFails) throw Exception('anonymous disabled');
    _hasSession = true;
    _accessToken = 'token-b';
  }

  @override
  Future<void> signOut() async {
    events.add('auth.signOut');
    signOutCalls++;
    _hasSession = false;
    _accessToken = null;
  }
}

class _MockConnectivity extends Mock implements Connectivity {}

int _dbCounter = 0;

Future<OfflineDatabase> _db() async {
  _dbCounter++;
  final db = OfflineDatabase(
    testPath: 'file:spec43_g6_$_dbCounter?mode=memory&cache=shared',
  );
  await db.db;
  return db;
}

TripNode _node(String id, String name) => TripNode(
      nodeId: id,
      venueName: name,
      venueId: 'v-$id',
      scheduledStart: DateTime.utc(2026, 10, 2, 9),
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: 'luang_prabang_laos',
    );

UserStatus _status(String userId) => UserStatus(
      userId: userId,
      tier: 'free',
      used: 0,
      remaining: 3,
      max: 3,
    );

Future<void> _seedWipeSurface(OfflineDatabase db) async {
  await db.enqueue(
    'sig-a',
    jsonEncode({
      'signal_id': 'sig-a',
      'signal_type': 'user_loved',
      'captured_at': DateTime.now().toUtc().toIso8601String(),
    }),
    DateTime.now().toUtc().toIso8601String(),
  );
  await db.cacheTrip('trip-a', jsonEncode({'trip_id': 'trip-a', 'nodes': []}));
  await db.cacheTripList('account:user-a', jsonEncode({'trips': []}));
  await db.cachePlace('place-a', jsonEncode({'name': 'Place A'}));
  await db.upsertLovedPlace(
    identityScope: 'account:user-a',
    tripId: 'trip-a',
    placeRef: 'place-a',
  );
  await db.setAppValue('last_session_at', DateTime.now().toUtc().toIso8601String());
  await db.upsertNodeOutcome(
    identityScope: 'account:user-a',
    tripId: 'trip-a',
    nodeId: 'node-a',
    outcome: NodeOutcome.visited,
  );
  await db.createAskThread(
    threadId: 'thread-a',
    identityScope: 'account:user-a',
    tripId: 'trip-a',
    title: 'Thread A',
  );
  await db.insertAskMessage(
    messageId: 'msg-a',
    threadId: 'thread-a',
    role: 'user',
    text: 'hello',
  );
  await db.cacheAlerts(
    identityScope: 'account:user-a',
    tripId: 'trip-a',
    payloadJson: jsonEncode({'alerts': []}),
    expiresAt: DateTime.now().toUtc().add(const Duration(hours: 1)).toIso8601String(),
  );
  await db.dismissAlert(identityScope: 'account:user-a', alertId: 'alert-a');
  await db.cacheNotifications(
    identityScope: 'account:user-a',
    tripId: 'trip-a',
    payloadJson: jsonEncode({'notifications': []}),
    expiresAt: DateTime.now().toUtc().add(const Duration(hours: 1)).toIso8601String(),
  );
  await db.dismissNotification(
    identityScope: 'account:user-a',
    notificationId: 'notif-a',
  );
}

Future<int> _count(OfflineDatabase db, String table) async {
  final database = await db.db;
  final rows = await database.rawQuery('SELECT COUNT(*) AS c FROM $table');
  return (rows.single['c'] as int?) ?? (rows.single['c'] as num).toInt();
}

void _stubSyncLifecycle(_MockSyncEngine sync, List<String> events) {
  when(() => sync.haltForAuthChange()).thenAnswer((_) {
    events.add('sync.halt');
  });
  when(() => sync.resetAuthHalted()).thenAnswer((_) {
    events.add('sync.reset');
  });
  when(() => sync.start()).thenAnswer((_) async {
    events.add('sync.start');
  });
}


void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  group('SPEC-43 Gap 6 sign out', () {
    test('sign-out calls signOut then exactly one signInAnonymously for a new session',
        () async {
      final db = await _db();
      final events = <String>[];
      final auth = _FakeAnonAuth(accessToken: 'token-a', events: events);
      final sync = _MockSyncEngine();
      _stubSyncLifecycle(sync, events);

      final container = ProviderContainer(overrides: [
        offlineDatabaseProvider.overrideWithValue(db),
        anonAuthProvider.overrideWithValue(auth),
        syncEngineProvider.overrideWithValue(sync),
      ]);
      addTearDown(container.dispose);
      addTearDown(db.close);

      final result = await container.read(signOutControllerProvider.notifier).run();

      expect(result.ok, isTrue);
      expect(events, ['sync.halt', 'auth.signOut', 'auth.signIn', 'sync.reset', 'sync.start']);
      expect(auth.signOutCalls, 1);
      expect(auth.signInCalls, 1);
      expect(auth.hasSession, isTrue);
      expect(auth.accessToken, 'token-b');
    });

    test('after wipe, cache_trip / cache_trip_list / outbox / ask_thread / loved_places / node_outcome are empty',
        () async {
      final db = await _db();
      await _seedWipeSurface(db);
      final auth = _FakeAnonAuth(accessToken: 'token-a');
      final sync = _MockSyncEngine();
      _stubSyncLifecycle(sync, <String>[]);

      final container = ProviderContainer(overrides: [
        offlineDatabaseProvider.overrideWithValue(db),
        anonAuthProvider.overrideWithValue(auth),
        syncEngineProvider.overrideWithValue(sync),
      ]);
      addTearDown(container.dispose);
      addTearDown(db.close);

      final result = await container.read(signOutControllerProvider.notifier).run();
      expect(result.ok, isTrue);

      for (final table in const [
        'cache_trip',
        'cache_trip_list',
        'outbox',
        'ask_thread',
        'ask_message',
        'loved_places',
        'node_outcome',
        'cache_place',
        'alert_cache',
        'alert_dismissals',
        'app_kv',
        'notification_cache',
        'notification_dismissals',
      ]) {
        expect(await _count(db, table), 0, reason: '$table should be empty');
      }
    });

    test('test_sign_out_does_not_upload_prior_outbox_under_new_identity', () async {
      final db = await _db();
      await db.enqueue(
        'sig-a',
        jsonEncode({
          'signal_id': 'sig-a',
          'signal_type': 'user_loved',
          'trip_id': 'trip-a',
          'captured_at': DateTime.now().toUtc().toIso8601String(),
        }),
        DateTime.now().toUtc().toIso8601String(),
      );

      final auth = _FakeAnonAuth(accessToken: 'token-a');
      final postedAuth = <String?>[];
      final dio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
      dio.interceptors.add(
        InterceptorsWrapper(
          onRequest: (options, handler) {
            postedAuth.add(options.headers['Authorization']?.toString());
            handler.resolve(
              Response(
                requestOptions: options,
                statusCode: 200,
                data: {'accepted': 1, 'duplicates': 0, 'rejected': []},
              ),
            );
          },
        ),
      );
      final api = ApiClient(
        tokenProvider: () async => auth.accessToken,
        dioOverride: dio,
      );
      final connectivity = _MockConnectivity();
      when(() => connectivity.onConnectivityChanged)
          .thenAnswer((_) => const Stream<List<ConnectivityResult>>.empty());
      final engine = SyncEngine(db: db, api: api, connectivity: connectivity);

      final container = ProviderContainer(overrides: [
        offlineDatabaseProvider.overrideWithValue(db),
        anonAuthProvider.overrideWithValue(auth),
        syncEngineProvider.overrideWithValue(engine),
      ]);
      addTearDown(container.dispose);
      addTearDown(() async {
        engine.stop();
        await db.close();
      });

      final result = await container.read(signOutControllerProvider.notifier).run();
      await Future<void>.delayed(const Duration(milliseconds: 50));

      expect(result.ok, isTrue);
      expect(await db.getOutboxSize(), 0);
      expect(postedAuth, isEmpty,
          reason: 'A queued row from identity A must never POST under B\'s Bearer');
    });

    test('home and itinerary providers after sign-out do not still hold A nodes',
        () async {
      final db = await _db();
      final auth = _FakeAnonAuth(accessToken: 'token-a');
      final sync = _MockSyncEngine();
      _stubSyncLifecycle(sync, <String>[]);
      final repo = _MockTripRepository();

      when(() => repo.getHomeSnapshot()).thenAnswer((_) async {
        if (auth.accessToken == 'token-a') {
          return HomeSnapshot(
            supportedRegions: const ['luang_prabang_laos'],
            trips: [
              TripSummary(
                tripId: 'trip-a',
                geoRegion: 'luang_prabang_laos',
                nodeCount: 1,
                bookingCount: 0,
                updatedAt: DateTime.utc(2026, 10, 2),
              ),
            ],
          );
        }
        return const HomeSnapshot(supportedRegions: ['luang_prabang_laos'], trips: []);
      });
      when(() => repo.getTrip('trip-a')).thenAnswer((_) async {
        if (auth.accessToken == 'token-a') {
          return TripState(
            tripId: 'trip-a',
            userId: 'user-a',
            nodes: [_node('node-a', 'A node')],
            geoRegion: 'luang_prabang_laos',
          );
        }
        return const TripState(
          tripId: 'trip-a',
          userId: 'user-b',
          nodes: [],
          geoRegion: 'luang_prabang_laos',
        );
      });

      final container = ProviderContainer(overrides: [
        offlineDatabaseProvider.overrideWithValue(db),
        anonAuthProvider.overrideWithValue(auth),
        syncEngineProvider.overrideWithValue(sync),
        tripRepoProvider.overrideWithValue(repo),
      ]);
      addTearDown(container.dispose);
      addTearDown(db.close);

      final homeA = await container.read(homeSnapshotProvider.future);
      expect(homeA.trips.single.tripId, 'trip-a');

      final firstLoad = Completer<void>();
      final itinerarySub = container.listen(
        itineraryControllerProvider('trip-a'),
        (_, next) {
          if (!next.loading && !firstLoad.isCompleted) firstLoad.complete();
        },
        fireImmediately: true,
      );
      await firstLoad.future;
      expect(
        container.read(itineraryControllerProvider('trip-a')).nodes.single.venueName,
        'A node',
      );

      final result = await container.read(signOutControllerProvider.notifier).run();
      expect(result.ok, isTrue);

      final homeB = await container.read(homeSnapshotProvider.future);
      expect(homeB.trips, isEmpty);

      final refreshed = Completer<void>();
      var seenEmptyNodes = false;
      final itinerarySubAfter = container.listen(
        itineraryControllerProvider('trip-a'),
        (_, next) {
          if (!next.loading && next.nodes.isEmpty && !refreshed.isCompleted) {
            seenEmptyNodes = true;
            refreshed.complete();
          }
        },
        fireImmediately: true,
      );
      await refreshed.future;
      expect(seenEmptyNodes, isTrue);

      itinerarySub.close();
      itinerarySubAfter.close();
    });

    testWidgets('router: signed-out user is not left on /trip/<old-id>',
        (tester) async {
      final db = await tester.runAsync(_db);
      if (db == null) fail('failed to open test database');
      final auth = _FakeAnonAuth(accessToken: 'token-a');
      final sync = _MockSyncEngine();
      _stubSyncLifecycle(sync, <String>[]);
      final repo = _MockTripRepository();
      when(() => repo.getHomeSnapshot()).thenAnswer(
        (_) async => const HomeSnapshot(
          supportedRegions: ['luang_prabang_laos'],
          trips: [],
        ),
      );

      final router = GoRouter(
        initialLocation: '/trip/trip-a',
        routes: [
          GoRoute(
            path: '/',
            builder: (context, state) => const Scaffold(
              body: Text('empty home', key: Key('home_root')),
            ),
          ),
          GoRoute(
            path: '/trip/:tripId',
            builder: (context, state) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  key: const Key('open_profile'),
                  onPressed: () => context.push('/profile'),
                  child: const Text('Profile'),
                ),
              ),
            ),
          ),
          GoRoute(path: '/profile', builder: (context, state) => const ProfileScreen()),
        ],
      );

      await tester.pumpWidget(
        ProviderScope(
          overrides: [
            offlineDatabaseProvider.overrideWithValue(db),
            anonAuthProvider.overrideWithValue(auth),
            syncEngineProvider.overrideWithValue(sync),
            tripRepoProvider.overrideWithValue(repo),
            userStatusProvider.overrideWith((ref) async => _status('user-a')),
            deviceIdProvider.overrideWith((ref) => 'device-1'),
          ],
          child: MaterialApp.router(routerConfig: router),
        ),
      );
      await tester.pump();
      expect(find.byKey(const Key('open_profile')), findsOneWidget);

      await tester.tap(find.byKey(const Key('open_profile')));
      await tester.pump();
      expect(find.byKey(const Key('profile_sign_out')), findsOneWidget);

      // Sqflite and SignOutController.run must run on the real event loop.
      // Starting that work from a tap inside fake-async never completes.
      final element = tester.element(find.byKey(const Key('profile_sign_out')));
      final container = ProviderScope.containerOf(element);
      final goRouter = GoRouter.of(element);
      final result = await tester.runAsync(
        () => container.read(signOutControllerProvider.notifier).run(),
      );
      expect(result, isNotNull);
      expect(result!.ok, isTrue);
      goRouter.go('/');
      await tester.pump();

      expect(find.byKey(const Key('home_root')), findsOneWidget);
      expect(find.byKey(const Key('profile_sign_out')), findsNothing);
      expect(router.routeInformationProvider.value.uri.path, '/');

      router.dispose();
      await tester.runAsync(db.close);
    }, timeout: const Timeout(Duration(seconds: 20)));

    test('sign-in failure keeps sync halted and returns a short error', () async {
      final db = await _db();
      final auth = _FakeAnonAuth(accessToken: 'token-a', signInFails: true);
      final sync = _MockSyncEngine();
      final events = <String>[];
      _stubSyncLifecycle(sync, events);

      final container = ProviderContainer(overrides: [
        offlineDatabaseProvider.overrideWithValue(db),
        anonAuthProvider.overrideWithValue(auth),
        syncEngineProvider.overrideWithValue(sync),
      ]);
      addTearDown(container.dispose);
      addTearDown(db.close);

      final result = await container.read(signOutControllerProvider.notifier).run();

      expect(result.ok, isFalse);
      expect(result.error, contains('new session'));
      expect(events, ['sync.halt', 'auth.signOut', 'auth.signIn']);
      verifyNever(() => sync.resetAuthHalted());
      verifyNever(() => sync.start());
    });
  });
}
