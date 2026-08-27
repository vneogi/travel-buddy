import 'dart:convert';

import 'package:flutter/foundation.dart';
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

  const AlertsState({
    this.alerts = const [],
    this.loading = false,
    this.status,
  });
}

/// SPEC-29: Fetches alerts for a trip without blocking itinerary.
class AlertsNotifier extends AutoDisposeFamilyAsyncNotifier<AlertsState, String> {
  @override
  Future<AlertsState> build(String tripId) async {
    return _load(tripId);
  }

  Future<AlertsState> _load(String tripId) async {
    try {
      final client = ref.read(apiClientProvider);
      final resp = await client.get('/trip/$tripId/alerts');
      final parsed = TripAlertsResponse.fromJson(resp);
      if (parsed.status == 'unconfigured') {
        return const AlertsState(status: 'unconfigured');
      }
      final valid = parsed.alerts.where((a) => !a.isExpired).toList();

      // Cache identity-scoped
      try {
        final db = ref.read(offlineDatabaseProvider);
        await db.cacheTrip(
          'alerts_$tripId',
          jsonEncode(resp),
        );
      } catch (_) {}

      return AlertsState(alerts: valid, status: 'available');
    } on UnauthorizedException {
      // 401/403 never falls back to cache
      return const AlertsState(status: 'auth_error');
    } on ForbiddenException {
      return const AlertsState(status: 'auth_error');
    } catch (e) {
      // Network failure: use unexpired cached alert
      return _loadFromCache(tripId);
    }
  }

  Future<AlertsState> _loadFromCache(String tripId) async {
    try {
      final db = ref.read(offlineDatabaseProvider);
      final cached = await db.getCachedTrip('alerts_$tripId');
      if (cached != null) {
        final parsed = TripAlertsResponse.fromJson(
          jsonDecode(cached) as Map<String, dynamic>,
        );
        final valid = parsed.alerts.where((a) => !a.isExpired).toList();
        return AlertsState(alerts: valid, status: 'cached');
      }
    } catch (_) {}
    return const AlertsState();
  }

  Future<void> refresh() async {
    state = const AsyncValue.loading();
    state = AsyncValue.data(await _load(arg));
  }
}

final alertsNotifierProvider = AsyncNotifierProvider.autoDispose
    .family<AlertsNotifier, AlertsState, String>(AlertsNotifier.new);
