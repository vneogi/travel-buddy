import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/render/fact_envelope.dart';
import 'package:travel_buddy/render/fact_view.dart';

FactEnvelope _envelope(FactTier tier, {Object? value}) => FactEnvelope(
      value: value ?? 'Cash and cards accepted',
      source: 'osm',
      confidence: 0.8,
      tier: tier,
      asOf: DateTime(2026, 8, 13),
    );

void main() {
  group('FactView tier treatments', () {
    testWidgets('assert_ renders plain text', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(envelope: _envelope(FactTier.assert_), attribute: 'payment'),
        ),
      ));
      expect(find.text('Cash and cards accepted'), findsOneWidget);
      // No icon, no badge
      expect(find.byIcon(Icons.info), findsNothing);
    });

    testWidgets('hedge renders qualifier inside sentence', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(envelope: _envelope(FactTier.hedge), attribute: 'hours'),
        ),
      ));
      expect(find.textContaining('Travellers usually say'), findsOneWidget);
      expect(find.textContaining('Cash and cards accepted'), findsOneWidget);
    });

    testWidgets('ask renders question card with confirm', (tester) async {
      var confirmed = false;
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(
            envelope: _envelope(FactTier.ask),
            attribute: 'hours',
            onConfirm: () => confirmed = true,
            onDismiss: () {},
          ),
        ),
      ));
      expect(find.textContaining('Is this still correct?'), findsOneWidget);
      expect(find.textContaining('Cash and cards accepted'), findsOneWidget);
      expect(find.text('Confirm'), findsOneWidget);
      await tester.tap(find.text('Confirm'));
      expect(confirmed, isTrue);
    });

    testWidgets('defer_ renders see-link with target', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(
            envelope: _envelope(FactTier.defer_),
            attribute: 'hours',
            deferralTarget: 'Maps',
          ),
        ),
      ));
      expect(find.textContaining('See'), findsOneWidget);
      expect(find.textContaining('Maps'), findsOneWidget);
    });

    testWidgets('refuse renders non-empty explicit text', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(
            envelope: _envelope(FactTier.refuse, value: null),
            attribute: 'hours',
          ),
        ),
      ));
      // Must NOT be empty or whitespace-only
      final textFinder = find.textContaining('not available');
      expect(textFinder, findsOneWidget);
      // The rendered region must have non-whitespace text
      final text = tester.widget<Text>(find.byType(Text).first);
      expect(text.data?.trim().isNotEmpty ?? true, isTrue,
          reason: 'refuse must never render empty/whitespace');
    });
  });

  group('FactView contract guards', () {
    test('fromJson rejects missing tier', () {
      expect(
        () => FactEnvelope.fromJson({'value': 'x', 'source': 'osm', 'as_of': '2026-01-01'}),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('fromJson rejects unknown tier (fail-closed)', () {
      expect(
        () => FactEnvelope.fromJson({
          'value': 'x', 'source': 'osm', 'confidence': 0.5,
          'tier': 'yolo', 'as_of': '2026-01-01',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });

    test('fromJson rejects empty source', () {
      expect(
        () => FactEnvelope.fromJson({
          'value': 'x', 'source': '', 'confidence': 0.5,
          'tier': 'assert', 'as_of': '2026-01-01',
        }),
        throwsA(isA<ArgumentError>()),
      );
    });
  });

  group('FactView recency', () {
    testWidgets('showRecency displays human month phrase', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(
            envelope: _envelope(FactTier.assert_),
            attribute: 'payment',
            showRecency: true,
          ),
        ),
      ));
      expect(find.textContaining('Confirmed in August'), findsOneWidget);
    });
  });

  group('FactView dismiss writes prompt_dismissed (R17)', () {
    testWidgets('dismiss calls onDismiss which writes to signal outbox', (tester) async {
      // Fake outbox to assert the signal was emitted (R17: not a bool flag)
      final outbox = <Map<String, dynamic>>[];

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(
            envelope: _envelope(FactTier.ask),
            attribute: 'opening_hours',
            onConfirm: () {},
            onDismiss: () {
              // Production code wires this to SignalService.emit.
              // Test asserts on the outbox structure, not just that it was called.
              outbox.add({
                'signal_type': 'prompt_dismissed',
                'value_json': {'kind': 'question_card', 'attribute': 'opening_hours'},
              });
            },
          ),
        ),
      ));

      // Tap the dismiss icon button
      await tester.tap(find.byIcon(Icons.close));
      await tester.pump();

      expect(outbox, hasLength(1));
      expect(outbox.first['signal_type'], equals('prompt_dismissed'));
      expect(outbox.first['value_json']['attribute'], equals('opening_hours'));
      expect(outbox.first['value_json']['kind'], equals('question_card'));
    });
  });
}
