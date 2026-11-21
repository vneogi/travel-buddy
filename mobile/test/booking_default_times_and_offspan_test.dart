// Booking defaults (Part A) and cards for dates outside the trip span
// (Part B). SPEC-10 "Decision: default hotel times", SPEC-42 "Decision:
// nodes outside the span". Rule 13 tests use Z-suffixed instants only so
// results do not depend on the machine's time zone.
//
// Written without a local Flutter SDK; CI is the first compile and run.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/itinerary/date_scope.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

// ---------------------------------------------------------------------------
// Sheet fakes (pattern from spec_g0_booking_city_test.dart)
// ---------------------------------------------------------------------------

class _FakeSignalService extends Fake implements SignalService {
  @override
  Future<void> emitBookingAdded({
    required String bookingType,
    required String importSource,
    String? placeRef,
    String? tripId,
  }) async {}
}

class _FakeItineraryController extends StateNotifier<ItineraryState>
    implements ItineraryController {
  _FakeItineraryController([ItineraryState? initial])
      : super(initial ?? const ItineraryState());

  final saved = <Map<String, dynamic>>[];

  @override
  Future<TripEventResult?> applyEvent({
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    saved.add(Map<String, dynamic>.of(preferences ?? const {}));
    return TripEventResult(
      message: 'Booking saved as a locked itinerary anchor.',
      updatedNodes: const [],
      routingTier: 'heavy',
      fromCache: false,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeOfflineDatabase extends Fake implements OfflineDatabase {
  @override
  Future<void> cachePlace(
    String placeRef,
    String dataJson, {
    required String identityScope,
  }) async {}
}

Widget _sheet(
  _FakeItineraryController controller, {
  String type = 'flight',
  TripNode? editNode,
  DateTime? initial,
}) {
  // A fresh tree per call: Save pops the only route, so a second pumpWidget
  // in the same test must not reuse the emptied MaterialApp navigator.
  return ProviderScope(
    key: UniqueKey(),
    overrides: [
      signalServiceProvider.overrideWithValue(_FakeSignalService()),
      offlineDatabaseProvider.overrideWithValue(_FakeOfflineDatabase()),
      itineraryControllerProvider.overrideWith((ref, tripId) => controller),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: AddBookingSheet(
          tripId: 'trip-1',
          initialBookingType: type,
          editNode: editNode,
          initialScheduledDate: initial,
        ),
      ),
    ),
  );
}

/// Trip whose creation context starts on [date] (yyyy-mm-dd).
ItineraryState _tripStarting(String date) => ItineraryState(
      creationContext: CreationContext(startDateLocal: date, endDateLocal: date),
    );

TripNode _editBooking(String type, DateTime startUtc, int minutes) => TripNode(
      nodeId: 'edit-1',
      venueName: 'Test Booking',
      scheduledStart: startUtc,
      durationMinutes: minutes,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: 'zanzibar_tanzania',
      nodeKind: 'booking',
      bookingType: type,
    );

DateTime _dateOnly(DateTime d) => DateTime(d.year, d.month, d.day);

DateTime _savedStart(_FakeItineraryController c) =>
    DateTime.parse(c.saved.last['scheduled_start'] as String);

Future<void> _enterTitle(WidgetTester tester, String name) async {
  await tester.enterText(find.widgetWithText(TextField, 'Title / Venue'), name);
  await tester.pumpAndSettle();
}

Future<void> _save(WidgetTester tester, {String label = 'Save Anchor'}) async {
  final button = find.widgetWithText(FilledButton, label);
  await tester.ensureVisible(button);
  await tester.pumpAndSettle();
  await tester.tap(button);
  await tester.pumpAndSettle();
}

Future<void> _openTile(WidgetTester tester, String title) async {
  final tile = find.widgetWithText(ListTile, title);
  await tester.ensureVisible(tile);
  await tester.pumpAndSettle();
  await tester.tap(tile);
  await tester.pumpAndSettle();
}

Finder _inDatePicker(Finder f) =>
    find.descendant(of: find.byType(DatePickerDialog), matching: f);

Finder _inTimePicker(Finder f) =>
    find.descendant(of: find.byType(TimePickerDialog), matching: f);

/// Tap [day] in the open date picker, then OK.
Future<void> _pickDay(WidgetTester tester, int day) async {
  await tester.tap(_inDatePicker(find.text('$day')));
  await tester.pumpAndSettle();
  await tester.tap(_inDatePicker(find.text('OK')));
  await tester.pumpAndSettle();
}

DateTime? _datePickerInitial(WidgetTester tester) =>
    tester.widget<DatePickerDialog>(find.byType(DatePickerDialog)).initialDate;

Finder _tileText(String tile, String text) => find.descendant(
      of: find.widgetWithText(ListTile, tile),
      matching: find.textContaining(text),
    );

// ---------------------------------------------------------------------------
// Timeline harness (pattern from spec31_widget_test.dart)
// ---------------------------------------------------------------------------

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

class _MockSignalService extends Mock implements SignalService {}

void _stubDatabase(_MockOfflineDatabase database) {
  when(() => database.getLovedPlaceRefs(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.getNodeOutcomes(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String, NodeOutcome>{});
  when(() => database.cachePlace(any(), any(), identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async {});
  when(() => database.cacheTrip(any(), any(), identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async {});
  when(() => database.getCachedTrip(any(), identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async => null);
  when(() => database.pruneAlertData()).thenAnswer((_) async {});
  when(() => database.getDismissedAlertIds(
        identityScope: any(named: 'identityScope'),
      )).thenAnswer((_) async => <String>{});
}

class _TimelineHarness {
  final ProviderContainer container;
  final void Function() closeSubscription;

  _TimelineHarness._(this.container, this.closeSubscription);

  static Future<_TimelineHarness> create(TripState trip) async {
    final database = _MockOfflineDatabase();
    final repository = _MockTripRepository();
    final api = _MockApiClient();
    _stubDatabase(database);
    when(() => repository.getTrip(trip.tripId)).thenAnswer((_) async => trip);
    when(() => api.get(any(), query: any(named: 'query'))).thenAnswer(
      (invocation) async {
        final path = invocation.positionalArguments.first as String;
        if (path.endsWith('/alerts')) {
          return {
            'trip_id': trip.tripId,
            'status': 'unconfigured',
            'alerts': <Object>[],
            'refreshed_at': '2026-08-31T12:00:00.000Z',
          };
        }
        return {
          'user_id': 'user-1',
          'tier': 'free',
          'daily_reroutes_used': 0,
          'daily_reroutes_remaining': 3,
          'max_daily_reroutes': 3,
        };
      },
    );
    final container = ProviderContainer(
      overrides: [
        tripRepoProvider.overrideWithValue(repository),
        apiClientProvider.overrideWithValue(api),
        offlineDatabaseProvider.overrideWithValue(database),
        identityCacheScopeProvider.overrideWithValue('account:user-1'),
        signalServiceProvider.overrideWithValue(_MockSignalService()),
      ],
    );
    final loaded = Completer<void>();
    final subscription = container.listen(
      itineraryControllerProvider(trip.tripId),
      (_, next) {
        if (!next.loading && !loaded.isCompleted) loaded.complete();
      },
      fireImmediately: true,
    );
    await loaded.future;
    return _TimelineHarness._(container, subscription.close);
  }

  Future<void> pump(WidgetTester tester, String tripId) async {
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: container,
        child: MaterialApp(home: ItineraryScreen(tripId: tripId)),
      ),
    );
    await tester.pump();
    await tester.pump();
  }

  void dispose() {
    closeSubscription();
    container.dispose();
  }
}

/// Node with no geoRegion: toDestinationLocal falls back to device-local, so
/// local DateTime inputs group on their own calendar date on any machine.
TripNode _spanNode(
  String id,
  DateTime start, {
  String kind = 'activity',
  String? bookingType,
  int minutes = 60,
  String? region,
}) =>
    TripNode(
      nodeId: id,
      venueName: id,
      venueId: '$id-ref',
      scheduledStart: start,
      durationMinutes: minutes,
      isLocked: kind == 'booking',
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: kind,
      bookingType: bookingType,
      geoRegion: region,
    );

List<DateTime> _dates(List<ItineraryDayGroup> groups) =>
    groups.map((g) => g.date).toList();

void main() {
  // -------------------------------------------------------------------------
  // Part A: default times
  // -------------------------------------------------------------------------
  group('Part A: booking default times', () {
    testWidgets('new hotel saves 12:00 check-in and 11:00 check-out on the next day',
        (tester) async {
      final c = _FakeItineraryController();
      await tester.pumpWidget(_sheet(c, type: 'hotel'));
      await tester.pumpAndSettle();
      await _enterTitle(tester, 'Beach Hotel');
      await _save(tester);

      expect(c.saved, hasLength(1));
      final start = _savedStart(c);
      expect([start.hour, start.minute, start.second, start.millisecond], [12, 0, 0, 0]);
      expect(c.saved.last['duration_minutes'], 1380);
    });

    testWidgets('hotel check-in picker opens no time picker', (tester) async {
      final c = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(c, type: 'hotel'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Check-in');
      expect(find.byType(DatePickerDialog), findsOneWidget);
      await _pickDay(tester, 27);
      expect(find.byType(TimePickerDialog), findsNothing);

      await _enterTitle(tester, 'Beach Hotel');
      await _save(tester);
      expect(_savedStart(c), DateTime(2026, 12, 27, 12));
      expect(find.byType(TimePickerDialog), findsNothing);
    });

    testWidgets('hotel check-out picker opens no time picker', (tester) async {
      final c = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(c, type: 'hotel'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Check-out');
      expect(find.byType(DatePickerDialog), findsOneWidget);
      await _pickDay(tester, 29);
      expect(find.byType(TimePickerDialog), findsNothing);

      await _enterTitle(tester, 'Beach Hotel');
      await _save(tester);
      expect(_savedStart(c), DateTime(2026, 12, 25, 12));
      // Dec 25 12:00 -> Dec 29 11:00.
      expect(c.saved.last['duration_minutes'], 4 * 1440 - 60);
    });

    testWidgets('hotel tiles show the fixed times', (tester) async {
      final c = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(c, type: 'hotel'));
      await tester.pumpAndSettle();
      expect(_tileText('Check-in', '12:00'), findsOneWidget);
      expect(_tileText('Check-out', '11:00'), findsOneWidget);
    });

    testWidgets('editing a hotel keeps stored times until a date is picked',
        (tester) async {
      // Zanzibar (UTC+3): 12:00Z is 15:00 local, 07:00Z is 10:00 local.
      final checkin = DateTime.parse('2026-12-25T12:00:00Z');
      final checkout = DateTime.parse('2026-12-28T07:00:00Z');
      final minutes = checkout.difference(checkin).inMinutes;
      final node = _editBooking('hotel', checkin, minutes);

      final c1 = _FakeItineraryController();
      await tester.pumpWidget(_sheet(c1, type: 'hotel', editNode: node));
      await tester.pumpAndSettle();
      await _save(tester, label: 'Save Changes');
      expect(c1.saved.last['scheduled_start'], '2026-12-25T15:00:00.000');
      expect(c1.saved.last['duration_minutes'], minutes);
      final savedCheckout =
          _savedStart(c1).add(Duration(minutes: c1.saved.last['duration_minutes'] as int));
      expect([savedCheckout.day, savedCheckout.hour, savedCheckout.minute], [28, 10, 0]);

      final c2 = _FakeItineraryController();
      await tester.pumpWidget(_sheet(c2, type: 'hotel', editNode: node));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Check-in');
      await _pickDay(tester, 26);
      await _save(tester, label: 'Save Changes');
      expect(c2.saved.last['scheduled_start'], '2026-12-26T12:00:00.000');
    });

    testWidgets('new flight starts at 12:00 not the clock', (tester) async {
      final c = _FakeItineraryController();
      await tester.pumpWidget(_sheet(c, type: 'flight'));
      await tester.pumpAndSettle();
      await _enterTitle(tester, 'ZNZ flight');
      await _save(tester);
      final start = _savedStart(c);
      expect([start.hour, start.minute, start.second, start.millisecond], [12, 0, 0, 0]);
    });

    testWidgets('flight keeps date and time pickers', (tester) async {
      final c = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(c, type: 'flight'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Date & Time');
      expect(find.byType(DatePickerDialog), findsOneWidget);
      expect(find.byType(TimePickerDialog), findsNothing);
      await tester.tap(_inDatePicker(find.text('OK')));
      await tester.pumpAndSettle();
      expect(find.byType(TimePickerDialog), findsOneWidget);
    });

    testWidgets('initialScheduledDate is used exactly as given', (tester) async {
      for (final type in ['hotel', 'flight']) {
        final c = _FakeItineraryController(_tripStarting('2026-12-25'));
        await tester.pumpWidget(_sheet(c, type: type, initial: DateTime(2026, 10, 6, 15, 0)));
        await tester.pumpAndSettle();
        await _enterTitle(tester, 'Booking $type');
        await _save(tester);
        expect(_savedStart(c), DateTime(2026, 10, 6, 15, 0), reason: type);
      }
    });

    testWidgets('dismissing the flight time picker keeps the current time',
        (tester) async {
      final c = _FakeItineraryController();
      await tester.pumpWidget(
          _sheet(c, type: 'flight', initial: DateTime(2026, 12, 25, 15, 0)));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Date & Time');
      await _pickDay(tester, 28);
      expect(find.byType(TimePickerDialog), findsOneWidget);
      await tester.tap(_inTimePicker(find.text('Cancel')));
      await tester.pumpAndSettle();

      await _enterTitle(tester, 'ZNZ flight');
      await _save(tester);
      final start = _savedStart(c);
      expect([start.hour, start.minute], [15, 0]);
    });
  });

  // -------------------------------------------------------------------------
  // Part A: default date and calendar month
  // -------------------------------------------------------------------------
  group('Part A: tripFirstLocalDate', () {
    TripNode node(String id, DateTime start, String? region) => TripNode(
          nodeId: id,
          venueName: id,
          scheduledStart: start,
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
          geoRegion: region,
        );

    test('tripFirstLocalDate prefers the creation context start date', () {
      final first = tripFirstLocalDate(
        creationContext: const CreationContext(startDateLocal: '2026-12-25'),
        segments: const [
          TripSegment(geoRegion: 'zanzibar_tanzania', startsOn: '2026-12-20', endsOn: '2026-12-22'),
        ],
        nodes: [node('n1', DateTime.parse('2026-12-01T09:00:00Z'), 'zanzibar_tanzania')],
      );
      expect(first, DateTime(2026, 12, 25));
    });

    test('tripFirstLocalDate uses the earliest segment start, not the first listed', () {
      final first = tripFirstLocalDate(
        segments: const [
          TripSegment(geoRegion: 'nungwi_tanzania', startsOn: '2026-12-28', endsOn: '2026-12-30'),
          TripSegment(geoRegion: 'zanzibar_tanzania', startsOn: '2026-12-25', endsOn: '2026-12-27'),
        ],
      );
      expect(first, DateTime(2026, 12, 25));
    });

    test('tripFirstLocalDate falls back to the earliest node in destination-local time', () {
      // 22:30Z on Dec 24 is 01:30 on Dec 25 in Zanzibar (UTC+3).
      final first = tripFirstLocalDate(
        nodes: [
          node('later', DateTime.parse('2026-12-27T10:00:00Z'), 'zanzibar_tanzania'),
          node('earliest', DateTime.parse('2026-12-24T22:30:00Z'), 'zanzibar_tanzania'),
        ],
      );
      expect(first, DateTime(2026, 12, 25));
    });

    test('tripFirstLocalDate returns null for a trip with no dates or nodes', () {
      expect(tripFirstLocalDate(), isNull);
      expect(tripFirstLocalDate(creationContext: const CreationContext()), isNull);
    });
  });

  group('Part A: calendar opens on the trip', () {
    testWidgets("add booking calendar opens on the trip's first day", (tester) async {
      final c = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(c, type: 'flight'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Date & Time');
      expect(_dateOnly(_datePickerInitial(tester)!), DateTime(2026, 12, 25));
    });

    testWidgets('hotel check-in calendar opens on the first day and check-out on the next day',
        (tester) async {
      final c = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(c, type: 'hotel'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Check-in');
      expect(_dateOnly(_datePickerInitial(tester)!), DateTime(2026, 12, 25));
      await tester.tap(_inDatePicker(find.text('Cancel')));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Check-out');
      expect(_dateOnly(_datePickerInitial(tester)!), DateTime(2026, 12, 26));
    });

    testWidgets('calendar does not assert when the trip started in the past',
        (tester) async {
      final c = _FakeItineraryController(_tripStarting('2020-03-10'));
      await tester.pumpWidget(_sheet(c, type: 'flight'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Date & Time');
      expect(tester.takeException(), isNull);
      expect(find.byType(DatePickerDialog), findsOneWidget);
      expect(_dateOnly(_datePickerInitial(tester)!), DateTime(2020, 3, 10));
    });

    testWidgets('picking a different day overrides the default and keeps the time rule',
        (tester) async {
      final flight = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(flight, type: 'flight'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Date & Time');
      await _pickDay(tester, 28);
      await tester.tap(_inTimePicker(find.text('OK')));
      await tester.pumpAndSettle();
      await _enterTitle(tester, 'ZNZ flight');
      await _save(tester);
      expect(_savedStart(flight), DateTime(2026, 12, 28, 12));

      final hotel = _FakeItineraryController(_tripStarting('2026-12-25'));
      await tester.pumpWidget(_sheet(hotel, type: 'hotel'));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Check-in');
      await _pickDay(tester, 28);
      await _enterTitle(tester, 'Beach Hotel');
      await _save(tester);
      expect(_savedStart(hotel), DateTime(2026, 12, 28, 12));
      expect(hotel.saved.last['duration_minutes'], 1380);
    });

    testWidgets('no trip dates falls back to tomorrow at 12:00', (tester) async {
      final c = _FakeItineraryController();
      await tester.pumpWidget(_sheet(c, type: 'flight'));
      await tester.pumpAndSettle();
      await _enterTitle(tester, 'ZNZ flight');
      await _save(tester);
      final start = _savedStart(c);
      expect(_dateOnly(start).isAfter(_dateOnly(DateTime.now())), isTrue);
      expect([start.hour, start.minute, start.second, start.millisecond], [12, 0, 0, 0]);
    });
  });

  // -------------------------------------------------------------------------
  // Part A: edit-mode wall time (rule 13)
  // -------------------------------------------------------------------------
  group('Part A: edit-mode wall time', () {
    final checkin = DateTime.parse('2026-12-24T23:02:00Z');
    const fourNights = 4 * 1440;

    testWidgets('edit sheet shows destination-local time, not UTC', (tester) async {
      final c = _FakeItineraryController();
      await tester.pumpWidget(
          _sheet(c, type: 'hotel', editNode: _editBooking('hotel', checkin, fourNights)));
      await tester.pumpAndSettle();
      expect(_tileText('Check-in', '25/12/2026 02:02'), findsOneWidget);
      expect(_tileText('Check-out', '29/12/2026 02:02'), findsOneWidget);
    });

    testWidgets('edit save without changes keeps the same instant', (tester) async {
      final c = _FakeItineraryController();
      await tester.pumpWidget(
          _sheet(c, type: 'hotel', editNode: _editBooking('hotel', checkin, fourNights)));
      await tester.pumpAndSettle();
      await _save(tester, label: 'Save Changes');

      final sent = c.saved.last['scheduled_start'] as String;
      expect(sent, '2026-12-25T02:02:00.000');
      expect(sent.endsWith('Z'), isFalse);
      expect(c.saved.last['duration_minutes'], fourNights);
      // Read the naive payload as Zanzibar wall time (UTC+3).
      final wall = DateTime.parse(sent);
      final instant = DateTime.utc(wall.year, wall.month, wall.day, wall.hour,
              wall.minute, wall.second, wall.millisecond)
          .subtract(const Duration(hours: 3));
      expect(instant, checkin);
    });

    testWidgets('edit flight time picker opens on destination-local time',
        (tester) async {
      final c = _FakeItineraryController();
      final flight = _editBooking('flight', DateTime.parse('2026-12-26T06:09:00Z'), 180);
      await tester.pumpWidget(_sheet(c, type: 'flight', editNode: flight));
      await tester.pumpAndSettle();
      await _openTile(tester, 'Date & Time');
      await tester.tap(_inDatePicker(find.text('OK')));
      await tester.pumpAndSettle();
      final picker = tester.widget<TimePickerDialog>(find.byType(TimePickerDialog));
      expect(picker.initialTime, const TimeOfDay(hour: 9, minute: 9));
    });
  });

  // -------------------------------------------------------------------------
  // Part B: cards for dates outside the span
  // -------------------------------------------------------------------------
  group('Part B: spanAwareDayGroups outside the span', () {
    final spanStart = DateTime(2026, 12, 25);
    final spanEnd = DateTime(2026, 12, 27);

    test('node before the span start gets its own earlier group', () {
      final groups = spanAwareDayGroups(
        nodes: [
          _spanNode('flight', DateTime(2026, 12, 24, 19, 6), kind: 'booking', bookingType: 'flight'),
          _spanNode('museum', DateTime(2026, 12, 25, 10)),
        ],
        startLocal: spanStart,
        endLocal: spanEnd,
      );
      expect(_dates(groups), [
        DateTime(2026, 12, 24),
        DateTime(2026, 12, 25),
        DateTime(2026, 12, 26),
        DateTime(2026, 12, 27),
      ]);
      expect(groups.first.nodes.single.nodeId, 'flight');
    });

    test('node after the span end gets its own later group', () {
      final groups = spanAwareDayGroups(
        nodes: [
          _spanNode('museum', DateTime(2026, 12, 25, 10)),
          _spanNode('tour', DateTime(2026, 12, 29, 9), kind: 'booking', bookingType: 'tour'),
        ],
        startLocal: spanStart,
        endLocal: spanEnd,
      );
      expect(_dates(groups), [
        DateTime(2026, 12, 25),
        DateTime(2026, 12, 26),
        DateTime(2026, 12, 27),
        DateTime(2026, 12, 29),
      ]);
      expect(groups.last.nodes.single.nodeId, 'tour');
    });

    test('no empty dates are invented outside the span', () {
      final groups = spanAwareDayGroups(
        nodes: [
          _spanNode('flight', DateTime(2026, 12, 20, 8), kind: 'booking', bookingType: 'flight'),
        ],
        startLocal: spanStart,
        endLocal: spanEnd,
      );
      expect(_dates(groups), [
        DateTime(2026, 12, 20),
        DateTime(2026, 12, 25),
        DateTime(2026, 12, 26),
        DateTime(2026, 12, 27),
      ]);
      expect(groups.skip(1).every((g) => g.nodes.isEmpty), isTrue);
    });

    test('nodes inside the span behave as before', () {
      final groups = spanAwareDayGroups(
        nodes: [
          _spanNode('a', DateTime(2026, 12, 25, 9)),
          _spanNode('b', DateTime(2026, 12, 27, 18)),
        ],
        startLocal: spanStart,
        endLocal: spanEnd,
      );
      expect(_dates(groups), [
        DateTime(2026, 12, 25),
        DateTime(2026, 12, 26),
        DateTime(2026, 12, 27),
      ]);
      expect(groups[0].nodes.single.nodeId, 'a');
      expect(groups[1].nodes, isEmpty);
      expect(groups[2].nodes.single.nodeId, 'b');
    });

    test('corridor segment includes a matching node dated before its start', () {
      // Zanzibar (UTC+3): 16:06Z on Dec 24 is 19:06 local, 07:00Z is 10:00.
      final cityGroups = spanAwareCorridorGroups(
        nodes: [
          _spanNode('flight', DateTime.parse('2026-12-24T16:06:00Z'),
              kind: 'booking', bookingType: 'flight', region: 'zanzibar_tanzania'),
          _spanNode('museum', DateTime.parse('2026-12-25T07:00:00Z'),
              region: 'zanzibar_tanzania'),
        ],
        segments: const [
          TripSegment(geoRegion: 'zanzibar_tanzania', startsOn: '2026-12-25', endsOn: '2026-12-27'),
        ],
      );
      expect(cityGroups, hasLength(1));
      final dayGroups = cityGroups.single.dayGroups;
      expect(_dates(dayGroups), [
        DateTime(2026, 12, 24),
        DateTime(2026, 12, 25),
        DateTime(2026, 12, 26),
        DateTime(2026, 12, 27),
      ]);
      expect(dayGroups.first.nodes.single.nodeId, 'flight');
    });

    test('hotel stay that starts before the span shows on each covered date', () {
      // Check-in Dec 23 12:00, check-out Dec 26 11:00: nights of 23, 24, 25.
      final hotel = _spanNode('hotel', DateTime(2026, 12, 23, 12),
          kind: 'booking', bookingType: 'hotel', minutes: 3 * 1440 - 60);
      final groups = spanAwareDayGroups(
        nodes: [hotel],
        startLocal: spanStart,
        endLocal: spanEnd,
      );
      expect(_dates(groups), [
        DateTime(2026, 12, 23),
        DateTime(2026, 12, 24),
        DateTime(2026, 12, 25),
        DateTime(2026, 12, 26),
        DateTime(2026, 12, 27),
      ]);
      for (final g in groups.take(3)) {
        expect(g.nodes.single.nodeId, 'hotel', reason: '${g.date}');
      }
      expect(groups[3].nodes, isEmpty);
      expect(groups[4].nodes, isEmpty);
    });
  });

  group('Part B: timeline', () {
    testWidgets('timeline renders a card for a booking the day before the trip',
        (tester) async {
      final harness = await _TimelineHarness.create(TripState(
        tripId: 'trip-1',
        userId: 'user-1',
        creationContext: const CreationContext(
          startDateLocal: '2026-12-25',
          endDateLocal: '2026-12-27',
        ),
        nodes: [
          _spanNode('Arrival Flight', DateTime(2026, 12, 24, 19, 6),
              kind: 'booking', bookingType: 'flight'),
          _spanNode('Stone Town Walk', DateTime(2026, 12, 25, 10)),
        ],
      ));
      addTearDown(harness.dispose);
      await harness.pump(tester, 'trip-1');

      expect(find.text('Thursday, 24 December 2026'), findsOneWidget);
      expect(
        find.descendant(of: find.byType(ActivityCard), matching: find.text('Arrival Flight')),
        findsOneWidget,
      );
    }, timeout: const Timeout(Duration(seconds: 20)));
  });
}
