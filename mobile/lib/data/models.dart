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
  reroute('reroute'),
  addBooking('add_booking'),
  editBooking('edit_booking'),
  deleteBooking('delete_booking');

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
  final String? geoRegion;
  // SPEC-10: Booking anchor fields
  final String nodeKind;
  final String? bookingType;
  final String? confirmationCode;
  final String? bookingNotes;
  final String? importSource;

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
    this.geoRegion,
    this.nodeKind = 'activity',
    this.bookingType,
    this.confirmationCode,
    this.bookingNotes,
    this.importSource,
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
        geoRegion: j['geo_region'] as String?,
        nodeKind: (j['node_kind'] as String?) ?? 'activity',
        bookingType: j['booking_type'] as String?,
        confirmationCode: j['confirmation_code'] as String?,
        bookingNotes: j['booking_notes'] as String?,
        importSource: j['import_source'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'node_id': nodeId,
        'venue_name': venueName,
        'venue_id': venueId,
        'scheduled_start': scheduledStart.toUtc().toIso8601String(),
        'duration_minutes': durationMinutes,
        'is_locked': isLocked,
        'status': status.name,
        'micro_location': microLocation,
        'vibe_tags': vibeTags,
        'lat': lat,
        'lng': lng,
        'opening_hours': openingHours,
        'names_local': namesLocal,
        'landmarks_local': landmarksLocal,
        'nearest_landmark': nearestLandmark,
        'geo_region': geoRegion,
        'node_kind': nodeKind,
        'booking_type': bookingType,
        'confirmation_code': confirmationCode,
        'booking_notes': bookingNotes,
        'import_source': importSource,
      };
}


/// SPEC-36: A supported corridor advertised by the server.
class SupportedCorridor {
  final String corridorId;
  final String displayName;
  final List<String> geoRegions;
  final int maxDays;
  final int maxDaysPerSegment;

  const SupportedCorridor({
    required this.corridorId,
    required this.displayName,
    required this.geoRegions,
    required this.maxDays,
    required this.maxDaysPerSegment,
  });

  factory SupportedCorridor.fromJson(Map<String, dynamic> j) =>
      SupportedCorridor(
        corridorId: j['corridor_id'] as String,
        displayName: j['display_name'] as String,
        geoRegions: (j['geo_regions'] as List).cast<String>(),
        maxDays: (j['max_days'] as num).toInt(),
        maxDaysPerSegment: (j['max_days_per_segment'] as num).toInt(),
      );

  Map<String, dynamic> toJson() => {
        'corridor_id': corridorId,
        'display_name': displayName,
        'geo_regions': geoRegions,
        'max_days': maxDays,
        'max_days_per_segment': maxDaysPerSegment,
      };
}

/// SPEC-36: A city segment in a corridor trip.
class TripSegment {
  final String geoRegion;
  final String startsOn;
  final String endsOn;

  const TripSegment({
    required this.geoRegion,
    required this.startsOn,
    required this.endsOn,
  });

  factory TripSegment.fromJson(Map<String, dynamic> j) => TripSegment(
        geoRegion: j['geo_region'] as String,
        startsOn: j['starts_on'] as String,
        endsOn: j['ends_on'] as String,
      );

  Map<String, dynamic> toJson() => {
        'geo_region': geoRegion,
        'starts_on': startsOn,
        'ends_on': endsOn,
      };
}
class TripState {
  final String tripId;
  final String userId;
  final String? mood;
  final String? geoRegion;
  final double? locationLat;
  final double? locationLng;
  final List<TripNode> nodes;
  final String? corridorId;
  final List<TripSegment> segments;

  const TripState({
    required this.tripId,
    required this.userId,
    required this.nodes,
    this.corridorId,
    this.segments = const [],
    this.mood,
    this.geoRegion,
    this.locationLat,
    this.locationLng,
  });

