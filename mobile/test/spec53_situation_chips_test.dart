// SPEC-53 slice 1: situation chips send What Now in one tap.
//
// Harness mirrors spec46_what_now_test.dart: in-memory
// OfflineDatabase(testPath:), _FakeConnectivity, mocked tripEventProvider,
// tester.runAsync + flush, no pumpAndSettle.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'package:travel_buddy/core/connectivity_helper.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/chat/chat_screen.dart';
import 'package:travel_buddy/features/chat/situation_chips.dart';
import 'package:travel_buddy/features/itinerary/itinerary_notifier.dart';
import 'package:travel_buddy/offline/offline_database.dart';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

class _MockTripRepository extends Mock implements TripRepository {}

class _MockTripEventService extends Mock implements TripEventService {}

class _FakeConnectivity extends ConnectivityHelper {
  final bool online;
  _FakeConnectivity({this.online = true});
  @override
  Future<bool> checkConnectivity() async => online;
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

// Source of truth: WhatNowRequest.ALLOWED_MINUTES, ALLOWED_ENERGY,
// ALLOWED_WALKING and ALLOWED_INTENT in services/ask_service.py.
const _allowedMinutes = {45, 90, 120};
const _allowedEnergy = {'low', 'normal', 'high'};
const _allowedWalking = {'short', 'normal', 'longer'};
const _allowedIntent = {'quiet', 'food', 'indoors', 'culture', 'anything'};

const _scope = 'account:spec53-test';
const _tripId = 'trip-sc';
int _harnessCounter = 0;

TripNode _node({required DateTime start}) => TripNode(
      nodeId: 'n1',
      venueName: 'Context Temple',
      venueId: 'ctx-1',
      scheduledStart: start,
      durationMinutes: 60,
      isLocked: false,
      status: NodeStatus.pending,
      vibeTags: const ['quiet', 'culture'],
      geoRegion: 'vientiane_laos',
      microLocation: 'nam_phou_fountain',
      lat: 17.96345,
      lng: 102.61112,
    );

AskResponse _whatNowResponse() => const AskResponse(
      answer: 'Found 1 option within reach: Wat Si Saket.',
      tier: AskTier.hedge,
      path: AskPath.groundedDeterministic,
      intent: AskResponseIntent.whatNow,
      sourceClass: 'curated_catalog',
      sourceIds: ['v1'],
      whatNow: WhatNowResult(
        locationSource: 'trip_position',
        contextLabel: 'Using your trip position',
        candidates: [
          WhatNowCandidate(
            candidateId: 'what_now:v1',
            venueId: 'v1',
            name: 'Wat Si Saket',
            microLocationDisplay: 'nam_phou_fountain',
            category: 'temple',
            typicalDwellMinutes: 45,
            scheduledStart: '2026-10-02T11:05:00',
            reasonCodes: ['fits_available_window'],
            unknownFields: ['price', 'live_crowds', 'traffic'],
          ),
        ],
      ),
    );

TripEventResult _whatNowEventResult() => TripEventResult(
      message: '',
      updatedNodes: const [],
      routingTier: 'light',
      fromCache: false,
      askResponse: _whatNowResponse(),
    );

typedef _Harness = ({
  ProviderContainer container,
  _MockTripEventService mockService,
  _FakeConnectivity connectivity,
  OfflineDatabase realDb,
  void Function() closeSubscription,
});

/// Build harness inside tester.runAsync (FFI I/O).
Future<_Harness> _buildHarness({
  bool online = true,
  Future<TripEventResult?> Function()? answer,
  List<TripNode>? nodes,
}) async {
  final now = DateTime.now().toUtc();
  _harnessCounter++;
  final realDb = OfflineDatabase(
    testPath: 'file:spec53_sc_$_harnessCounter?mode=memory&cache=shared',
  );

  final repo = _MockTripRepository();
  when(() => repo.getTrip(_tripId)).thenAnswer(
    (_) async => TripState(
      tripId: _tripId,
      userId: 'user-1',
      nodes: nodes ?? [_node(start: now.add(const Duration(hours: 1)))],
    ),
  );

  final mockService = _MockTripEventService();
  final Future<TripEventResult?> Function() reply =
      answer ?? () async => _whatNowEventResult();
  when(() => mockService.sendEvent(
        tripId: any(named: 'tripId'),
        type: any(named: 'type'),
        message: any(named: 'message'),
        targetNodeId: any(named: 'targetNodeId'),
        preferences: any(named: 'preferences'),
      )).thenAnswer((_) => reply());

  final connectivity = _FakeConnectivity(online: online);

  final container = ProviderContainer(
    overrides: [
      tripRepoProvider.overrideWithValue(repo),
      offlineDatabaseProvider.overrideWithValue(realDb),
      identityCacheScopeProvider.overrideWithValue(_scope),
      tripEventProvider.overrideWithValue(mockService),
    ],
  );

  final loaded = Completer<void>();
  final sub = container.listen(
    itineraryControllerProvider(_tripId),
    (_, next) {
      if (!next.loading && !loaded.isCompleted) loaded.complete();
    },
    fireImmediately: true,
  );
  await loaded.future;

  return (
    container: container,
    mockService: mockService,
    connectivity: connectivity,
    realDb: realDb,
    closeSubscription: sub.close,
  );
}

Widget _app(_Harness h, {double textScale = 1.0}) => UncontrolledProviderScope(
      container: h.container,
      child: MaterialApp(
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context)
              .copyWith(textScaler: TextScaler.linear(textScale)),
          child: child!,
        ),
        home: ChatScreen(
          tripId: _tripId,
          connectivityOverride: h.connectivity,
        ),
      ),
    );

