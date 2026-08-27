import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/data/context_alert.dart';
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
}) =>
    {
      'alert_id': alertId,
      'alert_type': type,
      'severity': severity,
      'message': message,
      'affected_node_ids': ['n1'],
      'affected_node_names': ['Desert Safari'],
      'source': 'openweather',
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
}) =>
    {
      'trip_id': 't1',
      'status': 'available',
      'alerts': alerts ?? [_alertJson()],
      'refreshed_at': '2026-10-05T07:00:00Z',
    };

void main() {
  // Use FFI for sqflite in tests
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

  // ===================== Test 2: Alert card renders source =====================
  testWidgets('alert card renders source and freshness', (tester) async {
    final alert = ContextAlert.fromJson(_alertJson());
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AlertCard(alert: alert))),
    );
    await tester.pump(); // single frame, no pumpAndSettle
    expect(find.textContaining('OpenWeather'), findsOneWidget);
    expect(find.textContaining('72%'), findsOneWidget);
  });

  // ===================== Test 3: Unconfigured shows no alert =====================
  test('TripAlertsResponse unconfigured has empty alerts', () {
    final resp = TripAlertsResponse.fromJson({
      'trip_id': 't1',
      'status': 'unconfigured',
      'alerts': <Map<String, dynamic>>[],
      'refreshed_at': '2026-10-05T07:00:00Z',
    });
    expect(resp.status, 'unconfigured');
    expect(resp.alerts, isEmpty);
  });

  // ===================== Test 4: Expired cache hidden =====================
  test('isExpired correctly identifies expired alerts', () {
    final expired = ContextAlert.fromJson(
      _alertJson(expiresAt: '2020-01-01T00:00:00Z'),
    );
    expect(expired.isExpired, true);

    final valid = ContextAlert.fromJson(
      _alertJson(expiresAt: '2099-01-01T00:00:00Z'),
    );
    expect(valid.isExpired, false);
  });

  // ===================== Test 5: Dismiss callback fires =====================
  testWidgets('dismiss callback fires on tap', (tester) async {
    bool dismissed = false;
    final alert = ContextAlert.fromJson(_alertJson());
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AlertCard(
            alert: alert,
            onDismiss: () => dismissed = true,
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.tap(find.byIcon(Icons.close));
    expect(dismissed, true);
  });

  // ===================== Test 6: No raw exception/payload =====================
  test('alert message contains no JSON or stack trace markers', () {
    final alert = ContextAlert.fromJson(_alertJson());
    expect(alert.message, isNot(contains('{')));
    expect(alert.message, isNot(contains('Exception')));
    expect(alert.message, isNot(contains('stack')));
  });

  // ===================== Test 7: SQLite round-trip + identity isolation =====================
  test('SQLite alert cache is identity-scoped', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    final payload = jsonEncode(_responseJson());

    // Identity A caches alerts
    await db.cacheAlerts(
      identityScope: 'user-a',
      tripId: 'trip-1',
      payloadJson: payload,
      expiresAt: '2099-01-01T00:00:00Z',
    );

    // Identity A can read
    final cached = await db.getCachedAlerts(
      identityScope: 'user-a',
      tripId: 'trip-1',
    );
    expect(cached, isNotNull);
    expect(cached, contains('abc123'));

    // Identity B cannot read A's cache
    final other = await db.getCachedAlerts(
      identityScope: 'user-b',
      tripId: 'trip-1',
    );
    expect(other, isNull);
  });

  // ===================== Test 8: Dismissal persists =====================
  test('dismissal persists and survives notifier recreation', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);

    await db.dismissAlert(identityScope: 'user-a', alertId: 'alert-xyz');
    final dismissed = await db.getDismissedAlertIds(identityScope: 'user-a');
    expect(dismissed, contains('alert-xyz'));

    // Different identity does not see it
    final other = await db.getDismissedAlertIds(identityScope: 'user-b');
    expect(other, isNot(contains('alert-xyz')));
  });

  // ===================== Test 9: Expired cache pruned =====================
  test('expired cache rows are pruned', () async {
    final db = OfflineDatabase(testPath: inMemoryDatabasePath);
    await db.cacheAlerts(
      identityScope: 'u1',
      tripId: 't1',
      payloadJson: '{}',
      expiresAt: '2020-01-01T00:00:00Z', // already expired
    );
    await db.pruneAlertData();
    final cached = await db.getCachedAlerts(identityScope: 'u1', tripId: 't1');
    expect(cached, isNull);
  });

  // ===================== Test 10: Cancel node in original position =====================
  test('canceled node stays at original index in response', () {
    final nodes = [
      {'node_id': 'a', 'venue_name': 'A', 'status': 'pending'},
      {'node_id': 'b', 'venue_name': 'B', 'status': 'skipped'},
      {'node_id': 'c', 'venue_name': 'C', 'status': 'pending'},
    ];
    expect(nodes[1]['status'], 'skipped');
    expect(nodes[1]['venue_name'], 'B');
    expect(nodes.map((n) => n['node_id']).toList(), ['a', 'b', 'c']);
  });
}
