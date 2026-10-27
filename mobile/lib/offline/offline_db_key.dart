import 'dart:async';
import 'dart:math';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';

/// Secure storage key for the offline SQLite (SQLCipher) passphrase.
const tbOfflineDbKey = 'tb_offline_db_key';

/// SPEC-43 Gap 5: per-install passphrase for the encrypted offline store.
///
/// 32 cryptographically random bytes, hex-encoded (64 chars), persisted in
/// FlutterSecureStorage (Android Keystore-backed / iOS Keychain). Never the
/// device UUID. Never logged. Storage errors are rethrown; there is no
/// fallback key.
///
/// Concurrent callers share one in-flight Future.
class OfflineDbKey {
  final FlutterSecureStorage _storage;
  final Random _random;
  Completer<String>? _completer;

  OfflineDbKey({FlutterSecureStorage? storage, Random? random})
      : _storage = storage ?? const FlutterSecureStorage(),
        _random = random ?? Random.secure();

  Future<String> getOrCreate() {
    final inFlight = _completer;
    if (inFlight != null) return inFlight.future;
    final completer = Completer<String>();
    _completer = completer;
    _resolve(completer);
    return completer.future;
  }

  Future<void> _resolve(Completer<String> completer) async {
    try {
      final existing = await _storage.read(key: tbOfflineDbKey);
      if (existing != null && existing.isNotEmpty) {
        completer.complete(existing);
        return;
      }
      final key = _generateHex(32);
      await _storage.write(key: tbOfflineDbKey, value: key);
      completer.complete(key);
    } catch (e, st) {
      _completer = null; // allow a later retry; never invent a key
      completer.completeError(e, st);
    }
  }

  String _generateHex(int byteCount) {
    final buffer = StringBuffer();
    for (var i = 0; i < byteCount; i++) {
      buffer.write(_random.nextInt(256).toRadixString(16).padLeft(2, '0'));
    }
    return buffer.toString();
  }
}