/// Let FFI futures land, then pump. Polls until [until] matches.
Future<void> _flushFfi(
  WidgetTester tester, {
  Finder? until,
  int maxRounds = 40,
}) async {
  for (var i = 0; i < maxRounds; i++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();
    if (until != null && tester.any(until)) return;
  }
  if (until != null) {
    expect(until, findsWidgets);
  }
}

/// Flush until [condition] holds (or fail after [maxRounds]).
Future<void> _flushUntil(
  WidgetTester tester,
  bool Function() condition, {
  int maxRounds = 40,
}) async {
  for (var i = 0; i < maxRounds; i++) {
    if (condition()) return;
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 50)),
    );
    await tester.pump();
  }
  expect(condition(), isTrue);
}

Finder _chip(String id) => find.byKey(Key('situation_chip_$id'));

bool _chipEnabled(WidgetTester tester, String id) =>
    tester.widget<ActionChip>(_chip(id)).onPressed != null;

bool _entryEnabled(WidgetTester tester) =>
    tester
        .widget<OutlinedButton>(find.byKey(const Key('what_now_entry')))
        .onPressed !=
    null;

Future<void> _tapChip(WidgetTester tester, String id) async {
  await tester.ensureVisible(_chip(id));
  await tester.pump(const Duration(milliseconds: 100));
  await tester.tap(_chip(id));
  await tester.pump();
}

/// Text widgets showing [text] outside the chip row (i.e. chat bubbles).
int _textOutsideChips(String text) {
  final all = find.text(text).evaluate().length;
  final inChips = find
      .descendant(
        of: find.byKey(const Key('situation_chip_row')),
        matching: find.text(text),
      )
      .evaluate()
      .length;
  return all - inChips;
}

/// Tall viewport so the reverse ListView builds every bubble (the What Now
/// result is tall enough to push the user bubble out of the lazy list).
void _tallSurface(WidgetTester tester) {
  tester.view.physicalSize = const Size(800, 3000);
  tester.view.devicePixelRatio = 1.0;
  addTearDown(tester.view.reset);
}

