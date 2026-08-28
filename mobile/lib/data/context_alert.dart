/// SPEC-29: Structured context alert from the backend.
class AlertEvidence {
  final double? rainProbability;
  final double? tempC;
  final double? feelsLikeC;
  final int? humidity;
  final int? conditionCode;

  const AlertEvidence({
    this.rainProbability,
    this.tempC,
    this.feelsLikeC,
    this.humidity,
    this.conditionCode,
  });

  factory AlertEvidence.fromJson(Map<String, dynamic> j) => AlertEvidence(
        rainProbability: (j['rain_probability'] as num?)?.toDouble(),
        tempC: (j['temp_c'] as num?)?.toDouble(),
        feelsLikeC: (j['feels_like_c'] as num?)?.toDouble(),
        humidity: (j['humidity'] as num?)?.toInt(),
        conditionCode: (j['condition_code'] as num?)?.toInt(),
      );
}

class ContextAlert {
  final String alertId;
  final String alertType;
  final String severity;
  final String message;
  final List<String> affectedNodeIds;
  final List<String> affectedNodeNames;
  final String source;
  final DateTime sourceUpdatedAt;
  final DateTime validFrom;
  final DateTime validUntil;
  final DateTime expiresAt;
  final String locationBasis;
  final String? geoRegion;
  final AlertEvidence evidence;
  final String? suggestedAction;
  final bool autoApplied;

  const ContextAlert({
    required this.alertId,
    required this.alertType,
    required this.severity,
    required this.message,
    required this.affectedNodeIds,
    required this.affectedNodeNames,
    required this.source,
    required this.sourceUpdatedAt,
    required this.validFrom,
    required this.validUntil,
    required this.expiresAt,
    required this.locationBasis,
    this.geoRegion,
    required this.evidence,
    this.suggestedAction,
    this.autoApplied = false,
  });

  factory ContextAlert.fromJson(Map<String, dynamic> j) => ContextAlert(
        alertId: j['alert_id'] as String,
        alertType: j['alert_type'] as String,
        severity: j['severity'] as String,
        message: j['message'] as String,
        affectedNodeIds:
            (j['affected_node_ids'] as List).cast<String>(),
        affectedNodeNames:
            (j['affected_node_names'] as List).cast<String>(),
        source: j['source'] as String,
        sourceUpdatedAt: DateTime.parse(j['source_updated_at'] as String),
        validFrom: DateTime.parse(j['valid_from'] as String),
        validUntil: DateTime.parse(j['valid_until'] as String),
        expiresAt: DateTime.parse(j['expires_at'] as String),
        locationBasis: j['location_basis'] as String,
        geoRegion: j['geo_region'] as String?,
        evidence:
            AlertEvidence.fromJson(j['evidence'] as Map<String, dynamic>),
        suggestedAction: j['suggested_action'] as String?,
        autoApplied: j['auto_applied'] as bool? ?? false,
      );

  bool get isExpired => DateTime.now().toUtc().isAfter(expiresAt);
}

class TripAlertsResponse {
  final String tripId;
  final String status;
  final List<ContextAlert> alerts;
  final DateTime refreshedAt;

  const TripAlertsResponse({
    required this.tripId,
    required this.status,
    required this.alerts,
    required this.refreshedAt,
  });

  factory TripAlertsResponse.fromJson(Map<String, dynamic> j) =>
      TripAlertsResponse(
        tripId: j['trip_id'] as String,
        status: j['status'] as String,
        alerts: (j['alerts'] as List)
            .map((e) => ContextAlert.fromJson(e as Map<String, dynamic>))
            .toList(),
        refreshedAt: DateTime.parse(j['refreshed_at'] as String),
      );
}
