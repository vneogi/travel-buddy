import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../offline/offline_database.dart';
import '../../services/signal_service.dart';
import '../driver_card/driver_card_helpers.dart';
import 'current_window.dart';

@immutable
class ItineraryState {
  final List<TripNode> nodes;
  final bool loading;          // initial fetch
  final bool processing;       // an event is in flight
  final String? banner;        // "Heads up: ..." note from last event
  final Object? error;         // load error → ErrorView
  final bool rerouteLimitHit;  // screen shows upgrade, then clears
  final Set<String> lovedPlaceRefs; // local-only: which venues the user loved
  final Map<String, NodeOutcome> nodeOutcomes;
  final Set<String> outcomeRecordingNodeIds;

  const ItineraryState({
    this.nodes = const [],
    this.loading = true,
    this.processing = false,
    this.banner,
    this.error,
    this.rerouteLimitHit = false,
    this.lovedPlaceRefs = const {},
    this.nodeOutcomes = const {},
    this.outcomeRecordingNodeIds = const {},
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
    Map<String, NodeOutcome>? nodeOutcomes,
    Set<String>? outcomeRecordingNodeIds,
  }) =>
      ItineraryState(
        nodes: nodes ?? this.nodes,
        loading: loading ?? this.loading,
        processing: processing ?? this.processing,
        banner: identical(banner, _keep) ? this.banner : banner as String?,
        error: identical(error, _keep) ? this.error : error,
        rerouteLimitHit: rerouteLimitHit ?? this.rerouteLimitHit,
        lovedPlaceRefs: lovedPlaceRefs ?? this.lovedPlaceRefs,
        nodeOutcomes: nodeOutcomes ?? this.nodeOutcomes,
        outcomeRecordingNodeIds:
            outcomeRecordingNodeIds ?? this.outcomeRecordingNodeIds,
      );
}

class ItineraryController extends StateNotifier<ItineraryState> {
  final Ref _ref;
  final String tripId;
  ItineraryController(this._ref, this.tripId) : super(const ItineraryState()) {
    load();
  }