  factory TripState.fromJson(Map<String, dynamic> j) {
    final ctx = j['current_context'] as Map?;
    return TripState(
      tripId: j['trip_id'] as String,
      userId: j['user_id'] as String,
      mood: ctx?['mood'] as String?,
      geoRegion: j['geo_region'] as String?,
      locationLat: (ctx?['location_lat'] as num?)?.toDouble(),
      locationLng: (ctx?['location_lng'] as num?)?.toDouble(),
      nodes: ((j['nodes'] as List?) ?? const [])
          .map((n) => TripNode.fromJson(n as Map<String, dynamic>))
          .toList(),
      corridorId: j['corridor_id'] as String?,
      segments: ((j['segments'] as List?) ?? const [])
          .map((s) => TripSegment.fromJson(s as Map<String, dynamic>))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() => {
        'trip_id': tripId,
        'user_id': userId,
        if (geoRegion != null) 'geo_region': geoRegion,
        'current_context': {
          'mood': mood,
          if (locationLat != null) 'location_lat': locationLat,
          if (locationLng != null) 'location_lng': locationLng,
        },
        'nodes': nodes.map((n) => n.toJson()).toList(),
        if (corridorId != null) 'corridor_id': corridorId,
        if (segments.isNotEmpty)
          'segments': segments.map((s) => s.toJson()).toList(),
      };
}

class TripSummary {
  final String tripId;
  final String geoRegion;
  final DateTime? startsAt;
  final DateTime? endsAt;
  final int nodeCount;
  final int bookingCount;
  final DateTime updatedAt;
  final String? corridorId;

  const TripSummary({
    required this.tripId,
    required this.geoRegion,
    required this.nodeCount,
    required this.bookingCount,
    required this.updatedAt,
    this.corridorId,
    this.startsAt,
    this.endsAt,
  });

  factory TripSummary.fromJson(Map<String, dynamic> json) => TripSummary(
        tripId: json['trip_id'] as String,
        geoRegion: json['geo_region'] as String,
        startsAt: json['starts_at'] == null
            ? null
            : DateTime.parse(json['starts_at'] as String),
        endsAt: json['ends_at'] == null
            ? null
            : DateTime.parse(json['ends_at'] as String),
        nodeCount: (json['node_count'] as num).toInt(),
        bookingCount: (json['booking_count'] as num).toInt(),
        updatedAt: DateTime.parse(json['updated_at'] as String),
        corridorId: json['corridor_id'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'trip_id': tripId,
        'geo_region': geoRegion,
        'starts_at': startsAt?.toUtc().toIso8601String(),
        'ends_at': endsAt?.toUtc().toIso8601String(),
        'node_count': nodeCount,
        'booking_count': bookingCount,
        'updated_at': updatedAt.toUtc().toIso8601String(),
        if (corridorId != null) 'corridor_id': corridorId,
      };
}

/// SPEC-26: A single actionable stop inside the featured trip.
class FeaturedStop {
  final String nodeId;
  final String? venueId;
  final String venueName;
  final DateTime scheduledStart;
  final String status;

  const FeaturedStop({
    required this.nodeId,
    this.venueId,
    required this.venueName,
    required this.scheduledStart,
    required this.status,
  });

  factory FeaturedStop.fromJson(Map<String, dynamic> json) => FeaturedStop(
        nodeId: json['node_id'] as String,
        venueId: json['venue_id'] as String?,
        venueName: json['venue_name'] as String,
        scheduledStart: DateTime.parse(json['scheduled_start'] as String),
        status: json['status'] as String,
      );

  Map<String, dynamic> toJson() => {
        'node_id': nodeId,
        'venue_id': venueId,
        'venue_name': venueName,
        'scheduled_start': scheduledStart.toUtc().toIso8601String(),
        'status': status,
      };
}

/// SPEC-26: Featured trip for the Home card. Never contains state_json
/// or a full node list.
class FeaturedTrip {
  final String tripId;
  final String geoRegion;
  final DateTime? startsAt;
  final DateTime? endsAt;
  final bool isActive;
  final FeaturedStop? actionableStop;
  final String? corridorId;

  const FeaturedTrip({
    required this.tripId,
    required this.geoRegion,
    this.isActive = false,
    this.startsAt,
    this.endsAt,
    this.actionableStop,
    this.corridorId,
  });

  factory FeaturedTrip.fromJson(Map<String, dynamic> json) => FeaturedTrip(
        tripId: json['trip_id'] as String,
        geoRegion: json['geo_region'] as String,
        startsAt: json['starts_at'] == null
            ? null
            : DateTime.parse(json['starts_at'] as String),
        endsAt: json['ends_at'] == null
            ? null
            : DateTime.parse(json['ends_at'] as String),
        isActive: json['is_active'] as bool? ?? false,
        actionableStop: json['actionable_stop'] == null
            ? null
            : FeaturedStop.fromJson(
                (json['actionable_stop'] as Map).cast<String, dynamic>()),
        corridorId: json['corridor_id'] as String?,
      );

  Map<String, dynamic> toJson() => {
        'trip_id': tripId,
        'geo_region': geoRegion,
        'starts_at': startsAt?.toUtc().toIso8601String(),
        'ends_at': endsAt?.toUtc().toIso8601String(),
        'is_active': isActive,
        'actionable_stop': actionableStop?.toJson(),
        if (corridorId != null) 'corridor_id': corridorId,
      };
}

class HomeSnapshot {
  final List<String> supportedRegions;
  final List<SupportedCorridor> supportedCorridors;
  final List<TripSummary> trips;
  final FeaturedTrip? featuredTrip;
  final bool fromCache;
  final DateTime? cachedAt;

  const HomeSnapshot({
    required this.supportedRegions,
    this.supportedCorridors = const [],
    required this.trips,
    this.featuredTrip,
    this.fromCache = false,
    this.cachedAt,
  });

  factory HomeSnapshot.fromJson(
    Map<String, dynamic> json, {
    bool fromCache = false,
    DateTime? cachedAt,
  }) =>
      HomeSnapshot(
        supportedRegions:
            ((json['supported_regions'] as List?) ?? const []).cast<String>(),
        supportedCorridors: ((json['supported_corridors'] as List?) ?? const [])
            .map((c) => SupportedCorridor.fromJson(
                  (c as Map).cast<String, dynamic>()))
            .toList(),
        trips: ((json['trips'] as List?) ?? const [])
            .map((trip) => TripSummary.fromJson(
                  (trip as Map).cast<String, dynamic>(),
                ))
            .toList(),
        featuredTrip: json['featured_trip'] == null
            ? null
            : FeaturedTrip.fromJson(
                (json['featured_trip'] as Map).cast<String, dynamic>()),
        fromCache: fromCache,
        cachedAt: cachedAt,
      );

  Map<String, dynamic> toJson() => {
        'supported_regions': supportedRegions,
        'supported_corridors':
            supportedCorridors.map((c) => c.toJson()).toList(),
        'trips': trips.map((trip) => trip.toJson()).toList(),
        'featured_trip': featuredTrip?.toJson(),
      };
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

  /// SPEC-17 decision 15: true when the server determined that a positive
  /// sponsored ranking contribution was applied to this result.
  final bool sponsoredBoostApplied;

  const VenueSearchResult({
    required this.venueId,
    required this.name,
    required this.description,
    required this.microLocation,
    required this.vibeTags,
    this.distanceKm,
    this.isSponsored = false,
    this.sponsoredBoostApplied = false,
  });

  factory VenueSearchResult.fromJson(Map<String, dynamic> j) => VenueSearchResult(
        venueId: j['venue_id'] as String,
        name: j['name'] as String,
        description: j['description'] as String? ?? '',
        microLocation: j['micro_location'] as String? ?? '',
        vibeTags: (j['vibe_tags'] as List?)?.cast<String>() ?? const [],
        distanceKm: (j['distance_km'] as num?)?.toDouble(),
        isSponsored: j['is_sponsored'] as bool? ?? false,
        sponsoredBoostApplied: j['sponsored_boost_applied'] as bool? ?? false,
      );
}
