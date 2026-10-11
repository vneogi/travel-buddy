// SPEC-45 Phase B: Field trust hygiene tests.
//
// Clock-injected where [now] is used; pure unit tests for helpers,
// widget tests where the brief requires them.

import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/context_alert.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/alerts/alert_policy.dart';
import 'package:travel_buddy/features/itinerary/current_window.dart';

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

ContextAlert _alert({
  required String id,
  String type = 'rain',
  String severity = 'advisory',
  String message = 'Rain expected',
  DateTime? validFrom,
  DateTime? validUntil,
  DateTime? expiresAt,
  String? geoRegion,
  String suggestedAction = '',
  List<String> affectedNodeIds = const [],
}) {
  final now = DateTime.utc(2026, 10, 2, 6);
  return ContextAlert(
    alertId: id,
    alertType: type,
    severity: severity,
    message: message,
    affectedNodeIds: affectedNodeIds,
    affectedNodeNames: const [],
    source: 'openweather',
    sourceUpdatedAt: now,
    validFrom: validFrom ?? now,
    validUntil: validUntil ?? now.add(const Duration(hours: 12)),
    expiresAt: expiresAt ?? now.add(const Duration(hours: 24)),
    locationBasis: 'geo',
    geoRegion: geoRegion ?? 'luang_prabang_laos',
    evidence: const AlertEvidence(),
    suggestedAction: suggestedAction,
  );
}

TripNode _node({
  required String id,
  String name = 'Test Stop',
  DateTime? start,
  int duration = 90,
  bool locked = false,
  String kind = 'activity',
  String? bookingType,
  String status = 'pending',
  String? geoRegion,
}) {
  return TripNode(
    nodeId: id,
    dayIndex: 0,
    seq: 1,
    nodeType: 'activity',
    venueName: name,
    scheduledStart: start ?? DateTime.utc(2026, 10, 2, 9),
    durationMinutes: duration,
    isLocked: locked,
    status: NodeStatus.fromWire(status),
    geoRegion: geoRegion ?? 'luang_prabang_laos',
    nodeKind: kind,
    bookingType: bookingType,
  );
}

