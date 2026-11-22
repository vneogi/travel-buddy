// SPEC-42 unknown-time excursions: window Add, review sheet, card label,
// and no Move or Swap on a window card.
// Written without a local Flutter SDK; CI is the first compile and run.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/destination_tz.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/direct_add/direct_add_sheet.dart';
import 'package:travel_buddy/features/direct_add/excursion_review_sheet.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

class _FakeRepo extends Fake implements TripRepository {
  @override
  Future<AddCandidatesResult> addCandidates({
    required String tripId,
    required String targetDate,
    required String targetSlot,
  }) async =>
      AddCandidatesResult(targetDate: targetDate, targetSlot: targetSlot);
}

TripNode _node(
  String id,
  String name,
  DateTime startUtc, {
  String? slot,
  String? window,
  int minutes = 60,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      scheduledStart: startUtc,
      durationMinutes: minutes,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: 'zanzibar_tanzania',
      slotName: slot,
      placeSource: 'trip_private',
      timeWindow: window,
    );

TripEventResult _ok([List<TripNode> nodes = const []]) => TripEventResult(
      message: 'ok',
      updatedNodes: nodes,
      routingTier: 'light',
      fromCache: false,
    );

class _Submitter {
  final calls = <Map<String, dynamic>>[];
  final List<ExcursionSubmitOutcome> replies;
  _Submitter(this.replies);

  Future<ExcursionSubmitOutcome> call(Map<String, dynamic> prefs) async {
    calls.add(Map<String, dynamic>.of(prefs));
    return replies[(calls.length - 1).clamp(0, replies.length - 1)];
  }
}

Widget _host(_Submitter submitter) => MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: TextButton(
              onPressed: () => showModalBottomSheet<EmptyDayAddChoice>(
                context: context,
                isScrollControlled: true,
                builder: (_) => DirectAddSheet(
                  tripId: 'trip-1',
                  targetDate: '2026-12-27',
                  repo: _FakeRepo(),
                  submitWindow: submitter.call,
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    );

Future<void> _tap(WidgetTester tester, Finder f) async {
  await tester.ensureVisible(f);
  await tester.pumpAndSettle();
  await tester.tap(f);
  await tester.pumpAndSettle();
}

/// Open the sheet, reach the private form, choose No fixed time + [window].
Future<void> _fillWindow(WidgetTester tester, String window) async {
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await _tap(tester, find.byKey(const Key('direct_add_slot_morning_tour')));
  await _tap(tester, find.byKey(const Key('uncatalogued_add_open')));
  await _tap(tester, find.byKey(const Key('direct_add_no_fixed_time')));
  await _tap(tester, find.byKey(Key('direct_add_window_$window')));
  await tester.enterText(find.byKey(const Key('uncatalogued_add_name')), 'Prison Island');
  await tester.pumpAndSettle();
  await _tap(tester, find.byKey(const Key('uncatalogued_add_confirm')));
}

final _lunch = _node('l1', 'Lukmaan', DateTime.utc(2026, 12, 27, 8), slot: 'lunch');
const _review = ExcursionReview(timeWindow: 'morning', skipNodeIds: ['l1']);

TripEventResult _needsReview() => TripEventResult(
      message: 'Adding this would skip other stops on that day.',
      updatedNodes: [_lunch],
      routingTier: 'light',
      fromCache: false,
      excursionReview: _review,
    );

Widget _card(TripNode node) => MaterialApp(
      home: Scaffold(
        body: SingleChildScrollView(
          child: ActivityCard(
            node: node,
            onTapSwap: () {},
            onTapCancel: () {},
            onTapMove: () {},
          ),
        ),
      ),
    );

void main() {
  testWidgets('No fixed time then Whole day sends time_window and no slot or dwell',
      (tester) async {
    final s = _Submitter([ExcursionSubmitOutcome(result: _ok())]);
    await tester.pumpWidget(_host(s));
    await _fillWindow(tester, 'whole_day');

    expect(s.calls, hasLength(1));
    final prefs = s.calls.single;
    expect(prefs['mode'], 'uncatalogued_add');
    expect(prefs['time_window'], 'whole_day');
    expect(prefs['target_date'], '2026-12-27');
    expect(prefs.containsKey('target_slot'), isFalse);
    expect(prefs.containsKey('typical_dwell_minutes'), isFalse);
    expect(find.byKey(const Key('direct_add_sheet_v1')), findsNothing);
  });

  testWidgets('needs_review opens the review sheet and Confirm resends the ids',
      (tester) async {
    final s = _Submitter([
      ExcursionSubmitOutcome(result: _needsReview()),
      ExcursionSubmitOutcome(result: _ok([_lunch])),
    ]);
    await tester.pumpWidget(_host(s));
    await _fillWindow(tester, 'morning');

    expect(find.byKey(const Key('excursion_review_sheet')), findsOneWidget);
    expect(find.text('Make room for this'), findsOneWidget);
    expect(find.byKey(const Key('excursion_review_skip_l1')), findsOneWidget);
    expect(find.text('Lukmaan'), findsOneWidget);

    await _tap(tester, find.byKey(const Key('excursion_review_confirm')));

    expect(s.calls, hasLength(2));
    expect(s.calls[1]['confirm_skip_node_ids'], ['l1']);
    expect(s.calls[1]['time_window'], 'morning');
    expect(s.calls[1].containsKey('target_slot'), isFalse);
    expect(find.byKey(const Key('excursion_review_sheet')), findsNothing);
    expect(find.byKey(const Key('direct_add_sheet_v1')), findsNothing);
  });

  testWidgets('Not now sends no second event and keeps the Add sheet', (tester) async {
    final s = _Submitter([ExcursionSubmitOutcome(result: _needsReview())]);
    await tester.pumpWidget(_host(s));
    await _fillWindow(tester, 'morning');
    expect(find.byKey(const Key('excursion_review_sheet')), findsOneWidget);

    await _tap(tester, find.byKey(const Key('excursion_review_dismiss')));

    expect(s.calls, hasLength(1));
    expect(find.byKey(const Key('excursion_review_sheet')), findsNothing);
    expect(find.byKey(const Key('direct_add_sheet_v1')), findsOneWidget);
  });

  testWidgets('a window card shows the window label and no clock time', (tester) async {
    final start = DateTime.utc(2026, 12, 27, 11);
    final node = _node('w1', 'Jozani Forest', start,
        slot: 'afternoon_evening_tour', window: 'afternoon', minutes: 180);
    await tester.pumpWidget(_card(node));
    expect(find.byKey(const Key('time_window_label_w1')), findsOneWidget);
    expect(find.text('Afternoon'), findsOneWidget);
    expect(find.text(formatDestinationTime(start, 'zanzibar_tanzania')), findsNothing);

    final whole = _node('w2', 'Prison Island', DateTime.utc(2026, 12, 27, 6),
        slot: 'morning_tour', window: 'whole_day', minutes: 480);
    await tester.pumpWidget(_card(whole));
    expect(find.text('Whole day'), findsOneWidget);
    expect(find.text('Morning'), findsNothing);
  });

  testWidgets('a window card offers no Move or Swap but keeps Skip / Cancel',
      (tester) async {
    final window = _node('w3', 'Prison Island', DateTime.utc(2026, 12, 27, 6),
        slot: 'morning_tour', window: 'whole_day', minutes: 480);
    await tester.pumpWidget(_card(window));
    expect(find.byTooltip('Swap this activity'), findsNothing);
    await _tap(tester, find.byTooltip('More actions'));
    expect(find.byKey(const Key('move_menu_w3')), findsNothing);
    expect(find.text('Move'), findsNothing);
    expect(find.text('Skip / Cancel'), findsOneWidget);

    // Control: the same stop without a window keeps Swap and Move.
    final plain = _node('p1', 'Darajani Walk', DateTime.utc(2026, 12, 27, 6),
        slot: 'morning_tour', minutes: 60);
    await tester.pumpWidget(_card(plain));
    await tester.pumpAndSettle();
    expect(find.byTooltip('Swap this activity'), findsOneWidget);
    await _tap(tester, find.byTooltip('More actions'));
    expect(find.byKey(const Key('move_menu_p1')), findsOneWidget);
  });
}
