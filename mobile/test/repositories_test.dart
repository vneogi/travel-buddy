import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';

class MockApiClient extends Mock implements ApiClient {}

void main() {
  late MockApiClient api;
  late TripRepository trips;

  setUp(() {
    api = MockApiClient();
    trips = TripRepository(api);
  });

  test('getTrip hits /trip/{id} and parses state', () async {
    when(() => api.get('/trip/t1')).thenAnswer((_) async => {
          'trip_id': 't1',
          'user_id': 'u1',
          'current_context': {'mood': 'relaxed'},
          'nodes': [
            {
              'node_id': 'n1',
              'venue_name': 'A',
              'scheduled_start': '2026-08-05T09:00:00',
            }
          ],
        });
    final state = await trips.getTrip('t1');
    expect(state.tripId, 't1');
    expect(state.nodes.single.venueName, 'A');
    verify(() => api.get('/trip/t1')).called(1);
  });

  test('sendEvent posts correct body shape', () async {
    when(() => api.post('/trip/event', body: any(named: 'body')))
        .thenAnswer((_) async => {
              'message': 'ok',
              'updated_nodes': [],
              'routing_tier_used': 'light',
              'from_cache': true,
              'reroutes_remaining': 5,
            });

    await trips.sendEvent(
      tripId: 't1',
      type: EventType.swapActivity,
      message: 'swap it',
      targetNodeId: 'n1',
      preferences: {'vibe_tags': ['artistic']},
    );

    final captured = verify(() => api.post('/trip/event',
        body: captureAny(named: 'body'))).captured.single as Map;
    expect(captured['trip_id'], 't1');
    expect(captured['event_type'], 'swap_activity'); // wire value, not enum name
    expect(captured['target_node_id'], 'n1');
    expect(captured['preferences'], {'vibe_tags': ['artistic']});
  });

  test('searchVenues uses `query` param (not `q`) and reads results[]', () async {
    when(() => api.get('/venues/search', query: any(named: 'query')))
        .thenAnswer((_) async => {
              'query': 'cafe',
              'results_count': 1,
              'results': [
                {
                  'venue_id': 'v1',
                  'name': 'Espresso Lab',
                  'description': 'quiet',
                  'micro_location': 'Business Bay',
                  'vibe_tags': ['leisurely'],
                }
              ],
            });

    final results = await trips.searchVenues(query: 'cafe');
    expect(results.single.name, 'Espresso Lab');

    final q = verify(() => api.get('/venues/search',
        query: captureAny(named: 'query'))).captured.single as Map;
    expect(q['query'], 'cafe'); // regression guard: must be `query`, not `q`
  });
}
