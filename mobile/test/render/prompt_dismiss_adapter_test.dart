import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/render/prompt_dismiss_adapter.dart';
import 'package:travel_buddy/services/signal_service.dart';

class FakeOfflineDatabase extends Mock implements OfflineDatabase {}
class FakeSyncEngine extends Mock implements SyncEngine {}

void main() {
  group('PromptDismissAdapter (R17)', () {
    late FakeOfflineDatabase fakeDb;
    late SignalService service;
    late List<String> captured;

    setUp(() {
      fakeDb = FakeOfflineDatabase();
      captured = [];

      when(() => fakeDb.getOutboxSize()).thenAnswer((_) async => 0);
      when(() => fakeDb.enqueue(any(), any(), any())).thenAnswer((inv) async {
        captured.add(inv.positionalArguments[1] as String);
      });

      service = SignalService(
        db: fakeDb,
        syncEngine: FakeSyncEngine(),
      );
    });

    test('handler emits prompt_dismissed to outbox with kind+attribute', () async {
      final adapter = PromptDismissAdapter(service, placeRef: 'place_123');

      adapter.handler(kind: 'question_card', attribute: 'opening_hours');

      // Give async emit a tick to persist
      await Future<void>.delayed(Duration.zero);

      expect(captured, hasLength(1));
      final payload = captured.first;
      expect(payload, contains('prompt_dismissed'));
      expect(payload, contains('opening_hours'));
      expect(payload, contains('question_card'));
    });
  });
}
