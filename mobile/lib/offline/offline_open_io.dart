import 'dart:io';

import 'package:sqflite/sqflite.dart' as plain;
import 'package:sqflite_sqlcipher/sqflite.dart' as cipher;

import 'offline_db_key.dart';

/// SPEC-43 Gap 5: open the offline store.
///
/// Android/iOS: SQLCipher with a passphrase from FlutterSecureStorage.
/// Desktop (Windows/macOS/Linux): unencrypted this slice.
Future<plain.Database> openOfflineStore(
  String path, {
  required int version,
  required plain.OnDatabaseCreateFn onCreate,
  required plain.OnDatabaseVersionChangeFn onUpgrade,
}) async {
  if (!(Platform.isAndroid || Platform.isIOS)) {
    return plain.openDatabase(
      path,
      version: version,
      onCreate: onCreate,
      onUpgrade: onUpgrade,
    );
  }

  final key = await OfflineDbKey().getOrCreate();
  try {
    return await _openEncrypted(path, key, version, onCreate, onUpgrade);
  } catch (error) {
    if (!_isUnreadableWithKey(error)) rethrow;
    // A plaintext file from before this slice, or a file written under a
    // lost key. Do not read it and do not migrate it: delete and recreate
    // encrypted. The retry is always WITH the password.
    await _deleteStoreFiles(path);
    return _openEncrypted(path, key, version, onCreate, onUpgrade);
  }
}

Future<plain.Database> _openEncrypted(
  String path,
  String key,
  int version,
  plain.OnDatabaseCreateFn onCreate,
  plain.OnDatabaseVersionChangeFn onUpgrade,
) {
  return cipher.openDatabase(
    path,
    password: key,
    version: version,
    onCreate: onCreate,
    onUpgrade: onUpgrade,
  );
}

bool _isUnreadableWithKey(Object error) {
  final message = error.toString().toLowerCase();
  return message.contains('file is not a database') ||
      message.contains('hmac') ||
      message.contains('not an encrypted') ||
      message.contains('sqlite_notadb') ||
      message.contains('code 26');
}

Future<void> _deleteStoreFiles(String path) async {
  for (final suffix in const ['', '-wal', '-shm', '-journal']) {
    final file = File(path + suffix);
    if (await file.exists()) {
      await file.delete();
    }
  }
}