  Future<void> load() async {
    // Preserve already-filled hearts through reload.
    final priorLoved = state.lovedPlaceRefs;
    final priorOutcomes = state.nodeOutcomes;
    final priorRecording = state.outcomeRecordingNodeIds;
    state = ItineraryState(
      loading: true,
      lovedPlaceRefs: priorLoved,
      nodeOutcomes: priorOutcomes,
      outcomeRecordingNodeIds: priorRecording,
    );
    try {
      final trip = await _ref.read(tripRepoProvider).getTrip(tripId);
      if (!mounted) return;
      // Restore persisted hearts (state hydration only -- no signal emission).
      final restored = await _restoreLovedRefs();
      if (!mounted) return;
      final merged = {...priorLoved, ...restored};
      final restoredOutcomes = await _restoreNodeOutcomes();
      if (!mounted) return;
      state = ItineraryState(
        nodes: trip.nodes,
        loading: false,
        lovedPlaceRefs: merged,
        nodeOutcomes: {...restoredOutcomes, ...priorOutcomes},
        outcomeRecordingNodeIds: priorRecording,
      );
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
        if (!mounted) return;
        if (cachedJson != null) {
          final cachedMap = jsonDecode(cachedJson) as Map<String, dynamic>;
          final cachedTrip = TripState.fromJson(cachedMap);
          final restored = await _restoreLovedRefs();
          if (!mounted) return;
          final merged = {...priorLoved, ...restored};
          final restoredOutcomes = await _restoreNodeOutcomes();
          if (!mounted) return;
          state = ItineraryState(
            nodes: cachedTrip.nodes,
            loading: false,
            banner: 'Offline: showing saved itinerary',
            lovedPlaceRefs: merged,
            nodeOutcomes: {...restoredOutcomes, ...priorOutcomes},
            outcomeRecordingNodeIds: priorRecording,
          );
          _preCachePlaces(cachedTrip.nodes);
          return;
        }
      } catch (cacheErr) {
        debugPrint('[ItineraryController] Offline cache read error: $cacheErr');
      }
      if (!mounted) return;
      state = ItineraryState(
        loading: false,
        error: e,
        lovedPlaceRefs: priorLoved,
        nodeOutcomes: priorOutcomes,
        outcomeRecordingNodeIds: priorRecording,
      );
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
    if (state.processing) return null;
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
        // Preserve loved refs through event application.
        lovedPlaceRefs: state.lovedPlaceRefs,
        nodeOutcomes: state.nodeOutcomes,
        outcomeRecordingNodeIds: state.outcomeRecordingNodeIds,
      );
      _preCachePlaces(state.nodes);
      _cacheUpdatedTripNodes(state.nodes);
      _ref.invalidate(userStatusProvider); // refresh reroute badge
      return result;
    } on RerouteLimitException {
      state = state.copyWith(processing: false, rerouteLimitHit: true);
      return null;
    } catch (error) {
      state = state.copyWith(
        processing: false,
        banner: error is NetworkException
            ? "Can't reach Travel Buddy \u2014 check your connection."
            : 'Something went wrong. Please try again.',
      );
      return null;
    }
  }

  void clearRerouteLimit() => state = state.copyWith(rerouteLimitHit: false);
  void clearBanner() => state = state.copyWith(banner: null);

  /// Mark a venue as loved: optimistic UI update, then persist.
  /// A cache write failure must not crash the itinerary.
  void markLoved(String placeRef) {
    if (!mounted) return;
    state = state.copyWith(
      lovedPlaceRefs: {...state.lovedPlaceRefs, placeRef},
    );
    // Persist to SQLite (fire-and-forget, never crash the itinerary).
    try {
      final db = _ref.read(offlineDatabaseProvider);
      final scope = _ref.read(identityCacheScopeProvider);
      db.upsertLovedPlace(
        identityScope: scope,
        tripId: tripId,
        placeRef: placeRef,
      ).catchError((e) {
        debugPrint('[ItineraryController] Persist loved error: $e');
      });
    } catch (e) {
      debugPrint('[ItineraryController] Persist loved error: $e');
    }
  }

  /// Restore persisted loved refs from SQLite.
  /// This is state hydration only -- it must NEVER emit a signal.
  Future<Set<String>> _restoreLovedRefs() async {
    try {
      final db = _ref.read(offlineDatabaseProvider);
      final scope = _ref.read(identityCacheScopeProvider);
      return await db.getLovedPlaceRefs(identityScope: scope, tripId: tripId);
    } catch (e) {
      debugPrint('[ItineraryController] Restore loved refs error: $e');
      return {};
    }
  }

  Future<Map<String, NodeOutcome>> _restoreNodeOutcomes() async {
    try {
      final db = _ref.read(offlineDatabaseProvider);
      final scope = _ref.read(identityCacheScopeProvider);
      return await db.getNodeOutcomes(
        identityScope: scope,
        tripId: tripId,
      );
    } catch (e) {
      debugPrint('[ItineraryController] Restore node outcomes error: $e');
      return {};
    }
  }

  Future<void> recordVisited(TripNode node) async {
    if (!nodeCanRecordOutcome(
      node,
      DateTime.now().toUtc(),
      state.nodeOutcomes[node.nodeId],
    )) {
      return;
    }
    if (!_beginOutcomeRecording(node.nodeId)) return;
    final outcome = NodeOutcome(
      outcome: NodeOutcome.visited,
      recordedAt: DateTime.now().toUtc(),
    );
    String? persistenceError;
    try {
      final enqueued =
          await _ref.read(signalServiceProvider).emitVisitedConfirmedWithResult(
            placeRef: node.venueId ?? node.venueName,
            tripId: tripId,
          );
      if (!enqueued) {
        if (mounted) {
          state = state.copyWith(
            banner: 'Could not record this outcome. Please try again.',
          );
        }
        return;
      }
      try {
        await _persistNodeOutcome(node.nodeId, outcome);
      } catch (error) {
        persistenceError = 'Could not save this outcome. Please try again later.';
        debugPrint('[ItineraryController] Persist node outcome error: $error');
      }
      if (!mounted) return;
      state = state.copyWith(
        nodeOutcomes: {...state.nodeOutcomes, node.nodeId: outcome},
        banner: persistenceError,
      );
    } finally {
      _finishOutcomeRecording(node.nodeId);
    }
  }

  Future<void> recordSkipped(TripNode node, String reason) async {
    if (!SignalService.validSkipReasons.contains(reason)) {
      throw ArgumentError.value(reason, 'reason', 'is not a valid skip reason');
    }
    if (!nodeCanRecordOutcome(
      node,
      DateTime.now().toUtc(),
      state.nodeOutcomes[node.nodeId],
    )) {
      return;
    }
    if (!_beginOutcomeRecording(node.nodeId)) return;
    final outcome = NodeOutcome(
      outcome: NodeOutcome.skipped,
      reason: reason,
      recordedAt: DateTime.now().toUtc(),
    );
    String? persistenceError;
    try {
      final enqueued =
          await _ref.read(signalServiceProvider).emitNodeSkippedWithResult(
            placeRef: node.venueId ?? node.venueName,
            reason: reason,
            tripId: tripId,
          );
      if (!enqueued) {
        if (mounted) {
          state = state.copyWith(
            banner: 'Could not record this outcome. Please try again.',
          );
        }
        return;
      }
      try {
        await _persistNodeOutcome(node.nodeId, outcome);
      } catch (error) {
        persistenceError = 'Could not save this outcome. Please try again later.';
        debugPrint('[ItineraryController] Persist node outcome error: $error');
      }
      if (!mounted) return;
      state = state.copyWith(
        nodeOutcomes: {...state.nodeOutcomes, node.nodeId: outcome},
        banner: persistenceError,
      );

      if (nodeIsCurrentWindow(node, DateTime.now().toUtc()) &&
          !node.isLocked &&
          node.status == NodeStatus.pending) {
        await applyEvent(
          type: EventType.cancelActivity,
          message: 'Skip ${node.venueName} ($reason)',
          targetNodeId: node.nodeId,
        );
        if (persistenceError != null && mounted) {
          state = state.copyWith(banner: persistenceError);
        }
      }
    } finally {
      _finishOutcomeRecording(node.nodeId);
    }
  }

  bool _beginOutcomeRecording(String nodeId) {
    if (!mounted ||
        state.nodeOutcomes.containsKey(nodeId) ||
        state.outcomeRecordingNodeIds.contains(nodeId)) {
      return false;
    }
    state = state.copyWith(
      outcomeRecordingNodeIds: {...state.outcomeRecordingNodeIds, nodeId},
    );
    return true;
  }

  void _finishOutcomeRecording(String nodeId) {
    if (!mounted || !state.outcomeRecordingNodeIds.contains(nodeId)) return;
    state = state.copyWith(
      outcomeRecordingNodeIds: {...state.outcomeRecordingNodeIds}..remove(nodeId),
    );
  }

  Future<void> _persistNodeOutcome(String nodeId, NodeOutcome outcome) {
    return _ref.read(offlineDatabaseProvider).upsertNodeOutcome(
          identityScope: _ref.read(identityCacheScopeProvider),
          tripId: tripId,
          nodeId: nodeId,
          outcome: outcome.outcome,
          reason: outcome.reason,
          recordedAt: outcome.recordedAt,
        );
  }

  void _cacheUpdatedTripNodes(List<TripNode> nodes) {
    try {
      final db = _ref.read(offlineDatabaseProvider);
      db.getCachedTrip(tripId).then((cachedJson) {
        if (cachedJson == null) return;
        final cached = (jsonDecode(cachedJson) as Map).cast<String, dynamic>();
        cached['nodes'] = nodes.map((node) => node.toJson()).toList();
        db.cacheTrip(tripId, jsonEncode(cached)).catchError((error) {
          debugPrint('[ItineraryController] Updated trip cache error: $error');
        });
      }).catchError((error) {
        debugPrint('[ItineraryController] Trip cache read error: $error');
      });
    } catch (error) {
      debugPrint('[ItineraryController] Updated trip cache error: $error');
    }
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
