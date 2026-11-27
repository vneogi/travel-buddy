// SPEC-57 Amendments 1 and 2: official option without fare bands, and
// sourced flat-fare cards shown exactly as stored. Screen tests inject a
// parsed hub; test 8 reads the real asset file; no network.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/features/arrival_armor/arrival_armor_screen.dart';
import 'package:travel_buddy/features/arrival_armor/arrival_hubs.dart';

Widget _app(ArrivalHub hub) => ProviderScope(
      child: MaterialApp(
        home: ArrivalArmorScreen(tripId: 't1', hubId: hub.id, hub: hub),
      ),
    );

Map<String, dynamic> _card(String route, {Map<String, dynamic> override = const {}}) => {
      'route': route,
      'vehicle': 'taxi',
      'currency': 'USD',
      'low': 20,
      'high': 30,
      'basis': 'one way, car for up to 4, quoted before the ride',
      'source': 'Hotel written reply (Test Hotel)',
      'surveyed_on': '2026-11-20',
      ...override,
    };

ArrivalHub _hub({List<Object?>? flatFares, String? official, String? source, String? surveyed}) =>
    ArrivalHub.fromJson({
      'id': 'test_hub',
      'label': 'Test hub',
      'geo_regions': ['zanzibar_tanzania'],
      'booking_types': ['flight'],
      'currency': 'TZS',
      'fare_band_low': null,
      'fare_band_high': null,
      'hard_ceiling': null,
      'official_option': official,
      'scam_notes': <String>[],
      'surveyed_on': surveyed,
      'source': source,
      if (flatFares != null) 'flat_fares': flatFares,
    });

bool _isCardKey(Key? k) => k is ValueKey<String> && k.value.startsWith('flat_fare_');

final _cards = find.byWidgetPredicate((w) => _isCardKey(w.key));

List<String> _cardTexts(int i) => find
    .descendant(of: find.byKey(Key('flat_fare_$i')), matching: find.byType(Text))
    .evaluate()
    .map((e) => (e.widget as Text).data ?? '')
    .toList();

/// Texts inside the Typical fares section that are not inside a card.
List<String> _looseSectionTexts() {
  final out = <String>[];
  final section = find.byKey(const Key('arrival_flat_fares'));
  for (final e in find.descendant(of: section, matching: find.byType(Text)).evaluate()) {
    var inCard = false;
    e.visitAncestorElements((a) {
      if (_isCardKey(a.widget.key)) {
        inCard = true;
        return false;
      }
      return true;
    });
    if (!inCard) out.add((e.widget as Text).data ?? '');
  }
  return out;
}

List<String> _allTexts() =>
    find.byType(Text).evaluate().map((e) => (e.widget as Text).data ?? '').toList();

