// SPEC-50 slice 1: inspectable swap comparison.
//
// Fake repository in the style of spec45_swap_confirm_test.dart. Venue
// and stop names are placeholders.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/swap_sheet/swap_comparison.dart';
import 'package:travel_buddy/features/swap_sheet/swap_sheet.dart';

/// Minimal fake that only implements swapCandidates and counts calls.
class _FakeTripRepo implements TripRepository {
  final List<VenueSearchResult> swapResults;
  int swapCalls = 0;
  _FakeTripRepo({required this.swapResults});

  @override
  Future<SwapCandidatesResult> swapCandidates({
    required String tripId,
    required String targetNodeId,
  }) async {
    swapCalls++;
    return SwapCandidatesResult(candidates: swapResults);
  }

  @override
  noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

const _comparison = Key('swap_comparison');
const _next = Key('swap_next_option');

TripNode _current({bool locked = false, String name = 'Current Stop'}) =>
    TripNode(
      nodeId: 'cur-1',
      venueName: name,
      scheduledStart: DateTime.utc(2026, 12, 27, 7),
      durationMinutes: 90,
      isLocked: locked,
      status: NodeStatus.pending,
      vibeTags: const ['culture'],
      geoRegion: 'zanzibar_tanzania',
    );

VenueSearchResult _venue(
  String id,
  String name, {
  String microLocation = 'nam_phou_fountain',
  List<String> vibes = const ['cafe'],
  bool boosted = false,
}) =>
    VenueSearchResult(
      venueId: id,
      name: name,
      description: '',
      microLocation: microLocation,
      vibeTags: vibes,
      isSponsored: boosted,
      sponsoredBoostApplied: boosted,
    );

final _three = [
  _venue('v1', 'Option One'),
  _venue('v2', 'Option Two'),
  _venue('v3', 'Option Three'),
];

/// Holds what the sheet returned after it closed.
class _Outcome {
  bool closed = false;
  VenueSearchResult? venue;
}

Future<_Outcome> _openSheet(
  WidgetTester tester,
  _FakeTripRepo repo, {
  TripNode? currentNode,
  bool passNode = true,
}) async {
  final outcome = _Outcome();
  await tester.pumpWidget(
    ProviderScope(
      overrides: [tripRepoProvider.overrideWithValue(repo)],
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => ElevatedButton(
              child: const Text('Open'),
              onPressed: () async {
                final result = await showModalBottomSheet<VenueSearchResult>(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => SwapSheet(
                    tripId: 'trip-1',
                    targetNodeId: 'cur-1',
                    tripState: const TripState(
                      tripId: 'trip-1',
                      userId: 'u1',
                      nodes: [],
                    ),
                    currentNode: passNode ? (currentNode ?? _current()) : null,
                  ),
                );
                outcome
                  ..closed = true
                  ..venue = result;
              },
            ),
          ),
        ),
      ),
    ),
  );
  await tester.tap(find.text('Open'));
  await tester.pumpAndSettle();
  return outcome;
}

Future<void> _tapText(WidgetTester tester, String text) async {
  await tester.tap(find.text(text));
  await tester.pumpAndSettle();
}

Future<void> _tapNext(WidgetTester tester) async {
  await tester.tap(find.byKey(_next));
  await tester.pumpAndSettle();
}

Finder _inPanel(String text) => find.descendant(
      of: find.byKey(_comparison),
      matching: find.textContaining(text),
    );

bool _nextEnabled(WidgetTester tester) =>
    tester.widget<TextButton>(find.byKey(_next)).onPressed != null;

