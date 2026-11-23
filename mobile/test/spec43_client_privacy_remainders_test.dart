// SPEC-43 client privacy remainders: booking reference masked by default
// (Gap 5) and optional signals not queued without a grant (Gap 7).
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
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/features/itinerary/itinerary_screen.dart';
import 'package:travel_buddy/offline/offline_database.dart';
import 'package:travel_buddy/offline/sync_engine.dart';
import 'package:travel_buddy/services/signal_service.dart';
import 'package:travel_buddy/widgets/activity_card.dart';

// ---------------------------------------------------------------------------
// Fakes
// ---------------------------------------------------------------------------

/// Outbox that only records enqueue calls (pure Dart, no SQLite).
class _RecordingOutbox extends Fake implements OfflineDatabase {
  final enqueued = <String>[];

  @override
  Future<int> getOutboxSize() async => enqueued.length;

  @override
  Future<void> enqueue(String signalId, String payloadJson, String capturedAt) async {
    enqueued.add(payloadJson);
  }
}

class _NoSync extends Fake implements SyncEngine {
  @override
  void triggerSync() {}
}

SignalService _service(_RecordingOutbox outbox) =>
    SignalService(db: outbox, syncEngine: _NoSync());

/// Any call into the sheet's offline database is recorded (test 7 expects none).
class _RecordingSheetDb implements OfflineDatabase {
  final calls = <Symbol>[];

  @override
  dynamic noSuchMethod(Invocation invocation) {
    calls.add(invocation.memberName);
    return Future<void>.value();
  }
}

class _SheetSignals extends Fake implements SignalService {
  int emits = 0;

  @override
  Future<void> emitBookingAdded({
    required String bookingType,
    required String importSource,
    String? placeRef,
    String? tripId,
  }) async {
    emits++;
  }
}

/// Holds sheet state without load() or network (as in spec_g0).
class _SheetController extends StateNotifier<ItineraryState>
    implements ItineraryController {
  _SheetController() : super(const ItineraryState());

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _MockTripRepository extends Mock implements TripRepository {}

class _MockApiClient extends Mock implements ApiClient {}

class _MockOfflineDatabase extends Mock implements OfflineDatabase {}

// ---------------------------------------------------------------------------
// Booking sheet helpers
// ---------------------------------------------------------------------------

const _kTripId = 'trip-1';
const _kCode = 'RSV12345';

TripNode _booking() => TripNode(
      nodeId: 'bk-1',
      nodeKind: 'booking',
      venueName: 'Sunset Beach Resort',
      scheduledStart: DateTime(2026, 10, 5, 15),
      durationMinutes: 120,
      isLocked: true,
      status: NodeStatus.pending,
      vibeTags: const [],
      bookingType: 'tour',
      confirmationCode: _kCode,
    );

Widget _sheet({TripNode? editNode, OfflineDatabase? db, SignalService? signals}) =>
    ProviderScope(
      key: UniqueKey(),
      overrides: [
        signalServiceProvider.overrideWithValue(signals ?? _SheetSignals()),
        offlineDatabaseProvider.overrideWithValue(db ?? _RecordingSheetDb()),
        itineraryControllerProvider.overrideWith((ref, tripId) => _SheetController()),
      ],
      child: MaterialApp(
        home: Scaffold(
          body: AddBookingSheet(
            tripId: _kTripId,
            initialBookingType: 'tour',
            editNode: editNode,
          ),
        ),
      ),
    );

Finder get _codeField => find.widgetWithText(TextField, 'Confirmation Code');

bool _obscured(WidgetTester tester) => tester.widget<TextField>(_codeField).obscureText;

void _tallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(2400, 4800);
  tester.view.devicePixelRatio = 3.0;
  addTearDown(tester.view.reset);
}

// ---------------------------------------------------------------------------
// Itinerary harness (as in spec31_widget_test), real SignalService on a
// recording outbox.
// ---------------------------------------------------------------------------

