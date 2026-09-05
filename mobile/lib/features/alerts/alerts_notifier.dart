import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/context_alert.dart';
import '../../offline/offline_database.dart';

const alertResumeRefreshInterval = Duration(minutes: 15);

bool alertResumeRefreshDue(DateTime lastAttempt, DateTime now) =>
    now.difference(lastAttempt) >= alertResumeRefreshInterval;

/// SPEC-29: Alert state for a trip.
class AlertsState {
  final List<ContextAlert> alerts;
  final bool loading;
  final String? status;
  final Set<String> dismissed;

  const AlertsState({
    this.alerts = const [],
    this.loading = false,
    this.status,
    this.dismissed = const {},
  });

  AlertsState copyWith({
    List<ContextAlert>? alerts,
    bool? loading,
    String? status,
    Set<String>? dismissed,
  }) =>
      AlertsState(
        alerts: alerts ?? this.alerts,
        loading: loading ?? this.loading,
        status: status ?? this.status,
        dismissed: dismissed ?? this.dismissed,
      );

  /// Visible alerts (not dismissed, not expired).
  List<ContextAlert> get visible => alerts
      .where((a) => !dismissed.contains(a.alertId) && !a.isExpired)
      .toList();
}

/// SPEC-29: Fetches alerts for a trip without blocking itinerary.
///
/// State remains scoped by trip for the app session.
/// - 401/403 never falls back to cache.
/// - NetworkException and WeatherUnavailableException use unexpired cache.
/// - JSON/parse/programming errors do not silently use stale cache.
class AlertsNotifier extends FamilyAsyncNotifier<AlertsState, String> {
  @override
  Future<AlertsState> build(String arg) async {
    return _load(arg);
  }

  String get _identityScope => ref.read(identityCacheScopeProvider);

  OfflineDatabase get _db => ref.read(offlineDatabaseProvider);

  Future<AlertsState> _load(String tripId) async {
    // Prune expired cache/dismissals safely (never blocks alerts).
    try {
      await _db.pruneAlertData();
    } catch (_) {}

    // Load persisted dismissals.
    Set<String> dismissedIds;
    try {
      dismissedIds = await _db.getDismissedAlertIds(
        identityScope: _identityScope,
      );
    } catch (_) {
      dismissedIds = {};
    }

    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/trip/$tripId/alerts');
      final parsed = TripAlertsResponse.fromJson(resp);
      if (parsed.status == 'unconfigured') {
        return AlertsState(status: 'unconfigured', dismissed: dismissedIds);
      }
      final valid = parsed.alerts.where((a) => !a.isExpired).toList();

      // Cache identity-scoped with expiry.
      try {
        final latestExpiry = valid.isEmpty
            ? DateTime.now().toUtc().add(const Duration(hours: 1))
            : valid
                .map((a) => a.expiresAt)
                .reduce((a, b) => a.isAfter(b) ? a : b);
        await _db.cacheAlerts(
          identityScope: _identityScope,
          tripId: tripId,
          payloadJson: jsonEncode(resp),
          expiresAt: latestExpiry.toIso8601String(),
        );
      } catch (_) {}

      return AlertsState(
        alerts: valid,
        status: 'available',
        dismissed: dismissedIds,
      );
    } on UnauthorizedException {
      // 401/403 NEVER fall back to cache.
      return AlertsState(status: 'auth_error', dismissed: dismissedIds);
    } on ForbiddenException {
      return AlertsState(status: 'auth_error', dismissed: dismissedIds);
    } on NetworkException {
      // Network failure: use unexpired identity-scoped cache.
      return _loadFromCache(tripId, dismissedIds);
    } on WeatherUnavailableException {
      // Weather provider 503: use unexpired identity-scoped cache.
      return _loadFromCache(tripId, dismissedIds);
    } catch (e) {
      // JSON/parse/programming errors: do NOT use stale cache.
      return AlertsState(status: 'error', dismissed: dismissedIds);
    }
  }

  Future<AlertsState> _loadFromCache(
    String tripId,
    Set<String> dismissedIds,
  ) async {
    try {
      final cached = await _db.getCachedAlerts(
        identityScope: _identityScope,
        tripId: tripId,
      );
      if (cached != null) {
        final parsed = TripAlertsResponse.fromJson(
          jsonDecode(cached) as Map<String, dynamic>,
        );
        final valid = parsed.alerts.where((a) => !a.isExpired).toList();
        return AlertsState(
          alerts: valid,
          status: 'cached',
          dismissed: dismissedIds,
        );
      }
    } catch (_) {}
    return AlertsState(dismissed: dismissedIds);
  }

  /// Dismiss an alert locally and persist the dismissal.
  Future<void> dismiss(String alertId) async {
    final current = state.valueOrNull ?? const AlertsState();
    final newDismissed = {...current.dismissed, alertId};
    state = AsyncValue.data(current.copyWith(dismissed: newDismissed));
    try {
      await _db.dismissAlert(
        identityScope: _identityScope,
        alertId: alertId,
      );
    } catch (_) {}
  }

  /// Manual refresh (pull-to-refresh or explicit tap).
  Future<void> refresh() async {
    state = AsyncValue.data(
      (state.valueOrNull ?? const AlertsState()).copyWith(loading: true),
    );
    state = AsyncValue.data(await _load(arg));
  }
}

/// Driver-card navigation and itinerary shimmer temporarily unmount the alert
/// section. Retaining this provider prevents each remount from becoming
/// another weather request.
final alertsNotifierProvider =
    AsyncNotifierProvider.family<AlertsNotifier, AlertsState, String>(
  AlertsNotifier.new,
);
