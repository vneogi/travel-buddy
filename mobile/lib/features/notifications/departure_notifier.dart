import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/departure_notification.dart';
import '../../offline/offline_database.dart';

/// SPEC-35 Phase A2: Departure notification state.
class DepartureState {
  final List<NotificationCandidate> candidates;
  final bool loading;
  final String? status;
  final Set<String> dismissed;

  const DepartureState({
    this.candidates = const [],
    this.loading = false,
    this.status,
    this.dismissed = const {},
  });

  DepartureState copyWith({
    List<NotificationCandidate>? candidates,
    bool? loading,
    String? status,
    Set<String>? dismissed,
  }) =>
      DepartureState(
        candidates: candidates ?? this.candidates,
        loading: loading ?? this.loading,
        status: status ?? this.status,
        dismissed: dismissed ?? this.dismissed,
      );

  /// At most one non-expired, non-dismissed departure_reminder.
  NotificationCandidate? get visible {
    for (final c in candidates) {
      if (c.type != 'departure_reminder') continue;
      if (c.isExpired) continue;
      if (dismissed.contains(c.notificationId)) continue;
      return c;
    }
    return null;
  }
}

/// SPEC-35 Phase A2: Fetches departure notifications for a trip.
///
/// Reuses the SPEC-29 fetch/error pattern:
/// - 401/403: never fall back to cache.
/// - Network/503: unexpired cache allowed.
/// - Parse/programming errors: do not silently use stale cache.
class DepartureNotifier
    extends AutoDisposeFamilyAsyncNotifier<DepartureState, String> {
  @override
  Future<DepartureState> build(String arg) async {
    return _load(arg);
  }

  String get _identityScope => ref.read(identityCacheScopeProvider);

  OfflineDatabase get _db => ref.read(offlineDatabaseProvider);

  Future<DepartureState> _load(String tripId) async {
    // Prune expired data safely.
    try {
      await _db.pruneNotificationData();
    } catch (_) {}

    // Load persisted dismissals from dedicated table.
    Set<String> dismissedIds;
    try {
      dismissedIds = await _db.getDismissedNotificationIds(
        identityScope: _identityScope,
      );
    } catch (_) {
      dismissedIds = {};
    }

    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/trip/$tripId/notifications');
      final parsed = TripNotificationsResponse.fromJson(
        resp as Map<String, dynamic>,
      );
      if (parsed.status == 'unconfigured') {
        return DepartureState(
          status: 'unconfigured',
          dismissed: dismissedIds,
        );
      }
      // Filter to departure_reminder only, non-expired.
      final valid = parsed.notifications
          .where((c) => c.type == 'departure_reminder' && !c.isExpired)
          .toList();

      // Cache identity-scoped with expiry.
      try {
        final latestExpiry = valid.isEmpty
            ? DateTime.now().toUtc().add(const Duration(hours: 1))
            : valid
                .map((c) => c.expiresAt)
                .reduce((a, b) => a.isAfter(b) ? a : b);
        await _db.cacheNotifications(
          identityScope: _identityScope,
          tripId: tripId,
          payloadJson: jsonEncode(resp),
          expiresAt: latestExpiry.toIso8601String(),
        );
      } catch (_) {}

      return DepartureState(
        candidates: valid,
        status: parsed.status,
        dismissed: dismissedIds,
      );
    } on UnauthorizedException {
      // 401/403 NEVER fall back to cache.
      return DepartureState(status: 'auth_error', dismissed: dismissedIds);
    } on ForbiddenException {
      return DepartureState(status: 'auth_error', dismissed: dismissedIds);
    } on NetworkException {
      // Network failure: use unexpired identity-scoped cache.
      return _loadFromCache(tripId, dismissedIds);
    } on WeatherUnavailableException {
      // 503: use unexpired cache.
      return _loadFromCache(tripId, dismissedIds);
    } catch (e) {
      // Parse/programming errors: do NOT use stale cache.
      return DepartureState(status: 'error', dismissed: dismissedIds);
    }
  }

  Future<DepartureState> _loadFromCache(
    String tripId,
    Set<String> dismissedIds,
  ) async {
    try {
      final cached = await _db.getCachedNotifications(
        identityScope: _identityScope,
        tripId: tripId,
      );
      if (cached != null) {
        final parsed = TripNotificationsResponse.fromJson(
          jsonDecode(cached) as Map<String, dynamic>,
        );
        final valid = parsed.notifications
            .where((c) => c.type == 'departure_reminder' && !c.isExpired)
            .toList();
        return DepartureState(
          candidates: valid,
          status: 'cached',
          dismissed: dismissedIds,
        );
      }
    } catch (_) {}
    return DepartureState(dismissed: dismissedIds);
  }

  /// Dismiss a notification locally and persist in dedicated table.
  Future<void> dismiss(String notificationId) async {
    final current = state.valueOrNull ?? const DepartureState();
    final newDismissed = {...current.dismissed, notificationId};
    state = AsyncValue.data(current.copyWith(dismissed: newDismissed));
    try {
      await _db.dismissNotification(
        identityScope: _identityScope,
        notificationId: notificationId,
      );
    } catch (_) {}
  }

  /// Manual refresh (shared with alerts refresh control).
  Future<void> refresh() async {
    state = AsyncValue.data(
      (state.valueOrNull ?? const DepartureState()).copyWith(loading: true),
    );
    state = AsyncValue.data(await _load(arg));
  }
}

/// autoDispose: leaving and reopening performs a fresh check.
final departureNotifierProvider = AsyncNotifierProvider.autoDispose
    .family<DepartureNotifier, DepartureState, String>(
  DepartureNotifier.new,
);
