import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/routing/redirect_for_auth.dart';

void main() {
  group('redirectForAuth', () {
    test('supabaseReady=true, no session, location / -> null (no redirect)', () {
      final result = redirectForAuth(
        supabaseReady: true,
        hasSession: false,
        location: '/',
      );
      expect(result, isNull);
    });

    test('authenticated user on /onboarding -> redirected to /', () {
      final result = redirectForAuth(
        supabaseReady: true,
        hasSession: true,
        location: '/onboarding',
      );
      expect(result, equals('/'));
    });

    test('supabaseReady=false -> null regardless of session', () {
      final result = redirectForAuth(
        supabaseReady: false,
        hasSession: false,
        location: '/',
      );
      expect(result, isNull);
    });

    test('anonymous user can stay on / (SPEC-09)', () {
      // This is the core SPEC-09 assertion: no session, still on /
      final result = redirectForAuth(
        supabaseReady: true,
        hasSession: false,
        location: '/',
      );
      expect(result, isNull,
          reason: 'SPEC-09 anonymous identity must not require session');
    });
  });
}
