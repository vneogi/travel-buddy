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
        await _api.get('/trip/$tripId') as Map<String, dynamic>,
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
  /// Backend param is `query` (NOT `q`). Vibe filtering is NOT a param here —
  /// it's applied via the /trip/event `preferences.vibe_tags` path.
  Future<List<VenueSearchResult>> searchVenues({
    required String query,
    double lat = 25.1972,
    double lng = 55.2744,
    int topK = 8,
  }) async {
    final data = await _api.get('/venues/search', query: {
      'query': query,
      'lat': lat,
      'lng': lng,
      'top_k': topK,
    });
    // Endpoint returns {query, results_count, results: [...]}.
    final results = (data as Map)['results'] as List? ?? const [];
    return results
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

  /// Backend returns {"plans": [...]}, not a bare list.
  Future<List<Map<String, dynamic>>> getPlans() async {
    final data = await _api.get('/payment/plans');
    return ((data as Map)['plans'] as List).cast<Map<String, dynamic>>();
  }

  Future<Map<String, dynamic>> getStatus() async =>
      await _api.get('/payment/status') as Map<String, dynamic>;

  /// Backend expects `plan_id` ("pro_monthly" | "pro_yearly"); it resolves the
  /// Stripe price id server-side.
  Future<String> createCheckout({required String planId}) async {
    final data = await _api.post('/payment/checkout', body: {'plan_id': planId});
    return data['checkout_url'] as String;
  }
}
