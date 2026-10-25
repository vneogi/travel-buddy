import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/anon_session.dart';
import '../../core/providers.dart';
import '../../features/alerts/alerts_notifier.dart';
import '../../features/home/home_controller.dart';
import '../../features/itinerary/itinerary_notifier.dart';
import '../../features/notifications/departure_notifier.dart';
import '../../routing/trip_route_auth.dart';

/// Result of the SPEC-43 Gap 6 sign-out lifecycle.
class SignOutResult {
  final bool ok;
  final String? error;
  const SignOutResult._({required this.ok, this.error});

  const SignOutResult.success() : this._(ok: true);
  const SignOutResult.failure(String message) : this._(ok: false, error: message);
}

/// Client-owned sign-out as an identity lifecycle, not a navigation.
///
/// Required order:
/// 1. Halt sync and keep it halted.
/// 2. Delete every local row, including the entire outbox.
/// 3. signOut() the current GoTrue session.
/// 4. Confirm there is no session.
/// 5. Only then mint a new anonymous JWT.
/// 6. Reset halt, restart sync.
/// 7. Invalidate identity-scoped providers.
/// 8. UI navigates to '/'.
class SignOutController extends StateNotifier<bool> {
  final Ref _ref;
  SignOutController(this._ref) : super(false);

  Future<SignOutResult> run() async {
    if (state) return const SignOutResult.failure('Sign out already in progress.');
    state = true;

    final auth = _ref.read(anonAuthProvider);
    if (auth == null) {
      state = false;
      return const SignOutResult.failure('Sign out is unavailable right now.');
    }

    final sync = _ref.read(syncEngineProvider);
    final db = _ref.read(offlineDatabaseProvider);
    sync.haltForAuthChange();

    try {
      await db.deleteAllLocalRows();
      // SPEC-43 Gap 12: the prior identity's owned trips are not ours.
      ownedTripCatalog.clear();
      await auth.signOut();
      if (auth.hasSession) {
        return const SignOutResult.failure('Could not finish signing out. Please try again.');
      }

      final ok = await ensureAnonymousSession(auth);
      if (!ok || !auth.hasSession) {
        _invalidateIdentityScopedProviders();
        return const SignOutResult.failure('Signed out. Could not start a new session yet.');
      }

      _invalidateIdentityScopedProviders();
      sync.resetAuthHalted();
      await sync.start();
      return const SignOutResult.success();
    } catch (_) {
      return const SignOutResult.failure('Sign out failed. Please try again.');
    } finally {
      state = false;
    }
  }

  void _invalidateIdentityScopedProviders() {
    _ref.invalidate(identityCacheScopeProvider);
    _ref.invalidate(userStatusProvider);
    _ref.invalidate(homeSnapshotProvider);
    _ref.invalidate(itineraryControllerProvider);
    _ref.invalidate(alertsNotifierProvider);
    _ref.invalidate(departureNotifierProvider);
  }
}

final signOutControllerProvider =
    StateNotifierProvider<SignOutController, bool>((ref) {
  return SignOutController(ref);
});
