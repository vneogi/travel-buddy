import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'api_client.dart';
import 'env.dart';
import '../data/repositories.dart';
import '../data/models.dart';
import '../offline/offline_database.dart';
import '../offline/sync_engine.dart';
import '../services/signal_service.dart';

/// Supabase access token provider (null in dev -> ApiClient falls back to
/// X-Debug-User-Id). Guarded because Supabase.instance throws if initialize()
/// was skipped (dev mode with no TB_SUPABASE_URL) -- mirrors main.dart's guard.
final tokenProvider = Provider<TokenProvider>((ref) {
  return () async {
    if (Env.supabaseUrl.isEmpty || Env.supabaseAnonKey.isEmpty) return null;
    try {
      return Supabase.instance.client.auth.currentSession?.accessToken;
    } catch (_) {
      return null; // not initialized / no session -> fall back to debug header
    }
  };
});

/// Central API client.
final apiClientProvider = Provider<ApiClient>(
  (ref) => ApiClient(ref.watch(tokenProvider)),
);

/// Offline database (SQLite — SPEC-02 Part A).
/// Single instance shared by SignalService and SyncEngine.
final offlineDatabaseProvider = Provider<OfflineDatabase>(
  (ref) => OfflineDatabase(),
);

/// Sync engine (SPEC-02 Part B).
/// Handles background sync: batch POST, backoff, crash recovery.
final syncEngineProvider = Provider<SyncEngine>((ref) {
  return SyncEngine(
    db: ref.watch(offlineDatabaseProvider),
    api: ref.watch(apiClientProvider),
  );
});

/// Signal service (SPEC-02 Part A.3 — offline seam, queue-backed).
/// All signal emissions go through this. Persists to SQLite BEFORE network.
/// UI call sites unchanged from SPEC-01.
final signalServiceProvider = Provider<SignalService>((ref) {
  return SignalService(
    db: ref.watch(offlineDatabaseProvider),
    syncEngine: ref.watch(syncEngineProvider),
  );
});

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