void main() {
  testWidgets('1. no bands + official option: heading, text and source; no empty line',
      (tester) async {
    await tester.pumpWidget(_app(_hub(
      official: 'Test official text',
      source: 'https://example.test/rates/',
      surveyed: '2026-11-27',
    )));
    expect(find.text('Official option'), findsOneWidget);
    expect(find.text('Test official text'), findsOneWidget);
    expect(find.text('Source: https://example.test/rates/ (2026-11-27)'), findsOneWidget);
    expect(find.text(kArrivalEmptyHub), findsNothing);
    expect(find.text('Fair fare guide'), findsNothing);
    expect(find.text(kArrivalFareCaption), findsNothing);
  });

  testWidgets('2. no bands and no official option shows neither; empty line shows',
      (tester) async {
    await tester.pumpWidget(_app(_hub()));
    expect(find.text('Official option'), findsNothing);
    expect(find.textContaining('Source:'), findsNothing);
    expect(find.text(kArrivalEmptyHub), findsOneWidget);

    // Only invalid cards: still empty, and no Typical fares section.
    await tester.pumpWidget(_app(_hub(flatFares: [
      _card('Broken route', override: {'low': null}),
    ])));
    expect(find.text('Typical fares'), findsNothing);
    expect(find.text(kArrivalEmptyHub), findsOneWidget);
  });

  testWidgets('3. a hub with bands keeps the band section; official shows too', (tester) async {
    const hub = ArrivalHub(
      id: 'band_hub',
      label: 'Band hub',
      currency: 'TZS',
      fareBandLow: 1,
      fareBandHigh: 2,
      hardCeiling: 3,
      officialOption: 'Band official text',
      surveyedOn: '2026-01-01',
      source: 'test fixture',
    );
    await tester.pumpWidget(_app(hub));
    expect(find.text('Fair fare guide'), findsOneWidget);
    expect(find.text('1 - 2 TZS'), findsOneWidget);
    expect(find.text('Walk-away above 3 TZS'), findsOneWidget);
    expect(find.text(kArrivalFareCaption), findsOneWidget);
    expect(find.text('Official option'), findsOneWidget);
    expect(find.text('Band official text'), findsOneWidget);
    expect(find.text('Source: test fixture (2026-01-01)'), findsOneWidget);
    expect(find.text(kArrivalEmptyHub), findsNothing);
  });

  testWidgets('4. a hub with no flat_fares key shows no Typical fares section', (tester) async {
    final hub = _hub(official: 'Some official text');
    expect(hub.flatFares, isEmpty);
    await tester.pumpWidget(_app(hub));
    expect(find.text('Typical fares'), findsNothing);
    expect(find.byKey(const Key('arrival_flat_fares')), findsNothing);
    expect(find.text(kFlatFareCaption), findsNothing);
  });

  testWidgets('5. a complete card shows its fields, source with date, and the caption',
      (tester) async {
    await tester.pumpWidget(_app(_hub(flatFares: [_card('Airport to Stone Town hotel area')])));
    expect(find.text('Typical fares'), findsOneWidget);
    expect(_cards, findsOneWidget);
    expect(_cardTexts(0), [
      'Airport to Stone Town hotel area',
      'taxi',
      '20 - 30 USD',
      'one way, car for up to 4, quoted before the ride',
      'Source: Hotel written reply (Test Hotel) (2026-11-20)',
    ]);
    expect(find.text(kFlatFareCaption), findsOneWidget);
    expect(kFlatFareCaption, 'Guides only. Agree the price before you get in.');
    expect(find.text(kArrivalEmptyHub), findsNothing);
  });

  testWidgets('6. incomplete or invalid cards are skipped with no placeholder', (tester) async {
    final invalid = <Map<String, dynamic>>[
      _card('Route null low', override: {'low': null}),
      _card('Route low above high', override: {'low': 40, 'high': 30}),
      _card('Route missing source', override: {'source': null}),
      _card('Route missing date', override: {'surveyed_on': null}),
      _card('Route bad date', override: {'surveyed_on': '2026-13-40'}),
      _card('Route lowercase currency', override: {'currency': 'usd'}),
      _card('Route missing currency', override: {'currency': null}),
    ];
    final hub = _hub(flatFares: [
      invalid[0],
      _card('Valid route one'),
      ...invalid.sublist(1),
      'not a card',
      _card('Valid route two'),
    ]);
    expect(hub.validFlatFares.map((f) => f.route), ['Valid route one', 'Valid route two']);
    await tester.pumpWidget(_app(hub));
    expect(_cards, findsNWidgets(2));
    expect(_cardTexts(0).first, 'Valid route one');
    expect(_cardTexts(1).first, 'Valid route two');
    for (final c in invalid) {
      expect(find.textContaining(c['route'] as String), findsNothing);
    }
    expect(_looseSectionTexts(), ['Typical fares', kFlatFareCaption]);
  });

  testWidgets('7. nothing computed: only stored numbers appear', (tester) async {
    final cards = [
      _card('Airport to Stone Town hotel area'),
      _card('Stone Town to Nungwi', override: {'currency': 'TZS', 'low': 10000, 'high': 30000}),
    ];
    await tester.pumpWidget(_app(_hub(flatFares: cards)));
    expect(_cardTexts(0)[2], '20 - 30 USD');
    expect(_cardTexts(1)[2], '10000 - 30000 TZS');
    // Every integer on screen must come from the stored data (numbers and
    // the digits inside stored strings). A midpoint (25, 20000) or a
    // multiple of high (45, 60, 45000, 60000) is not allowed.
    final allowed = <String>{};
    for (final c in cards) {
      for (final v in c.values) {
        allowed.addAll(RegExp(r'\d+').allMatches('$v').map((m) => m.group(0)!));
      }
    }
    final shown = <String>{
      for (final t in _allTexts()) ...RegExp(r'\d+').allMatches(t).map((m) => m.group(0)!),
    };
    expect(shown.difference(allowed), isEmpty);
    for (final bad in ['25', '20000', '45', '60', '45000', '60000']) {
      expect(shown.contains(bad), isFalse, reason: bad);
    }
  });

  testWidgets('8. the real ferry hub shows the Azam Marine text and its source', (tester) async {
    final hubs = parseArrivalHubs(File('assets/arrival_hubs.json').readAsStringSync());
    final ferry = hubs.singleWhere((h) => h.id == 'stone_town_ferry');
    expect(ferry.hasFare, isFalse);
    expect(ferry.bookingTypes, ['train']);
    expect(ferry.officialOption, contains('Azam Marine'));
    await tester.pumpWidget(_app(ferry));
    expect(find.text('Official option'), findsOneWidget);
    expect(find.text(ferry.officialOption!), findsOneWidget);
    expect(find.textContaining('Source: https://azammarine.com/rates/'), findsWidgets);
    expect(find.text(kArrivalEmptyHub), findsNothing);
    expect(find.text('Fair fare guide'), findsNothing);
  });

  test('9. Driver Card and Show-to-driver carry no official or fare text', () {
    final src = File('lib/features/driver_card/driver_card_screen.dart').readAsStringSync();
    // Strip comments before matching (R17).
    final code = src
        .replaceAll(RegExp(r'/\*[\s\S]*?\*/'), '')
        .split('\n')
        .map((l) => l.replaceFirst(RegExp(r'//.*$'), ''))
        .join('\n');
    // The scan reads the right file: Show-to-driver lives here.
    expect(code, contains('show_to_driver_enter'));
    for (final token in [
      'arrival_armor',
      'arrival_hubs',
      'officialOption',
      'flatFares',
      'validFlatFares',
      'FlatFare',
      'fareBand',
      'hardCeiling',
      'kArrivalFareCaption',
      'kFlatFareCaption',
      'Official option',
      'Typical fares',
      'Fair fare guide',
    ]) {
      expect(code.contains(token), isFalse, reason: token);
    }
  });
}
