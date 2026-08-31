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

bool nodeCanRecordOutcome(
  TripNode node,
  DateTime now,
  NodeOutcome? recordedOutcome,
) {
  if (node.status != NodeStatus.pending) return false;
  if (recordedOutcome != null) return false;
  return !now.isBefore(node.scheduledStart);
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
