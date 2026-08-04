import '../core/api_client.dart';
import 'models.dart';

/// Trip operations: create, fetch, and send events.
class TripRepository {
  final ApiClient _api;
  TripRepository(this._api);

  /// NOTE: backend currently returns a FIXED sample itinerary; `mood` is stored
  /// but preferences don't yet personalize generation.
  Future<TripState> create({required DateTime startDate, String? mood}) async {
    final data = await _api.post('/trip/create', body: {
      'start_date': startDate.toIso8601String(),
      if (mood != null) 'initial_mood': mood,
    });
    // create returns {trip_id, nodes[...], ...}; fetch full state for consistency.
    return getTrip(data['trip_id'] as String);
  }

  Future<TripState> getTrip(String tripId) async => TripState.fromJson(
        await _api.get('/trip/\$tripId') as Map<String, dynamic>,
      );

  /// The one endpoint for cancel/swap/add/reroute/translate/ask_info/etc.
  /// There is NO WebSocket — chat is this REST call.
  Future<TripEventResult> sendEvent({
    required String tripId,
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    final data = await _api.post('/trip/event', body: {
      'trip_id': tripId,
      'event_type': type.wire,
      'message': message,
      if (targetNodeId != null) 'target_node_id': targetNodeId,
      if (preferences != null) 'preferences': preferences,
    });
    return TripEventResult.fromJson(data as Map<String, dynamic>);
  }

  /// RAG venue search for swap suggestions.
  Future<List<VenueSearchResult>> searchVenues({
    required String query,
    List<String>? vibeTags,
  }) async {
    final data = await _api.get('/venues/search', query: {
      'q': query,
      if (vibeTags != null && vibeTags.isNotEmpty) 'vibe_tags': vibeTags.join(','),
    });
    return (data as List)
        .map((v) => VenueSearchResult.fromJson(v as Map<String, dynamic>))
        .toList();
  }
}

/// User status and tier info.
class UserRepository {
  final ApiClient _api;
  UserRepository(this._api);

  Future<UserStatus> status() async => UserStatus.fromJson(
        await _api.get('/user/status') as Map<String, dynamic>,
      );
}

/// Payment operations (scaffolded — activates when Stripe/RC keys are set).
class PaymentRepository {
  final ApiClient _api;
  PaymentRepository(this._api);

  Future<List<Map<String, dynamic>>> getPlans() async {
    final data = await _api.get('/payment/plans');
    return (data as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> getStatus() async =>
      await _api.get('/payment/status') as Map<String, dynamic>;

  Future<String> createCheckout({required String priceId}) async {
    final data = await _api.post('/payment/checkout', body: {'price_id': priceId});
    return data['checkout_url'] as String;
  }
}
