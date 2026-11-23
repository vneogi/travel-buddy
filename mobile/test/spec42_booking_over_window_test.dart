// SPEC-42 booking over an active excursion: the booking sheet shows the
// server's typed refusal (ValidationException) and keeps the fixed copy for
// every other failure. Written without a local Flutter SDK; CI is the first
// compile and run.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';

const _kTripId = 'trip-bow-1';
const _kFixedCopy =
    'Could not save this booking. Check your connection and try again.';
const _kRefusal = 'This overlaps Prison Island (morning, 2026-12-27). '
    'Cancel the excursion first, then add the booking.';

/// Real ItineraryController path: getTrip fails (so load() takes its offline
/// fallback and finds nothing), and sendEvent throws the given error.
class _FakeRepo extends Fake implements TripRepository {
  final Object error;
  int sends = 0;
  _FakeRepo(this.error);

  @override
  Future<TripState> getTrip(String tripId) async => throw const NetworkException();

  @override
  Future<TripEventResult> sendEvent({
    required String tripId,
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    sends++;
    throw error;
  }
}

class _FakeOfflineDatabase extends Fake implements OfflineDatabase {
  @override
  Future<String?> getCachedTrip(
    String tripId, {
    required String identityScope,
  }) async =>
      null;
}

class _FakeSignalService extends Fake implements SignalService {}

Widget _app(_FakeRepo repo) => ProviderScope(
      key: UniqueKey(),
      overrides: [
        tripRepoProvider.overrideWithValue(repo),
        offlineDatabaseProvider.overrideWithValue(_FakeOfflineDatabase()),
        identityCacheScopeProvider.overrideWithValue('anonymous:test'),
        signalServiceProvider.overrideWithValue(_FakeSignalService()),
      ],
      child: MaterialApp(
        home: Scaffold(
          // Keeps the controller alive, as the itinerary screen does behind
          // the real modal sheet.
          body: Consumer(
            builder: (context, ref, _) {
              ref.watch(itineraryControllerProvider(_kTripId));
              return const AddBookingSheet(
                tripId: _kTripId,
                initialBookingType: 'tour',
              );
            },
          ),
        ),
      ),
    );

void _tallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(2400, 4800);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

Future<void> _saveTour(WidgetTester tester) async {
  await tester.enterText(find.widgetWithText(TextField, 'Title / Venue'), 'Spice tour');
  await tester.pumpAndSettle();
  final save = find.text('Save Anchor');
  await tester.ensureVisible(save);
  await tester.pumpAndSettle();
  await tester.tap(save);
  await tester.pumpAndSettle();
}

ItineraryState _controllerState(WidgetTester tester) =>
    ProviderScope.containerOf(tester.element(find.byType(AddBookingSheet)))
        .read(itineraryControllerProvider(_kTripId));

void main() {
  testWidgets('a refused save shows the server message and the sheet stays open',
      (tester) async {
    _tallSurface(tester);
    final repo = _FakeRepo(const ValidationException(_kRefusal));
    await tester.pumpWidget(_app(repo));
    await tester.pumpAndSettle();

    await _saveTour(tester);

    expect(repo.sends, 1);
    expect(find.text(_kRefusal), findsOneWidget);
    expect(find.text(_kFixedCopy), findsNothing);
    expect(find.byType(AddBookingSheet), findsOneWidget);
    // The banner behind the sheet is cleared once the sheet shows the text.
    expect(_controllerState(tester).banner, isNull);
    expect(_controllerState(tester).validationMessage, isNull);
  });

  testWidgets('network and unknown failures keep the fixed copy', (tester) async {
    _tallSurface(tester);
    for (final error in <Object>[const NetworkException(), StateError('boom')]) {
      final repo = _FakeRepo(error);
      await tester.pumpWidget(_app(repo));
      await tester.pumpAndSettle();

      await _saveTour(tester);

      expect(repo.sends, 1, reason: '$error');
      expect(find.text(_kFixedCopy), findsOneWidget, reason: '$error');
      expect(find.text(_kRefusal), findsNothing, reason: '$error');
      expect(_controllerState(tester).validationMessage, isNull, reason: '$error');

      // Tear the app down before pumping the next case.
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();
    }
  });
}
