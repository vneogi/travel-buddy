// SPEC-43 Gap 12: release builds fail closed on non-HTTPS endpoints.
// Pure function tests: no network, no SQLite, no widgets.

import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/env.dart';

const _httpsApi = 'https://travel-buddy-196190001420.asia-south1.run.app';
const _httpsSupabase = 'https://example-project.supabase.co';
const _emulatorApi = 'http://10.0.2.2:8000';

void main() {
  group('assertSecureTransport', () {
    test('test_release_http_api_base_url_is_rejected', () {
      expect(
        () => assertSecureTransport(
          release: true,
          apiBaseUrl: _emulatorApi,
          supabaseUrl: _httpsSupabase,
        ),
        throwsA(isA<InsecureTransportError>()),
      );
    });

    test('release rejects http Supabase URL', () {
      expect(
        () => assertSecureTransport(
          release: true,
          apiBaseUrl: _httpsApi,
          supabaseUrl: 'http://example-project.supabase.co',
        ),
        throwsA(isA<InsecureTransportError>()),
      );
    });

    test('release rejects empty Supabase URL', () {
      expect(
        () => assertSecureTransport(
          release: true,
          apiBaseUrl: _httpsApi,
          supabaseUrl: '',
        ),
        throwsA(isA<InsecureTransportError>()),
      );
    });

    test('release rejects malformed or scheme-less API URL', () {
      for (final url in ['travel-buddy.run.app', '', 'ftp://host', 'https://']) {
        expect(
          () => assertSecureTransport(
            release: true,
            apiBaseUrl: url,
            supabaseUrl: _httpsSupabase,
          ),
          throwsA(isA<InsecureTransportError>()),
          reason: url,
        );
      }
    });

    test('release with https API and https Supabase succeeds', () {
      expect(
        () => assertSecureTransport(
          release: true,
          apiBaseUrl: _httpsApi,
          supabaseUrl: _httpsSupabase,
        ),
        returnsNormally,
      );
    });

    test('debug with emulator http default succeeds', () {
      expect(
        () => assertSecureTransport(
          release: false,
          apiBaseUrl: _emulatorApi,
          supabaseUrl: '',
        ),
        returnsNormally,
      );
    });

    test('debug default is still the emulator http URL (not rewritten)', () {
      expect(Env.apiBaseUrl, _emulatorApi);
      expect(() => assertSecureTransport(release: false), returnsNormally);
    });
  });
}
