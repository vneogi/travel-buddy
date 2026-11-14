// F3: the review step shows a non-blocking overlap note; Create stays enabled.
// Fixtures and the app harness are copied from spec40_create_wizard_test.dart.
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:go_router/go_router.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/create_trip/create_trip_screen.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/theme/app_theme.dart';

const _options = CreateTripOptions(
  partyTypes: [PartyOption(id: 'solo', label: 'Solo')],
  interests: [InterestOption(id: 'history_culture', label: 'History & culture')],
  maxDaysByRegion: {'luang_prabang_laos': 5},
  maxAutoPopulatedDays: 5,
  tripSpanSanityDays: 90,
);

/// Existing trip whose activity span is 2026-11-02 in Luang Prabang.
final _existing = TripSummary(
  tripId: 'existing-1',
  geoRegion: 'luang_prabang_laos',
  nodeCount: 2,
  bookingCount: 0,
  updatedAt: DateTime.utc(2026, 10, 1),
  startsAt: DateTime.utc(2026, 11, 2, 2), // 09:00 local
  endsAt: DateTime.utc(2026, 11, 2, 10), // 17:00 local
);

/// Injected picker: 2026-11-01 to 2026-11-03 (bypasses the F3 calendar).
Future<DateTimeRange?> _fakePicker({
  required BuildContext context,
  required DateTime firstDate,
  required DateTime lastDate,
  DateTimeRange? initialDateRange,
}) async =>
    DateTimeRange(start: DateTime(2026, 11, 1), end: DateTime(2026, 11, 3));

Widget _app(List<TripSummary> trips) {
  final snap = HomeSnapshot(
    supportedRegions: const ['luang_prabang_laos'],
    trips: trips,
    createTripOptions: _options,
  );
  final router = GoRouter(
    initialLocation: '/trip/create',
    routes: [
      GoRoute(
        path: '/trip/create',
        builder: (_, __) => const CreateTripScreen(datePickerBuilder: _fakePicker),
      ),
    ],
  );
  return ProviderScope(
    overrides: [homeSnapshotProvider.overrideWith((_) async => snap)],
    child: MaterialApp.router(theme: AppTheme.light, routerConfig: router),
  );
}

Future<void> _toReview(WidgetTester t) async {
  await t.tap(find.text('Luang Prabang'));
  await t.pump();
  await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
  await t.pumpAndSettle();
  await t.tap(find.widgetWithText(OutlinedButton, 'Select date range'));
  await t.pumpAndSettle();
  for (var i = 0; i < 3; i++) {
    await t.tap(find.widgetWithText(ElevatedButton, 'Next'));
    await t.pumpAndSettle();
  }
  expect(find.text('Review your trip'), findsOneWidget);
}

void main() {
  testWidgets('review shows overlap note and Create stays enabled', (t) async {
    await t.pumpWidget(_app([_existing]));
    await t.pumpAndSettle();
    await _toReview(t);
    final note = find.byKey(const Key('create_trip_overlap_note'));
    expect(note, findsOneWidget);
    expect(
      t.widget<Text>(note).data,
      'Overlaps with an existing trip on 2026-11-02.',
    );
    final submit = t.widget<ElevatedButton>(find.byKey(const Key('create_trip_submit')));
    expect(submit.onPressed, isNotNull);
    expect(find.text('Create trip'), findsOneWidget);
  });

  testWidgets('review has no overlap note when no trip overlaps', (t) async {
    await t.pumpWidget(_app(const []));
    await t.pumpAndSettle();
    await _toReview(t);
    expect(find.byKey(const Key('create_trip_overlap_note')), findsNothing);
  });
}
