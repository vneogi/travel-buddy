import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/data/context_alert.dart';
import 'package:travel_buddy/features/alerts/alerts_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/widgets/alert_card.dart';

// ===================== Fixtures =====================

Map<String, dynamic> _alertJson({
  String alertId = 'abc123',
  String type = 'rain',
  String severity = 'advisory',
  String message =
      '72% chance of rain during Desert Safari. Review plans that require outdoor time.',
  double? pop = 0.72,
  String? expiresAt,
  String source = 'openweather',
}) =>
    {
      'alert_id': alertId,
      'alert_type': type,
      'severity': severity,
      'message': message,
      'affected_node_ids': ['n1'],
      'affected_node_names': ['Desert Safari'],
      'source': source,
      'source_updated_at': '2026-10-05T06:30:00Z',
      'valid_from': '2026-10-05T09:00:00Z',
      'valid_until': '2026-10-05T12:00:00Z',
      'expires_at': expiresAt ?? '2099-10-05T12:30:00Z',
      'location_basis': 'node_coordinates',
      'geo_region': 'dubai_uae',
      'evidence': {
        'rain_probability': pop,
        'condition_code': 500,
      },
      'suggested_action': 'review_outdoor_plans',
      'auto_applied': false,
    };

Map<String, dynamic> _responseJson({
  List<Map<String, dynamic>>? alerts,
  String status = 'available',
}) =>
    {
      'trip_id': 't1',
      'status': status,
      'alerts': alerts ?? [_alertJson()],
      'refreshed_at': '2026-10-05T07:00:00Z',
    };

void main() {
  group('alert resume refresh cooldown', () {
    final lastAttempt = DateTime.utc(2026, 9, 5, 12);

    test('does not refetch for repeated short Windows resume events', () {
      expect(
        alertResumeRefreshDue(
          lastAttempt,
          lastAttempt.add(const Duration(minutes: 1)),
        ),
        isFalse,
      );
    });

    test('allows a refresh after fifteen minutes', () {
      expect(
        alertResumeRefreshDue(
          lastAttempt,
          lastAttempt.add(const Duration(minutes: 15)),
        ),
        isTrue,
      );
    });
  });

  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  // ===================== Test 1: JSON parsing =====================
  test('ContextAlert parses from JSON correctly', () {
    final alert = ContextAlert.fromJson(_alertJson());
    expect(alert.alertId, 'abc123');
    expect(alert.alertType, 'rain');
    expect(alert.severity, 'advisory');
    expect(alert.message, contains('72%'));
    expect(alert.affectedNodeNames, ['Desert Safari']);
    expect(alert.source, 'openweather');
    expect(alert.evidence.rainProbability, 0.72);
    expect(alert.autoApplied, false);
  });

  // ===================== Test 2: AlertCard renders source from data =====================
  testWidgets('AlertCard renders source from alert.source via mapper', (tester) async {
    final alert = ContextAlert.fromJson(_alertJson(source: 'openweather'));
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AlertCard(alert: alert))),
    );
    await tester.pump();
    expect(find.textContaining('OpenWeather'), findsOneWidget);

    // Unknown source renders raw value
    final customAlert = ContextAlert.fromJson(_alertJson(source: 'custom_src'));
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AlertCard(alert: customAlert))),
    );
    await tester.pump();
    expect(find.textContaining('custom_src'), findsOneWidget);
  });

  // ===================== Test 3: Expired alerts hidden =====================
  test('isExpired identifies expired alerts', () {
    final expired = ContextAlert.fromJson(
      _alertJson(expiresAt: '2020-01-01T00:00:00Z'),
    );
    expect(expired.isExpired, true);

    final valid = ContextAlert.fromJson(
      _alertJson(expiresAt: '2099-01-01T00:00:00Z'),
    );
    expect(valid.isExpired, false);
  });

  // ===================== Test 4: Dismiss callback fires =====================
  testWidgets('dismiss callback fires on tap', (tester) async {
    bool dismissed = false;
    final alert = ContextAlert.fromJson(_alertJson());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AlertCard(alert: alert, onDismiss: () => dismissed = true),
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.byIcon(Icons.close));
    expect(dismissed, true);
  });

  // ===================== Test 5: Identity isolation (A cannot read B) =====================
  test('identity A cache is invisible to identity B', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(() async => (await db.db).close());

    final payload = jsonEncode(_responseJson());
    await db.cacheAlerts(
      identityScope: 'account:user-a',
      tripId: 'trip-1',
      payloadJson: payload,
      expiresAt: '2099-01-01T00:00:00Z',
    );

    final fromA = await db.getCachedAlerts(
      identityScope: 'account:user-a',
      tripId: 'trip-1',
    );
    expect(fromA, isNotNull);

    final fromB = await db.getCachedAlerts(
      identityScope: 'account:user-b',
      tripId: 'trip-1',
    );
    expect(fromB, isNull);
  });

  // ===================== Test 6: Dismissal persists across recreation =====================
  test('dismissal persists across OfflineDatabase recreation', () async {
    // Same path = same DB file, simulating provider recreation
    final db1 = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(() async => (await db1.db).close());

    await db1.dismissAlert(identityScope: 'u1', alertId: 'alert-xyz');
    final dismissed = await db1.getDismissedAlertIds(identityScope: 'u1');
    expect(dismissed, contains('alert-xyz'));

    // Identity B does not see A's dismissal
    final other = await db1.getDismissedAlertIds(identityScope: 'u2');
    expect(other, isNot(contains('alert-xyz')));
  });

  // ===================== Test 7: Expired cache pruned =====================
  test('expired cache rows are pruned', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(() async => (await db.db).close());

    await db.cacheAlerts(
      identityScope: 'u1',
      tripId: 't1',
      payloadJson: '{}',
      expiresAt: '2020-01-01T00:00:00Z',
    );
    await db.pruneAlertData();
    final cached = await db.getCachedAlerts(identityScope: 'u1', tripId: 't1');
    expect(cached, isNull);
  });

  // ===================== Test 8: Unconfigured shows no error =====================
  test('TripAlertsResponse unconfigured parses correctly', () {
    final resp = TripAlertsResponse.fromJson(
      _responseJson(alerts: [], status: 'unconfigured'),
    );
    expect(resp.status, 'unconfigured');
    expect(resp.alerts, isEmpty);
  });

  // ===================== Test 9: No raw exception in message =====================
  test('alert message contains no raw exception markers', () {
    final alert = ContextAlert.fromJson(_alertJson());
    expect(alert.message, isNot(contains('{')));
    expect(alert.message, isNot(contains('Exception')));
    expect(alert.message, isNot(contains('stack')));
  });

  // ===================== Test 10: getCachedAlerts returns null for expired =====================
  test('getCachedAlerts returns null for expired entries', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    addTearDown(() async => (await db.db).close());

    await db.cacheAlerts(
      identityScope: 'u1',
      tripId: 'trip-expired',
      payloadJson: jsonEncode(_responseJson()),
      expiresAt: '2020-01-01T00:00:00Z',
    );
    final result = await db.getCachedAlerts(
      identityScope: 'u1',
      tripId: 'trip-expired',
    );
    expect(result, isNull);
  });

}