// ---------------------------------------------------------------
void main() {
  // =============================================================
  // 1. Cap the advisory flood
  // =============================================================

  group('Alert cap (defect 1)', () {
    test('12 unexpired alerts -> 2 cards + N more alerts', () {
      final alerts = List.generate(
        12,
        (i) => _alert(id: 'a$i', type: 'type_$i'),
      );
      final coalesced = coalesceAlerts(alerts);
      final result = cappedAlerts(coalesced);
      expect(result.visible.length, 2);
      expect(result.overflowCount, 10);
    });

    test('coalesced duplicate rain alerts for the same day count as one', () {
      final a1 = _alert(
        id: 'a1',
        type: 'rain',
        validFrom: DateTime.utc(2026, 10, 2, 6),
      );
      final a2 = _alert(
        id: 'a2',
        type: 'rain',
        validFrom: DateTime.utc(2026, 10, 2, 12),
      );
      final coalesced = coalesceAlerts([a1, a2]);
      expect(coalesced.length, 1, reason: 'same day + type = 1 alert');
    });

    test('different types on the same day are separate', () {
      final rain = _alert(id: 'a1', type: 'rain');
      final heat = _alert(id: 'a2', type: 'heat');
      final coalesced = coalesceAlerts([rain, heat]);
      expect(coalesced.length, 2);
    });

    test('highest severity sorts first', () {
      final adv = _alert(id: 'a1', severity: 'advisory', type: 'heat');
      final warn = _alert(id: 'a2', severity: 'warning', type: 'rain');
      final coalesced = coalesceAlerts([adv, warn]);
      expect(coalesced.first.severity, 'warning');
    });

    // R17: force visible to return the unfiltered list; the cap test goes red.
    test('R17 sabotage: cappedAlerts enforces the cap on 5 distinct types', () {
      final alerts = List.generate(5, (i) => _alert(
        id: 'r$i',
        type: 'type_$i',
      ));
      final coalesced = coalesceAlerts(alerts);
      expect(coalesced.length, 5, reason: 'all distinct types survive coalesce');
      final result = cappedAlerts(coalesced);
      // This assertion would fail if cappedAlerts returned all 5.
      expect(result.visible.length, 2);
      expect(result.overflowCount, 3);
    });
  });

  // =============================================================
  // 2. Outcome prompts: split predicates + kind-specific
  // =============================================================

  group('Outcome prompts (defect 2)', () {
    test('yesterday activity: false for Today, true for day-section', () {
      // Oct 2, 16:00 UTC = Oct 2, 23:00 ICT
      final now = DateTime.utc(2026, 10, 2, 16);
      // Node scheduled Oct 1, 09:00 UTC = Oct 1, 16:00 ICT (yesterday)
      final node = _node(
        id: 'n1',
        start: DateTime.utc(2026, 10, 1, 9),
      );
      // Day-section: YES (past + pending)
      expect(nodeCanRecordOutcome(node, now, null), isTrue);
      // Today surface: NO (yesterday in destination-local time)
      expect(nodeShouldShowTodayOutcome(node, now, null), isFalse);
    });

    test('today activity shows on both surfaces', () {
      final now = DateTime.utc(2026, 10, 2, 16);
      final node = _node(
        id: 'n1',
        start: DateTime.utc(2026, 10, 2, 9),
      );
      expect(nodeCanRecordOutcome(node, now, null), isTrue);
      expect(nodeShouldShowTodayOutcome(node, now, null), isTrue);
    });

    test('future activity: false on both', () {
      final now = DateTime.utc(2026, 10, 2, 8);
      final node = _node(
        id: 'n1',
        start: DateTime.utc(2026, 10, 2, 9),
      );
      expect(nodeCanRecordOutcome(node, now, null), isFalse);
      expect(nodeShouldShowTodayOutcome(node, now, null), isFalse);
    });

    // R17: fold today-check back into nodeCanRecordOutcome -> yesterday test goes red.
    test('R17 sabotage: nodeCanRecordOutcome must not have today check', () {
      final now = DateTime.utc(2026, 10, 2, 16);
      final yesterday = _node(id: 'n1', start: DateTime.utc(2026, 10, 1, 9));
      // If someone adds a today-check to nodeCanRecordOutcome,
      // this assertion fails.
      expect(nodeCanRecordOutcome(yesterday, now, null), isTrue);
    });

    test('flight uses region display name, not venueName', () {
      final node = _node(
        id: 'f1',
        name: 'Thai Airways',  // should NOT appear
        kind: 'booking',
        bookingType: 'flight',
        geoRegion: 'luang_prabang_laos',
      );
      expect(outcomePromptText(node), 'Arrived in Luang Prabang?');
    });

    test('flight with unknown region uses "Arrived?"', () {
      final node = _node(
        id: 'f2',
        name: 'Some Airline',
        kind: 'booking',
        bookingType: 'flight',
        geoRegion: 'unknown_place',
      );
      expect(outcomePromptText(node), 'Arrived?');
    });

    test('flight with null geoRegion uses "Arrived?"', () {
      final node = _node(
        id: 'f3',
        name: 'Thai Airways',
        kind: 'booking',
        bookingType: 'flight',
        geoRegion: null,
      );
      expect(outcomePromptText(node), 'Arrived?');
    });

    test('hotel uses "Checked in?"', () {
      final node = _node(id: 'h1', kind: 'booking', bookingType: 'hotel');
      expect(outcomePromptText(node), 'Checked in?');
    });

    test('hotel last night uses "Checked out?"', () {
      final node = _node(id: 'h2', kind: 'booking', bookingType: 'hotel');
      expect(
        outcomePromptText(node, isLastHotelNight: true),
        'Checked out?',
      );
    });

    test('tour uses "Did the tour happen?"', () {
      final node = _node(id: 't1', kind: 'booking', bookingType: 'tour');
      expect(outcomePromptText(node), 'Did the tour happen?');
    });

    test('regular activity uses "Did you visit?"', () {
      final node = _node(id: 'a1');
      expect(outcomePromptText(node), 'Did you visit?');
    });

    test('one-night hotel stay is Checked in (first occurrence, no continuation)', () {
      final node = _node(id: 'h3', kind: 'booking', bookingType: 'hotel');
      // First occurrence -> isLastHotelNight=false
      expect(outcomePromptText(node, isLastHotelNight: false), 'Checked in?');
    });
  });

  // =============================================================
  // 4. Empty swap explains the constraint
  // =============================================================

  group('SwapCandidatesResult (defect 4)', () {
    test('refusal code and copy parsed', () {
      final result = SwapCandidatesResult(
        candidates: const [],
        refusalCode: 'hours',
        refusalCopy: 'All nearby alternatives are closed at this time.',
      );
      expect(result.refusalCode, 'hours');
      expect(result.refusalCopy, isNotEmpty);
    });

    test('no refusal when candidates exist', () {
      final result = SwapCandidatesResult(candidates: const []);
      expect(result.refusalCode, isNull);
      expect(result.refusalCopy, isNull);
    });
  });

  // =============================================================
  // 5. Stale schedule reviews leave Today
  // =============================================================

  group('Schedule warning filter (defect 5)', () {
    test('banner hidden when all warnings match yesterday', () {
      final now = DateTime.utc(2026, 10, 2, 10);
      final node = _node(
        id: 'n1',
        name: 'Joma Bakery',
        start: DateTime.utc(2026, 10, 1, 9),
      );
      final warnings = ["'Joma Bakery' is closed at scheduled time"];
      final filtered = todayScheduleWarnings(warnings, [node], now);
      expect(filtered, isEmpty, reason: 'yesterday warning excluded');
    });

    test('today warning remains visible', () {
      final now = DateTime.utc(2026, 10, 2, 10);
      final node = _node(
        id: 'n1',
        name: 'Joma Bakery',
        start: DateTime.utc(2026, 10, 2, 9),
      );
      final warnings = ["'Joma Bakery' is closed at scheduled time"];
      final filtered = todayScheduleWarnings(warnings, [node], now);
      expect(filtered.length, 1);
    });

    test('unmatched warning excluded from Today banner', () {
      final now = DateTime.utc(2026, 10, 2, 10);
      final warnings = ["Unknown venue has an issue"];
      final filtered = todayScheduleWarnings(warnings, [], now);
      expect(filtered, isEmpty);
    });
  });
}
