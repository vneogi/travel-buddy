import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:mocktail/mocktail.dart';
import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/create_trip/create_trip_screen.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/theme/app_theme.dart';

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const _partyTypes = [
  PartyOption(id: 'solo', label: 'Solo'),
  PartyOption(id: 'couple', label: 'Couple'),
  PartyOption(id: 'friends', label: 'Friends'),
  PartyOption(id: 'family_young_kids', label: 'Family with young kids'),
  PartyOption(id: 'family_teens', label: 'Family with teens'),
  PartyOption(id: 'multigen', label: 'Multi-generation'),
];

const _interests = [
  InterestOption(id: 'history_culture', label: 'History & culture'),
  InterestOption(id: 'food_markets', label: 'Food & markets'),
  InterestOption(id: 'nature_scenery', label: 'Nature & scenery'),
  InterestOption(id: 'adventure_outdoors', label: 'Adventure & outdoors'),
  InterestOption(id: 'arts_crafts', label: 'Arts & crafts'),
  InterestOption(id: 'wellness_slow', label: 'Wellness & slow travel'),
  InterestOption(id: 'nightlife_social', label: 'Nightlife & social'),
];

const _options = CreateTripOptions(
  partyTypes: _partyTypes,
  interests: _interests,
  maxDaysByRegion: {'luang_prabang_laos': 5, 'dubai_uae': 4},
);

final _snapshot = HomeSnapshot(
  supportedRegions: ['luang_prabang_laos', 'dubai_uae'],
  trips: [],
  createTripOptions: _options,
);

final _tripFixture = TripState(
  tripId: 'created-trip-1',
  userId: 'u1',
  nodes: [],
  geoRegion: 'luang_prabang_laos',
);

/// Fixed date range for deterministic tests.
final _fixedRange = DateTimeRange(
  start: DateTime(2026, 11, 1),
  end: DateTime(2026, 11, 3),
);

/// Old/offline snapshot with no create_trip_options.
final _staleSnapshot = HomeSnapshot(
  supportedRegions: ['luang_prabang_laos'],
  trips: [],
  createTripOptions: null,
);

/// Injected picker that immediately returns [_fixedRange].
Future<DateTimeRange?> _fakePicker({
  required BuildContext context,
  required DateTime firstDate,
  required DateTime lastDate,
  DateTimeRange? initialDateRange,
}) async => _fixedRange;

/// Injected picker returning an 8-day range (exceeds any destination max).
Future<DateTimeRange?> _overMaxPicker({
  required BuildContext context,
  required DateTime firstDate,
  required DateTime lastDate,
  DateTimeRange? initialDateRange,
}) async =>
    DateTimeRange(
      start: DateTime(2026, 11, 1),
      end: DateTime(2026, 11, 8),
    );

/// Injected picker returning a 5-day range (fits LP max=5 but not Dubai max=4).
Future<DateTimeRange?> _fiveDayPicker({
  required BuildContext context,
  required DateTime firstDate,
  required DateTime lastDate,
  DateTimeRange? initialDateRange,
}) async =>
    DateTimeRange(
      start: DateTime(2026, 11, 1),
      end: DateTime(2026, 11, 5),
    );

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

class MockTripRepository extends Mock implements TripRepository {}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/// Build wizard with provider overrides, injectable date picker, and
/// optional mock repository. Wraps in GoRouter so success navigation works.
Widget _app({
  Size size = const Size(400, 800),
  double textScale = 1.0,
  MockTripRepository? repo,
  DateRangePickerBuilder? picker,
  HomeSnapshot? snapshot,
}) {
  final snap = snapshot ?? _snapshot;
  final router = GoRouter(
    initialLocation: '/trip/create',
    routes: [
      GoRoute(
        path: '/trip/create',
        builder: (_, __) => CreateTripScreen(datePickerBuilder: picker),
      ),
      GoRoute(
        path: '/trip/:id',
        builder: (_, state) => Scaffold(
          body: Center(
            child: Text('TripView ${state.pathParameters['id']}'),
          ),
        ),
      ),
    ],
  );
  return ProviderScope(
    overrides: [
      homeSnapshotProvider.overrideWith((_) async => snap),
      if (repo != null) tripRepoProvider.overrideWithValue(repo),
    ],
    child: MediaQuery(
      data: MediaQueryData(
        size: size,
        textScaler: TextScaler.linear(textScale),
      ),
      child: MaterialApp.router(
        theme: AppTheme.light,
        routerConfig: router,
      ),
    ),
  );
}