/// Same teardown order as spec46_what_now_test.dart: close the harness
/// listener while chat is still mounted, then dispose the container.
Future<void> _dispose(WidgetTester tester, _Harness h) async {
  await _flushFfi(tester, maxRounds: 4); // drain persist
  h.closeSubscription();
  h.container.dispose();
  await tester.runAsync(() => h.realDb.close());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  sqfliteFfiInit();
  databaseFactory = databaseFactoryFfi;

  setUpAll(() => registerFallbackValue(EventType.askInfo));

  // -------------------------------------------------------------------------
  // Unit
  // -------------------------------------------------------------------------

  test('chip presets use only values the backend accepts', () {
    for (final chip in kSituationChips) {
      expect(_allowedMinutes, contains(chip.availableMinutes), reason: chip.id);
      expect(_allowedEnergy, contains(chip.energy), reason: chip.id);
      expect(_allowedWalking, contains(chip.walking), reason: chip.id);
      expect(_allowedIntent, contains(chip.intent), reason: chip.id);
    }
  });

  test('chip labels and order are exact', () {
    expect(
      kSituationChips.map((c) => c.label).toList(),
      ['Quick break', 'Low energy', 'Indoors', 'Something to eat'],
    );
    expect(
      kSituationChips.map((c) => c.id).toList(),
      ['quick_break', 'low_energy', 'indoors', 'food'],
    );
  });

  test('preferences omit context_node_id when none', () {
    final prefs = kSituationChips.first.preferences();
    expect(prefs, {
      'mode': 'what_now',
      'available_minutes': 45,
      'energy': 'low',
      'walking': 'short',
      'intent': 'anything',
    });
    expect(prefs.containsKey('context_node_id'), isFalse);
  });

  test('preferences include context_node_id when given', () {
    final prefs = kSituationChips.first.preferences(contextNodeId: 'n1');
    expect(prefs['context_node_id'], 'n1');
    expect(prefs['mode'], 'what_now');
  });

  // -------------------------------------------------------------------------
  // Widget
  // -------------------------------------------------------------------------

  testWidgets(
    'chip row renders four chips next to the What now button',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_entry')));

      expect(find.byKey(const Key('what_now_entry')), findsOneWidget);
      expect(find.byKey(const Key('situation_chip_row')), findsOneWidget);
      for (final chip in kSituationChips) {
        expect(_chip(chip.id), findsOneWidget, reason: chip.id);
        expect(
          find.descendant(of: _chip(chip.id), matching: find.text(chip.label)),
          findsOneWidget,
        );
      }

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'tapping Quick break sends the exact What Now preferences',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');
      _tallSurface(tester);

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('quick_break'));

      await _tapChip(tester, 'quick_break');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));

      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: 'Quick break',
            targetNodeId: any(named: 'targetNodeId'),
            preferences: captureAny(named: 'preferences'),
          )).captured;
      expect(captured, hasLength(1));
      expect(captured.single, {
        'mode': 'what_now',
        'available_minutes': 45,
        'energy': 'low',
        'walking': 'short',
        'intent': 'anything',
        'context_node_id': 'n1',
      });

      expect(find.byKey(const Key('what_now_bubble')), findsOneWidget);
      // User bubble shows the chip label, not "What now?".
      expect(_textOutsideChips('Quick break'), 1);
      expect(find.text('What now?'), findsOneWidget); // the button only

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'each chip sends its own preset',
    timeout: const Timeout(Duration(seconds: 60)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('quick_break'));

      for (final chip in kSituationChips) {
        await _flushUntil(tester, () => _chipEnabled(tester, chip.id));
        await _tapChip(tester, chip.id);
        await _flushUntil(tester, () => _chipEnabled(tester, chip.id));
      }

      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: captureAny(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: captureAny(named: 'preferences'),
          )).captured;
      expect(captured, hasLength(kSituationChips.length * 2));
      for (var i = 0; i < kSituationChips.length; i++) {
        final chip = kSituationChips[i];
        expect(captured[i * 2], chip.label);
        expect(captured[i * 2 + 1], {
          'mode': 'what_now',
          'available_minutes': chip.availableMinutes,
          'energy': chip.energy,
          'walking': chip.walking,
          'intent': chip.intent,
          'context_node_id': 'n1',
        });
      }

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'chips are disabled while a request is in flight',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final pending = Completer<TripEventResult?>();
      final h = await tester.runAsync(
        () => _buildHarness(answer: () => pending.future),
      );
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('quick_break'));

      await _tapChip(tester, 'quick_break');
      await _flushUntil(tester, () => !_chipEnabled(tester, 'quick_break'));

      for (final chip in kSituationChips) {
        expect(_chipEnabled(tester, chip.id), isFalse, reason: chip.id);
      }
      expect(_entryEnabled(tester), isFalse);

      // A second tap while in flight sends nothing.
      await _tapChip(tester, 'low_energy');
      await _flushFfi(tester, maxRounds: 4);
      verify(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).called(1);

      pending.complete(_whatNowEventResult());
      await _flushUntil(tester, () => _chipEnabled(tester, 'quick_break'));
      for (final chip in kSituationChips) {
        expect(_chipEnabled(tester, chip.id), isTrue, reason: chip.id);
      }
      expect(_entryEnabled(tester), isTrue);

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'offline tap refuses and sends nothing',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(online: false));
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('quick_break'));

      await _tapChip(tester, 'quick_break');
      await _flushFfi(tester, until: find.byKey(const Key('ask_offline_refuse')));

      expect(find.byKey(const Key('ask_offline_refuse')), findsOneWidget);
      verifyNever(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          ));

      await _flushFfi(tester, maxRounds: 4); // drain user persist
      final threads = await tester.runAsync(
        () => h.realDb.listAskThreads(identityScope: _scope, tripId: _tripId),
      );
      expect(threads, isNotNull);
      expect(threads!, isNotEmpty);
      final messages = await tester.runAsync(
        () => h.realDb.loadAskMessages(
          threadId: threads.first['thread_id'] as String,
          identityScope: _scope,
        ),
      );
      expect(messages!.map((m) => m['role']).toList(), ['user']);
      expect(messages.single['text'], 'Quick break');

      final outbox = await tester.runAsync(() => h.realDb.getPendingBatch());
      expect(outbox, isNotNull);
      expect(outbox!, isEmpty);

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'no context stop omits context_node_id',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness(nodes: const []));
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('indoors'));

      await _tapChip(tester, 'indoors');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));

      final captured = verify(() => h.mockService.sendEvent(
            tripId: _tripId,
            type: EventType.askInfo,
            message: 'Indoors',
            targetNodeId: any(named: 'targetNodeId'),
            preferences: captureAny(named: 'preferences'),
          )).captured;
      final prefs = captured.single as Map<String, dynamic>;
      expect(prefs.containsKey('context_node_id'), isFalse);
      expect(prefs['intent'], 'indoors');

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'chip row has no overflow at 360dp and 2.0 text scale',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      tester.view.physicalSize = const Size(1080, 2400);
      tester.view.devicePixelRatio = 3.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h, textScale: 2.0));
      await _flushFfi(tester, until: _chip('quick_break'));

      expect(tester.takeException(), isNull);
      expect(
        tester.getSize(find.byKey(const Key('situation_chip_row'))).width,
        lessThanOrEqualTo(360),
      );

      final last = _chip(kSituationChips.last.id);
      await tester.ensureVisible(last);
      await tester.pump(const Duration(milliseconds: 100));
      expect(last.hitTestable(), findsOneWidget);
      expect(tester.takeException(), isNull);

      await _dispose(tester, h);
    },
  );

  testWidgets(
    'chips keep 44dp tap targets and button semantics',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final handle = tester.ensureSemantics();
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('quick_break'));

      for (final chip in kSituationChips) {
        await tester.ensureVisible(_chip(chip.id));
        await tester.pump(const Duration(milliseconds: 100));
        expect(
          tester.getSize(_chip(chip.id)).height,
          greaterThanOrEqualTo(44),
          reason: chip.id,
        );
        expect(
          tester.getSemantics(_chip(chip.id)),
          containsSemantics(label: chip.label, isButton: true),
          reason: chip.id,
        );
      }

      await _dispose(tester, h);
      handle.dispose();
    },
  );

  testWidgets(
    'history reopens with the chip label',
    timeout: const Timeout(Duration(seconds: 30)),
    (tester) async {
      final h = await tester.runAsync(() => _buildHarness());
      if (h == null) fail('harness null');
      _tallSurface(tester);

      // First session: send a chip.
      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: _chip('quick_break'));
      await _tapChip(tester, 'quick_break');
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));
      await _flushFfi(tester, maxRounds: 4); // drain persist

      // Dispose and rebuild over the same thread.
      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pump();
      reset(h.mockService);
      when(() => h.mockService.sendEvent(
            tripId: any(named: 'tripId'),
            type: any(named: 'type'),
            message: any(named: 'message'),
            targetNodeId: any(named: 'targetNodeId'),
            preferences: any(named: 'preferences'),
          )).thenAnswer((_) async => _whatNowEventResult());

      await tester.pumpWidget(_app(h));
      await _flushFfi(tester, until: find.byKey(const Key('what_now_bubble')));

      expect(_textOutsideChips('Quick break'), 1);
      expect(find.byKey(const Key('what_now_bubble')), findsOneWidget);
      // Reopened results are display-only: no Add to plan.
      expect(find.byKey(const Key('what_now_add_v1')), findsNothing);
      verifyZeroInteractions(h.mockService);

      await _dispose(tester, h);
    },
  );
}
