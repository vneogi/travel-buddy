import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'api_client.dart';
import 'env.dart';
import '../data/repositories.dart';
import '../data/models.dart';
import '../services/signal_service.dart';

/// Supabase access token provider (null in dev → ApiClient falls back to
/// X-Debug-User-Id). Guarded because Supabase.instance throws if initialize()
/// was skipped (dev mode with no TB_SUPABASE_URL) — mirrors main.dart's guard.
final tokenProvider = Provider<TokenProvider>((ref) {
  return () async {
    if (Env.supabaseUrl.isEmpty || Env.supabaseAnonKey.isEmpty) return null;
    try {
      return Supabase.instance.client.auth.currentSession?.accessToken;
    } catch (_) {
      return null; // not initialized / no session → fall back to debug header
    }
  };
});

/// Central API client.
final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(ref.watch(tokenProvider)),
);

/// Repositories.
final tripRepoProvider = Provider<TripRepository>(
  (ref) => TripRepository(ref.watch(apiClientProvider)),
);
final userRepoProvider = Provider<UserRepository>(
  (ref) => UserRepository(ref.watch(apiClientProvider)),
);

/// Live reroute counter for the badge; invalidate after each structural event.
final userStatusProvider = FutureProvider<UserStatus>(
  (ref) => ref.watch(userRepoProvider).status(),
);

/// Signal service (the offline seam — SPEC-01 B.3).
/// All signal emissions go through this; SPEC-02 swaps implementation.
final signalServiceProvider = Provider<SignalService>(
  (ref) => SignalService(ref.watch(apiClientProvider)),
);
