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
            onDismiss: ({required String kind, required String attribute}) {},
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

  group('FactView dismiss invokes typed handler with attribute (R17)', () {
    testWidgets('ask tier dismiss passes kind=question_card and widget attribute', (tester) async {
      String? receivedKind;
      String? receivedAttribute;

      await tester.pumpWidget(MaterialApp(
        home: Scaffold(
          body: FactView(
            envelope: _envelope(FactTier.ask),
            attribute: 'opening_hours',
            onConfirm: () {},
            onDismiss: ({required String kind, required String attribute}) {
              receivedKind = kind;
              receivedAttribute = attribute;
            },
          ),
        ),
      ));

      await tester.tap(find.byIcon(Icons.close));
      await tester.pump();

      expect(receivedKind, equals('question_card'));
      expect(receivedAttribute, equals('opening_hours'));
    });
  });
}
