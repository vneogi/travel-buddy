import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_client.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/context_alert.dart';
import '../../offline/offline_database.dart';

/// SPEC-29: Alert state for a trip.
class AlertsState {
  final List<ContextAlert> alerts;
  final bool loading;
  final String? status;
  final Set<String> _dismissed;

  const AlertsState({
    this.alerts = const [],
    this.loading = false,
    this.status,
    Set<String> dismissed = const {},
  }) : _dismissed = dismissed;

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
        dismissed: dismissed ?? _dismissed,
      );

  /// Visible alerts (not dismissed, not expired).
  List<ContextAlert> get visible => alerts
      .where((a) => !_dismissed.contains(a.alertId) && !a.isExpired)
      .toList();
}

/// SPEC-29: Fetches alerts for a trip without blocking itinerary.
///
/// - 401/403 never falls back to cache.
/// - Only network errors use unexpired, identity-scoped cache.
/// - JSON/parse errors do not silently use stale cache.
class AlertsNotifier extends FamilyAsyncNotifier<AlertsState, String> {
  @override
  Future<AlertsState> build(String arg) async {
    return _load(arg);
  }

  String get _identityScope {
    try {
      return ref.read(currentUserIdProvider);
    } catch (_) {
      return 'anonymous';
    }
  }

  OfflineDatabase get _db => ref.read(offlineDatabaseProvider);

  Future<AlertsState> _load(String tripId) async {
    // Load persisted dismissals first.
    Set<String> dismissed;
    try {
      dismissed = await _db.getDismissedAlertIds(
        identityScope: _identityScope,
      );
    } catch (_) {
      dismissed = {};
    }

    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/trip/$tripId/alerts');
      final parsed = TripAlertsResponse.fromJson(resp);
      if (parsed.status == 'unconfigured') {
        return AlertsState(status: 'unconfigured', dismissed: dismissed);
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
        dismissed: dismissed,
      );
    } on UnauthorizedException {
      // 401/403 never falls back to cache.
      return AlertsState(status: 'auth_error', dismissed: dismissed);
    } on ForbiddenException {
      return AlertsState(status: 'auth_error', dismissed: dismissed);
    } on NetworkException {
      // Only network errors may use unexpired cache.
      return _loadFromCache(tripId, dismissed);
    } catch (e) {
      // JSON/parse/programming errors: do NOT use stale cache.
      return AlertsState(status: 'error', dismissed: dismissed);
    }
  }

  Future<AlertsState> _loadFromCache(
    String tripId,
    Set<String> dismissed,
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
          dismissed: dismissed,
        );
      }
    } catch (_) {}
    return AlertsState(dismissed: dismissed);
  }

  /// Dismiss an alert locally and persist the dismissal.
  Future<void> dismiss(String alertId) async {
    final current = state.valueOrNull ?? const AlertsState();
    final newDismissed = {...current._dismissed, alertId};
    state = AsyncValue.data(current.copyWith(dismissed: newDismissed));
    try {
      await _db.dismissAlert(
        identityScope: _identityScope,
        alertId: alertId,
      );
    } catch (_) {}
  }

  /// Manual refresh (pull-to-refresh or resume).
  Future<void> refresh() async {
    state = AsyncValue.data(
      (state.valueOrNull ?? const AlertsState()).copyWith(loading: true),
    );
    state = AsyncValue.data(await _load(arg));
  }
}

final alertsNotifierProvider =
    AsyncNotifierProvider.family<AlertsNotifier, AlertsState, String>(
  AlertsNotifier.new,
);
