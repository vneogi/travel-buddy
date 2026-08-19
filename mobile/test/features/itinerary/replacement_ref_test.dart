import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/replacement_ref.dart';

TripNode _node(String nodeId, String venueName, {String? venueId}) => TripNode(
      nodeId: nodeId,
      venueName: venueName,
      venueId: venueId,
      scheduledStart: DateTime(2026, 8, 19, 10, 0),
      durationMinutes: 90,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

void main() {
  group('replacementRefForSwap', () {
    test('picks the same node_id with a new venue', () {
      // Fixture: n1 swapped from old_venue to new_venue.
      // n2 is a sibling with a different nodeId.
      final updated = [
        _node('n1', 'new_venue'),
        _node('n2', 'other_venue'),
      ];
      final result = replacementRefForSwap(
        originalNodeId: 'n1',
        originalVenueKey: 'old_venue',
        updatedNodes: updated,
      );
      expect(result, equals('new_venue'));
    });

    test('returns unknown when node_id not found', () {
      final updated = [_node('n2', 'other_venue')];
      final result = replacementRefForSwap(
        originalNodeId: 'n1',
        originalVenueKey: 'old_venue',
        updatedNodes: updated,
      );
      expect(result, equals('unknown'));
    });

    test('returns unknown when venue did not change', () {
      final updated = [_node('n1', 'old_venue')];
      final result = replacementRefForSwap(
        originalNodeId: 'n1',
        originalVenueKey: 'old_venue',
        updatedNodes: updated,
      );
      expect(result, equals('unknown'));
    });

    test('uses venueId over venueName when present', () {
      final updated = [_node('n1', 'display_name', venueId: 'new_id')];
      final result = replacementRefForSwap(
        originalNodeId: 'n1',
        originalVenueKey: 'old_id',
        updatedNodes: updated,
      );
      expect(result, equals('new_id'));
    });
  });
}
