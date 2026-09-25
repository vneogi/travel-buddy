// SPEC-45 R2: Production warning widget sabotage proofs.
//
// UNVERIFIED: flutter test has not been run on this host.
//
// These tests render the production WarningRow widget from
// warning_helpers.dart -- the same code used by ItineraryScreen's
// _ScheduleWarningsBanner sheet. If WarningRow, matchWarningToNode,
// warningLocalDate, or the button callbacks are broken, these tests fail.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/warning_helpers.dart';

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

final _jomaNode = TripNode(
  nodeId: 'joma-1',
  venueName: 'Joma Bakery',
  // 2 Oct 2026, 02:00 UTC => Fri 2 Oct 09:00 ICT (Vientiane)
  scheduledStart: DateTime.utc(2026, 10, 2, 2, 0),
  durationMinutes: 90,
  isLocked: false,
  status: NodeStatus.pending,
  vibeTags: const [],
  geoRegion: 'vientiane_laos',
);

void main() {
  // ---- Unit proofs for production helpers ----

  group('extractQuotedVenue (production code)', () {
    test('extracts quoted venue name', () {
      expect(
        extractQuotedVenue(
            "'Joma Bakery' is closed at its scheduled time."),
        'Joma Bakery',
      );
    });

    test('returns null for unquoted warning', () {
      expect(
        extractQuotedVenue('General warning without quotes.'),
        isNull,
      );
    });
  });

  group('matchWarningToNode (production code)', () {
    test('matches by exact venueName', () {
      final result = matchWarningToNode(
        "'Joma Bakery' is closed at its scheduled time.",
        [_jomaNode],
      );
      expect(result, isNotNull);
      expect(result!.nodeId, 'joma-1');
    });

    test('returns null for unmatched venue', () {
      final result = matchWarningToNode(
        "'Unknown Place' has no map location.",
        [_jomaNode],
      );
      expect(result, isNull);
    });
  });

  group('warningLocalDate (production code)', () {
    test('formats destination-local date correctly', () {
      // 2 Oct 2026 is a Friday. Vientiane is UTC+7.
      expect(warningLocalDate(_jomaNode), 'Fri, 2 Oct');
    });
  });

  // ---- Widget proofs for production WarningRow ----

  group('WarningRow matched warning', () {
    testWidgets('shows venue, local date, reason, and Open stop',
        (tester) async {
      String? focusedNodeId;
      await tester.pumpWidget(_wrap(WarningRow(
        warning: "'Joma Bakery' is closed at its scheduled time.",
        nodes: [_jomaNode],
        onFocusNode: (id) => focusedNodeId = id,
      )));
      await tester.pumpAndSettle();

      // Venue name (bold)
      expect(find.text('Joma Bakery'), findsOneWidget);
      // Destination-local date
      expect(find.text('Fri, 2 Oct'), findsOneWidget);
      // Reason text
      expect(
        find.text("'Joma Bakery' is closed at its scheduled time."),
        findsOneWidget,
      );
      // Open stop button present
      expect(find.text('Open stop'), findsOneWidget);
      // Dismiss button absent for matched row
      expect(find.text('Dismiss'), findsNothing);

      // Tap Open stop
      await tester.tap(find.text('Open stop'));
      await tester.pumpAndSettle();

      // Exact node ID reaches the focus callback
      expect(focusedNodeId, 'joma-1');
    });
  });

  group('WarningRow unmatched warning', () {
    testWidgets('shows raw text and Dismiss; Dismiss fires onDismiss',
        (tester) async {
      var dismissed = false;
      await tester.pumpWidget(_wrap(WarningRow(
        warning: 'Evening return was not checked.',
        nodes: [_jomaNode],
        onDismiss: () => dismissed = true,
      )));
      await tester.pumpAndSettle();

      // Venue name NOT shown (unmatched)
      expect(find.text('Joma Bakery'), findsNothing);
      // Raw warning text shown
      expect(find.text('Evening return was not checked.'), findsOneWidget);
      // Dismiss present, Open stop absent
      expect(find.text('Dismiss'), findsOneWidget);
      expect(find.text('Open stop'), findsNothing);

      // Tap Dismiss
      await tester.tap(find.text('Dismiss'));
      await tester.pumpAndSettle();
      expect(dismissed, isTrue,
          reason: 'Dismiss button must fire onDismiss callback');
    });

    testWidgets('unmatched does not crash with null onDismiss',
        (tester) async {
      await tester.pumpWidget(_wrap(const WarningRow(
        warning: 'Some generic warning.',
        nodes: [],
        // onDismiss intentionally null
      )));
      await tester.pumpAndSettle();
      expect(find.text('Dismiss'), findsOneWidget);
      // Button rendered but disabled (onPressed is null).
      final button = tester.widget<TextButton>(
        find.ancestor(
          of: find.text('Dismiss'),
          matching: find.byType(TextButton),
        ),
      );
      expect(button.onPressed, isNull);
    });
  });
}