Future<({ProviderContainer container, _RecordingOutbox outbox})> _itinerary() async {
  final database = _MockOfflineDatabase();
  final repository = _MockTripRepository();
  final api = _MockApiClient();
  when(() => database.getLovedPlaceRefs(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String>{});
  when(() => database.getNodeOutcomes(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
      )).thenAnswer((_) async => <String, NodeOutcome>{});
  when(() => database.upsertLovedPlace(
        identityScope: any(named: 'identityScope'),
        tripId: any(named: 'tripId'),
        placeRef: any(named: 'placeRef'),
      )).thenAnswer((_) async {});
  when(() => database.cachePlace(any(), any(), identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async {});
  when(() => database.cacheTrip(any(), any(), identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async {});
  when(() => database.getCachedTrip(any(), identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async => null);
  when(() => database.pruneAlertData()).thenAnswer((_) async {});
  when(() => database.getDismissedAlertIds(identityScope: any(named: 'identityScope')))
      .thenAnswer((_) async => <String>{});
  when(() => repository.getTrip(_kTripId)).thenAnswer(
    (_) async => TripState(
      tripId: _kTripId,
      userId: 'user-1',
      nodes: [
        TripNode(
          nodeId: 'a',
          venueName: 'Market',
          venueId: 'a-ref',
          scheduledStart: DateTime(2026, 10, 5, 9),
          durationMinutes: 60,
          isLocked: false,
          status: NodeStatus.pending,
          vibeTags: const [],
        ),
      ],
    ),
  );
  when(() => api.get(any(), query: any(named: 'query'))).thenAnswer((invocation) async {
    final path = invocation.positionalArguments.first as String;
    if (path.endsWith('/alerts')) {
      return {
        'trip_id': _kTripId,
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
  });
  final outbox = _RecordingOutbox();
  final container = ProviderContainer(
    overrides: [
      tripRepoProvider.overrideWithValue(repository),
      apiClientProvider.overrideWithValue(api),
      offlineDatabaseProvider.overrideWithValue(database),
      identityCacheScopeProvider.overrideWithValue('account:user-1'),
      signalServiceProvider.overrideWithValue(_service(outbox)),
    ],
  );
  final loaded = Completer<void>();
  final sub = container.listen(
    itineraryControllerProvider(_kTripId),
    (_, next) {
      if (!next.loading && !loaded.isCompleted) loaded.complete();
    },
    fireImmediately: true,
  );
  await loaded.future;
  addTearDown(() {
    sub.close();
    container.dispose();
  });
  return (container: container, outbox: outbox);
}

void main() {
  setUpAll(() => registerFallbackValue(EventType.askInfo));

  testWidgets('1. the confirmation code renders obscured on open', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_sheet(editNode: _booking()));
    await tester.pumpAndSettle();
    expect(_codeField, findsOneWidget);
    expect(_obscured(tester), isTrue);

    // Revealed, then the sheet is closed and opened again: hidden again.
    await tester.tap(find.byKey(const Key('booking_code_reveal')));
    await tester.pumpAndSettle();
    await tester.pumpWidget(const SizedBox());
    await tester.pumpAndSettle();
    await tester.pumpWidget(_sheet(editNode: _booking()));
    await tester.pumpAndSettle();
    expect(_obscured(tester), isTrue);
  });

  testWidgets('2. the reveal control shows the code, then hides it again', (tester) async {
    _tallSurface(tester);
    await tester.pumpWidget(_sheet(editNode: _booking()));
    await tester.pumpAndSettle();
    final reveal = find.byKey(const Key('booking_code_reveal'));
    final start = _obscured(tester);

    await tester.tap(reveal);
    await tester.pumpAndSettle();
    expect(_obscured(tester), !start);
    expect(find.byTooltip(start ? 'Hide code' : 'Show code'), findsOneWidget);

    await tester.tap(reveal);
    await tester.pumpAndSettle();
    expect(_obscured(tester), start);
    expect(tester.widget<TextField>(_codeField).controller!.text, _kCode);
  });

  test('3. emitUserLoved writes no outbox row', () async {
    final outbox = _RecordingOutbox();
    final before = await outbox.getOutboxSize();
    await _service(outbox).emitUserLoved(placeRef: 'souk-ref', tripId: _kTripId);
    expect(await outbox.getOutboxSize(), before);
  });

  test('4. reroute accepted and rejected write no outbox rows', () async {
    final outbox = _RecordingOutbox();
    final service = _service(outbox);
    await service.emitRerouteAccepted(placeRef: 'a', replacementRef: 'b', tripId: _kTripId);
    await service.emitRerouteRejected(placeRef: 'a', rejectedRefs: const ['c', 'd'], tripId: _kTripId);
    expect(outbox.enqueued, isEmpty);
  });

  test('5. node skipped and visited confirmed still write one row each', () async {
    final outbox = _RecordingOutbox();
    final service = _service(outbox);
    await service.emitNodeSkipped(placeRef: 'a', reason: 'closed', tripId: _kTripId);
    expect(outbox.enqueued, hasLength(1));
    await service.emitVisitedConfirmed(placeRef: 'a', tripId: _kTripId);
    expect(outbox.enqueued, hasLength(2));
    expect(outbox.enqueued.first, contains('node_skipped'));
    expect(outbox.enqueued.last, contains('visited_confirmed'));
  });

  testWidgets('6. love on an itinerary card shows loved and writes no outbox row',
      (tester) async {
    final harness = await _itinerary();
    await tester.pumpWidget(
      UncontrolledProviderScope(
        container: harness.container,
        child: const MaterialApp(home: ItineraryScreen(tripId: _kTripId)),
      ),
    );
    await tester.pump();
    await tester.pump();

    await tester.tap(find.byTooltip('More actions').first);
    await tester.pumpAndSettle();
    await tester.tap(find.text('Love this place'));
    await tester.pumpAndSettle();

    expect(
      harness.container.read(itineraryControllerProvider(_kTripId)).lovedPlaceRefs,
      contains('a-ref'),
    );
    expect(tester.widget<ActivityCard>(find.byType(ActivityCard).first).isLoved, isTrue);
    expect(harness.outbox.enqueued, isEmpty);
  });

  testWidgets('7. a paste parse with a code writes nothing to the database', (tester) async {
    _tallSurface(tester);
    final db = _RecordingSheetDb();
    final signals = _SheetSignals();
    await tester.pumpWidget(_sheet(db: db, signals: signals));
    await tester.pumpAndSettle();

    await tester.tap(find.text('Paste confirmation text'));
    await tester.pumpAndSettle();
    await tester.enterText(
      find.widgetWithText(TextField, 'Paste email / booking text here'),
      'Your reservation is ready\n'
      'Hotel: Sunset Beach Resort\n'
      'Check-in: 5 October 2026\n'
      'Check-out: 7 October 2026\n'
      'Confirmation code: $_kCode\n'
      'Dubai, UAE\n',
    );
    await tester.pumpAndSettle();
    final autoFill = find.text('Auto-fill from paste');
    await tester.ensureVisible(autoFill);
    await tester.pumpAndSettle();
    await tester.tap(autoFill);
    await tester.pumpAndSettle();

    // The code was parsed into the field (memory only).
    expect(tester.widget<TextField>(_codeField).controller!.text, _kCode);
    // Nothing reached the offline store or the outbox.
    expect(db.calls, isEmpty);
    expect(signals.emits, 0);
  });
}
