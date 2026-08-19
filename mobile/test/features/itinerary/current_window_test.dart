import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/current_window.dart';

TripNode _node({
  required DateTime start,
  int duration = 90,
  NodeStatus status = NodeStatus.pending,
}) => TripNode(
      nodeId: 'n1',
      venueName: 'Test Venue',
      scheduledStart: start,
      durationMinutes: duration,
      isLocked: false,
      status: status,
      vibeTags: const [],
    );

void main() {
  // now = 10:30 UTC
  final now = DateTime.utc(2026, 8, 19, 10, 30);

  group('nodeIsCurrentWindow', () {
    test('node 10:00 for 90 minutes contains 10:30 -> true', () {
      final node = _node(start: DateTime.utc(2026, 8, 19, 10, 0));
      expect(nodeIsCurrentWindow(node, now), isTrue);
    });

    test('node 12:00 does not contain 10:30 -> false', () {
      final node = _node(start: DateTime.utc(2026, 8, 19, 12, 0));
      expect(nodeIsCurrentWindow(node, now), isFalse);
    });

    test('skipped node in window -> false', () {
      final node = _node(
        start: DateTime.utc(2026, 8, 19, 10, 0),
        status: NodeStatus.skipped,
      );
      expect(nodeIsCurrentWindow(node, now), isFalse);
    });

    test('completed node in window -> false', () {
      final node = _node(
        start: DateTime.utc(2026, 8, 19, 10, 0),
        status: NodeStatus.completed,
      );
      expect(nodeIsCurrentWindow(node, now), isFalse);
    });

    test('node that ended exactly at now -> false (exclusive end)', () {
      // start 09:00, duration 90min -> end 10:30 == now -> false
      final node = _node(start: DateTime.utc(2026, 8, 19, 9, 0));
      expect(nodeIsCurrentWindow(node, now), isFalse);
    });
  });
}
