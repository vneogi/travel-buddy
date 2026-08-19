/// Testable redirect logic for the auth gate.
///
/// SPEC-09: anonymous identity means no Supabase session is required.
/// The only redirect we keep: if the user is authenticated AND on
/// /onboarding, send them home.
String? redirectForAuth({
  required bool supabaseReady,
  required bool hasSession,
  required String location,
}) {
  if (!supabaseReady) return null;
  final isOnboarding = location == '/onboarding';
  if (hasSession && isOnboarding) return '/';
  return null;
}
