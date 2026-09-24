// SPEC G0 field-fix -- Flutter booking city control proofs.
//
// D1: defaultCityForDate uses _ymd (local dates), not DateTime.parse (UTC).
// D2: Proper stubs copied from spec36_corridor_test.dart patterns.
// D3: Add-mode date-default proof -- scheduledStart Oct 6 defaults to LP.
// F1: City default recomputes when segments arrive asynchronously.
// F2: Sheet-level LP default/save proof via initialScheduledDate.
// F3: FakeSignalService (no mocktail shape mismatch).
//
// UNVERIFIED: flutter test has not been run on this host.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';

// ---------------------------------------------------------------------------
// F3: Fakes (no mocktail matcher mismatch). Pattern from
// mobile/test/features/booking/provider_paste_widget_test.dart.
// ---------------------------------------------------------------------------

/// Fake signal service -- captures calls without mocktail.
class _FakeSignalService extends Fake implements SignalService {
  final calls = <Map<String, String?>>[];

  @override
  Future<void> emitBookingAdded({
    required String bookingType,
    required String importSource,
    String? placeRef,
    String? tripId,
  }) async {
    calls.add({
      'bookingType': bookingType,
      'importSource': importSource,
      'placeRef': placeRef,
      'tripId': tripId,
    });
  }
}

