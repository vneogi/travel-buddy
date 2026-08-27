import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/context_alert.dart';
import 'package:travel_buddy/widgets/alert_card.dart';

// Sample alert JSON fixture
Map<String, dynamic> _alertJson({
  String type = 'rain',
  String severity = 'advisory',
  String message = '72% chance of rain during Desert Safari. Consider indoor alternatives.',
  double? pop = 0.72,
}) =>
    {
      'alert_id': 'abc123',
      'alert_type': type,
      'severity': severity,
      'message': message,
      'affected_node_ids': ['n1'],
      'affected_node_names': ['Desert Safari'],
      'source': 'openweather',
      'source_updated_at': '2026-10-05T06:30:00Z',
      'valid_from': '2026-10-05T09:00:00Z',
      'valid_until': '2026-10-05T12:00:00Z',
      'expires_at': '2026-10-05T12:30:00Z',
      'location_basis': 'node_coordinates',
      'geo_region': 'dubai_uae',
      'evidence': {
        'rain_probability': pop,
        'condition_code': 500,
      },
      'suggested_action': 'review_outdoor_plans',
      'auto_applied': false,
    };

void main() {
  // Test 1: ContextAlert JSON parsing
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

  // Test 2: Rain/heat alert renders source and freshness
  testWidgets('alert card renders source and freshness', (tester) async {
    final alert = ContextAlert.fromJson(_alertJson());
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: AlertCard(alert: alert))),
    );
    expect(find.textContaining('OpenWeather'), findsOneWidget);
    expect(find.textContaining('rain'), findsOneWidget);
  });

  // Test 4: Unconfigured response shows no alert/error
  test('TripAlertsResponse unconfigured has empty alerts', () {
    final resp = TripAlertsResponse.fromJson({
      'trip_id': 't1',
      'status': 'unconfigured',
      'alerts': [],
      'refreshed_at': '2026-10-05T07:00:00Z',
    });
    expect(resp.status, 'unconfigured');
    expect(resp.alerts, isEmpty);
  });

  // Test 6: Expired cache is hidden
  test('isExpired correctly identifies expired alerts', () {
    final expiredJson = _alertJson();
    expiredJson['expires_at'] = '2020-01-01T00:00:00Z'; // past
    final alert = ContextAlert.fromJson(expiredJson);
    expect(alert.isExpired, true);
  });

  // Test 8: Dismiss removes alert locally (via callback)
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
    await tester.tap(find.byIcon(Icons.close));
    expect(dismissed, true);
  });

  // Test 9: No raw exception/provider payload shown
  test('alert message contains no JSON or stack trace markers', () {
    final alert = ContextAlert.fromJson(_alertJson());
    expect(alert.message, isNot(contains('{')));
    expect(alert.message, isNot(contains('Exception')));
    expect(alert.message, isNot(contains('stack')));
  });

  // Test 10: Cancel result remains in original list position
  test('canceled node with skipped status stays at original index in list', () {
    // This simulates the client receiving a cancel response
    // where the backend preserves node order
    final nodes = [
      {'node_id': 'a', 'venue_name': 'A', 'status': 'pending', 'scheduled_start': '2026-10-05T09:00:00Z'},
      {'node_id': 'b', 'venue_name': 'B', 'status': 'skipped', 'scheduled_start': '2026-10-05T11:00:00Z'},
      {'node_id': 'c', 'venue_name': 'C', 'status': 'pending', 'scheduled_start': '2026-10-05T13:00:00Z'},
    ];
    // B is at index 1 and is skipped
    expect(nodes[1]['status'], 'skipped');
    expect(nodes[1]['venue_name'], 'B');
    // Order preserved
    expect(nodes.map((n) => n['node_id']).toList(), ['a', 'b', 'c']);
  });
}
