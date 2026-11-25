// SPEC-58 slice 1b: paste-your-plan import (Flutter).
//
// Harness: a fake ApiClient records every request (method, path, body) and a
// real TripRepository sits on top of it. No database FFI, no timers on the
// screen; time advances with bounded timed pumps (no pumpAndSettle).

import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/connectivity_helper.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/activity_detail/activity_detail_screen.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/paste_plan/paste_plan_screen.dart';
import 'package:travel_buddy/features/paste_plan/plan_parser.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';

const _geo = 'zanzibar_tanzania';
const _fixtures = 'test/fixtures/spec58';
const _start = '2026-12-27';
const _end = '2026-12-29';

String _fixture(String name) => File('$_fixtures/$name').readAsStringSync();

class _FakeConnectivity extends ConnectivityHelper {
  final bool online;
  _FakeConnectivity({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

class _Call {
  final String method;
  final String path;
  final Object? body;
  _Call(this.method, this.path, this.body);
}

/// Records every request. Catalog match: names in [matched] get a match.
class _FakeApi extends Fake implements ApiClient {
  final calls = <_Call>[];
  Set<String> matched = {'Forodhani Gardens', 'House of Wonders'};
  Object? eventError;
  List<Map<String, dynamic>>? importResults;

  List<_Call> posts(String path) =>
      calls.where((c) => c.method == 'POST' && c.path == path).toList();

  static Map<String, dynamic> venue(String name) => {
        'venue_id': 'znz-${name.toLowerCase().replaceAll(' ', '-')}',
        'name': name,
        'geo_region': _geo,
        'provenance': 'curated_catalog',
      };

  @override
  Future<dynamic> post(String path, {Object? body}) async {
    calls.add(_Call('POST', path, body));
    switch (path) {
      case '/trip/catalog_match':
        final names = ((body as Map)['names'] as List).cast<String>();
        return {
          'results': [
            for (final n in names)
              {'name': n, 'match': matched.contains(n) ? venue(n) : null, 'near': <Object>[]},
          ],
        };
      case '/trip/create':
        return {'trip_id': 'trip-new'};
      case '/trip/event':
        final err = eventError;
        if (err != null) throw err;
        final items = (((body as Map)['preferences'] as Map)['items'] as List);
        return {
          'message': 'ok',
          'updated_nodes': <Object>[],
          'import_results': importResults ??
              [
                for (var i = 0; i < items.length; i++)
                  {'index': i, 'status': 'added', 'node_id': 'n$i', 'code': null, 'message': null},
              ],
        };
    }
    throw StateError('unexpected POST $path');
  }

  @override
  Future<dynamic> get(String path, {Map<String, dynamic>? query}) async {
    calls.add(_Call('GET', path, query));
    if (path == '/trip/trip-new') {
      return {'trip_id': 'trip-new', 'user_id': 'u1', 'geo_region': _geo, 'nodes': <Object>[]};
    }
    throw StateError('unexpected GET $path');
  }
}

class _SheetDb implements OfflineDatabase {
  @override
  dynamic noSuchMethod(Invocation invocation) => Future<void>.value();
}

class _SheetSignals extends Fake implements SignalService {}

class _SheetController extends StateNotifier<ItineraryState>
    implements ItineraryController {
  _SheetController() : super(const ItineraryState());

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _settle(WidgetTester t) async {
  for (var i = 0; i < 12; i++) {
    await t.pump(const Duration(milliseconds: 50));
  }
}

Future<_FakeApi> _pump(WidgetTester tester, String text, {_FakeApi? api, bool online = true}) async {
  tester.view.physicalSize = const Size(1200, 9000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
  final fake = api ?? _FakeApi();
  await tester.pumpWidget(ProviderScope(
    key: UniqueKey(),
    overrides: [
      tripRepoProvider.overrideWithValue(TripRepository(fake)),
      signalServiceProvider.overrideWithValue(_SheetSignals()),
      offlineDatabaseProvider.overrideWithValue(_SheetDb()),
      itineraryControllerProvider.overrideWith((ref, tripId) => _SheetController()),
    ],
    child: MaterialApp(
      home: PastePlanScreen(
        regions: const [_geo],
        initialRegion: _geo,
        initialStartDate: DateTime(2026, 12, 27),
        initialEndDate: DateTime(2026, 12, 29),
        initialText: text,
        connectivityOverride: _FakeConnectivity(online: online),
      ),
    ),
  ));
  await tester.pump();
  return fake;
}

Future<void> _tap(WidgetTester t, String key) async {
  final f = find.byKey(Key(key));
  await t.ensureVisible(f);
  await t.pump();
  await t.tap(f);
  await _settle(t);
}

bool _has(String key) => find.byKey(Key(key)).evaluate().isNotEmpty;

String _text(WidgetTester t, String key) => t.widget<Text>(find.byKey(Key(key))).data ?? '';

VoidCallback? _create(WidgetTester t) =>
    t.widget<ElevatedButton>(find.byKey(const Key('paste_plan_create'))).onPressed;

Future<void> _parseAndMatch(WidgetTester t) async {
  await _tap(t, 'paste_plan_parse');
  await _tap(t, 'paste_plan_match');
}

/// Makes rows ready: accept matches, 60 min for plain rows, morning when no slot.
Future<void> _readyRows(WidgetTester t, Iterable<int> rows) async {
  for (final i in rows) {
    if (_has('paste_plan_accept_$i')) await _tap(t, 'paste_plan_accept_$i');
    if (_has('paste_plan_dwell_${i}_60')) await _tap(t, 'paste_plan_dwell_${i}_60');
    if (_has('paste_plan_slot_${i}_morning_tour')) await _tap(t, 'paste_plan_slot_${i}_morning_tour');
  }
}

/// Pops every booking sheet the import opens (traveller skips each one).
Future<int> _skipSheets(WidgetTester t) async {
  var n = 0;
  while (find.byType(AddBookingSheet).evaluate().isNotEmpty && n < 10) {
    Navigator.of(t.element(find.byType(AddBookingSheet))).pop();
    await _settle(t);
    n++;
  }
  return n;
}

Map<String, dynamic> _prefs(_Call c) =>
    Map<String, dynamic>.from((c.body as Map)['preferences'] as Map);

TripNode _plainNode() => TripNode(
      nodeId: 'p1',
      venueName: 'Sunset jetty',
      scheduledStart: DateTime.utc(2026, 12, 27, 11),
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      placeSource: 'trip_private',
    );

TripNode _catalogNode() => TripNode(
      nodeId: 'c1',
      venueId: 'znz-forodhani-gardens',
      venueName: 'Forodhani Gardens',
      scheduledStart: DateTime.utc(2026, 12, 27, 6),
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      lat: -6.1622,
      lng: 39.1880,
    );

void main() {
  // -------------------------------------------------------------------------
  // Parser (pure)
  // -------------------------------------------------------------------------

  test('1. chatbot-style three-day paste matches the fixture output', () {
    final r = parsePlan(_fixture('chatbot_three_day.txt'), startDate: _start, endDate: _end);
    expect(r.isRefused, isFalse);
    expect(r.toJson(), jsonDecode(_fixture('chatbot_three_day.expected.json')));
  });

  test('2. agent-style paste routes flight and hotel lines to bookingLines', () {
    final r = parsePlan(_fixture('agent_with_bookings.txt'), startDate: _start, endDate: _end);
    expect(r.bookingLines, [
      'Flight EK 725 Dubai to Zanzibar, 27 Dec 10:40',
      'Hotel check-in: Emerson Spice, 27 Dec 14:00',
      'Booking ref: ZX81KD',
      'Check-out 29 Dec 11:00',
    ]);
    expect([for (final d in r.days) d.date], ['2026-12-27', '2026-12-28']);
    expect([for (final s in r.days[0].stops) s.name], ['Stone Town walking tour', 'Lukmaan Restaurant']);
    expect([for (final s in r.days[1].stops) s.name], ['Mnarani Turtle Sanctuary']);
    final names = [for (final d in r.days) for (final s in d.stops) s.name.toLowerCase()];
    expect(names.any((n) => n.contains('flight') || n.contains('hotel') || n.contains('check')), isFalse);
  });

  test('3. blog-style paste puts bad lines in notUnderstood and keeps valid stops', () {
    final r = parsePlan(_fixture('blog_with_bad_lines.txt'), startDate: _start, endDate: _end);
    expect(r.notUnderstood, [
      'Our favourite Stone Town day:',
      '- http://example.com/our-blog-post',
      '- Tips:',
      '- We loved every single minute of this wonderful place honestly',
      'Day 9',
    ]);
    expect(r.days.first.date, '2026-12-29'); // weekday-plus-date heading
    expect([for (final s in r.days.first.stops) s.name], ['Darajani Market', 'Jozani Forest']);
    expect(r.days.first.stops[0].note, 'go early, it gets hot');
    expect(r.days.first.stops[1].note, 'red colobus monkeys');
    // A heading outside the span is never silently mapped to a trip date.
    expect(r.days.last.date, isNull);
    expect([for (final s in r.days.last.stops) s.name], ['Spice farm tour']);
  });

  test('4. clock-time to slot hint boundaries', () {
    expect(slotForClockTime(10, 59), 'morning_tour');
    expect(slotForClockTime(11, 0), 'lunch');
    expect(slotForClockTime(13, 59), 'lunch');
    expect(slotForClockTime(14, 0), 'afternoon_evening_tour');
    expect(slotForClockTime(16, 59), 'afternoon_evening_tour');
    expect(slotForClockTime(17, 0), 'dinner');
    final r = parsePlan(
      '- 10:59 Alpha place\n- 11:00 Bravo place\n- 1:59 pm Charlie place\n'
      '- 2pm Delta place\n- 16.59 Echo place\n- 5 pm Foxtrot place',
      startDate: _start,
      endDate: _end,
    );
    expect([for (final s in r.days.single.stops) s.slotHint], [
      'morning_tour', 'lunch', 'lunch', 'afternoon_evening_tour', 'afternoon_evening_tour', 'dinner',
    ]);
  });

  // -------------------------------------------------------------------------
  // Import screen
  // -------------------------------------------------------------------------

  testWidgets('5. empty, over-60-stop and over-14-day pastes are refused with no request',
      (tester) async {
    final over60 = [for (var i = 1; i <= 61; i++) '- Stop place $i'].join('\n');
    final over14 = [for (var i = 1; i <= 15; i++) 'Day $i\n- Place number $i'].join('\n');
    for (final (text, msg) in [
      ('   ', 'Paste a plan first.'),
      (over60, 'more than 60 stops'),
      (over14, 'more than 14 days'),
    ]) {
      final api = await _pump(tester, text);
      await _tap(tester, 'paste_plan_parse');
      expect(_text(tester, 'paste_plan_error'), contains(msg));
      expect(_has('paste_plan_match'), isFalse);
      expect(api.calls, isEmpty);
    }
  });

  testWidgets('6. catalog match sends only geo_region and names', (tester) async {
    final api = await _pump(tester, _fixture('chatbot_three_day.txt'));
    await _parseAndMatch(tester);
    final body = Map<String, dynamic>.from(api.posts('/trip/catalog_match').single.body as Map);
    expect(body.keys.toSet(), {'geo_region', 'names'});
    expect(body['geo_region'], _geo);
    expect(body['names'], [
      'Forodhani Gardens',
      'Lukmaan Restaurant',
      'House of Wonders',
      'Prison Island tour',
      'Forodhani Night Food Market',
      'Mnarani Turtle Sanctuary',
    ]);
  });

  testWidgets('7. raw paste, clock times, notes and booking lines appear in no request',
      (tester) async {
    final raw = '${_fixture('chatbot_three_day.txt')}Flight EK 725 to Zanzibar\n';
    final api = await _pump(tester, raw);
    await _parseAndMatch(tester);
    await _readyRows(tester, [0, 1, 2, 3, 4, 5]);
    await _tap(tester, 'paste_plan_create');
    expect(await _skipSheets(tester), 1);
    expect(api.posts('/trip/event'), hasLength(1));
    const forbidden = [
      'Here is your 3-day', 'sunrise stroll', 'try the biryani', 'Stone Town', 'Nungwi',
      '9:00 AM', '12:30', '3pm', '7:30', '19:30', '11am', '09:00', 'EK 725', 'Flight',
    ];
    for (final c in api.calls) {
      final encoded = jsonEncode(c.body);
      expect(encoded.contains(raw.trim()), isFalse, reason: c.path);
      for (final f in forbidden) {
        expect(encoded.contains(f), isFalse, reason: '$f in ${c.path}');
      }
    }
  });

  testWidgets('8. nothing is committed before Create trip; matches start unconfirmed',
      (tester) async {
    final api = await _pump(tester, _fixture('chatbot_three_day.txt'));
    await _parseAndMatch(tester);
    expect(_text(tester, 'paste_plan_status_0'), 'Not yet confirmed');
    expect(_text(tester, 'paste_plan_status_2'), 'Not yet confirmed');
    expect(_create(tester), isNull);
    await _readyRows(tester, [1, 3, 4, 5]);
    expect(_create(tester), isNull); // rows 0 and 2 still unconfirmed
    expect(api.posts('/trip/create'), isEmpty);
    expect(api.posts('/trip/event'), isEmpty);
  });

  testWidgets('9. a rejected match becomes a plain row needing a stay length; accept path',
      (tester) async {
    // Reject path.
    await _pump(tester, _fixture('chatbot_three_day.txt'));
    await _parseAndMatch(tester);
    await _readyRows(tester, [1, 2, 3, 4, 5]);
    expect(_has('paste_plan_dwell_0_60'), isFalse);
    await _tap(tester, 'paste_plan_reject_0');
    expect(_text(tester, 'paste_plan_status_0'), 'Rejected');
    expect(_has('paste_plan_dwell_0_60'), isTrue);
    expect(_create(tester), isNull);
    await _tap(tester, 'paste_plan_dwell_0_60');
    expect(_create(tester), isNotNull);

    // Accept path.
    await _pump(tester, _fixture('chatbot_three_day.txt'));
    await _parseAndMatch(tester);
    expect(_text(tester, 'paste_plan_status_0'), 'Not yet confirmed');
    await _readyRows(tester, [1, 2, 3, 4, 5]);
    expect(_create(tester), isNull);
    await _tap(tester, 'paste_plan_accept_0');
    expect(_text(tester, 'paste_plan_status_0'), 'Accepted');
    expect(_has('paste_plan_dwell_0_60'), isFalse);
    expect(_create(tester), isNotNull);
  });

  testWidgets('10. Create trip: rangeCreate with start_empty, then one sorted import_plan',
      (tester) async {
    final api = await _pump(
      tester,
      'Day 2\n- 9am Beach walk\nDay 1\n- 7pm Night market stall\n- 9am Coffee house',
    );
    await _parseAndMatch(tester);
    await _readyRows(tester, [0, 1, 2]);
    await _tap(tester, 'paste_plan_create');
    final paths = [for (final c in api.calls) '${c.method} ${c.path}'];
    expect(paths, [
      'POST /trip/catalog_match',
      'POST /trip/create',
      'GET /trip/trip-new',
      'POST /trip/event',
    ]);
    final create = Map<String, dynamic>.from(api.posts('/trip/create').single.body as Map);
    expect(create['start_empty'], isTrue);
    expect(create['geo_region'], _geo);
    expect(create['start_date'], _start);
    expect(create['end_date'], _end);
    expect((create['party'] as Map)['party_type'], 'solo');
    expect((create['party'] as Map)['size'], 1);
    expect((create['preferences'] as Map)['interest_ids'], isEmpty);
    final event = api.posts('/trip/event').single;
    expect((event.body as Map)['event_type'], 'add_activity');
    final prefs = _prefs(event);
    expect(prefs['mode'], 'import_plan');
    expect(prefs['items'], [
      {'kind': 'plain', 'name': 'Coffee house', 'target_date': '2026-12-27',
        'target_slot': 'morning_tour', 'typical_dwell_minutes': 60},
      {'kind': 'plain', 'name': 'Night market stall', 'target_date': '2026-12-27',
        'target_slot': 'dinner', 'typical_dwell_minutes': 60},
      {'kind': 'plain', 'name': 'Beach walk', 'target_date': '2026-12-28',
        'target_slot': 'morning_tour', 'typical_dwell_minutes': 60},
    ]);
  });

  testWidgets('11. 200 shows added stops; 422 import_plan_refused shows Not imported',
      (tester) async {
    const reason = 'That slot already has an activity on this day.';
    // 200 with one refused item.
    final ok = _FakeApi()
      ..importResults = [
        for (var i = 0; i < 6; i++)
          i == 4
              ? {'index': i, 'status': 'refused', 'code': 'occupied', 'message': reason}
              : {'index': i, 'status': 'added', 'node_id': 'n$i'},
      ];
    await _pump(tester, _fixture('chatbot_three_day.txt'), api: ok);
    await _parseAndMatch(tester);
    await _readyRows(tester, [0, 1, 2, 3, 4, 5]);
    await _tap(tester, 'paste_plan_create');
    expect(_text(tester, 'paste_plan_added_count'), 'Added: 5');
    expect(_text(tester, 'paste_plan_not_imported_count'), 'Not imported: 1');
    expect(_text(tester, 'paste_plan_not_imported_0'),
        'Forodhani Night Food Market (2026-12-28): $reason');
    expect(find.textContaining(kPlainRowLabel), findsWidgets);

    // 422: every item refused; the empty trip stays, nothing else is sent.
    final refused = _FakeApi()
      ..eventError = ValidationException('None of these stops could be added.', {
        'error': 'import_plan_refused',
        'message': 'None of these stops could be added.',
        'results': [
          for (var i = 0; i < 6; i++)
            {'index': i, 'status': 'refused', 'code': 'occupied', 'message': reason},
        ],
      });
    await _pump(tester, _fixture('chatbot_three_day.txt'), api: refused);
    await _parseAndMatch(tester);
    await _readyRows(tester, [0, 1, 2, 3, 4, 5]);
    await _tap(tester, 'paste_plan_create');
    expect(_text(tester, 'paste_plan_added_count'), 'Added: 0');
    expect(_text(tester, 'paste_plan_not_imported_count'), 'Not imported: 6');
    for (var i = 0; i < 6; i++) {
      expect(_text(tester, 'paste_plan_not_imported_$i'), endsWith(reason));
    }
    expect(refused.posts('/trip/event'), hasLength(1));
    expect(refused.calls.last.path, '/trip/event');
  });

  testWidgets('12. booking lines open AddBookingSheet with pastedText; nothing saves',
      (tester) async {
    final api = await _pump(
      tester,
      'Day 1\n- 10:00 Darajani Market\nFlight EK 725 to Zanzibar\nBooking ref: ZX81KD',
    );
    await _parseAndMatch(tester);
    expect(find.byType(AddBookingSheet), findsNothing);
    await _readyRows(tester, [0]);
    expect(find.byType(AddBookingSheet), findsNothing); // not before the trip exists
    await _tap(tester, 'paste_plan_create');
    expect(api.posts('/trip/create'), hasLength(1));
    final seen = <String?>[];
    while (find.byType(AddBookingSheet).evaluate().isNotEmpty && seen.length < 5) {
      final sheet = tester.widget<AddBookingSheet>(find.byType(AddBookingSheet));
      expect(sheet.tripId, 'trip-new');
      seen.add(sheet.pastedText);
      Navigator.of(tester.element(find.byType(AddBookingSheet))).pop();
      await _settle(tester);
    }
    expect(seen, ['Flight EK 725 to Zanzibar', 'Booking ref: ZX81KD']);
    expect(_text(tester, 'paste_plan_booking_count'), 'Bookings saved: 0');
    expect(api.posts('/trip/event'), hasLength(1)); // the import only; no booking saved
  });

  testWidgets('13. plain row detail: label, Swap and Love; no Open in Maps or Driver card',
      (tester) async {
    await tester.pumpWidget(MaterialApp(
      home: ActivityDetailScreen(
        node: _plainNode(),
        onSwap: () {},
        onCancel: () {},
        onMove: () {},
        onLoved: () {},
      ),
    ));
    await tester.pump();
    expect(find.byKey(const Key('detail_plain_label')), findsOneWidget);
    expect(find.text(kPlainRowLabel), findsOneWidget);
    expect(find.byKey(const Key('detail_open_maps')), findsNothing);
    expect(find.byKey(const Key('detail_driver_card')), findsNothing);
    expect(find.byKey(const Key('detail_swap')), findsOneWidget);
    expect(find.byKey(const Key('detail_love')), findsOneWidget);
    expect(find.byKey(const Key('detail_cancel')), findsOneWidget);
    expect(find.byKey(const Key('move_detail_p1')), findsOneWidget);

    // Control: a catalog row keeps Open in Maps and Driver card, no label.
    await tester.pumpWidget(MaterialApp(
      home: ActivityDetailScreen(
        key: UniqueKey(),
        node: _catalogNode(),
        onSwap: () {},
        onCancel: () {},
        onMove: () {},
        onLoved: () {},
      ),
    ));
    await tester.pump();
    expect(find.byKey(const Key('detail_plain_label')), findsNothing);
    expect(find.byKey(const Key('detail_open_maps')), findsOneWidget);
    expect(find.byKey(const Key('detail_driver_card')), findsOneWidget);
  });

  testWidgets('14. Move and Cancel work on a plain row through the existing event calls',
      (tester) async {
    final api = _FakeApi();
    final repo = TripRepository(api);
    var moves = 0;
    await tester.pumpWidget(MaterialApp(
      home: ActivityDetailScreen(
        node: _plainNode(),
        onSwap: () {},
        onCancel: () => repo.sendEvent(
          tripId: 'trip-new',
          type: EventType.cancelActivity,
          message: 'Cancel',
          targetNodeId: 'p1',
        ),
        onMove: () => moves++,
        onLoved: () {},
      ),
    ));
    await tester.pump();
    await tester.ensureVisible(find.byKey(const Key('detail_cancel')));
    await tester.tap(find.byKey(const Key('detail_cancel')));
    await tester.pump();
    final cancel = api.posts('/trip/event').single.body as Map;
    expect(cancel['event_type'], 'cancel_activity');
    expect(cancel['target_node_id'], 'p1');
    await tester.ensureVisible(find.byKey(const Key('move_detail_p1')));
    await tester.tap(find.byKey(const Key('move_detail_p1')));
    await tester.pump();
    expect(moves, 1);
  });

  testWidgets('15. offline: the match step refuses with the offline banner, sends nothing',
      (tester) async {
    final api = await _pump(tester, _fixture('chatbot_three_day.txt'), online: false);
    await _parseAndMatch(tester);
    expect(find.byKey(const Key('paste_plan_offline')), findsOneWidget);
    expect(_has('paste_plan_create'), isFalse);
    expect(api.calls, isEmpty);
  });

  testWidgets('16. Copy copies names, days and reasons, and no other data', (tester) async {
    String? copied;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(SystemChannels.platform,
        (call) async {
      if (call.method == 'Clipboard.setData') {
        copied = (call.arguments as Map)['text'] as String?;
      }
      return null;
    });
    addTearDown(() => tester.binding.defaultBinaryMessenger
        .setMockMethodCallHandler(SystemChannels.platform, null));
    const reason = 'That slot already has an activity on this day.';
    final api = _FakeApi()
      ..importResults = [
        for (var i = 0; i < 6; i++)
          i == 4
              ? {'index': i, 'status': 'refused', 'code': 'occupied', 'message': reason}
              : {'index': i, 'status': 'added', 'node_id': 'n$i'},
      ];
    await _pump(tester, _fixture('chatbot_three_day.txt'), api: api);
    await _parseAndMatch(tester);
    await _readyRows(tester, [0, 1, 2, 3, 4, 5]);
    await _tap(tester, 'paste_plan_create');
    await _tap(tester, 'paste_plan_copy');
    expect(copied, 'Forodhani Night Food Market | 2026-12-28 | $reason');
  });
}
