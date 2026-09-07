/// Environment configuration via compile-time --dart-define flags.

/// Extract the hostname from a base URL string.
///
/// Returns just the host (e.g. 'service-name.run.app'), never a path,
/// port, or credentials. Falls back to the raw string if parsing fails.
String hostnameFromBaseUrl(String url) {
  final uri = Uri.tryParse(url);
  if (uri != null && uri.host.isNotEmpty) return uri.host;
  return url;
}

class Env {
  Env._();

  /// Android emulator reaches host localhost via 10.0.2.2; iOS sim uses localhost.
  /// Override at run: --dart-define=TB_API_BASE_URL=https://your.api
  static const apiBaseUrl = String.fromEnvironment(
    'TB_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  /// Hostname-only for display in Profile/About (no path, no credentials).
  static String get apiHostname => hostnameFromBaseUrl(apiBaseUrl);

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
}
