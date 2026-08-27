import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'api_client.dart';
import 'device_identity.dart';
import 'env.dart';
import '../data/repositories.dart';
import '../data/models.dart';
import '../offline/offline_database.dart';
import '../offline/sync_engine.dart';
import '../services/signal_service.dart';

/// Device identity (SPEC-09). Eagerly resolved in main() before runApp;
/// overridden with the resolved string so downstream reads are synchronous.
final deviceIdentityProvider = Provider<DeviceIdentity>(
  (ref) => DeviceIdentity(),
);

/// Resolved device UUID string. Set by main() after getOrCreate().
final deviceIdProvider = StateProvider<String>((ref) => '');

/// Stable local cache namespace. Prevents a stale anonymous/account trip list
/// from being shown after an identity switch on the same installation.
final identityCacheScopeProvider = Provider<String>((ref) {
  if (Env.supabaseUrl.isNotEmpty && Env.supabaseAnonKey.isNotEmpty) {
    try {
      final userId = Supabase.instance.client.auth.currentUser?.id;
      if (userId != null && userId.isNotEmpty) return 'account:$userId';
    } catch (_) {}
  }
  return 'anonymous:${ref.watch(deviceIdProvider)}';
});

/// Supabase access token provider (null when no Supabase session).
final tokenProvider = Provider<TokenProvider>((ref) {
  return () async {
    if (Env.supabaseUrl.isEmpty || Env.supabaseAnonKey.isEmpty) return null;
    try {
      return Supabase.instance.client.auth.currentSession?.accessToken;
    } catch (_) {
      return null;
    }
  };
});

/// Central API client (SPEC-09: Anonymous header when no JWT).
final apiClientProvider = Provider<ApiClient>((ref) {
  final resolvedDeviceId = ref.watch(deviceIdProvider);
  return ApiClient(
    tokenProvider: ref.watch(tokenProvider),
    deviceIdProvider: () async => resolvedDeviceId,
  );
});

/// Offline database (SQLite -- SPEC-02 Part A).
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

/// Signal service (SPEC-02 Part A.3 -- offline seam, queue-backed).
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
