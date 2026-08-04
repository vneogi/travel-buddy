/// Environment configuration via compile-time --dart-define flags.
class Env {
  Env._();

  /// Android emulator reaches host localhost via 10.0.2.2; iOS sim uses localhost.
  /// Override at run: --dart-define=TB_API_BASE_URL=https://your.api
  static const apiBaseUrl = String.fromEnvironment(
    'TB_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Supabase project URL (for auth).
  static const supabaseUrl = String.fromEnvironment(
    'TB_SUPABASE_URL',
    defaultValue: '',
  );

  /// Supabase anon key (for auth client).
  static const supabaseAnonKey = String.fromEnvironment(
    'TB_SUPABASE_ANON_KEY',
    defaultValue: '',
  );

  /// Dev-only: when backend has no JWT secret, send X-Debug-User-Id.
  /// MUST be a UUID once the Supabase backend is flipped on (user_id is UUID).
  static const debugUserId = String.fromEnvironment(
    'TB_DEBUG_USER_ID',
    defaultValue: '',
  );
}
