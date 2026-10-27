// SPEC-43 Gap 5: production offline store opens with SQLCipher.
//
// Reads source files from disk. Directory.current is mobile/.
// No widgets, no SQLite open, no network.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _pubspec = 'pubspec.yaml';
const _keyHelper = 'lib/offline/offline_db_key.dart';
const _openExport = 'lib/offline/offline_open.dart';
const _openIo = 'lib/offline/offline_open_io.dart';
const _openStub = 'lib/offline/offline_open_stub.dart';
const _offlineDb = 'lib/offline/offline_database.dart';

String _read(String path) => File(path).readAsStringSync();

/// Strip // line comments so assertions never depend on comments.
String _code(String source) =>
    source.split('\n').map((l) {
      final i = l.indexOf('//');
      return i < 0 ? l : l.substring(0, i);
    }).join('\n');

/// Argument text of every call to [callee] (balanced parentheses).
List<String> _callArgs(String code, String callee) {
  final out = <String>[];
  var from = 0;
  while (true) {
    final start = code.indexOf('$callee(', from);
    if (start < 0) return out;
    var depth = 0;
    var i = start + callee.length;
    for (; i < code.length; i++) {
      final ch = code[i];
      if (ch == '(') depth++;
      if (ch == ')') {
        depth--;
        if (depth == 0) break;
      }
    }
    out.add(code.substring(start + callee.length + 1, i));
    from = i;
  }
}

/// Bodies of every `catch (...) { ... }` block (balanced braces).
List<String> _catchBodies(String code) {
  final out = <String>[];
  for (final m in RegExp(r'catch\s*\([^)]*\)\s*\{').allMatches(code)) {
    var depth = 1;
    var i = m.end;
    for (; i < code.length && depth > 0; i++) {
      if (code[i] == '{') depth++;
      if (code[i] == '}') depth--;
    }
    out.add(code.substring(m.end, i - 1));
  }
  return out;
}

void main() {
  test('test_production_offline_open_passes_sqlcipher_password', () {
    expect(_read(_pubspec), contains('sqflite_sqlcipher'));

    expect(File(_keyHelper).existsSync(), isTrue);
    final key = _code(_read(_keyHelper));
    expect(key, contains('tb_offline_db_key'));
    expect(key, contains('FlutterSecureStorage'));

    final io = _code(_read(_openIo));
    expect(io, contains('package:sqflite_sqlcipher/'));
    expect(io, contains('password:'));

    // Every SQLCipher open passes the password.
    final cipherOpens = _callArgs(io, 'cipher.openDatabase');
    expect(cipherOpens, isNotEmpty);
    for (final args in cipherOpens) {
      expect(args, contains('password:'));
    }

    // No catch block falls back to an open without password:.
    for (final body in _catchBodies(io)) {
      expect(body, isNot(contains('plain.openDatabase')));
      for (final args in _callArgs(body, 'openDatabase')) {
        expect(args, contains('password:'));
      }
    }

    expect(
      _code(_read(_offlineDb)),
      contains("_dbName = 'travel_buddy_offline.db'"),
    );
  });

  test('offline store helpers exist and production open is routed', () {
    for (final path in [_keyHelper, _openExport, _openIo, _openStub]) {
      expect(File(path).existsSync(), isTrue, reason: path);
    }
    expect(
      _read(_openExport),
      contains("if (dart.library.io) 'offline_open_io.dart'"),
    );
    final db = _code(_read(_offlineDb));
    expect(db, contains('openOfflineStore('));
    expect(db, isNot(contains('dart:io')));
    final io = _code(_read(_openIo));
    expect(io, contains('Platform.isAndroid'));
    expect(io, contains('Platform.isIOS'));
    expect(io, contains('OfflineDbKey().getOrCreate()'));
    expect(io, isNot(contains('tb_device_uuid')));
    expect(io, isNot(contains('DeviceIdentity')));
  });
}
