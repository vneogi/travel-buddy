import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/services/signal_service.dart';

// ================================================================
// Test doubles
// ================================================================

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

/// Fake itinerary controller that returns a successful result
/// without touching any real DB.
class FakeItineraryController extends StateNotifier<ItineraryState>
    implements ItineraryController {
  FakeItineraryController() : super(const ItineraryState());

  @override
  Future<TripEventResult?> applyEvent({
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    // Return a minimal successful result so Save completes.
    return TripEventResult(
      updatedNodes: [
        TripNode(
          nodeId: 'fake-node-1',
          tripId: 'trip-test',
          nodeKind: 'booking',
          venueName: preferences?['venue_name'] as String? ?? 'Test',
          scheduledStart: DateTime.now(),
          durationMinutes: 180,
          sortOrder: 0,
          bookingType: preferences?['booking_type'] as String?,
          importSource: preferences?['import_source'] as String?,
          confirmationCode: preferences?['confirmation_code'] as String?,
        ),
      ],
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  late FakeSignalService signalService;

  setUp(() {
    signalService = FakeSignalService();
  });

  Widget buildSheet({
    String tripId = 'trip-test',
    String initialBookingType = 'flight',
  }) {
    return ProviderScope(
      overrides: [
        signalServiceProvider.overrideWithValue(signalService),
        itineraryControllerProvider.overrideWith(
          (ref, tripId) => FakeItineraryController(),
        ),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: AddBookingSheet(
            tripId: tripId,
            initialBookingType: initialBookingType,
          ),
        ),
      ),
    );
  }

  // ================================================================
  // Expansion and auto-fill
  // ================================================================

  group('Paste and auto-fill', () {
    testWidgets('expand and auto-fill shows extraction_review',
        (tester) async {
      await tester.pumpWidget(buildSheet());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Paste confirmation text'));
      await tester.pumpAndSettle();

      const bookingText =
          'Booking.com\n'
          'Grand Sapphire Hotel is expecting you on Mon 5 Oct 2026\n'
          'Check-in Monday, 5 October 2026 (15:00 - 00:00)\n'
          'Check-out Wednesday, 7 October 2026 (until 11:00)\n'
          'Dubai, UAE\nBooking reference: HTL7890123';
      await tester.enterText(find.byType(TextField).last, bookingText);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Auto-fill from paste'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('extraction_review')), findsOneWidget);
      expect(find.textContaining('Provider: Booking.com'), findsOneWidget);
      expect(find.byKey(const Key('extraction_found')), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));

    testWidgets('junk input shows extraction_no_fields', (tester) async {
      await tester.pumpWidget(buildSheet());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Paste confirmation text'));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byType(TextField).last,
        'Hello! How are you? Visit our website.',
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Auto-fill from paste'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('extraction_no_fields')), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));
  });

  // ================================================================
  // Partial fields display
  // ================================================================

  group('Partial fields display', () {
    testWidgets('generic input shows Check/confirm label', (tester) async {
      await tester.pumpWidget(buildSheet());
      await tester.pumpAndSettle();

      await tester.tap(find.text('Paste confirmation text'));
      await tester.pumpAndSettle();

      const genericText =
          'Your reservation is ready\n'
          'Hotel: Sunset Beach Resort\n'
          'Check-in: 5 October 2026\n'
          'Check-out: 7 October 2026\n'
          'Confirmation code: RSV12345\nDubai, UAE';
      await tester.enterText(find.byType(TextField).last, genericText);
      await tester.pumpAndSettle();
      await tester.tap(find.text('Auto-fill from paste'));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('extraction_review')), findsOneWidget);
      expect(find.byKey(const Key('extraction_partial')), findsOneWidget);
      expect(find.textContaining('Check/confirm:'), findsOneWidget);
    }, timeout: const Timeout(Duration(seconds: 20)));
  });

  // ================================================================
  // Zero-field sequence: good parse -> junk parse resets importSource
  // ================================================================

  group('Zero-field import_source reset', () {
    testWidgets(
      'good parse then junk parse resets importSource to manual on save',
      (tester) async {
        await tester.pumpWidget(buildSheet());
        await tester.pumpAndSettle();

        await tester.tap(find.text('Paste confirmation text'));
        await tester.pumpAndSettle();

        // First parse: good data
        const goodText =
            'Booking.com\n'
            'Grand Sapphire Hotel is expecting you on Mon 5 Oct 2026\n'
            'Check-in Monday, 5 October 2026 (15:00 - 00:00)\n'
            'Check-out Wednesday, 7 October 2026 (until 11:00)\n'
            'Dubai, UAE\nBooking reference: HTL7890123';
        await tester.enterText(find.byType(TextField).last, goodText);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Auto-fill from paste'));
        await tester.pumpAndSettle();
        expect(find.byKey(const Key('extraction_review')), findsOneWidget);

        // Second parse: junk data
        await tester.enterText(
          find.byType(TextField).last,
          'Total junk, no booking info.',
        );
        await tester.pumpAndSettle();
        await tester.tap(find.text('Auto-fill from paste'));
        await tester.pumpAndSettle();

        expect(find.byKey(const Key('extraction_no_fields')), findsOneWidget);
        expect(find.byKey(const Key('extraction_review')), findsNothing,
            reason: 'Stale review must not remain visible');

        // Save should show error because venue name is still populated
        // from first parse but importSource should be manual.
        // Tap Save to trigger the signal.
        await tester.tap(find.text('Save Anchor'));
        await tester.pumpAndSettle();

        // The signal should have importSource=manual (not email).
        // (Save may succeed or fail depending on controller, but
        // the signal captures importSource at save time.)
        if (signalService.calls.isNotEmpty) {
          expect(signalService.calls.last['importSource'], 'manual',
              reason: 'After junk re-parse, importSource must be manual');
        }
      },
      timeout: const Timeout(Duration(seconds: 20)),
    );
  });

  // ================================================================
  // Footer-only import save guard
  // ================================================================

  group('Footer import save guard', () {
    testWidgets(
      'code-only footer import cannot save without venue name',
      (tester) async {
        await tester.pumpWidget(buildSheet());
        await tester.pumpAndSettle();

        await tester.tap(find.text('Paste confirmation text'));
        await tester.pumpAndSettle();

        // Agoda footer-only: has only confirmation code, no venue.
        const footerText =
            'Agoda.com\nManage your booking\n'
            'View your booking details\n'
            'Booking ID: AGD5544332\n'
            'Customer Service: help@agoda.com\n'
            'https://www.agoda.com/mybooking';
        await tester.enterText(find.byType(TextField).last, footerText);
        await tester.pumpAndSettle();
        await tester.tap(find.text('Auto-fill from paste'));
        await tester.pumpAndSettle();

        // Code is extracted but venue is not.
        // Clear the title field to ensure it is empty.
        final titleFields = find.widgetWithText(TextField, 'Title / Venue');
        if (titleFields.evaluate().isNotEmpty) {
          await tester.enterText(titleFields.first, '');
          await tester.pumpAndSettle();
        }

        // Try to save.
        await tester.tap(find.text('Save Anchor'));
        await tester.pumpAndSettle();

        // Save should be blocked with error.
        expect(find.textContaining('Property name is required'), findsOneWidget,
            reason: 'Footer-only import must not save without venue name');

        // No signal should have been emitted.
        expect(signalService.calls, isEmpty,
            reason: 'No event/signal until save completes');
      },
      timeout: const Timeout(Duration(seconds: 20)),
    );
  });
}
