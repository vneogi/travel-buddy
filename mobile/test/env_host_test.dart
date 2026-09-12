import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/env.dart';

void main() {
  test('hostnameFromBaseUrl extracts host from Cloud Run URL', () {
    expect(
      hostnameFromBaseUrl('https://travel-buddy-field.run.app'),
      'travel-buddy-field.run.app',
    );
  });

  test('hostnameFromBaseUrl extracts host from URL with port', () {
    expect(
      hostnameFromBaseUrl('http://10.0.2.2:8000'),
      '10.0.2.2',
    );
  });

  test('hostnameFromBaseUrl returns raw string for unparseable input', () {
    expect(hostnameFromBaseUrl(''), '');
  });

  test('Env.apiHostname calls hostnameFromBaseUrl on default', () {
    // Default is http://10.0.2.2:8000, so hostname is 10.0.2.2
    final hostname = Env.apiHostname;
    expect(hostname, '10.0.2.2');
    // A hosted build would NOT show a local address
    expect(
      hostnameFromBaseUrl('https://travel-buddy-field.run.app')
          .contains('10.0.2.2'),
      isFalse,
    );
  });
}
