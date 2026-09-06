/// SPEC-35 Phase A2: Dart models for GET /api/v1/trip/{trip_id}/notifications.
///
/// Typed response models mirroring the backend PR #50 schema.
/// Do not invent traffic or rain copy client-side.

class RouteEvidence {
  final String source;
  final DateTime observedAt;
  final int? normalDurationMinutes;
  final int trafficDurationMinutes;
  final String mode;
  final String originBasis;

  const RouteEvidence({
    required this.source,
    required this.observedAt,
    this.normalDurationMinutes,
    required this.trafficDurationMinutes,
    required this.mode,
    required this.originBasis,
  });

  factory RouteEvidence.fromJson(Map<String, dynamic> j) => RouteEvidence(
        source: j['source'] as String,
        observedAt: DateTime.parse(j['observed_at'] as String),
        normalDurationMinutes: (j['normal_duration_minutes'] as num?)?.toInt(),
        trafficDurationMinutes: (j['traffic_duration_minutes'] as num).toInt(),
        mode: j['mode'] as String,
        originBasis: j['origin_basis'] as String,
      );
}

class WeatherEvidence {
  final String source;
  final DateTime observedAt;
  final double rainProbability;

  const WeatherEvidence({
    required this.source,
    required this.observedAt,
    required this.rainProbability,
  });

  factory WeatherEvidence.fromJson(Map<String, dynamic> j) => WeatherEvidence(
        source: j['source'] as String,
        observedAt: DateTime.parse(j['observed_at'] as String),
        rainProbability: (j['rain_probability'] as num).toDouble(),
      );
}

class PolicyBuffers {
  final int arrivalBufferMinutes;
  final int weatherBufferMinutes;

  const PolicyBuffers({
    required this.arrivalBufferMinutes,
    required this.weatherBufferMinutes,
  });

  factory PolicyBuffers.fromJson(Map<String, dynamic> j) => PolicyBuffers(
        arrivalBufferMinutes: (j['arrival_buffer_minutes'] as num).toInt(),
        weatherBufferMinutes: (j['weather_buffer_minutes'] as num).toInt(),
      );
}

class DepartureEvidence {
  final RouteEvidence? route;
  final WeatherEvidence? weather;
  final PolicyBuffers policy;

  const DepartureEvidence({
    this.route,
    this.weather,
    required this.policy,
  });

  factory DepartureEvidence.fromJson(Map<String, dynamic> j) =>
      DepartureEvidence(
        route: j['route'] != null
            ? RouteEvidence.fromJson(j['route'] as Map<String, dynamic>)
            : null,
        weather: j['weather'] != null
            ? WeatherEvidence.fromJson(j['weather'] as Map<String, dynamic>)
            : null,
        policy:
            PolicyBuffers.fromJson(j['policy'] as Map<String, dynamic>),
      );
}

class NotificationCandidate {
  final String notificationId;
  final String type;
  final String priority;
  final String nodeId;
  final String title;
  final String message;
  final DateTime eligibleAt;
  final DateTime expiresAt;
  final DateTime? recommendedDepartureAt;
  final String? timeZone;
  final String deepLink;
  final DepartureEvidence evidence;

  const NotificationCandidate({
    required this.notificationId,
    required this.type,
    required this.priority,
    required this.nodeId,
    required this.title,
    required this.message,
    required this.eligibleAt,
    required this.expiresAt,
    this.recommendedDepartureAt,
    this.timeZone,
    required this.deepLink,
    required this.evidence,
  });

  factory NotificationCandidate.fromJson(Map<String, dynamic> j) =>
      NotificationCandidate(
        notificationId: j['notification_id'] as String,
        type: j['type'] as String,
        priority: j['priority'] as String,
        nodeId: j['node_id'] as String,
        title: j['title'] as String,
        message: j['message'] as String,
        eligibleAt: DateTime.parse(j['eligible_at'] as String),
        expiresAt: DateTime.parse(j['expires_at'] as String),
        recommendedDepartureAt: j['recommended_departure_at'] != null
            ? DateTime.parse(j['recommended_departure_at'] as String)
            : null,
        timeZone: j['time_zone'] as String?,
        deepLink: j['deep_link'] as String,
        evidence: DepartureEvidence.fromJson(
            j['evidence'] as Map<String, dynamic>),
      );

  bool get isExpired => DateTime.now().toUtc().isAfter(expiresAt);
}

class TripNotificationsResponse {
  final String tripId;
  final DateTime refreshedAt;
  final String status;
  final List<NotificationCandidate> notifications;

  const TripNotificationsResponse({
    required this.tripId,
    required this.refreshedAt,
    required this.status,
    required this.notifications,
  });

  factory TripNotificationsResponse.fromJson(Map<String, dynamic> j) =>
      TripNotificationsResponse(
        tripId: j['trip_id'] as String,
        refreshedAt: DateTime.parse(j['refreshed_at'] as String),
        status: j['status'] as String,
        notifications: (j['notifications'] as List)
            .map((e) =>
                NotificationCandidate.fromJson(e as Map<String, dynamic>))
            .toList(),
      );
}
