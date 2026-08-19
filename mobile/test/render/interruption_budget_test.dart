import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/render/interruption_budget.dart';

void main() {
  group('InterruptionBudget', () {
    test('two requests inside min-gap: exactly one grant', () {
      var now = DateTime(2026, 8, 19, 10, 0);
      final budget = InterruptionBudget(now: () => now);

      final first = budget.request(category: 'question_card');
      expect(first, isTrue);

      // 5 minutes later (inside 30-min gap)
      now = DateTime(2026, 8, 19, 10, 5);
      final second = budget.request(category: 'question_card');
      expect(second, isFalse);
    });

    test('fourth request same day: denied', () {
      var now = DateTime(2026, 8, 19, 8, 0);
      final budget = InterruptionBudget(now: () => now);

      // Three grants, each 31 minutes apart
      expect(budget.request(category: 'a'), isTrue);
      now = DateTime(2026, 8, 19, 8, 31);
      expect(budget.request(category: 'b'), isTrue);
      now = DateTime(2026, 8, 19, 9, 2);
      expect(budget.request(category: 'c'), isTrue);

      // Fourth same day: denied
      now = DateTime(2026, 8, 19, 9, 33);
      expect(budget.request(category: 'd'), isFalse);
    });

    test('after dismiss, next request inside 120 min: denied', () {
      var now = DateTime(2026, 8, 19, 10, 0);
      final budget = InterruptionBudget(now: () => now);

      expect(budget.request(category: 'question_card'), isTrue);

      // Dismiss at 10:31 (past min-gap)
      now = DateTime(2026, 8, 19, 10, 31);
      budget.dismiss();

      // Request 60 min after dismiss: denied (inside 120-min suppression)
      now = DateTime(2026, 8, 19, 11, 31);
      expect(budget.request(category: 'checklist'), isFalse);

      // Request 121 min after dismiss: granted
      now = DateTime(2026, 8, 19, 12, 33);
      expect(budget.request(category: 'checklist'), isTrue);
    });

    test('grants reset on new calendar day', () {
      var now = DateTime(2026, 8, 19, 8, 0);
      final budget = InterruptionBudget(now: () => now);

      expect(budget.request(category: 'a'), isTrue);
      now = DateTime(2026, 8, 19, 8, 31);
      expect(budget.request(category: 'b'), isTrue);
      now = DateTime(2026, 8, 19, 9, 2);
      expect(budget.request(category: 'c'), isTrue);
      now = DateTime(2026, 8, 19, 9, 33);
      expect(budget.request(category: 'd'), isFalse);

      // Next day
      now = DateTime(2026, 8, 20, 8, 0);
      expect(budget.request(category: 'e'), isTrue);
    });
  });
}
