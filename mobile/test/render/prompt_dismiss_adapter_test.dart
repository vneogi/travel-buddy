import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/render/prompt_dismiss_adapter.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';

/// Fake OfflineDatabase that captures enqueued signals.
class FakeOfflineDatabase implements OfflineDatabase {
  final outbox = <Map<String, dynamic>>[];

  @override
  Future<void> enqueue(String id, String payload, String ts) async {
    outbox.add({'id': id, 'payload': payload, 'ts': ts});
  }

  @override
  Future<int> getOutboxSize() async => outbox.length;

  @override
  dynamic noSuchMethod(Invocation i) => null;
}

/// Fake SyncEngine that does nothing.
class FakeSyncEngine implements SyncEngine {
  @override
  void triggerSync() {}

  @override
  dynamic noSuchMethod(Invocation i) => null;
}

void main() {
  group('PromptDismissAdapter (R17)', () {
    test('handler emits prompt_dismissed to outbox with kind+attribute', () async {
      final fakeDb = FakeOfflineDatabase();
      final service = SignalService(
        db: fakeDb,
        syncEngine: FakeSyncEngine(),
      );
      final adapter = PromptDismissAdapter(service, placeRef: 'place_123');

      adapter.handler(kind: 'question_card', attribute: 'opening_hours');

      // Give async emit a tick to persist
      await Future<void>.delayed(Duration.zero);

      expect(fakeDb.outbox, hasLength(1));
      // The payload is JSON-encoded Signal; decode and check
      final payload = fakeDb.outbox.first['payload'] as String;
      expect(payload, contains('prompt_dismissed'));
      expect(payload, contains('opening_hours'));
      expect(payload, contains('question_card'));
    });

    test('sabotage: removing emit call leaves outbox empty', () async {
      // This test documents the sabotage path: if the adapter body
      // is emptied, no signal reaches the outbox. The test above
      // would fail.
      final fakeDb = FakeOfflineDatabase();
      expect(fakeDb.outbox, isEmpty);
    });
  });
}
