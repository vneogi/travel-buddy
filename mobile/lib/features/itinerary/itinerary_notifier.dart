import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../driver_card/driver_card_helpers.dart';

@immutable
class ItineraryState {
  final List<TripNode> nodes;
  final bool loading;          // initial fetch
  final bool processing;       // an event is in flight
  final String? banner;        // "Heads up: ..." note from last event
  final Object? error;         // load error → ErrorView
  final bool rerouteLimitHit;  // screen shows upgrade, then clears
  final Set<String> lovedPlaceRefs; // local-only: which venues the user loved

  const ItineraryState({
    this.nodes = const [],
    this.loading = true,
    this.processing = false,
    this.banner,
    this.error,
    this.rerouteLimitHit = false,
    this.lovedPlaceRefs = const {},
  });

  static const _keep = Object();
  ItineraryState copyWith({
    List<TripNode>? nodes,
    bool? loading,
    bool? processing,
    Object? banner = _keep,
    Object? error = _keep,
    bool? rerouteLimitHit,
    Set<String>? lovedPlaceRefs,
  }) =>
      ItineraryState(
        nodes: nodes ?? this.nodes,
        loading: loading ?? this.loading,
        processing: processing ?? this.processing,
        banner: identical(banner, _keep) ? this.banner : banner as String?,
        error: identical(error, _keep) ? this.error : error,
        rerouteLimitHit: rerouteLimitHit ?? this.rerouteLimitHit,
        lovedPlaceRefs: lovedPlaceRefs ?? this.lovedPlaceRefs,
      );
}

class ItineraryController extends StateNotifier<ItineraryState> {
  final Ref _ref;
  final String tripId;
  ItineraryController(this._ref, this.tripId) : super(const ItineraryState()) {
    load();
  }

  Future<void> load() async {
    state = const ItineraryState(loading: true);
    try {
      final trip = await _ref.read(tripRepoProvider).getTrip(tripId);
      if (!mounted) return;
      state = ItineraryState(nodes: trip.nodes, loading: false);
      _preCachePlaces(trip.nodes);
      // SPEC-04: Persist to SQLite cache_trip for offline reads
      try {
        final db = _ref.read(offlineDatabaseProvider);
        db.cacheTrip(tripId, jsonEncode(trip.toJson())).catchError((e) {
          debugPrint('[ItineraryController] Cache trip error: $e');
        });
      } catch (_) {}
    } catch (e) {
      if (!mounted) return;
      // SPEC-04: Offline fallback -- read from SQLite cache_trip
      try {
        final db = _ref.read(offlineDatabaseProvider);
        final cachedJson = await db.getCachedTrip(tripId);
        if (cachedJson != null && mounted) {
          final cachedMap = jsonDecode(cachedJson) as Map<String, dynamic>;
          final cachedTrip = TripState.fromJson(cachedMap);
          state = ItineraryState(
            nodes: cachedTrip.nodes,
            loading: false,
            banner: 'Offline: showing saved itinerary',
          );
          _preCachePlaces(cachedTrip.nodes);
          return;
        }
      } catch (cacheErr) {
        debugPrint('[ItineraryController] Offline cache read error: $cacheErr');
      }
      state = ItineraryState(loading: false, error: e);
    }
  }

  /// SPEC-12: pre-cache place data for offline driver cards.
  void _preCachePlaces(List<TripNode> nodes) {
    try {
      final db = _ref.read(offlineDatabaseProvider);
      for (final node in nodes) {
        final placeRef = node.venueId ?? node.venueName;
        final data = PlaceDriverCardData.fromTripNode(node);
        db.cachePlace(placeRef, data.serialize()).catchError((e) {
          debugPrint('[ItineraryController] Pre-cache place error: $e');
        });
      }
    } catch (e) {
      debugPrint('[ItineraryController] Pre-cache places error: $e');
    }
  }

  /// Returns the result (null on reroute-limit or error — the UI state is set
  /// here so callers don't have to handle those visually).
  Future<TripEventResult?> applyEvent({
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    state = state.copyWith(processing: true, banner: null);
    try {
      final result = await _ref.read(tripRepoProvider).sendEvent(
            tripId: tripId,
            type: type,
            message: message,
            targetNodeId: targetNodeId,
            preferences: preferences,
          );
      if (!mounted) return null;
      state = state.copyWith(
        // For light/info events the server returns the unchanged node list, so
        // this is always safe; the screen's diff produces no animation then.
        nodes: result.updatedNodes.isNotEmpty ? result.updatedNodes : state.nodes,
        processing: false,
        banner: _headsUp(result.message),
      );
      _ref.invalidate(userStatusProvider); // refresh reroute badge
      return result;
    } on RerouteLimitException {
      state = state.copyWith(processing: false, rerouteLimitHit: true);
      return null;
    } catch (_) {
      state = state.copyWith(
          processing: false, banner: 'Something went wrong. Please try again.');
      return null;
    }
  }

  void clearRerouteLimit() => state = state.copyWith(rerouteLimitHit: false);
  void clearBanner() => state = state.copyWith(banner: null);

  /// Mark a venue as loved (local UI state — the signal itself goes through
  /// SignalService/outbox). The backend doesn't return love state, so we track
  /// it client-side for the filled-heart affordance.
  void markLoved(String placeRef) {
    if (!mounted) return;
    state = state.copyWith(
      lovedPlaceRefs: {...state.lovedPlaceRefs, placeRef},
    );
  }

  String? _headsUp(String msg) {
    final i = msg.indexOf('Heads up:');
    return i >= 0 ? msg.substring(i).trim() : null;
  }
}

final itineraryControllerProvider = StateNotifierProvider.autoDispose
    .family<ItineraryController, ItineraryState, String>(
  (ref, tripId) => ItineraryController(ref, tripId),
);

/// Compat shim so chat_screen keeps working unchanged. Routes chat-sent events
/// through the SAME controller instance → chat-triggered structural changes
/// animate the timeline underneath. (Itinerary stays mounted under the pushed
/// chat screen, so autoDispose keeps the instance alive.)
final tripEventProvider = Provider<TripEventService>((ref) => TripEventService(ref));

class TripEventService {
  final Ref _ref;
  TripEventService(this._ref);

  Future<TripEventResult?> sendEvent({
    required String tripId,
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) =>
      _ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(
            type: type,
            message: message,
            targetNodeId: targetNodeId,
            preferences: preferences,
          );
}
