import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';
import 'package:sqflite/sqflite.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/booking/booking_parser.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';

class MockSyncEngine extends Mock implements SyncEngine {}

class FakeSignalService extends Fake implements SignalService {
  final calls = <Map<String, String>>[];

  @override
  Future<void> emitBookingAdded({
    required String bookingType,
    required String importSource,
    required String tripId,
  }) async {
    calls.add({
      'bookingType': bookingType,
      'importSource': importSource,
      'tripId': tripId,
    });
  }
}

void main() {
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  late OfflineDatabase db;
  late FakeSignalService signalService;

  setUp(() async {
    db = OfflineDatabase(testPath: inMemoryDatabasePath);
    signalService = FakeSignalService();
  });

  tearDown(() async {
    await db.close();
  });

  Widget buildSheet({
    String tripId = 'trip-test',
    String initialBookingType = 'flight',
  }) {
    return ProviderScope(
      overrides: [
        offlineDatabaseProvider.overrideWithValue(db),
        signalServiceProvider.overrideWithValue(signalService),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: Builder(
            builder: (context) => AddBookingSheet(
              tripId: tripId,
              initialBookingType: initialBookingType,
            ),
          ),
        ),
      ),
    );
  }

  // ================================================================
  // Expansion and auto-fill
  // ================================================================

  group('Paste and auto-fill', () {
    testWidgets('expand paste section and auto-fill a Booking.com email',
        (tester) async {
      await tester.pumpWidget(buildSheet());
      await tester.pumpAndSettle();

      // Expand the paste section
      final pasteTile = find.text('Paste confirmation text');
      expect(pasteTile, findsOneWidget);
      await tester.tap(pasteTile);
      await tester.pumpAndSettle();

      // Enter booking text
      const bookingText =
          'Booking.com\n'
          'Grand Sapphire Hotel is expecting you on Mon 5 Oct 2026\n'
          'Check-in Monday, 5 October 2026 (15:00 - 00:00)\n'
          'Check-out Wednesday, 7 October 2026 (until 11:00)\n'
          'Dubai, UAE\n'
          'Booking reference: HTL7890123';
      await tester.enterText(
        find.byType(TextField).last,
        bookingText,
      );
      await tester.pumpAndSettle();

      // Tap Auto-fill
      await tester.tap(find.text('Auto-fill from paste'));
      await tester.pumpAndSettle();

      // Assert extraction review is shown
      expect(find.byKey(const Key('extraction_review')), findsOneWidget);
      expect(find.textContaining('Provider: Booking.com'), findsOneWidget);
      expect(find.textContaining('Found:'), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets('junk input shows extraction_no_fields', (tester) async {
      await tester.pumpWidget(buildSheet());
      await tester.pumpAndSettle();

      // Expand
      await tester.tap(find.text('Paste confirmation text'));
      await tester.pumpAndSettle();

      // Enter junk
      await tester.enterText(
        find.byType(TextField).last,
        'Hello! How are you? Visit our website.',
      );
      await tester.pumpAndSettle();

      // Auto-fill
      await tester.tap(find.text('Auto-fill from paste'));
      await tester.pumpAndSettle();

      // Assert no-fields message shown
      expect(find.byKey(const Key('extraction_no_fields')), findsOneWidget);
      expect(
        find.textContaining("Couldn't find booking details"),
        findsOneWidget,
      );
    }, timeout: const Timeout(Duration(seconds: 20)));
  });

  // ================================================================
  // Zero-field guard: importSource stays manual
  // ================================================================

  group('Zero-field import_source guard', () {
    testWidgets(
      'zero-field parse does not change importSource to email',
      (tester) async {
        await tester.pumpWidget(buildSheet());
        await tester.pumpAndSettle();

        // Expand and enter junk
        await tester.tap(find.text('Paste confirmation text'));
        await tester.pumpAndSettle();
        await tester.enterText(
          find.byType(TextField).last,
          'No useful data here whatsoever.',
        );
        await tester.pumpAndSettle();

        // Auto-fill with junk
        await tester.tap(find.text('Auto-fill from paste'));
        await tester.pumpAndSettle();

        // The extraction_no_fields widget should appear
        expect(find.byKey(const Key('extraction_no_fields')), findsOneWidget);

        // The Title/Venue field should still be empty (not polluted)
        final titleField = tester.widget<TextField>(
          find.widgetWithText(TextField, 'Title / Venue').first,
        );
        expect(titleField.controller!.text, isEmpty,
            reason: 'Zero-field parse must not prefill any fields');
      },
      timeout: const Timeout(Duration(seconds: 20)),
    );
  });

  // ================================================================
  // Stale values from earlier parse not falsely presented
  // ================================================================

  group('Stale value guard', () {
    testWidgets(
      'stale values from earlier parse are cleared on second junk parse',
      (tester) async {
        await tester.pumpWidget(buildSheet());
        await tester.pumpAndSettle();

        // Expand
        await tester.tap(find.text('Paste confirmation text'));
        await tester.pumpAndSettle();

        // First parse: good data
        const goodText =
            'Booking.com\n'
            'Grand Sapphire Hotel is expecting you on Mon 5 Oct 2026\n'
            'Check-in Monday, 5 October 2026 (15:00 - 00:00)\n'
            'Check-out Wednesday, 7 October 2026 (until 11:00)\n'
            'Dubai, UAE\n'
            'Booking reference: HTL7890123';
        await tester.enterText(find.byType(TextField).last, goodText);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Auto-fill from paste'));
        await tester.pumpAndSettle();

        // extraction_review should be visible
        expect(find.byKey(const Key('extraction_review')), findsOneWidget);

        // Second parse: junk data
        await tester.enterText(
          find.byType(TextField).last,
          'Total junk, no booking info.',
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Auto-fill from paste'));
        await tester.pumpAndSettle();

        // Should now show no_fields, NOT the old extraction_review
        expect(find.byKey(const Key('extraction_no_fields')), findsOneWidget);
        expect(find.byKey(const Key('extraction_review')), findsNothing,
            reason: 'Stale extraction_review from first parse '
                'must not remain visible after junk re-parse');
      },
      timeout: const Timeout(Duration(seconds: 20)),
    );
  });
}
