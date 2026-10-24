/// Environment configuration via compile-time --dart-define flags.

import 'package:flutter/foundation.dart' show kReleaseMode;

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

/// SPEC-43 Gap 12: thrown when a release build is configured for cleartext.
class InsecureTransportError extends StateError {
  InsecureTransportError(super.message);
}

bool _isHttps(String url) {
  final uri = Uri.tryParse(url);
  return uri != null && uri.scheme.toLowerCase() == 'https' && uri.host.isNotEmpty;
}

/// SPEC-43 Gap 12: release builds fail closed on non-HTTPS endpoints.
///
/// In release, [apiBaseUrl] must be https and [supabaseUrl] must be a
/// non-empty https URL. Debug/profile keep the emulator HTTP default and
/// allow an empty Supabase URL (tests). Never rewrites http to https.
///
/// [release] defaults to [kReleaseMode]; tests pass `release: true`.
void assertSecureTransport({
  bool release = kReleaseMode,
  String apiBaseUrl = Env.apiBaseUrl,
  String supabaseUrl = Env.supabaseUrl,
}) {
  if (!release) return;
  if (!_isHttps(apiBaseUrl)) {
    throw InsecureTransportError(
      'Release build refuses non-HTTPS TB_API_BASE_URL '
      '(host: ${hostnameFromBaseUrl(apiBaseUrl)})',
    );
  }
  if (supabaseUrl.isEmpty) {
    throw InsecureTransportError('Release build requires TB_SUPABASE_URL (https)');
  }
  if (!_isHttps(supabaseUrl)) {
    throw InsecureTransportError(
      'Release build refuses non-HTTPS TB_SUPABASE_URL '
      '(host: ${hostnameFromBaseUrl(supabaseUrl)})',
    );
  }
}