/// Advance through steps 1-2 (destination + dates) so party step is visible.
Future<void> _toStep3(WidgetTester t) async {
  // Step 1: select Luang Prabang
  await t.tap(find.text('Luang Prabang'));
  await t.pump();
  await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
  await t.pumpAndSettle();
  // Step 2: tap date picker button, which uses our fake
  await t.tap(find.widgetWithText(OutlinedButton, 'Select date range'));
  await t.pumpAndSettle();
  // Dates are now set; tap Next
  await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
  await t.pumpAndSettle();
}

/// Advance through steps 1-3 (dest + dates + party) so interests step is visible.
Future<void> _toStep4(WidgetTester t) async {
  await _toStep3(t);
  // Step 3: party defaults to solo, just tap Next
  await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
  await t.pumpAndSettle();
}

/// Advance through all steps to review (step 5).
Future<void> _toStep5(WidgetTester t) async {
  await _toStep4(t);
  // Step 4: interests -- skip, tap Next
  await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
  await t.pumpAndSettle();
}

void main() {
  late MockTripRepository mockRepo;

  setUpAll(() {
    registerFallbackValue(DateTime(2026));
    registerFallbackValue(<String>[]);
  });

  setUp(() {
    mockRepo = MockTripRepository();
  });

  // -----------------------------------------------------------------------
  // Full five-step navigation
  // -----------------------------------------------------------------------
  testWidgets('navigates all five wizard steps to review', (t) async {
    await t.pumpWidget(_app(picker: _fakePicker));
    await t.pumpAndSettle();

    // Step 1
    expect(find.text('Where are you going?'), findsOneWidget);
    await t.tap(find.text('Luang Prabang'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 2
    expect(find.text('When?'), findsOneWidget);
    await t.tap(find.widgetWithText(OutlinedButton, 'Select date range'));
    await t.pumpAndSettle();
    expect(find.textContaining('3 days'), findsOneWidget);
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 3
    expect(find.text('Who is travelling?'), findsOneWidget);
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 4
    expect(find.textContaining('interests'), findsOneWidget);
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 5
    expect(find.text('Review your trip'), findsOneWidget);
    expect(find.text('Luang Prabang'), findsOneWidget);
    expect(find.textContaining('3 days'), findsOneWidget);
    expect(find.text('Balanced'), findsOneWidget);
  });

  // -----------------------------------------------------------------------
  // Party type taps: tap each, verify selection changes
  // -----------------------------------------------------------------------
  testWidgets('tapping each party type selects it without crash', (t) async {
    await t.pumpWidget(_app(picker: _fakePicker));
    await t.pumpAndSettle();
    await _toStep3(t);

    expect(find.text('Who is travelling?'), findsOneWidget);
    for (final pt in _partyTypes) {
      await t.tap(find.text(pt.label));
      await t.pump();
    }
    // After tapping multigen (last), the slider should appear
    expect(find.byType(Slider), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  // -----------------------------------------------------------------------
  // Fourth-interest refusal: tap 4 chips, only 3 selected
  // -----------------------------------------------------------------------
  testWidgets('fourth interest chip is refused', (t) async {
    await t.pumpWidget(_app(picker: _fakePicker));
    await t.pumpAndSettle();
    await _toStep4(t);

    expect(find.textContaining('interests'), findsOneWidget);
    // Tap first 4 interest chips
    await t.tap(find.text('History & culture'));
    await t.pump();
    await t.tap(find.text('Food & markets'));
    await t.pump();
    await t.tap(find.text('Nature & scenery'));
    await t.pump();
    await t.tap(find.text('Adventure & outdoors'));
    await t.pump();

    // Only 3 should be selected (FilterChip.selected == true)
    final chips = t.widgetList<FilterChip>(find.byType(FilterChip));
    final selectedCount = chips.where((c) => c.selected).length;
    expect(selectedCount, 3);
  });

  // -----------------------------------------------------------------------
  // Exact review: verify all fields on step 5
  // -----------------------------------------------------------------------
  testWidgets('review step shows exact entered data', (t) async {
    await t.pumpWidget(_app(picker: _fakePicker));
    await t.pumpAndSettle();

    // Step 1: Dubai
    await t.tap(find.text('Dubai'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 2: dates
    await t.tap(find.widgetWithText(OutlinedButton, 'Select date range'));
    await t.pumpAndSettle();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 3: tap Friends
    await t.tap(find.text('Friends'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 4: select food_markets + arts_crafts
    await t.tap(find.text('Food & markets'));
    await t.pump();
    await t.tap(find.text('Arts & crafts'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 5: review
    expect(find.text('Review your trip'), findsOneWidget);
    expect(find.text('Dubai'), findsOneWidget);
    expect(find.textContaining('3 days'), findsOneWidget);
    expect(find.textContaining('Friends'), findsOneWidget);
    expect(find.textContaining('Food & markets'), findsOneWidget);
    expect(find.textContaining('Arts & crafts'), findsOneWidget);
  });

  // -----------------------------------------------------------------------
  // Exact repository payload
  // -----------------------------------------------------------------------
  testWidgets('submit sends exact payload to repository', (t) async {
    when(() => mockRepo.rangeCreate(
      geoRegion: any(named: 'geoRegion'),
      startDate: any(named: 'startDate'),
      endDate: any(named: 'endDate'),
      partyType: any(named: 'partyType'),
      partySize: any(named: 'partySize'),
      interestIds: any(named: 'interestIds'),
    )).thenAnswer((_) async => _tripFixture);

    await t.pumpWidget(_app(picker: _fakePicker, repo: mockRepo));
    await t.pumpAndSettle();
    await _toStep5(t);

    // Tap Create trip
    await t.tap(find.widgetWithText(ElevatedButton, 'Create trip'));
    await t.pumpAndSettle();

    final captured = verify(() => mockRepo.rangeCreate(
      geoRegion: captureAny(named: 'geoRegion'),
      startDate: captureAny(named: 'startDate'),
      endDate: captureAny(named: 'endDate'),
      partyType: captureAny(named: 'partyType'),
      partySize: captureAny(named: 'partySize'),
      interestIds: captureAny(named: 'interestIds'),
    )).captured;

    expect(captured[0], 'luang_prabang_laos');
    expect(captured[1], _fixedRange.start);
    expect(captured[2], _fixedRange.end);
    expect(captured[3], 'solo');
    expect(captured[4], 1);
    expect(captured[5], <String>[]);
  });

  // -----------------------------------------------------------------------
  // Delayed duplicate-submit: second tap does not call repo again
  // -----------------------------------------------------------------------
  testWidgets('duplicate submit sends only one request', (t) async {
    final completer = Completer<TripState>();
    when(() => mockRepo.rangeCreate(
      geoRegion: any(named: 'geoRegion'),
      startDate: any(named: 'startDate'),
      endDate: any(named: 'endDate'),
      partyType: any(named: 'partyType'),
      partySize: any(named: 'partySize'),
      interestIds: any(named: 'interestIds'),
    )).thenAnswer((_) => completer.future);

    await t.pumpWidget(_app(picker: _fakePicker, repo: mockRepo));
    await t.pumpAndSettle();
    await _toStep5(t);

    // Both taps locate the same keyed primary action.
    final keyFinder = find.byKey(const Key('create_trip_submit'));
    await t.tap(keyFinder);
    await t.pump();
    // Second tap while repo Future is pending.
    await t.tap(keyFinder);
    await t.pump();

    // Complete the future
    completer.complete(_tripFixture);
    await t.pumpAndSettle();

    verify(() => mockRepo.rangeCreate(
      geoRegion: any(named: 'geoRegion'),
      startDate: any(named: 'startDate'),
      endDate: any(named: 'endDate'),
      partyType: any(named: 'partyType'),
      partySize: any(named: 'partySize'),
      interestIds: any(named: 'interestIds'),
    )).called(1);
  });

  // -----------------------------------------------------------------------
  // Typed failure preserving state
  // -----------------------------------------------------------------------
  testWidgets('server error shows message, retains wizard state', (t) async {
    when(() => mockRepo.rangeCreate(
      geoRegion: any(named: 'geoRegion'),
      startDate: any(named: 'startDate'),
      endDate: any(named: 'endDate'),
      partyType: any(named: 'partyType'),
      partySize: any(named: 'partySize'),
      interestIds: any(named: 'interestIds'),
    )).thenThrow(const ValidationException('Dates overlap a holiday.'));

    await t.pumpWidget(_app(picker: _fakePicker, repo: mockRepo));
    await t.pumpAndSettle();
    await _toStep5(t);

    await t.tap(find.widgetWithText(ElevatedButton, 'Create trip'));
    await t.pumpAndSettle();

    // Error message shown
    expect(find.text('Dates overlap a holiday.'), findsOneWidget);
    // Still on review step (state retained)
    expect(find.text('Review your trip'), findsOneWidget);
    // Create trip button is re-enabled
    final btn = t.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Create trip'));
    expect(btn.onPressed, isNotNull);
  });

  // -----------------------------------------------------------------------
  // Success navigation: goes to /trip/{id}
  // -----------------------------------------------------------------------
  testWidgets('successful create navigates to trip view', (t) async {
    when(() => mockRepo.rangeCreate(
      geoRegion: any(named: 'geoRegion'),
      startDate: any(named: 'startDate'),
      endDate: any(named: 'endDate'),
      partyType: any(named: 'partyType'),
      partySize: any(named: 'partySize'),
      interestIds: any(named: 'interestIds'),
    )).thenAnswer((_) async => _tripFixture);

    await t.pumpWidget(_app(picker: _fakePicker, repo: mockRepo));
    await t.pumpAndSettle();
    await _toStep5(t);

    await t.tap(find.widgetWithText(ElevatedButton, 'Create trip'));
    await t.pumpAndSettle();

    expect(find.text('TripView created-trip-1'), findsOneWidget);
  });

  // -----------------------------------------------------------------------
  // Later-step 800x600 and large-text reachability
  // -----------------------------------------------------------------------
  testWidgets('800x600 party step: non-solo party opens slider without overflow',
      (t) async {
    await t.pumpWidget(_app(
      size: const Size(800, 600),
      picker: _fakePicker,
    ));
    await t.pumpAndSettle();
    await _toStep3(t);
    expect(find.text('Who is travelling?'), findsOneWidget);

    // Select Friends (non-solo, non-couple) to reveal slider.
    await t.tap(find.text('Friends'));
    await t.pump();
    expect(find.byType(Slider), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  testWidgets('large text interests step reachable', (t) async {
    await t.pumpWidget(_app(textScale: 1.5, picker: _fakePicker));
    await t.pumpAndSettle();
    await _toStep4(t);
    expect(find.textContaining('interests'), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  testWidgets('800x600 review step reachable', (t) async {
    await t.pumpWidget(_app(
      size: const Size(800, 600),
      picker: _fakePicker,
    ));
    await t.pumpAndSettle();
    await _toStep5(t);
    expect(find.text('Review your trip'), findsOneWidget);
    expect(t.takeException(), isNull);
  });

  // Home -> GoRouter -> wizard is covered by home_screen_test.dart
  // ('create card opens guided wizard').

  // -----------------------------------------------------------------------
  // Loading and error states
  // -----------------------------------------------------------------------
  testWidgets('loading state shows spinner', (t) async {
    // Use a Completer that is never completed -- no pending Timer.
    final never = Completer<HomeSnapshot>();
    await t.pumpWidget(ProviderScope(
      overrides: [
        homeSnapshotProvider.overrideWith((_) => never.future),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: const CreateTripScreen(),
      ),
    ));
    await t.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);
  });

  testWidgets('error state shows retry', (t) async {
    await t.pumpWidget(ProviderScope(
      overrides: [
        homeSnapshotProvider
            .overrideWith((_) => Future<HomeSnapshot>.error('fail')),
      ],
      child: MaterialApp(
        theme: AppTheme.light,
        home: const CreateTripScreen(),
      ),
    ));
    await t.pumpAndSettle();
    expect(find.text('Could not load trip options.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
  });

  // -----------------------------------------------------------------------
  // Destination gating: region without maxDays disabled
  // -----------------------------------------------------------------------
  testWidgets(
      'unavailable destination cannot be selected and cannot enable Next',
      (t) async {
    final snap = HomeSnapshot(
      supportedRegions: ['luang_prabang_laos', 'unknown_region'],
      trips: [],
      createTripOptions: const CreateTripOptions(
        partyTypes: _partyTypes,
        interests: _interests,
        maxDaysByRegion: {'luang_prabang_laos': 5},
      ),
    );
    await t.pumpWidget(_app(snapshot: snap));
    await t.pumpAndSettle();
    expect(find.text('Unavailable'), findsOneWidget);

    // Attempt to tap the unavailable region.
    await t.tap(find.text('unknown_region'));
    await t.pump();

    // Next must be disabled (no region with known maxDays selected).
    final btn = t.widget<ElevatedButton>(
        find.widgetWithText(ElevatedButton, 'Next'));
    expect(btn.onPressed, isNull);
  });

  // -----------------------------------------------------------------------
  // Production-path proof: over-max date range refused
  // -----------------------------------------------------------------------
  testWidgets('injected over-max date range is refused', (t) async {
    await t.pumpWidget(_app(picker: _overMaxPicker));
    await t.pumpAndSettle();

    // Step 1: select Dubai (max 4 days)
    await t.tap(find.text('Dubai'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 2: tap date picker -- returns 8-day range
    await t.tap(find.widgetWithText(OutlinedButton, 'Select date range'));
    await t.pumpAndSettle();

    // Snackbar with refusal message.
    expect(find.textContaining('Maximum 4 days'), findsOneWidget);
    // Range was NOT accepted -- still shows placeholder.
    expect(find.text('Select date range'), findsOneWidget);
  });

  // -----------------------------------------------------------------------
  // Production-path proof: destination change clears invalid range
  // -----------------------------------------------------------------------
  testWidgets('changing destination clears range invalid for new max',
      (t) async {
    await t.pumpWidget(_app(picker: _fiveDayPicker));
    await t.pumpAndSettle();

    // Step 1: select Luang Prabang (max 5)
    await t.tap(find.text('Luang Prabang'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Step 2: pick 5-day range
    await t.tap(find.widgetWithText(OutlinedButton, 'Select date range'));
    await t.pumpAndSettle();
    expect(find.text('5 days'), findsOneWidget);

    // Go back to step 1
    await t.tap(find.byIcon(Icons.arrow_back));
    await t.pumpAndSettle();

    // Switch to Dubai (max 4) -- 5-day range should be cleared
    await t.tap(find.text('Dubai'));
    await t.pump();
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();

    // Dates step shows placeholder (range was cleared).
    expect(find.text('Select date range'), findsOneWidget);
  });

  // -----------------------------------------------------------------------
  // Production-path proof: stale snapshot without create_trip_options
  // -----------------------------------------------------------------------
  testWidgets(
      'old snapshot without create_trip_options shows unavailable state',
      (t) async {
    await t.pumpWidget(_app(snapshot: _staleSnapshot));
    await t.pumpAndSettle();

    expect(
        find.text('Trip creation is currently unavailable.'), findsOneWidget);
    expect(find.text('Retry'), findsOneWidget);
    expect(find.text('Back'), findsOneWidget);
  });
}
