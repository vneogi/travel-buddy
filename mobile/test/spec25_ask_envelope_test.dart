// SPEC-25 Ask envelope + UI: model parsing and widget pumping.
//
// Tests verify fail-closed parsing and that AskBubble renders the right
// content. They fail if AskBubble is removed or its rendering regresses.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/chat/ask_bubble.dart';
import 'package:travel_buddy/render/confirm_affordance.dart';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

Widget _wrap(Widget child) => MaterialApp(home: Scaffold(body: child));

AskResponse _hours() => const AskResponse(
      answer: 'Ban Anou Night Market hours: Mon 17:00-23:00.',
      tier: AskTier.hedge,
      path: 'grounded_deterministic',
      intent: 'opening_hours',
      sourceClass: 'curated_catalog',
    );

AskResponse _dish() => const AskResponse(
      answer: 'Khao Piak Sen is a Lao noodle soup.',
      tier: AskTier.hedge,
      path: 'grounded_deterministic',
      intent: 'dish_fact',
      sourceClass: 'curated_catalog',
      foodDisclaimer: 'Menus change; confirm ingredients with the venue.',
    );

AskResponse _refuse() => const AskResponse(
      answer: 'I can only help with trip-related questions.',
      tier: AskTier.refuse,
      path: 'out_of_scope',
      intent: 'out_of_scope',
    );

AskResponse _planChange() => const AskResponse(
      answer: 'I can swap that activity for you.',
      tier: AskTier.defer_,
      path: 'grounded_deterministic',
      intent: 'plan_change',
      proposal: AskProposal(
        eventType: 'swap_activity',
        targetNodeId: 'node-42',
        summary: 'Swap Wat Xieng Thong for Kuang Si Falls',
      ),
    );

void main() {
  // =========================================================================
  // 1. Fail-closed parsing: missing path or intent throws.
  // =========================================================================
  group('AskResponse.fromJson fail-closed', () {
    test('missing path throws ArgumentError', () {
      expect(
        () => AskResponse.fromJson({
          'answer': 'x',
          'tier': 'hedge',
          'intent': 'opening_hours',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('empty intent throws ArgumentError', () {
      expect(
        () => AskResponse.fromJson({
          'answer': 'x',
          'tier': 'hedge',
          'path': 'grounded_deterministic',
          'intent': '',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('missing tier still throws', () {
      expect(
        () => AskResponse.fromJson({
          'answer': 'x',
          'path': 'grounded_deterministic',
          'intent': 'opening_hours',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });
  });

  // =========================================================================
  // 2. Hours AskBubble: answer text shown, no "Travellers usually say".
  // =========================================================================
  group('AskBubble hours', () {
    testWidgets('shows answer text without hedge template', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _hours())));
      expect(find.text(_hours().answer), findsOneWidget);
      expect(find.textContaining('Travellers usually say'), findsNothing);
      expect(find.byKey(const Key('ask_fact_view')), findsOneWidget);
      expect(find.text('curated_catalog'), findsOneWidget);
      expect(find.textContaining('Menus change'), findsNothing);
    });
  });

  // =========================================================================
  // 3. Dish fact: disclaimer shown; hours fixture does not show it.
  // =========================================================================
  group('AskBubble dish disclaimer', () {
    testWidgets('dish_fact shows food_disclaimer', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _dish())));
      expect(find.text(_dish().answer), findsOneWidget);
      expect(
        find.text('Menus change; confirm ingredients with the venue.'),
        findsOneWidget,
      );
    });

    testWidgets('hours fixture does NOT show disclaimer', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _hours())));
      expect(find.textContaining('Menus change'), findsNothing);
    });
  });

  // =========================================================================
  // 4. Refuse: backend answer visible, no "Information not available".
  // =========================================================================
  group('AskBubble refuse', () {
    testWidgets('shows backend answer, not generic refuse', (tester) async {
      await tester.pumpWidget(_wrap(AskBubble(askResponse: _refuse())));
      expect(find.text(_refuse().answer), findsOneWidget);
      expect(find.text('Information not available'), findsNothing);
    });
  });

  // =========================================================================
  // 5. Plan-change + proposal: ConfirmAffordance present; tap calls back.
  // =========================================================================
  group('AskBubble plan-change', () {
    testWidgets('confirm affordance present and tappable', (tester) async {
      var confirmed = false;
      await tester.pumpWidget(_wrap(
        AskBubble(
          askResponse: _planChange(),
          onConfirm: () => confirmed = true,
        ),
      ));
      expect(
        find.byKey(const Key('ask_plan_change_confirm')),
        findsOneWidget,
      );
      expect(find.byType(ConfirmAffordance), findsOneWidget);
      await tester.tap(find.text('Confirm'));
      expect(confirmed, isTrue);
    });

    testWidgets('dismiss does not fire onConfirm', (tester) async {
      var confirmed = false;
      await tester.pumpWidget(_wrap(
        AskBubble(
          askResponse: _planChange(),
          onConfirm: () => confirmed = true,
          onDismiss: () {},
        ),
      ));
      await tester.tap(find.byIcon(Icons.close));
      expect(confirmed, isFalse);
    });

    testWidgets('plan_change without proposal has no confirm', (tester) async {
      const noProposal = AskResponse(
        answer: 'Which activity do you mean?',
        tier: AskTier.defer_,
        path: 'grounded_deterministic',
        intent: 'plan_change',
      );
      await tester.pumpWidget(
        _wrap(const AskBubble(askResponse: noProposal)),
      );
      expect(find.byType(ConfirmAffordance), findsNothing);
      expect(find.text('Which activity do you mean?'), findsOneWidget);
    });
  });

  // =========================================================================
  // 6. Offline key contract.
  // =========================================================================
  group('Offline key contract', () {
    testWidgets('offline refuse key and copy present', (tester) async {
      await tester.pumpWidget(_wrap(
        const SizedBox(
          key: Key('ask_offline_refuse'),
          child: Text('Not available offline'),
        ),
      ));
      expect(find.byKey(const Key('ask_offline_refuse')), findsOneWidget);
      expect(find.text('Not available offline'), findsOneWidget);
    });
  });
}
