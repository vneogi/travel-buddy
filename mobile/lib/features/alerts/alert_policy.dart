// SPEC-45 Phase B defects 1 + 5: advisory flood cap and schedule filter.
//
// Public helpers so tests can exercise the same code paths the
// ItineraryAlertsSection and _ScheduleWarningsBanner use.

import '../../core/destination_tz.dart';
import '../../data/context_alert.dart';
import '../../data/models.dart';
import '../itinerary/warning_helpers.dart';

/// Maximum visible alert cards on the primary surface.
const int maxVisibleAlerts = 2;

/// Severity sort rank -- lower is higher priority.
int _severityRank(String severity) {
  switch (severity) {
    case 'warning':
      return 0;
    case 'advisory':
      return 1;
    default:
      return 2;
  }
}

/// Two alerts are duplicates when they share the same alert_type
/// and affect the same destination-local date.
String _coalesceKey(ContextAlert alert, String? fallbackRegion) {
  final region = alert.geoRegion ?? fallbackRegion;
  final local = toDestinationLocal(alert.validFrom, region);
  return '${alert.alertType}|${local.year}-${local.month}-${local.day}';
}

/// Coalesce duplicate alerts for the same day + type, then sort by
/// severity (highest first), then by validFrom (earliest first).
///
/// Returns the full coalesced list -- call [cappedAlerts] to limit to
/// [maxVisibleAlerts].
List<ContextAlert> coalesceAlerts(
  List<ContextAlert> alerts, {
  String? fallbackRegion,
}) {
  final seen = <String>{};
  final deduped = <ContextAlert>[];
  // Sort by severity then validFrom before dedup so we keep the
  // highest-severity representative of each group.
  final sorted = List<ContextAlert>.from(alerts)
    ..sort((a, b) {
      final cmp = _severityRank(a.severity).compareTo(_severityRank(b.severity));
      if (cmp != 0) return cmp;
      return a.validFrom.compareTo(b.validFrom);
    });
  for (final alert in sorted) {
    final key = _coalesceKey(alert, fallbackRegion);
    if (seen.add(key)) {
      deduped.add(alert);
    }
  }
  return deduped;
}

/// Return at most [maxVisibleAlerts] alerts and the overflow count.
({List<ContextAlert> visible, int overflowCount}) cappedAlerts(
  List<ContextAlert> coalesced,
) {
  if (coalesced.length <= maxVisibleAlerts) {
    return (visible: coalesced, overflowCount: 0);
  }
  return (
    visible: coalesced.sublist(0, maxVisibleAlerts),
    overflowCount: coalesced.length - maxVisibleAlerts,
  );
}

/// Filter schedule warnings to only those whose matched node falls on
/// the current destination-local date.
///
/// [now] is injected for testability.
List<String> todayScheduleWarnings(
  List<String> warnings,
  List<TripNode> nodes,
  DateTime now,
) {
  return warnings.where((w) {
    final matched = matchWarningToNode(w, nodes);
    if (matched == null) return false; // unmatched: exclude from Today
    final nodeLocal = toDestinationLocal(matched.scheduledStart, matched.geoRegion);
    final nowLocal = toDestinationLocal(now, matched.geoRegion);
    return nodeLocal.year == nowLocal.year &&
        nodeLocal.month == nowLocal.month &&
        nodeLocal.day == nowLocal.day;
  }).toList();
}
