import '../../core/destination_tz.dart';
import '../../data/models.dart';
import '../../offline/offline_database.dart';

const skipReasonLabels = {
  'too_far': 'Too far away',
  'too_tired': 'Too tired',
  'closed': 'Place is closed',
  'crowded': 'Too crowded',
  'not_interested': 'Not interested',
  'ran_out_of_time': 'Ran out of time',
  'weather': 'Bad weather',
};

/// True when the node's time window contains [now] and it has not been
/// skipped or completed.
///
/// This drives the NOW badge and visited-confirm button. The server does
/// not stamp NodeStatus.active; client-side window check is sufficient
/// for October.
bool nodeIsCurrentWindow(TripNode node, DateTime now) {
  if (node.status == NodeStatus.completed || node.status == NodeStatus.skipped) {
    return false;
  }
  final end = node.scheduledStart.add(Duration(minutes: node.durationMinutes));
  return !now.isBefore(node.scheduledStart) && now.isBefore(end);
}

bool nodeIsElapsed(TripNode node, DateTime now) {
  final end = node.scheduledStart.add(Duration(minutes: node.durationMinutes));
  return !now.isBefore(end);
}

/// True when an outcome prompt should appear on the primary Today surface.
///
/// Conditions:
/// - Node is pending, no outcome recorded yet.
/// - Node's scheduled start is in the past (or current window).
/// - Node's destination-local date is **today** (SPEC-45 B2).
///
/// Past-day nodes are still recordable from their day section; they just
/// must not flood Today.
bool nodeCanRecordOutcome(
  TripNode node,
  DateTime now,
  NodeOutcome? recordedOutcome,
) {
  if (node.status != NodeStatus.pending) return false;
  if (recordedOutcome != null) return false;
  if (now.isBefore(node.scheduledStart)) return false;
  // SPEC-45 B2: destination-local date must be today.
  final nodeLocal = toDestinationLocal(node.scheduledStart, node.geoRegion);
  final nowLocal = toDestinationLocal(now, node.geoRegion);
  return nodeLocal.year == nowLocal.year &&
      nodeLocal.month == nowLocal.month &&
      nodeLocal.day == nowLocal.day;
}

/// Kind-specific outcome prompt copy (SPEC-45 B2).
///
/// - flight: "Arrived in [city]?" (or "Arrived?" if city unknown)
/// - hotel first night: "Checked in?"
/// - hotel checkout / last night: "Checked out?"
/// - tour: "Did the tour happen?"
/// - else: "Did you visit?"
String outcomePromptText(TripNode node, {bool isLastHotelNight = false}) {
  if (node.nodeKind == 'booking' && node.bookingType == 'flight') {
    final city = node.venueName.isNotEmpty ? node.venueName : null;
    return city != null ? 'Arrived in $city?' : 'Arrived?';
  }
  if (node.nodeKind == 'booking' && node.bookingType == 'hotel') {
    return isLastHotelNight ? 'Checked out?' : 'Checked in?';
  }
  if (node.nodeKind == 'booking' && node.bookingType == 'tour') {
    return 'Did the tour happen?';
  }
  return 'Did you visit?';
}

/// Returns the first unlocked pending node whose time window has not ended,
/// or null if no such node exists.
///
/// A node whose window contains [now] (currently in progress) IS a valid
/// target.  A node whose entire window is in the past is not.
///
/// [now] is injected for testability -- callers pass DateTime.now().toUtc().
TripNode? nextMovableStop(
  List<TripNode> nodes,
  DateTime now, {
  Set<String> excludedNodeIds = const {},
}) {
  for (final node in nodes) {
    if (node.status != NodeStatus.pending) continue;
    if (node.isLocked) continue;
    if (excludedNodeIds.contains(node.nodeId)) continue;
    final end = node.scheduledStart.add(Duration(minutes: node.durationMinutes));
    if (now.isBefore(end)) return node;
  }
  return null;
}
