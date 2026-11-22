// SPEC-25 trip-optional Ask (slice 2, Flutter entry).
// Written without a local Flutter SDK; CI is the first compile and run.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/connectivity_helper.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/region_defaults.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/ask/trip_optional_ask_screen.dart';
import 'package:travel_buddy/features/chat/ask_bubble.dart';
import 'package:travel_buddy/features/chat/ask_entry_bar.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/features/home/home_screen.dart';

class _FakeConnectivity extends ConnectivityHelper {
  final bool online;
  _FakeConnectivity(this.online);

  @override
  Future<bool> checkConnectivity() async => online;
}

AskResponse _response({String answer = 'House of Wonders is a palace.', String? fallbackReason}) =>
    AskResponse.fromJson({
      'answer': answer,
      'tier': fallbackReason == null ? 'hedge' : 'refuse',
      'path': fallbackReason == null ? 'grounded_deterministic' : 'retrieval_miss',
      'intent': fallbackReason == null ? 'place_identity' : 'plan_change',
      'source_ids': fallbackReason == null ? ['znz-house-of-wonders'] : <String>[],
      'source_class': fallbackReason == null ? 'curated_catalog' : '',
      'from_cache': false,
      'fallback_reason': fallbackReason ?? '',
      'proposal': null,
      'food_disclaimer': null,
      'what_now': null,
    });

class _FakeRepo extends Fake implements TripRepository {
  final calls = <Map<String, String>>[];
  AskResponse reply;
  bool fail = false;
  _FakeRepo([AskResponse? reply]) : reply = reply ?? _response();

  @override
  Future<AskResponse> askWithoutTrip({
    required String question,
    required String geoRegion,
  }) async {
    calls.add({'question': question, 'geo_region': geoRegion});
    if (fail) throw Exception('server down');
    return reply;
  }
}

class _FakeApi extends Fake implements ApiClient {
  String? path;
  Object? body;

  @override
  Future<dynamic> post(String path, {Object? body}) async {
    this.path = path;
    this.body = body;
    return {
      'ask_response': {
        'answer': 'ok',
        'tier': 'hedge',
        'path': 'grounded_deterministic',
        'intent': 'place_identity',
        'source_ids': <String>[],
        'source_class': 'curated_catalog',
        'from_cache': false,
        'fallback_reason': '',
      },
    };
  }
}

TripSummary _trip(String id, String region, DateTime updatedAt) => TripSummary(
      tripId: id,
      geoRegion: region,
      nodeCount: 4,
      bookingCount: 0,
      updatedAt: updatedAt,
    );

const _regions = ['vientiane_laos', 'zanzibar_tanzania', 'nungwi_tanzania'];

HomeSnapshot _snapshot({List<TripSummary> trips = const [], FeaturedTrip? featured}) => HomeSnapshot(
      supportedRegions: _regions,
      trips: trips,
      featuredTrip: featured,
    );

Widget _app({
  required HomeSnapshot snapshot,
  required _FakeRepo repo,
  bool online = true,
  String initial = '/ask',
}) {
  final router = GoRouter(
    initialLocation: initial,
    routes: [
      GoRoute(path: '/', builder: (_, __) => const HomeScreen()),
      GoRoute(
        path: '/ask',
        builder: (_, __) => TripOptionalAskScreen(connectivityOverride: _FakeConnectivity(online)),
      ),
      GoRoute(
        path: '/trip/create',
        builder: (_, __) => const Scaffold(body: Text('create-trip-route')),
      ),
    ],
  );
  return ProviderScope(
    key: UniqueKey(),
    overrides: [
      homeSnapshotProvider.overrideWith((ref) async => snapshot),
      tripRepoProvider.overrideWithValue(repo),
    ],
    child: MaterialApp.router(routerConfig: router),
  );
}

void _tallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

Future<void> _ask(WidgetTester tester, String question) async {
  await tester.enterText(find.descendant(of: find.byType(AskEntryBar), matching: find.byType(TextField)), question);
  await tester.pumpAndSettle();
  await tester.tap(find.byTooltip('Send'));
  await tester.pumpAndSettle();
}

Future<void> _pickRegion(WidgetTester tester, String label) async {
  await tester.tap(find.byKey(const Key('ask_region_picker')));
  await tester.pumpAndSettle();
  await tester.tap(find.text(label).last);
  await tester.pumpAndSettle();
}

String? _pickerValue(WidgetTester tester) =>
    tester.widget<DropdownButton<String>>(find.byKey(const Key('ask_region_picker'))).value;

bool _barEnabled(WidgetTester tester) => tester.widget<AskEntryBar>(find.byType(AskEntryBar)).enabled;