/// Fake itinerary controller seeded with corridor segments.
/// Does not call load(), so no getTrip stub is needed.
class _FakeItineraryController extends StateNotifier<ItineraryState>
    implements ItineraryController {
  _FakeItineraryController({List<TripSegment> segments = const []})
      : super(ItineraryState(segments: segments));

  Map<String, dynamic>? lastPreferences;

  /// Seed segments after construction (for F1 async-load proof).
  void seedSegments(List<TripSegment> segs) {
    state = ItineraryState(segments: segs);
  }

  @override
  Future<TripEventResult?> applyEvent({
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    lastPreferences = preferences;
    return TripEventResult(
      message: 'Booking saved as a locked itinerary anchor.',
      updatedNodes: [
        TripNode(
          nodeId: 'fake-node-1',
          nodeKind: 'booking',
          venueName: preferences?['venue_name'] as String? ?? 'Test',
          scheduledStart: DateTime(2026, 10, 6, 15, 0),
          durationMinutes: 1440,
          isLocked: true,
          status: NodeStatus.pending,
          vibeTags: const [],
          bookingType: preferences?['booking_type'] as String?,
          geoRegion: preferences?['geo_region'] as String?,
        ),
      ],
      routingTier: 'heavy',
      fromCache: false,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Fake offline database -- stubs cachePlace for the save path.
class _FakeOfflineDatabase extends Fake implements OfflineDatabase {
  @override
  Future<void> cachePlace(String placeRef, String dataJson) async {}
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const _kTripId = 'trip-corridor-1';

const _segments = <TripSegment>[
  TripSegment(
    geoRegion: 'vientiane_laos',
    startsOn: '2026-10-02',
    endsOn: '2026-10-03',
  ),
  TripSegment(
    geoRegion: 'vang_vieng_laos',
    startsOn: '2026-10-04',
    endsOn: '2026-10-05',
  ),
  TripSegment(
    geoRegion: 'luang_prabang_laos',
    startsOn: '2026-10-06',
    endsOn: '2026-10-09',
  ),
];

Widget _wrapSheet({
  required _FakeItineraryController controller,
  required _FakeSignalService signalService,
  required _FakeOfflineDatabase database,
  String bookingType = 'hotel',
  TripNode? editNode,
  DateTime? initialScheduledDate,
}) {
  return ProviderScope(
    overrides: [
      signalServiceProvider.overrideWithValue(signalService),
      offlineDatabaseProvider.overrideWithValue(database),
      itineraryControllerProvider.overrideWith(
        (ref, tripId) => controller,
      ),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: AddBookingSheet(
          tripId: _kTripId,
          initialBookingType: bookingType,
          editNode: editNode,
          initialScheduledDate: initialScheduledDate,
        ),
      ),
    ),
  );
}

void main() {
  // ---------------------------------------------------------------------------
  // D1: Unit test -- defaultCityForDate uses local dates
  // ---------------------------------------------------------------------------
  group('defaultCityForDate (top-level, D1)', () {
    test('Oct 6 resolves to LP regardless of device TZ', () {
      final result = defaultCityForDate(DateTime(2026, 10, 6), _segments);
      expect(result, 'luang_prabang_laos');
    });

    test('Oct 2 resolves to VTE', () {
      expect(
        defaultCityForDate(DateTime(2026, 10, 2), _segments),
        'vientiane_laos',
      );
    });

    test('Oct 4 resolves to VV', () {
      expect(
        defaultCityForDate(DateTime(2026, 10, 4), _segments),
        'vang_vieng_laos',
      );
    });

    test('Oct 15 (outside all segments) returns null', () {
      expect(defaultCityForDate(DateTime(2026, 10, 15), _segments), isNull);
    });

    test('Sep 30 (before all segments) returns null', () {
      expect(defaultCityForDate(DateTime(2026, 9, 30), _segments), isNull);
    });
  });

  // ---------------------------------------------------------------------------
  // Widget tests
  // ---------------------------------------------------------------------------
  group('AddBookingSheet corridor city control', () {
    late _FakeItineraryController controller;
    late _FakeSignalService signalService;
    late _FakeOfflineDatabase database;

    setUp(() {
      controller = _FakeItineraryController(segments: _segments);
      signalService = _FakeSignalService();
      database = _FakeOfflineDatabase();
    });

    testWidgets('city control is visible with three segments',
        (tester) async {
      await tester.pumpWidget(_wrapSheet(
        controller: controller,
        signalService: signalService,
        database: database,
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('booking_city_control')), findsOneWidget);
    });

    testWidgets('save button says Save Anchor', (tester) async {
      await tester.pumpWidget(_wrapSheet(
        controller: controller,
        signalService: signalService,
        database: database,
      ));
      await tester.pumpAndSettle();

      expect(find.text('Save Anchor'), findsOneWidget);
    });

    testWidgets('add-mode date outside corridor auto-selects no city',
        (tester) async {
      // Default scheduledStart is now + 24h (outside Oct 2026 corridor).
      await tester.pumpWidget(_wrapSheet(
        controller: controller,
        signalService: signalService,
        database: database,
      ));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('booking_city_control')), findsOneWidget);
      // No segment city name should appear as the selected dropdown value.
      expect(find.text('Vientiane'), findsNothing);
      expect(find.text('Vang Vieng'), findsNothing);
      expect(find.text('Luang Prabang'), findsNothing);
    });

    // F1: Segments arrive after the initial post-frame callback.
    testWidgets('F1: city default recomputes when segments arrive async',
        (tester) async {
      // Start with no segments -- simulates ItineraryController.load()
      // not having completed yet.
      final emptyController = _FakeItineraryController();

      await tester.pumpWidget(_wrapSheet(
        controller: emptyController,
        signalService: signalService,
        database: database,
        // Oct 6 is in the LP segment.
        initialScheduledDate: DateTime(2026, 10, 6, 15, 0),
      ));
      await tester.pumpAndSettle();

      // No segments yet: city control is hidden (segs.length <= 1).
      expect(find.byKey(const Key('booking_city_control')), findsNothing);

      // Simulate segments arriving from getTrip.
      emptyController.seedSegments(_segments.toList());
      await tester.pumpAndSettle();

      // City control now visible.
      expect(find.byKey(const Key('booking_city_control')), findsOneWidget);
      // F1: ref.listen fired and scheduled _recomputeCityDefault.
      // Date is Oct 6, which falls in LP -> auto-selects Luang Prabang.
      expect(find.text('Luang Prabang'), findsOneWidget);
    });

    // F2: Sheet-level LP default/save proof (add-mode, no editNode).
    testWidgets(
        'F2: add-mode Oct 6 check-in defaults to LP and save sends LP',
        (tester) async {
      await tester.pumpWidget(_wrapSheet(
        controller: controller,
        signalService: signalService,
        database: database,
        // F2: inject Oct 6 as the initial scheduled date.
        initialScheduledDate: DateTime(2026, 10, 6, 15, 0),
      ));
      await tester.pumpAndSettle();

      // City control shows Luang Prabang (auto-defaulted, no dropdown tap).
      expect(find.byKey(const Key('booking_city_control')), findsOneWidget);
      expect(find.text('Luang Prabang'), findsOneWidget);

      // Fill required title.
      await tester.enterText(
        find.widgetWithText(TextField, 'Title / Venue'),
        'Queens House Luang Prabang',
      );
      await tester.pumpAndSettle();

      // Scroll Save Anchor into the viewport, then tap.
      final saveButton = find.widgetWithText(FilledButton, 'Save Anchor');
      await tester.ensureVisible(saveButton);
      await tester.pumpAndSettle();
      await tester.tap(saveButton);
      await tester.pumpAndSettle();

      // Verify applyEvent was called with geo_region = LP.
      expect(controller.lastPreferences, isNotNull,
          reason: 'applyEvent must have been called');
      expect(controller.lastPreferences!['geo_region'], 'luang_prabang_laos',
          reason: 'Save must send geo_region=luang_prabang_laos');

      // F3: signal service was called without error.
      expect(signalService.calls, isNotEmpty,
          reason: 'emitBookingAdded must have been called');
    });

    // Explicit manual dropdown test -- user picks LP then saves.
    testWidgets('tap LP in dropdown then Save Anchor sends LP geo_region',
        (tester) async {
      await tester.pumpWidget(_wrapSheet(
        controller: controller,
        signalService: signalService,
        database: database,
      ));
      await tester.pumpAndSettle();

      // Select LP city from the dropdown.
      await tester.tap(find.byKey(const Key('booking_city_control')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Luang Prabang').last);
      await tester.pumpAndSettle();

      // Fill required title.
      await tester.enterText(
        find.widgetWithText(TextField, 'Title / Venue'),
        'Queens House Luang Prabang',
      );
      await tester.pumpAndSettle();

      // Scroll Save Anchor into the viewport, then tap.
      final saveButton = find.widgetWithText(FilledButton, 'Save Anchor');
      await tester.ensureVisible(saveButton);
      await tester.pumpAndSettle();
      await tester.tap(saveButton);
      await tester.pumpAndSettle();

      expect(controller.lastPreferences, isNotNull,
          reason: 'applyEvent must have been called');
      expect(controller.lastPreferences!['geo_region'], 'luang_prabang_laos');
    });
  });
}
