import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'api_client.dart';
import '../data/repositories.dart';
import '../data/models.dart';

/// Supabase access token provider (null in dev -> falls back to X-Debug-User-Id).
final tokenProvider = Provider<TokenProvider>((ref) {
  return () async => Supabase.instance.client.auth.currentSession?.accessToken;
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