void main() {
  testWidgets('comparison hidden until a candidate is selected',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo);
    expect(find.text('Swap to...'), findsOneWidget);
    expect(find.byKey(_comparison), findsNothing);
    expect(find.byKey(_next), findsNothing);

    await _tapText(tester, 'Option One');
    expect(find.byKey(_comparison), findsOneWidget);
  });

  testWidgets('selecting shows now and option rows with names and area',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');

    expect(_inPanel('Current Stop'), findsOneWidget);
    expect(_inPanel('10:00 to 11:30'), findsOneWidget);
    expect(_inPanel('Option One'), findsOneWidget);
    expect(_inPanel('Nam Phou Fountain area'), findsOneWidget);
    expect(_inPanel('cafe'), findsOneWidget);
    expect(find.text(kSwapChecksCopy), findsOneWidget);
    // The panel never adds an exact-match copy of the venue name.
    expect(find.text('Option One'), findsOneWidget);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
  });

  testWidgets('missing area and vibes show not available, not blank',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: [
      _venue('v1', 'Option One', microLocation: '', vibes: const []),
    ]);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');

    expect(find.text(kSwapAreaMissing), findsOneWidget);
    expect(find.text(kSwapVibesMissing), findsOneWidget);
  });

  testWidgets(
      'no score, rank, better or recommended wording anywhere in the sheet',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');
    await _tapNext(tester);

    final banned = RegExp(
      r'\b(score|scores|rank|ranked|better|recommended)\b',
      caseSensitive: false,
    );
    final texts = tester
        .widgetList<Text>(find.byType(Text))
        .map((t) => t.data ?? t.textSpan?.toPlainText() ?? '')
        .toList();
    expect(texts, isNotEmpty);
    for (final text in texts) {
      expect(banned.hasMatch(text), isFalse, reason: '"$text"');
    }
  });

  testWidgets(
      'sponsored option adds the ranking note and keeps exactly one Sponsored label',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: [
      _venue('v1', 'Boosted Place', boosted: true),
      _venue('v2', 'Organic Place'),
    ]);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Boosted Place');

    expect(find.text(kSwapSponsoredCopy), findsOneWidget);
    expect(find.text('Sponsored'), findsOneWidget);
    expect(
      find.text('Paid placement influenced this ranking.'),
      findsOneWidget,
    );

    // An organic option has no ranking note.
    await _tapNext(tester);
    expect(_inPanel('Organic Place'), findsOneWidget);
    expect(find.text(kSwapSponsoredCopy), findsNothing);
    expect(find.text('Sponsored'), findsOneWidget);
  });

  testWidgets(
      'Next option moves to the next visible candidate and stops at the end',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');
    expect(_nextEnabled(tester), isTrue);

    await _tapNext(tester);
    expect(_inPanel('Option Two'), findsOneWidget);
    await _tapNext(tester);
    expect(_inPanel('Option Three'), findsOneWidget);

    // Last visible candidate: disabled, no wrap to the first.
    expect(_nextEnabled(tester), isFalse);
    await tester.tap(find.byKey(_next));
    await tester.pumpAndSettle();
    expect(_inPanel('Option Three'), findsOneWidget);
    expect(_inPanel('Option One'), findsNothing);
  });

  testWidgets(
      'Next option is disabled when the selected candidate is filtered out',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: [
      _venue('v1', 'Option One', vibes: const ['cafe']),
      _venue('v2', 'Option Two', vibes: const ['museum']),
      _venue('v3', 'Option Three', vibes: const ['cafe']),
    ]);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Option Two');
    expect(_nextEnabled(tester), isTrue);

    await tester.tap(find.widgetWithText(FilterChip, 'cafe'));
    await tester.pumpAndSettle();
    expect(find.text('Option Two'), findsNothing);
    expect(_nextEnabled(tester), isFalse);

    // Inside the filtered list, Next skips the hidden candidate.
    await _tapText(tester, 'Option One');
    expect(_nextEnabled(tester), isTrue);
    await _tapNext(tester);
    expect(_inPanel('Option Three'), findsOneWidget);
  });

  testWidgets('locked current stop never shows the comparison',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo, currentNode: _current(locked: true));
    await _tapText(tester, 'Option One');
    expect(find.byKey(_comparison), findsNothing);
    expect(find.byKey(_next), findsNothing);
    expect(find.byIcon(Icons.check_circle), findsOneWidget);
  });

  testWidgets('no comparison when currentNode is not passed', (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo, passNode: false);
    await _tapText(tester, 'Option One');
    expect(find.byKey(_comparison), findsNothing);
    expect(find.byKey(_next), findsNothing);
  });

  testWidgets('Confirm swap pops the currently shown option; Cancel pops null',
      (tester) async {
    final repo = _FakeTripRepo(swapResults: _three);
    final confirmed = await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');
    await _tapNext(tester);
    await _tapText(tester, 'Confirm swap');
    expect(confirmed.closed, isTrue);
    expect(confirmed.venue?.venueId, 'v2');

    final cancelled = await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');
    await _tapText(tester, 'Cancel');
    expect(cancelled.closed, isTrue);
    expect(cancelled.venue, isNull);
  });

  testWidgets('browsing does not call the repository again', (tester) async {
    final repo = _FakeTripRepo(swapResults: [
      _venue('v1', 'Option One', vibes: const ['cafe']),
      _venue('v2', 'Option Two', vibes: const ['museum']),
      _venue('v3', 'Option Three', vibes: const ['cafe']),
    ]);
    await _openSheet(tester, repo);
    expect(repo.swapCalls, 1);

    await _tapText(tester, 'Option One');
    await _tapNext(tester);
    await _tapNext(tester);
    await tester.tap(find.widgetWithText(FilterChip, 'cafe'));
    await tester.pumpAndSettle();
    await tester.tap(find.widgetWithText(FilterChip, 'cafe'));
    await tester.pumpAndSettle();
    await _tapText(tester, 'Option Two');

    expect(repo.swapCalls, 1);
  });

  testWidgets('no overflow at 360dp and 2.0 text scale with long names',
      (tester) async {
    tester.view.physicalSize = const Size(1080, 2400);
    tester.view.devicePixelRatio = 3.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    final longStop = 'S' * 20 + ' Long Current Stop Name For The Comparison';
    final longOption = 'O' * 20 + ' Long Candidate Option Name For Comparison';
    expect(longStop.length, greaterThanOrEqualTo(60));
    expect(longOption.length, greaterThanOrEqualTo(60));

    // The panel alone; the sheet header is unchanged existing layout.
    await tester.pumpWidget(MaterialApp(
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context)
            .copyWith(textScaler: TextScaler.linear(2.0)),
        child: child!,
      ),
      home: Scaffold(
        body: Column(
          children: [
            SwapComparisonPanel(
              current: _current(name: longStop),
              option: _venue('v1', longOption, boosted: true),
              onNextOption: () {},
            ),
          ],
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
    expect(
      tester.getRect(find.byKey(_comparison)).right,
      lessThanOrEqualTo(360),
    );
    await tester.ensureVisible(find.byKey(_next));
    await tester.pumpAndSettle();
    expect(find.byKey(_next).hitTestable(), findsOneWidget);
  });

  testWidgets('Next option and Confirm meet 44dp min height and button semantics',
      (tester) async {
    final handle = tester.ensureSemantics();
    final repo = _FakeTripRepo(swapResults: _three);
    await _openSheet(tester, repo);
    await _tapText(tester, 'Option One');

    final confirm = find.ancestor(
      of: find.text('Confirm swap'),
      matching: find.byType(FilledButton),
    );
    expect(tester.getSize(find.byKey(_next)).height, greaterThanOrEqualTo(44));
    expect(tester.getSize(confirm).height, greaterThanOrEqualTo(44));
    expect(
      tester.getSemantics(find.byKey(_next)),
      containsSemantics(label: 'Next option', isButton: true),
    );
    expect(
      tester.getSemantics(confirm),
      containsSemantics(label: 'Confirm swap', isButton: true),
    );
    handle.dispose();
  });
}
