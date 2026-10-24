import 'package:flutter/foundation.dart' show debugPrint;
import 'package:supabase_flutter/supabase_flutter.dart';

/// SPEC-43 Gap 1: the minimal auth surface startup needs.
/// Abstracted so widget/unit tests never touch live Supabase Auth.
abstract class AnonAuth {
  bool get hasSession;
  Future<void> signInAnonymously();
}

/// Production adapter over the Supabase GoTrue client.
class SupabaseAnonAuth implements AnonAuth {
  final GoTrueClient _auth;
  SupabaseAnonAuth(this._auth);

  @override
  bool get hasSession => _auth.currentSession != null;

  @override
  Future<void> signInAnonymously() async {
    await _auth.signInAnonymously();
  }
}

/// Ensure a server-issued session exists before the first API call.
///
/// - Existing (persisted) session -> reuse it; never mint a second account.
/// - No session -> one `signInAnonymously()`; the SDK refreshes thereafter.
/// - Failure (offline, anonymous sign-ins disabled) -> returns false; API
///   calls then carry no Authorization and 401. Never falls back to the
///   device UUID. Tokens are never logged.
Future<bool> ensureAnonymousSession(AnonAuth auth) async {
  if (auth.hasSession) return true;
  try {
    await auth.signInAnonymously();
    return auth.hasSession;
  } catch (e) {
    debugPrint('Anonymous sign-in failed: ${e.runtimeType}');
    return false;
  }
}
