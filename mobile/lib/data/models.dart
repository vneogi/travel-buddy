/// Data models matching the Travel Buddy backend API contract.
/// Hand-written fromJson (no codegen) for flexibility.

enum EventType {
  cancelActivity('cancel_activity'),
  swapActivity('swap_activity'),
  addActivity('add_activity'),
  changeMood('change_mood'),
  weatherAlert('weather_alert'),
  translate('translate'),
  askInfo('ask_info'),
  reroute('reroute');

  final String wire;
  const EventType(this.wire);
}

enum NodeStatus {
  pending,
  active,
  completed,
  skipped;

  static NodeStatus fromWire(String s) => NodeStatus.values.firstWhere(
        (e) => e.name == s,
        orElse: () => NodeStatus.pending,
      );
}

class TripNode {
  final String nodeId;
  final String venueName;
  final String? venueId;
  final DateTime scheduledStart;
  final int durationMinutes;
  final bool isLocked;
  final NodeStatus status;
  final String? microLocation;
  final List<String> vibeTags;
  final double? lat, lng;
  final String? openingHours;
  final Map<String, dynamic>? namesLocal;
  final Map<String, dynamic>? landmarksLocal;
  final String? nearestLandmark;

  const TripNode({
    required this.nodeId,
    required this.venueName,
    required this.scheduledStart,
    required this.durationMinutes,
    required this.isLocked,
    required this.status,
    required this.vibeTags,
    this.venueId,
    this.microLocation,
    this.lat,
    this.lng,
    this.openingHours,
    this.namesLocal,
    this.landmarksLocal,
    this.nearestLandmark,
  });

  factory TripNode.fromJson(Map<String, dynamic> j) => TripNode(
        nodeId: j['node_id'] as String,
        venueName: j['venue_name'] as String,
        venueId: j['venue_id'] as String?,
        scheduledStart: DateTime.parse(j['scheduled_start'] as String),
        durationMinutes: (j['duration_minutes'] as num?)?.toInt() ?? 90,
        isLocked: j['is_locked'] as bool? ?? false,
        status: NodeStatus.fromWire(j['status'] as String? ?? 'pending'),
        microLocation: j['micro_location'] as String?,
        vibeTags: (j['vibe_tags'] as List?)?.cast<String>() ?? const [],
        lat: (j['lat'] as num?)?.toDouble(),
        lng: (j['lng'] as num?)?.toDouble(),
        openingHours: j['opening_hours'] as String?,
        namesLocal: (j['names_local'] as Map?)?.cast<String, dynamic>(),
        landmarksLocal: (j['landmarks_local'] as Map?)?.cast<String, dynamic>(),
        nearestLandmark: j['nearest_landmark'] as String?,
      );
}

class TripState {
  final String tripId;
  final String userId;
  final String? mood;
  final List<TripNode> nodes;

  const TripState({
    required this.tripId,
    required this.userId,
    required this.nodes,
    this.mood,
  });

  factory TripState.fromJson(Map<String, dynamic> j) => TripState(
        tripId: j['trip_id'] as String,
        userId: j['user_id'] as String,
        mood: (j['current_context'] as Map?)?['mood'] as String?,
        nodes: ((j['nodes'] as List?) ?? const [])
            .map((n) => TripNode.fromJson(n as Map<String, dynamic>))
            .toList(),
      );
}

class TripEventResult {
  /// May include a "Heads up: ..." scheduler note at the end.
  final String message;
  final List<TripNode> updatedNodes;
  final String routingTier; // "light" | "heavy"
  final bool fromCache;
  final int? reroutesRemaining;

  const TripEventResult({
    required this.message,
    required this.updatedNodes,
    required this.routingTier,
    required this.fromCache,
    this.reroutesRemaining,
  });

  factory TripEventResult.fromJson(Map<String, dynamic> j) => TripEventResult(
        message: j['message'] as String? ?? '',
        updatedNodes: ((j['updated_nodes'] as List?) ?? const [])
            .map((n) => TripNode.fromJson(n as Map<String, dynamic>))
            .toList(),
        routingTier: j['routing_tier_used'] as String? ?? 'light',
        fromCache: j['from_cache'] as bool? ?? false,
        reroutesRemaining: (j['reroutes_remaining'] as num?)?.toInt(),
      );
}

class UserStatus {
  final String userId;
  final String tier; // "free" | "pro"
  final int used, remaining, max;

  const UserStatus({
    required this.userId,
    required this.tier,
    required this.used,
    required this.remaining,
    required this.max,
  });

  factory UserStatus.fromJson(Map<String, dynamic> j) => UserStatus(
        userId: j['user_id'] as String,
        tier: j['tier'] as String,
        used: (j['daily_reroutes_used'] as num).toInt(),
        remaining: (j['daily_reroutes_remaining'] as num).toInt(),
        max: (j['max_daily_reroutes'] as num).toInt(),
      );
}

class VenueSearchResult {
  final String venueId, name, description, microLocation;
  final List<String> vibeTags;
  final double? distanceKm;
  final bool isSponsored;

  const VenueSearchResult({
    required this.venueId,
    required this.name,
    required this.description,
    required this.microLocation,
    required this.vibeTags,
    this.distanceKm,
    this.isSponsored = false,
  });

  factory VenueSearchResult.fromJson(Map<String, dynamic> j) => VenueSearchResult(
        venueId: j['venue_id'] as String,
        name: j['name'] as String,
        description: j['description'] as String? ?? '',
        microLocation: j['micro_location'] as String? ?? '',
        vibeTags: (j['vibe_tags'] as List?)?.cast<String>() ?? const [],
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        isSponsored: j['is_sponsored'] as bool? ?? false,
      );
}
