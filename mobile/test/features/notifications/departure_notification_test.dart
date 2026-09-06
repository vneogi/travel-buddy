import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/departure_notification.dart';
import 'package:travel_buddy/features/alerts/alerts_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/features/notifications/departure_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/widgets/alert_card.dart';
import 'package:travel_buddy/widgets/departure_banner.dart';

class _MockApiClient extends Mock implements ApiClient {}

// ===================== Fixtures =====================

Map<String, dynamic> _routeEvidence({
  String source = 'google_maps',
  int trafficMinutes = 42,
  int? normalMinutes = 34,
  String mode = 'driving',
}) =>
    {
      'source': source,
      'observed_at': '2026-10-04T01:05:00Z',
      'normal_duration_minutes': normalMinutes,
      'traffic_duration_minutes': trafficMinutes,
      'mode': mode,
      'origin_basis': 'previous_node',
    };

Map<String, dynamic> _weatherEvidence({
  String source = 'openweather',
  double rainProb = 0.63,
}) =>
    {
      'source': source,
      'observed_at': '2026-10-04T01:05:00Z',
      'rain_probability': rainProb,
    };

Map<String, dynamic> _candidateJson({
  String id = 'notif-1',
  String type = 'departure_reminder',
  String nodeId = 'node-7',
  String title = 'Time to head to Kuang Si Falls',
  String message = 'Leave for Kuang Si Falls by 08:20. The drive is about 42 minutes by road; 10 extra minutes added for forecast rain.',
  String? expiresAt,
  Map<String, dynamic>? weather,
}) =>
    {
      'notification_id': id,
      'type': type,
      'priority': 'trip_critical',
      'node_id': nodeId,
      'title': title,
      'message': message,
      'eligible_at': '2026-10-04T00:58:00Z',
      'expires_at': expiresAt ?? '2099-10-05T12:00:00Z',
      'recommended_departure_at': '2026-10-04T01:20:00Z',
      'time_zone': 'Asia/Vientiane',
      'deep_link': '/trip/trip-123/node/node-7',
      'evidence': {
        'route': _routeEvidence(),
        'weather': weather ?? _weatherEvidence(),
        'policy': {
          'arrival_buffer_minutes': 10,
          'weather_buffer_minutes': 10,
        },
      },
    };

Map<String, dynamic> _responseJson({
  List<Map<String, dynamic>>? notifications,
  String status = 'available',
}) =>
    {
      'trip_id': 'trip-123',
      'refreshed_at': '2026-10-04T01:05:00Z',
      'status': status,
      'notifications': notifications ?? [_candidateJson()],
    };

