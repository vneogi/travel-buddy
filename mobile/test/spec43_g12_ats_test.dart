// SPEC-43 Gap 12: Android network security config and iOS ATS.
//
// Reads the policy files from disk. Directory.current is mobile/.
// No widgets, no SQLite, no network.

import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

const _release = 'android/app/src/main/res/xml/network_security_config.xml';
const _debug = 'android/app/src/debug/res/xml/network_security_config.xml';
const _profile = 'android/app/src/profile/res/xml/network_security_config.xml';
const _manifest = 'android/app/src/main/AndroidManifest.xml';
const _plist = 'ios/Runner/Info.plist';

const _cleartextFalse = 'cleartextTrafficPermitted="false"';
const _cleartextTrue = 'cleartextTrafficPermitted="true"';

String _read(String path) => File(path).readAsStringSync();

/// Domains inside the cleartext-permitting domain-config, in order.
List<String> _cleartextDomains(String xml) {
  final block = RegExp(
    r'<domain-config\s+cleartextTrafficPermitted="true"\s*>([\s\S]*?)</domain-config>',
  );
  final domain = RegExp(r'<domain[^>]*>\s*([^<\s]+)\s*</domain>');
  return [
    for (final b in block.allMatches(xml))
      for (final d in domain.allMatches(b.group(1)!)) d.group(1)!,
  ];
}

void main() {
  test('test_release_network_security_config_forbids_cleartext', () {
    final xml = _read(_release);
    expect(xml, contains(_cleartextFalse));
    expect(xml, isNot(contains(_cleartextTrue)));
    expect(xml, isNot(contains('10.0.2.2')));
    expect(xml, isNot(contains('localhost')));
    expect(xml, isNot(contains('127.0.0.1')));
    expect(xml, contains('<certificates src="system" />'));
    expect(xml, isNot(contains('src="user"')));
  });

  test('main AndroidManifest references the network security config', () {
    final manifest = _read(_manifest);
    expect(
      manifest,
      contains('android:networkSecurityConfig="@xml/network_security_config"'),
    );
    expect(manifest, isNot(contains('usesCleartextTraffic')));
  });

  test('debug overlay permits cleartext only for loopback hosts', () {
    final xml = _read(_debug);
    expect(xml, contains('<base-config $_cleartextFalse>'));
    expect(_cleartextDomains(xml), ['10.0.2.2', 'localhost', '127.0.0.1']);
    expect(_cleartextTrue.allMatches(xml), hasLength(1));
  });

  test('profile overlay matches the debug loopback exception', () {
    final debug = _read(_debug);
    final profile = _read(_profile);
    expect(profile, contains('<base-config $_cleartextFalse>'));
    expect(_cleartextDomains(profile), _cleartextDomains(debug));
    expect(_cleartextTrue.allMatches(profile), hasLength(1));
  });

  test('debug and profile manifests do not enable global cleartext', () {
    for (final variant in ['debug', 'profile']) {
      final manifest = _read('android/app/src/$variant/AndroidManifest.xml');
      expect(manifest, isNot(contains('usesCleartextTraffic')), reason: variant);
      expect(
        manifest,
        contains('android.permission.INTERNET'),
        reason: variant,
      );
    }
  });

  test('iOS Info.plist declares ATS with arbitrary loads disabled', () {
    final plist = _read(_plist);
    expect(
      RegExp(
        r'<key>NSAppTransportSecurity</key>\s*<dict>\s*'
        r'<key>NSAllowsArbitraryLoads</key>\s*<false\s*/>\s*</dict>',
      ).hasMatch(plist),
      isTrue,
    );
    expect(plist, isNot(contains('NSExceptionDomains')));
    expect(plist, isNot(contains('NSAllowsLocalNetworking')));
    expect(plist, isNot(contains('10.0.2.2')));
    expect(plist, isNot(contains('localhost')));
  });
}
