import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';

class MockTripRepository extends Mock implements TripRepository {}

TripState _trip(List<TripNode> nodes) =>
    TripState(tripId: 't1', userId: 'u1', nodes: nodes);

TripNode _node(String id, String name) => TripNode(
      nodeId: id,
      venueName: name,
      scheduledStart: DateTime(2026, 8, 5, 9),
      durationMinutes: 90,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
    );

void main() {
  setUpAll(() {
    registerFallbackValue(EventType.askInfo);
  });

  late MockTripRepository repo;
  late ProviderContainer container;

  setUp(() {
    repo = MockTripRepository();
    // Initial load for the controller's constructor.
    when(() => repo.getTrip('t1'))
        .thenAnswer((_) async => _trip([_node('n1', 'Old')]));
    container = ProviderContainer(
      overrides: [tripRepoProvider.overrideWithValue(repo)],
    );
    addTearDown(container.dispose);
  });

  Future<ItineraryController> ready() async {
    final c = container.read(itineraryControllerProvider('t1').notifier);
    // Wait for the constructor's load() to settle.
    await Future<void>.delayed(Duration.zero);
    return c;
  }

  test('loads nodes on init', () async {
    await ready();
    final s = container.read(itineraryControllerProvider('t1'));
    expect(s.loading, false);
    expect(s.nodes.single.venueName, 'Old');
  });

  test('successful event replaces nodes and extracts Heads up banner', () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenAnswer((_) async => TripEventResult(
          message: 'Swapped. Heads up: New venue closes early.',
          updatedNodes: [_node('n1', 'New')],
          routingTier: 'heavy',
          fromCache: false,
        ));

    final c = await ready();
    final result = await c.applyEvent(
        type: EventType.swapActivity, message: 'swap', targetNodeId: 'n1');

    final s = container.read(itineraryControllerProvider('t1'));
    expect(result, isNotNull);
    expect(s.nodes.single.venueName, 'New');
    expect(s.banner, startsWith('Heads up:'));
    expect(s.processing, false);
  });

  test('reroute limit sets flag and returns null (no crash, no node change)',
      () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenThrow(const RerouteLimitException());

    final c = await ready();
    final result = await c.applyEvent(
        type: EventType.reroute, message: 'reroute everything');

    final s = container.read(itineraryControllerProvider('t1'));
    expect(result, isNull);
    expect(s.rerouteLimitHit, true);
    expect(s.nodes.single.venueName, 'Old'); // unchanged
  });

  test('generic error surfaces a banner, keeps nodes', () async {
    when(() => repo.sendEvent(
          tripId: any(named: 'tripId'),
          type: any(named: 'type'),
          message: any(named: 'message'),
          targetNodeId: any(named: 'targetNodeId'),
          preferences: any(named: 'preferences'),
        )).thenThrow(const ServerException());

    final c = await ready();
    await c.applyEvent(type: EventType.askInfo, message: 'hi');

    final s = container.read(itineraryControllerProvider('t1'));
    expect(s.banner, isNotNull);
    expect(s.nodes.single.venueName, 'Old');
  });

  test('load error populates error state', () async {
    when(() => repo.getTrip('t2')).thenThrow(const NetworkException());
    final c = container.read(itineraryControllerProvider('t2').notifier);
    await Future<void>.delayed(Duration.zero);
    final s = container.read(itineraryControllerProvider('t2'));
    expect(s.error, isA<NetworkException>());
    expect(s.loading, false);
  });
}
