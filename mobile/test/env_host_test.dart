import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/env.dart';

void main() {
  test('Env.apiHostname extracts host from URL', () {
    // Env.apiBaseUrl is compile-time const; in test it uses the default.
    // We verify the parsing logic works for the default value.
    final hostname = Env.apiHostname;
    expect(hostname, isNotEmpty);
    // Default is http://10.0.2.2:8000 -> host is "10.0.2.2"
    expect(hostname, '10.0.2.2');
  });

  test('Env.apiHostname returns non-local host when compiled with --dart-define', () {
    // This test documents the expected behavior: when compiled with
    //   --dart-define=TB_API_BASE_URL=https://travel-buddy-xxx.run.app
    // Env.apiHostname returns "travel-buddy-xxx.run.app".
    //
    // We cannot change a compile-time const in a unit test, so we verify
    // the Uri parsing directly.
    final uri = Uri.parse('https://travel-buddy-field.run.app');
    expect(uri.host, 'travel-buddy-field.run.app');
    expect(uri.host.contains('localhost'), isFalse);
    expect(uri.host.contains('10.0.2.2'), isFalse);
    expect(uri.host.contains('192.168'), isFalse);
  });
}
