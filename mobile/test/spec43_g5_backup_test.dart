// SPEC-43 Gap 5: the offline store must not ride Android Auto Backup or
// device-to-device transfer. Reads the policy files from disk.
// Directory.current is mobile/. No widgets, no SQLite, no network.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _manifest = 'android/app/src/main/AndroidManifest.xml';
const _backupRules = 'android/app/src/main/res/xml/backup_rules.xml';
const _extractionRules =
    'android/app/src/main/res/xml/data_extraction_rules.xml';
const _plist = 'ios/Runner/Info.plist';

String _read(String path) => File(path).readAsStringSync();

/// Body of the first <tag>...</tag> block, or null.
String? _block(String xml, String tag) =>
    RegExp('<$tag>([\\s\\S]*?)</$tag>').firstMatch(xml)?.group(1);

void main() {
  test('test_release_android_backup_excludes_offline_store', () {
    final manifest = _read(_manifest);
    expect(manifest, contains('android:allowBackup="false"'));
    expect(manifest, isNot(contains('allowBackup="true"')));
    expect(
      manifest,
      contains('android:fullBackupContent="@xml/backup_rules"'),
    );
    expect(
      manifest,
      contains('android:dataExtractionRules="@xml/data_extraction_rules"'),
    );

    expect(File(_backupRules).existsSync(), isTrue);
    expect(File(_extractionRules).existsSync(), isTrue);

    for (final path in [_backupRules, _extractionRules]) {
      final xml = _read(path);
      expect(xml, contains('domain="database"'), reason: path);
      expect(xml, contains('domain="sharedpref"'), reason: path);
    }

    final extraction = _read(_extractionRules);
    expect(extraction, contains('cloud-backup'));
    expect(extraction, contains('device-transfer'));
  });

  test('backup rules only exclude and never include root or a database',
      () {
    for (final path in [_backupRules, _extractionRules]) {
      final xml = _read(path);
      expect(xml, isNot(contains('<include')), reason: path);
      expect(xml, isNot(contains('domain="root"')), reason: path);
      expect(xml, isNot(contains('travel_buddy_offline.db')), reason: path);
    }
    final backup = _read(_backupRules);
    expect(backup, contains('<exclude domain="database" />'));
    expect(backup, contains('<exclude domain="sharedpref" />'));
  });

  test('cloud-backup and device-transfer each exclude database and prefs',
      () {
    final xml = _read(_extractionRules);
    for (final section in ['cloud-backup', 'device-transfer']) {
      final body = _block(xml, section);
      expect(body, isNotNull, reason: section);
      expect(body, contains('<exclude domain="database" />'), reason: section);
      expect(body, contains('<exclude domain="sharedpref" />'),
          reason: section);
    }
  });

  test('debug and profile manifests do not re-enable backup', () {
    for (final variant in ['debug', 'profile']) {
      final manifest = _read('android/app/src/$variant/AndroidManifest.xml');
      expect(manifest, isNot(contains('allowBackup')), reason: variant);
    }
  });

  test('network security config reference is kept', () {
    expect(
      _read(_manifest),
      contains('android:networkSecurityConfig="@xml/network_security_config"'),
    );
  });

  test('iOS Info.plist does not enable UIFileSharingEnabled', () {
    final plist = _read(_plist);
    expect(
      RegExp(r'<key>UIFileSharingEnabled</key>\s*<true\s*/>').hasMatch(plist),
      isFalse,
    );
    expect(
      RegExp(r'<key>LSSupportsOpeningDocumentsInPlace</key>\s*<true\s*/>')
          .hasMatch(plist),
      isFalse,
    );
  });
}
