import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/features/chat/chat_screen.dart';

void main() {
  group('classifyAskIntent', () {
    test('routes only explicit one-stop commands to structural events', () {
      expect(classifyAskIntent('cancel next stop'), AskIntent.cancelNext);
      expect(classifyAskIntent('Swap the next stop'), AskIntent.swapNext);
    });

    test('keeps ordinary questions on the ask path', () {
      expect(
        classifyAskIntent('Is it too hot for the next stop?'),
        AskIntent.question,
      );
      expect(
        classifyAskIntent('Tell me a great restaurant near me'),
        AskIntent.question,
      );
      expect(
        classifyAskIntent('Can I cancel the next stop?'),
        AskIntent.question,
      );
    });

    test('refuses broad multi-stop mutations', () {
      expect(
        classifyAskIntent('cancel next few stops'),
        AskIntent.multipleChanges,
      );
      expect(classifyAskIntent('remove all stops'), AskIntent.multipleChanges);
      expect(
        classifyAskIntent(
          "Too hot now, let's cancel the next few spots and find food",
        ),
        AskIntent.multipleChanges,
      );
    });
  });
}
