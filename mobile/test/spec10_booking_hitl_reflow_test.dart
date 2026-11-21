// SPEC-10 HITL reflow: the Adjust-this-day sheet after a booking save.
// Written without a local Flutter SDK; CI is the first compile and run.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/booking/add_booking_sheet.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/services/signal_service.dart';

class _FakeSignalService extends Fake implements SignalService {
  @override
  Future<void> emitBookingAdded({
    required String bookingType,
    required String importSource,
    String? placeRef,
    String? tripId,
  }) async {}
}

class _FakeOfflineDatabase extends Fake implements OfflineDatabase {
  @override
  Future<void> cachePlace(
    String placeRef,
    String dataJson, {
    required String identityScope,
  }) async {}
}

class _Call {
  final EventType type;
  final String? targetNodeId;
  final Map<String, dynamic> preferences;
  const _Call(this.type, this.targetNodeId, this.preferences);
}

TripNode _node(
  String id,
  String name,
  DateTime startUtc, {
  String? slot,
  String kind = 'activity',
  String? bookingType,
  bool locked = false,
  int minutes = 60,
}) =>
    TripNode(
      nodeId: id,
      venueName: name,
      scheduledStart: startUtc,
      durationMinutes: minutes,
      isLocked: locked,
      status: NodeStatus.pending,
      vibeTags: const [],
      geoRegion: 'zanzibar_tanzania',
      nodeKind: kind,
      bookingType: bookingType,
      slotName: slot,
    );

// Zanzibar is UTC+3: 06Z morning, 08Z lunch, 11Z afternoon, 14Z dinner, and
// a flight landing at 15Z (18:00 local) on 25 Dec.
final _nodes = [
  _node('m', 'Spice Farm', DateTime.utc(2026, 12, 25, 6), slot: 'morning_tour'),
  _node('l', 'Lukmaan', DateTime.utc(2026, 12, 25, 8), slot: 'lunch'),
  _node('a', 'Old Fort', DateTime.utc(2026, 12, 25, 11), slot: 'afternoon_evening_tour'),
  _node('d', 'Forodhani', DateTime.utc(2026, 12, 25, 14), slot: 'dinner'),
  _node('bk-1', 'ZNZ flight', DateTime.utc(2026, 12, 25, 15),
      kind: 'booking', bookingType: 'flight', locked: true, minutes: 120),
];

const _reflow = BookingReflow(
  bookingNodeId: 'bk-1',
  intents: ['conservative', 'restore_evening', 'keep_open'],
  defaultIntent: 'conservative',
  days: [
    BookingReflowDay(
      localDate: '2026-12-25',
      conservativeSlots: ['dinner'],
      extraNodeIds: ['m', 'l', 'a'],
    ),
  ],
);

class _FakeController extends StateNotifier<ItineraryState>
    implements ItineraryController {
  _FakeController() : super(const ItineraryState());

  final calls = <_Call>[];

  @override
  Future<TripEventResult?> applyEvent({
    required EventType type,
    required String message,
    String? targetNodeId,
    Map<String, dynamic>? preferences,
  }) async {
    calls.add(_Call(type, targetNodeId, Map<String, dynamic>.of(preferences ?? const {})));
    return TripEventResult(
      message: 'ok',
      updatedNodes: _nodes,
      routingTier: 'light',
      fromCache: false,
      bookingReflow: type == EventType.addBooking ? _reflow : null,
    );
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _app(_FakeController controller) {
  return ProviderScope(
    key: UniqueKey(),
    overrides: [
      signalServiceProvider.overrideWithValue(_FakeSignalService()),
      offlineDatabaseProvider.overrideWithValue(_FakeOfflineDatabase()),
      itineraryControllerProvider.overrideWith((ref, tripId) => controller),
    ],
    child: MaterialApp(
      home: Scaffold(
        body: Builder(
          builder: (context) => Center(
            child: TextButton(
              onPressed: () => showModalBottomSheet<void>(
                context: context,
                isScrollControlled: true,
                builder: (_) => AddBookingSheet(
                  tripId: 'trip-1',
                  initialBookingType: 'flight',
                  initialScheduledDate: DateTime(2026, 12, 25, 18),
                ),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ),
  );
}

Future<void> _saveFlight(WidgetTester tester) async {
  await tester.tap(find.text('open'));
  await tester.pumpAndSettle();
  await tester.enterText(find.widgetWithText(TextField, 'Title / Venue'), 'ZNZ flight');
  await tester.pumpAndSettle();
  final save = find.widgetWithText(FilledButton, 'Save Anchor');
  await tester.ensureVisible(save);
  await tester.pumpAndSettle();
  await tester.tap(save);
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('reflow sheet confirm sends one conservative confirm event', (tester) async {
    final c = _FakeController();
    await tester.pumpWidget(_app(c));
    await _saveFlight(tester);

    expect(find.byKey(const Key('booking_reflow_sheet')), findsOneWidget);
    expect(find.text('Adjust this day'), findsOneWidget);
    for (final id in ['m', 'l', 'a']) {
      expect(find.byKey(Key('booking_reflow_skip_$id')), findsOneWidget, reason: id);
    }
    expect(find.byKey(const Key('booking_reflow_skip_d')), findsNothing);
    expect(c.calls, hasLength(1));
    expect(c.calls.first.type, EventType.addBooking);

    await tester.tap(find.byKey(const Key('booking_reflow_confirm')));
    await tester.pumpAndSettle();

    expect(c.calls, hasLength(2));
    expect(c.calls[1].type, EventType.confirmBookingReflow);
    expect(c.calls[1].targetNodeId, 'bk-1');
    expect(c.calls[1].preferences, {'intent': 'conservative'});
    expect(find.byKey(const Key('booking_reflow_sheet')), findsNothing);
    expect(find.text('Save Anchor'), findsNothing);
  });

  testWidgets('reflow sheet Not now sends no second event', (tester) async {
    final c = _FakeController();
    await tester.pumpWidget(_app(c));
    await _saveFlight(tester);
    expect(find.byKey(const Key('booking_reflow_sheet')), findsOneWidget);

    await tester.tap(find.byKey(const Key('booking_reflow_dismiss')));
    await tester.pumpAndSettle();

    expect(c.calls, hasLength(1));
    expect(c.calls.single.type, EventType.addBooking);
    expect(find.byKey(const Key('booking_reflow_sheet')), findsNothing);
    expect(find.text('Save Anchor'), findsNothing);
  });

  testWidgets('selecting keep_open then Confirm sends intent keep_open', (tester) async {
    final c = _FakeController();
    await tester.pumpWidget(_app(c));
    await _saveFlight(tester);

    await tester.tap(find.byKey(const Key('booking_reflow_intent_keep_open')));
    await tester.pumpAndSettle();
    // keep_open also previews the dinner stop.
    expect(find.byKey(const Key('booking_reflow_skip_d')), findsOneWidget);

    await tester.tap(find.byKey(const Key('booking_reflow_confirm')));
    await tester.pumpAndSettle();

    expect(c.calls, hasLength(2));
    expect(c.calls[1].type, EventType.confirmBookingReflow);
    expect(c.calls[1].preferences, {'intent': 'keep_open'});
  });
}