void main() {
  testWidgets('Home shows home_ask_bar between featured and create; tap opens Ask', (tester) async {
    _tallSurface(tester);
    final snapshot = _snapshot(
      trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))],
      featured: FeaturedTrip(tripId: 't1', geoRegion: 'zanzibar_tanzania'),
    );
    await tester.pumpWidget(_app(snapshot: snapshot, repo: _FakeRepo(), initial: '/'));
    await tester.pumpAndSettle();
    final featured = tester.getTopLeft(find.byKey(const Key('featured_trip_card'))).dy;
    final ask = tester.getTopLeft(find.byKey(const Key('home_ask_bar'))).dy;
    final create = tester.getTopLeft(find.byKey(const Key('create_trip_card'))).dy;
    expect(featured, lessThan(ask));
    expect(ask, lessThan(create));
    expect(find.text('Ask about a place'), findsOneWidget);

    await tester.tap(find.byKey(const Key('home_ask_bar')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('ask_region_picker')), findsOneWidget);
    expect(find.text('Ask'), findsOneWidget);
  });

  testWidgets('default region is the latest-updated trip region', (tester) async {
    final snapshot = _snapshot(trips: [
      _trip('old', 'vientiane_laos', DateTime.utc(2026, 10, 1)),
      _trip('new', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20)),
    ]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: _FakeRepo()));
    await tester.pumpAndSettle();
    expect(_pickerValue(tester), 'zanzibar_tanzania');
    expect(find.text('Zanzibar'), findsOneWidget);
    expect(_barEnabled(tester), isTrue);
  });

  testWidgets('no trips: no default, bar disabled until a region is picked', (tester) async {
    await tester.pumpWidget(_app(snapshot: _snapshot(), repo: _FakeRepo()));
    await tester.pumpAndSettle();
    expect(_pickerValue(tester), isNull);
    expect(find.text('Pick a place first.'), findsOneWidget);
    expect(_barEnabled(tester), isFalse);

    await _pickRegion(tester, 'Nungwi (Zanzibar)');
    expect(_pickerValue(tester), 'nungwi_tanzania');
    expect(find.text('Pick a place first.'), findsNothing);
    expect(_barEnabled(tester), isTrue);
  });

  testWidgets('sending calls askWithoutTrip once with question and region, no trip_id', (tester) async {
    final repo = _FakeRepo();
    final snapshot = _snapshot(trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: repo));
    await tester.pumpAndSettle();
    await _ask(tester, 'What is the House of Wonders?');
    expect(repo.calls, [
      {'question': 'What is the House of Wonders?', 'geo_region': 'zanzibar_tanzania'},
    ]);
    expect(find.text('What is the House of Wonders?'), findsOneWidget);

    // The repository body itself never carries a trip_id.
    final api = _FakeApi();
    await TripRepository(api).askWithoutTrip(question: 'Q', geoRegion: 'zanzibar_tanzania');
    expect(api.path, '/ask');
    expect(api.body, {'question': 'Q', 'geo_region': 'zanzibar_tanzania'});
    expect((api.body as Map).containsKey('trip_id'), isFalse);
  });

  testWidgets('answer renders through the Ask fact widget with its source caption', (tester) async {
    final snapshot = _snapshot(trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: _FakeRepo()));
    await tester.pumpAndSettle();
    await _ask(tester, 'What is the House of Wonders building?');
    expect(find.byType(AskBubble), findsOneWidget);
    expect(find.byKey(const Key('ask_fact_view')), findsOneWidget);
    expect(find.text('House of Wonders is a palace.'), findsOneWidget);
    expect(find.text('curated_catalog'), findsOneWidget);
    expect(find.byKey(const Key('ask_start_trip')), findsNothing);
  });

  testWidgets('no_trip answer shows Start a trip, which opens /trip/create', (tester) async {
    final repo = _FakeRepo(_response(answer: 'That question is about a trip plan.', fallbackReason: 'no_trip'));
    final snapshot = _snapshot(trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: repo));
    await tester.pumpAndSettle();
    await _ask(tester, 'Can you swap my next stop?');
    expect(find.text('That question is about a trip plan.'), findsOneWidget);
    expect(find.byKey(const Key('ask_start_trip')), findsOneWidget);

    await tester.tap(find.byKey(const Key('ask_start_trip')));
    await tester.pumpAndSettle();
    expect(find.text('create-trip-route'), findsOneWidget);
  });

  testWidgets('offline: shows the offline refusal and never calls the repository', (tester) async {
    final repo = _FakeRepo();
    final snapshot = _snapshot(trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: repo, online: false));
    await tester.pumpAndSettle();
    await _ask(tester, 'What is the House of Wonders now?');
    expect(find.byKey(const Key('ask_offline_refuse')), findsOneWidget);
    expect(find.text('Not available offline'), findsOneWidget);
    expect(repo.calls, isEmpty);
  });

  testWidgets('repository error shows one error line and the bar stays enabled', (tester) async {
    final repo = _FakeRepo()..fail = true;
    final snapshot = _snapshot(trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: repo));
    await tester.pumpAndSettle();
    await _ask(tester, 'Is the House of Wonders open?');
    expect(find.byKey(const Key('ask_error')), findsOneWidget);
    expect(_barEnabled(tester), isTrue);
  });

  testWidgets('changing the region sends the new region', (tester) async {
    final repo = _FakeRepo();
    final snapshot = _snapshot(trips: [_trip('t1', 'zanzibar_tanzania', DateTime.utc(2026, 11, 20))]);
    await tester.pumpWidget(_app(snapshot: snapshot, repo: repo));
    await tester.pumpAndSettle();
    await _ask(tester, 'First question?');
    await _pickRegion(tester, 'Vientiane');
    await _ask(tester, 'Second question?');
    expect(repo.calls.map((c) => c['geo_region']).toList(), ['zanzibar_tanzania', 'vientiane_laos']);
  });

  test('regionDisplayName maps all six codes and falls back for unknown', () {
    expect(regionDisplayName('dubai_uae'), 'Dubai');
    expect(regionDisplayName('luang_prabang_laos'), 'Luang Prabang');
    expect(regionDisplayName('vang_vieng_laos'), 'Vang Vieng');
    expect(regionDisplayName('vientiane_laos'), 'Vientiane');
    expect(regionDisplayName('zanzibar_tanzania'), 'Zanzibar');
    expect(regionDisplayName('nungwi_tanzania'), 'Nungwi (Zanzibar)');
    expect(regionDisplayName('mars_base'), 'mars_base');
  });
}
