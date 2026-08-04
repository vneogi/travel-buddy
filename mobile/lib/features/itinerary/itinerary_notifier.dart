import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/providers.dart';
import '../../data/models.dart';

/// Per-trip state provider. Fetches once, then updates in-place after events.
final tripProvider = FutureProvider.family<TripState, String>((ref, tripId) {
  return ref.watch(tripRepoProvider).getTrip(tripId);
});

/// Sends an event and refreshes the trip + user status.
/// Use: ref.read(tripEventProvider).sendEvent(...)
final tripEventProvider = Provider<TripEventService>((ref) {
  return TripEventService(ref);
});

class TripEventService {
  final Ref _ref;
  TripEventService(this._ref);

  Future<TripEventResult> sendEvent({
    required String tripId,
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    final repo = _ref.read(tripRepoProvider);
    final result = await repo.sendEvent(
      tripId: tripId,
      type: type,
      message: message,
      targetNodeId: targetNodeId,
      preferences: preferences,
    );
    // Refresh trip state and reroute counter.
    _ref.invalidate(tripProvider(tripId));
    _ref.invalidate(userStatusProvider);
    return result;
  }
}
