import 'dart:async';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:travel_buddy/core/device_identity.dart';

// ---------------------------------------------------------------------------
// Fake secure storage (in-memory map) -- no plugin dependency in tests.
// ---------------------------------------------------------------------------
class FakeSecureStorage implements FlutterSecureStorage {
  final Map<String, String> _store = {};
  int writeCount = 0;

  @override
  Future<String?> read({
    required String key,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    return _store[key];
  }

  @override
  Future<void> write({
    required String key,
    required String? value,
    IOSOptions? iOptions,
    AndroidOptions? aOptions,
    LinuxOptions? lOptions,
    WebOptions? webOptions,
    MacOsOptions? mOptions,
    WindowsOptions? wOptions,
  }) async {
    writeCount++;
    if (value != null) {
      _store[key] = value;
    } else {
      _store.remove(key);
    }
  }

  // Unused stubs required by the interface.
  @override
  dynamic noSuchMethod(Invocation invocation) => throw UnimplementedError();
}

void main() {
  group('DeviceIdentity', () {
    late FakeSecureStorage fakeStorage;
    late DeviceIdentity identity;

    setUp(() {
      fakeStorage = FakeSecureStorage();
      identity = DeviceIdentity(storage: fakeStorage);
    });

    test('first launch generates a valid UUID v4', () async {
      final id = await identity.getOrCreate();

      // UUID v4 format: 8-4-4-4-12 hex with version nibble = 4
      final regex = RegExp(
        r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
      );
      expect(id, matches(regex), reason: 'Must be canonical UUID v4');
      // Verify variant bits: character at position 19 must be 8, 9, a, or b
      final variantChar = id[19];
      expect('89ab'.contains(variantChar), isTrue,
          reason: 'RFC 4122 variant bits');
    });

    test('second call returns same id (no second write)', () async {
      final first = await identity.getOrCreate();
      final second = await identity.getOrCreate();

      expect(second, equals(first));
      expect(fakeStorage.writeCount, equals(1),
          reason: 'Only one write on first generation');
    });

    test('concurrent getOrCreate returns identical id', () async {
      // Kick off multiple concurrent calls
      final futures = List.generate(10, (_) => identity.getOrCreate());
      final results = await Future.wait(futures);

      // All must be the same value
      expect(results.toSet().length, equals(1),
          reason: 'All concurrent callers must get the same id');
      expect(fakeStorage.writeCount, equals(1),
          reason: 'Only one generation path');
    });

    test('reads existing id from storage without generating new one', () async {
      // Pre-seed storage (simulates second app launch)
      final existingId = '12345678-1234-4abc-9def-123456789abc';
      await fakeStorage.write(key: tbDeviceUuidKey, value: existingId);
      fakeStorage.writeCount = 0; // reset counter

      final id = await identity.getOrCreate();

      expect(id, equals(existingId));
      expect(fakeStorage.writeCount, equals(0),
          reason: 'No write when id already in storage');
    });
  });
}
