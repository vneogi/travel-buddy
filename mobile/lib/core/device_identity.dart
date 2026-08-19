import 'dart:async';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

/// Secure storage key for the persisted device UUID.
const tbDeviceUuidKey = 'tb_device_uuid';

/// Manages a per-device anonymous UUID v4, generated on first launch and
/// persisted in platform secure storage (Keychain / EncryptedSharedPrefs).
///
/// Thread-safe: concurrent callers share a single in-flight Future.
class DeviceIdentity {
  final FlutterSecureStorage _storage;
  Completer<String>? _completer;

  DeviceIdentity({FlutterSecureStorage? storage})
      : _storage = storage ?? const FlutterSecureStorage();

  /// Returns the device UUID, generating and persisting it on first call.
  ///
  /// Safe under concurrent callers: only one generation path executes;
  /// subsequent callers await the same Future.
  Future<String> getOrCreate() {
    if (_completer != null) return _completer!.future;
    _completer = Completer<String>();
    _resolve();
    return _completer!.future;
  }

  Future<void> _resolve() async {
    try {
      final existing = await _storage.read(key: tbDeviceUuidKey);
      if (existing != null && existing.isNotEmpty) {
        _completer!.complete(existing);
        return;
      }
      final id = const Uuid().v4();
      await _storage.write(key: tbDeviceUuidKey, value: id);
      _completer!.complete(id);
    } catch (e) {
      _completer!.completeError(e);
      _completer = null; // allow retry on error
    }
  }
}
