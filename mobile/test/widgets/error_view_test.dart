import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/widgets/error_view.dart';

void main() {
  testWidgets('generic failures never expose implementation details', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ErrorView(error: StateError('databaseFactory exploded')),
        ),
      ),
    );

    expect(find.text('Something went wrong'), findsOneWidget);
    expect(find.textContaining('databaseFactory'), findsNothing);
    expect(find.textContaining('check your connection'), findsOneWidget);
  });

  testWidgets('network failures use calm connection copy', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ErrorView(error: NetworkException()),
        ),
      ),
    );

    expect(find.text('No connection'), findsOneWidget);
    expect(find.textContaining('Travel Buddy'), findsOneWidget);
  });

  testWidgets('raw socket failures do not leak exception text', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: ErrorView(error: SocketException('Connection refused')),
        ),
      ),
    );

    expect(find.textContaining('SocketException'), findsNothing);
    expect(find.textContaining('check your connection'), findsOneWidget);
  });
}
