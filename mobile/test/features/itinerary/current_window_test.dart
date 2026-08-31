import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/itinerary/current_window.dart';
import 'package:travel_buddy/offline/offline_database.dart';

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

  group('outcome eligibility', () {
    test('active pending node can record an outcome', () {
      final node = _node(start: DateTime.utc(2026, 8, 19, 10));
      expect(nodeCanRecordOutcome(node, now, null), isTrue);
      expect(nodeIsElapsed(node, now), isFalse);
    });

    test('elapsed pending node can record an outcome', () {
      final node = _node(start: DateTime.utc(2026, 8, 19, 8));
      expect(nodeCanRecordOutcome(node, now, null), isTrue);
      expect(nodeIsElapsed(node, now), isTrue);
    });

    test('future pending node cannot record an outcome', () {
      final node = _node(start: DateTime.utc(2026, 8, 19, 12));
      expect(nodeCanRecordOutcome(node, now, null), isFalse);
    });

    test('completed and skipped nodes cannot record an outcome', () {
      for (final status in [NodeStatus.completed, NodeStatus.skipped]) {
        final node = _node(
          start: DateTime.utc(2026, 8, 19, 10),
          status: status,
        );
        expect(nodeCanRecordOutcome(node, now, null), isFalse);
      }
    });

    test('locally recorded node cannot record another outcome', () {
      final node = _node(start: DateTime.utc(2026, 8, 19, 10));
      final outcome = NodeOutcome(
        outcome: NodeOutcome.visited,
        recordedAt: now,
      );
      expect(nodeCanRecordOutcome(node, now, outcome), isFalse);
    });
  });

  _nextMovableStopTests();
}

TripNode _movableNode({
  required String id,
  required DateTime start,
  int duration = 60,
  NodeStatus status = NodeStatus.pending,
  bool isLocked = false,
}) => TripNode(
      nodeId: id,
      venueName: 'Venue $id',
      scheduledStart: start,
      durationMinutes: duration,
      isLocked: isLocked,
      status: status,
      vibeTags: const [],
    );

void _nextMovableStopTests() {
  group('nextMovableStop', () {
    // Scenario: 09:00 (60m), 13:00 (60m), 17:00 (60m), now = 15:00
    // 09:00 window ends 10:00 (past), 13:00 ends 14:00 (past), 17:00 ends 18:00 (future)
    test('at 15:00, returns the 17:00 node (past windows skipped)', () {
      final now = DateTime.utc(2026, 8, 19, 15, 0);
      final nodes = [
        _movableNode(id: 'a', start: DateTime.utc(2026, 8, 19, 9, 0)),
        _movableNode(id: 'b', start: DateTime.utc(2026, 8, 19, 13, 0)),
        _movableNode(id: 'c', start: DateTime.utc(2026, 8, 19, 17, 0)),
      ];
      final target = nextMovableStop(nodes, now);
      expect(target, isNotNull);
      expect(target!.nodeId, 'c');
    });

    // Scenario: now = 09:30, 09:00 node window still open (ends 10:00)
    test('at 09:30, returns 09:00 node (window still open)', () {
      final now = DateTime.utc(2026, 8, 19, 9, 30);
      final nodes = [
        _movableNode(id: 'a', start: DateTime.utc(2026, 8, 19, 9, 0)),
        _movableNode(id: 'b', start: DateTime.utc(2026, 8, 19, 13, 0)),
        _movableNode(id: 'c', start: DateTime.utc(2026, 8, 19, 17, 0)),
      ];
      final target = nextMovableStop(nodes, now);
      expect(target, isNotNull);
      expect(target!.nodeId, 'a');
    });

    // Scenario: all windows already ended
    test('all windows ended returns null', () {
      final now = DateTime.utc(2026, 8, 19, 20, 0);
      final nodes = [
        _movableNode(id: 'a', start: DateTime.utc(2026, 8, 19, 9, 0)),
        _movableNode(id: 'b', start: DateTime.utc(2026, 8, 19, 13, 0)),
        _movableNode(id: 'c', start: DateTime.utc(2026, 8, 19, 17, 0)),
      ];
      final target = nextMovableStop(nodes, now);
      expect(target, isNull);
    });

    // Edge: locked nodes are skipped even if window is open
    test('locked node with open window is skipped', () {
      final now = DateTime.utc(2026, 8, 19, 9, 30);
      final nodes = [
        _movableNode(
          id: 'locked',
          start: DateTime.utc(2026, 8, 19, 9, 0),
          isLocked: true,
        ),
        _movableNode(id: 'b', start: DateTime.utc(2026, 8, 19, 13, 0)),
      ];
      final target = nextMovableStop(nodes, now);
      expect(target, isNotNull);
      expect(target!.nodeId, 'b');
    });

    // Edge: skipped node is not a target
    test('skipped node is not a target', () {
      final now = DateTime.utc(2026, 8, 19, 9, 30);
      final nodes = [
        _movableNode(
          id: 'skipped',
          start: DateTime.utc(2026, 8, 19, 9, 0),
          status: NodeStatus.skipped,
        ),
        _movableNode(id: 'b', start: DateTime.utc(2026, 8, 19, 13, 0)),
      ];
      final target = nextMovableStop(nodes, now);
      expect(target, isNotNull);
      expect(target!.nodeId, 'b');
    });

    test('locally acknowledged active node is excluded', () {
      final now = DateTime.utc(2026, 8, 19, 9, 30);
      final nodes = [
        _movableNode(id: 'active', start: DateTime.utc(2026, 8, 19, 9)),
        _movableNode(id: 'next', start: DateTime.utc(2026, 8, 19, 13)),
      ];

      final target = nextMovableStop(
        nodes,
        now,
        excludedNodeIds: {'active'},
      );

      expect(target?.nodeId, 'next');
    });
  });
}
