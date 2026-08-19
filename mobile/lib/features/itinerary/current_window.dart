import '../../data/models.dart';

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
