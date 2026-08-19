import '../../data/models.dart';

/// Identifies which venue replaced the original after a swap.
///
/// The server keeps node_id stable across swaps (SPEC-16). The replacement
/// is the node whose nodeId == originalNodeId but whose venue key differs.
String replacementRefForSwap({
  required String originalNodeId,
  required String originalVenueKey,
  required List<TripNode> updatedNodes,
}) {
  for (final n in updatedNodes) {
    if (n.nodeId == originalNodeId) {
      final key = n.venueId ?? n.venueName;
      if (key != originalVenueKey) return key;
    }
  }
  return 'unknown';
}