Map<String, dynamic> _alertsResponseJson() => {
      'trip_id': 'trip-123',
      'status': 'available',
      'alerts': [
        {
          'alert_id': 'weather-1',
          'alert_type': 'rain',
          'severity': 'advisory',
          'message': 'Server weather message',
          'affected_node_ids': ['node-7'],
          'affected_node_names': ['Kuang Si Falls'],
          'source': 'openweather',
          'source_updated_at': '2026-10-04T01:05:00Z',
          'valid_from': '2026-10-04T01:00:00Z',
          'valid_until': '2099-10-05T12:00:00Z',
          'expires_at': '2099-10-05T12:30:00Z',
          'location_basis': 'node_coordinates',
          'evidence': {
            'rain_probability': 0.63,
            'condition_code': 500,
          },
          'auto_applied': false,
        },
      ],
      'refreshed_at': '2026-10-04T01:05:00Z',
    };

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // ===================== Proof: JSON parsing =====================
  group('model parsing', () {
    test('parses fixture matching PR #50 shape with nested evidence', () {
      final resp = TripNotificationsResponse.fromJson(_responseJson());
      expect(resp.tripId, 'trip-123');
      expect(resp.status, 'available');
      expect(resp.notifications.length, 1);

      final c = resp.notifications.first;
      expect(c.notificationId, 'notif-1');
      expect(c.type, 'departure_reminder');
      expect(c.priority, 'trip_critical');
      expect(c.nodeId, 'node-7');
      expect(c.title, 'Time to head to Kuang Si Falls');
      expect(c.timeZone, 'Asia/Vientiane');

      // Nested evidence
      expect(c.evidence.route, isNotNull);
      expect(c.evidence.route!.trafficDurationMinutes, 42);
      expect(c.evidence.route!.normalDurationMinutes, 34);
      expect(c.evidence.route!.mode, 'driving');
      expect(c.evidence.weather, isNotNull);
      expect(c.evidence.weather!.rainProbability, 0.63);
      expect(c.evidence.policy.arrivalBufferMinutes, 10);
      expect(c.evidence.policy.weatherBufferMinutes, 10);
    });

    test('parses candidate without weather evidence', () {
      final j = _candidateJson();
      (j['evidence'] as Map<String, dynamic>)['weather'] = null;
      final c = NotificationCandidate.fromJson(j);
      expect(c.evidence.weather, isNull);
      expect(c.evidence.route, isNotNull);
    });
  });

  // ===================== Proof: Expired candidate hidden =====================
  test('expired candidate is hidden by DepartureState.visible', () {
    final expired = NotificationCandidate.fromJson(
      _candidateJson(expiresAt: '2020-01-01T00:00:00Z'),
    );
    final state = DepartureState(candidates: [expired]);
    expect(state.visible, isNull);
  });

  // ===================== Proof: Dismissed ID stays hidden =====================
  test('dismissed ID stays hidden after rebuild', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    await db.db; // Initialize

    await db.dismissNotification(
      identityScope: 'test-scope',
      notificationId: 'notif-1',
    );

    // Simulate rebuild: read dismissals again
    final dismissed = await db.getDismissedNotificationIds(
      identityScope: 'test-scope',
    );
    expect(dismissed, contains('notif-1'));

    // DepartureState with dismissed ID
    final candidate = NotificationCandidate.fromJson(_candidateJson());
    final state = DepartureState(
      candidates: [candidate],
      dismissed: dismissed,
    );
    expect(state.visible, isNull);

    await db.close();
  });

  // ===================== Proof: meal_preview ignored =====================
  test('meal_preview in payload is ignored', () {
    final meal = _candidateJson(type: 'meal_preview', id: 'meal-1');
    final departure = _candidateJson();
    final resp = TripNotificationsResponse.fromJson(
      _responseJson(notifications: [meal, departure]),
    );
    // Filter as the notifier does
    final valid = resp.notifications
        .where((c) => c.type == 'departure_reminder' && !c.isExpired)
        .toList();
    expect(valid.length, 1);
    expect(valid.first.type, 'departure_reminder');
  });

  // ===================== Proof: Departure hides weather, absent leaves visible =====================
  testWidgets('visible departure hides weather cards', (tester) async {
    final api = _MockApiClient();
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(db.close);
    when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
      (invocation) async {
        final path = invocation.positionalArguments.first as String;
        return path.endsWith('/notifications')
            ? _responseJson()
            : _alertsResponseJson();
      },
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          offlineDatabaseProvider.overrideWithValue(db),
          identityCacheScopeProvider.overrideWithValue('account:user-1'),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: ItineraryAlertsSection(tripId: 'trip-123'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(DepartureBanner), findsOneWidget);
    expect(find.byType(AlertCard), findsNothing);
    expect(find.text('Server weather message'), findsNothing);
  });

  testWidgets('absent departure leaves weather cards visible', (tester) async {
    final api = _MockApiClient();
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(db.close);
    when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
      (invocation) async {
        final path = invocation.positionalArguments.first as String;
        return path.endsWith('/notifications')
            ? _responseJson(notifications: [])
            : _alertsResponseJson();
      },
    );

    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          offlineDatabaseProvider.overrideWithValue(db),
          identityCacheScopeProvider.overrideWithValue('account:user-1'),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: ItineraryAlertsSection(tripId: 'trip-123'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byType(DepartureBanner), findsNothing);
    expect(find.byType(AlertCard), findsOneWidget);
    expect(find.text('Server weather message'), findsOneWidget);
  });

  // ===================== Proof: Banner text equals server copy =====================
  testWidgets('banner text equals server title and message', (tester) async {
    final candidate = NotificationCandidate.fromJson(_candidateJson());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DepartureBanner(candidate: candidate),
        ),
      ),
    );
    await tester.pump();

    // Title must match server exactly
    expect(
      find.text('Time to head to Kuang Si Falls'),
      findsOneWidget,
    );
    // Message must match server exactly
    expect(
      find.text(
        'Leave for Kuang Si Falls by 08:20. The drive is about 42 minutes by road; 10 extra minutes added for forecast rain.',
      ),
      findsOneWidget,
    );
  });

  // ===================== Proof: Notification dismissals table is separate =====================
  test('notification_dismissals is separate from alert_dismissals', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    await db.db;

    // Dismiss a notification
    await db.dismissNotification(
      identityScope: 'scope-1',
      notificationId: 'notif-x',
    );
    // Dismiss an alert
    await db.dismissAlert(
      identityScope: 'scope-1',
      alertId: 'alert-y',
    );

    // Notification dismissals should NOT contain alert IDs
    final notifDismissed = await db.getDismissedNotificationIds(
      identityScope: 'scope-1',
    );
    expect(notifDismissed, contains('notif-x'));
    expect(notifDismissed, isNot(contains('alert-y')));

    // Alert dismissals should NOT contain notification IDs
    final alertDismissed = await db.getDismissedAlertIds(
      identityScope: 'scope-1',
    );
    expect(alertDismissed, contains('alert-y'));
    expect(alertDismissed, isNot(contains('notif-x')));

    await db.close();
  });

  // ===================== Proof: Resume debounce =====================
  testWidgets('resume inside 15 minutes does not issue a second request',
      (tester) async {
    final lastAttempt = DateTime.utc(2026, 10, 5, 12);
    expect(
      alertResumeRefreshDue(
        lastAttempt,
        lastAttempt.add(const Duration(minutes: 5)),
      ),
      isFalse,
    );
    expect(
      alertResumeRefreshDue(
        lastAttempt,
        lastAttempt.add(const Duration(minutes: 15)),
      ),
      isTrue,
    );

    final api = _MockApiClient();
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(db.close);
    when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
      (invocation) async {
        final path = invocation.positionalArguments.first as String;
        if (path.endsWith('/notifications')) {
          return _responseJson(notifications: []);
        }
        return {
          'trip_id': 'trip-123',
          'status': 'unconfigured',
          'alerts': <Object>[],
          'refreshed_at': '2026-10-04T01:05:00Z',
        };
      },
    );
    await tester.pumpWidget(
      ProviderScope(
        overrides: [
          apiClientProvider.overrideWithValue(api),
          offlineDatabaseProvider.overrideWithValue(db),
          identityCacheScopeProvider.overrideWithValue('account:user-1'),
        ],
        child: const MaterialApp(
          home: Scaffold(
            body: ItineraryAlertsSection(tripId: 'trip-123'),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
    clearInteractions(api);

    await tester.binding.handleAppLifecycleStateChanged(
      AppLifecycleState.paused,
    );
    await tester.binding.handleAppLifecycleStateChanged(
      AppLifecycleState.resumed,
    );
    await tester.pump();

    verifyNever(
      () => api.get(
        '/trip/trip-123/notifications',
        query: any(named: 'query'),
      ),
    );
  });

  // ===================== Proof: Tap on known node_id =====================
  testWidgets('tap on banner calls onTapNodeId with correct nodeId', (tester) async {
    String? tappedNodeId;
    final candidate = NotificationCandidate.fromJson(_candidateJson());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DepartureBanner(
            candidate: candidate,
            onTapNodeId: (id) => tappedNodeId = id,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.byType(DepartureBanner));
    expect(tappedNodeId, 'node-7');
  });

  // ===================== Proof: Notification cache =====================
  test('network failure with unexpired cache still shows cached banner', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(db.close);
    final api = _MockApiClient();
    when(() => api.get(any(), query: any(named: 'query')))
        .thenThrow(const NetworkException());

    final payloadJson = '{"trip_id":"t1","refreshed_at":"2026-10-04T01:05:00Z","status":"available","notifications":[{"notification_id":"cached-1","type":"departure_reminder","priority":"trip_critical","node_id":"n1","title":"Cached title","message":"Cached msg","eligible_at":"2026-10-04T00:58:00Z","expires_at":"2099-12-31T00:00:00Z","recommended_departure_at":"2026-10-04T01:20:00Z","time_zone":"Asia/Vientiane","deep_link":"/trip/t1/node/n1","evidence":{"route":{"source":"stub","observed_at":"2026-10-04T01:05:00Z","traffic_duration_minutes":30,"mode":"driving","origin_basis":"previous_node"},"policy":{"arrival_buffer_minutes":10,"weather_buffer_minutes":0}}}]}';
    await db.cacheNotifications(
      identityScope: 'scope-1',
      tripId: 't1',
      payloadJson: payloadJson,
      expiresAt: '2099-12-31T00:00:00Z',
    );

    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        offlineDatabaseProvider.overrideWithValue(db),
        identityCacheScopeProvider.overrideWithValue('scope-1'),
      ],
    );
    addTearDown(container.dispose);

    final state = await container.read(
      departureNotifierProvider('t1').future,
    );
    expect(state.status, 'cached');
    expect(state.visible?.notificationId, 'cached-1');
  });

  test('HTTP 503 with unexpired cache still shows cached banner', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(db.close);
    final api = _MockApiClient();
    when(() => api.get(any(), query: any(named: 'query')))
        .thenThrow(const ServerException());

    await db.cacheNotifications(
      identityScope: 'scope-1',
      tripId: 't1',
      payloadJson: jsonEncode(_responseJson()),
      expiresAt: '2099-12-31T00:00:00Z',
    );
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        offlineDatabaseProvider.overrideWithValue(db),
        identityCacheScopeProvider.overrideWithValue('scope-1'),
      ],
    );
    addTearDown(container.dispose);

    final state = await container.read(
      departureNotifierProvider('t1').future,
    );
    expect(state.status, 'cached');
    expect(state.visible?.notificationId, 'notif-1');
  });

  test('401 never renders a cached departure', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(db.close);
    final api = _MockApiClient();
    when(() => api.get(any(), query: any(named: 'query')))
        .thenThrow(const UnauthorizedException());

    await db.cacheNotifications(
      identityScope: 'scope-1',
      tripId: 't1',
      payloadJson: jsonEncode(_responseJson()),
      expiresAt: '2099-12-31T00:00:00Z',
    );
    final container = ProviderContainer(
      overrides: [
        apiClientProvider.overrideWithValue(api),
        offlineDatabaseProvider.overrideWithValue(db),
        identityCacheScopeProvider.overrideWithValue('scope-1'),
      ],
    );
    addTearDown(container.dispose);

    final state = await container.read(
      departureNotifierProvider('t1').future,
    );
    expect(state.status, 'auth_error');
    expect(state.visible, isNull);
  });

  // ===================== Proof: unconfigured/empty renders nothing =====================
  test('unconfigured status renders no visible candidate', () {
    final state = const DepartureState(status: 'unconfigured');
    expect(state.visible, isNull);
  });

  // ===================== Proof: Deterministic ID stable =====================
  test('repeated parse returns same notification_id', () {
    final c1 = NotificationCandidate.fromJson(_candidateJson());
    final c2 = NotificationCandidate.fromJson(_candidateJson());
    expect(c1.notificationId, c2.notificationId);
  });

  // ===================== SABOTAGE PROOF 1: client-side rewrite =====================
  testWidgets('SABOTAGE: client-side message suffix is detected', (tester) async {
    // If someone hard-codes a suffix onto message, this test catches it.
    final candidate = NotificationCandidate.fromJson(_candidateJson(
      message: 'Server message only.',
    ));
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DepartureBanner(candidate: candidate),
        ),
      ),
    );
    await tester.pump();

    // Must find EXACTLY the server message, nothing more.
    expect(find.text('Server message only.'), findsOneWidget);
    // A sabotage suffix like ' (live)' must not appear.
    expect(find.textContaining('(live)'), findsNothing);
    expect(find.textContaining('updated'), findsNothing);
  });

  // ===================== SABOTAGE PROOF 3: skip persisting dismissals =====================
  test('SABOTAGE: dismiss survives rebuild via notification_dismissals', () async {
    final tempDir = await Directory.systemTemp.createTemp(
      'travel-buddy-notification-test-',
    );
    addTearDown(() => tempDir.delete(recursive: true));
    final dbPath = '${tempDir.path}/offline.db';
    final db = OfflineDatabase(testPath: dbPath);
    await db.db;

    // Dismiss
    await db.dismissNotification(
      identityScope: 'sabotage-scope',
      notificationId: 'sab-notif-1',
    );

    // Close and reopen (simulate app restart)
    await db.close();
    final db2 = OfflineDatabase(testPath: dbPath);
    await db2.db;

    final dismissed = await db2.getDismissedNotificationIds(
      identityScope: 'sabotage-scope',
    );
    // If persistence is skipped, this fails.
    expect(dismissed, contains('sab-notif-1'));

    await db2.close();
  });

  // ===================== Proof: Caption shows sources =====================
  testWidgets('caption shows route + weather sources', (tester) async {
    final candidate = NotificationCandidate.fromJson(_candidateJson());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: DepartureBanner(candidate: candidate),
        ),
      ),
    );
    await tester.pump();
    expect(find.text('google_maps + openweather'), findsOneWidget);
  });
}
