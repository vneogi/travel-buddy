// F3: the existing-trip range calendar (widget tests).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/widgets/existing_trip_date_range_picker.dart';

final _firstDate = DateTime(2026, 12, 1); // fixes the visible month
final _lastDate = DateTime(2027, 12, 31);
final _occupied = {DateTime(2026, 12, 10), DateTime(2026, 12, 11)};

class _Result {
  bool closed = false;
  DateTimeRange? range;
}

Future<_Result> _open(WidgetTester t) async {
  t.binding.platformDispatcher.localeTestValue = const Locale('en', 'US');
  addTearDown(t.binding.platformDispatcher.clearLocaleTestValue);
  final result = _Result();
  await t.pumpWidget(MaterialApp(
    home: Builder(
      builder: (context) => Scaffold(
        body: Center(
          child: ElevatedButton(
            onPressed: () async {
              result.range = await showExistingTripDateRangePicker(
                context: context,
                firstDate: _firstDate,
                lastDate: _lastDate,
                occupiedDays: _occupied,
              );
              result.closed = true;
            },
            child: const Text('open'),
          ),
        ),
      ),
    ),
  ));
  await t.tap(find.text('open'));
  await t.pumpAndSettle();
  expect(find.byKey(const Key('picker-month')), findsOneWidget);
  expect(find.text('December 2026'), findsOneWidget);
  return result;
}

Finder _day(String iso) => find.byKey(Key('day-$iso'));

void main() {
  testWidgets('occupied_day_shows_a_marker', (t) async {
    await _open(t);
    expect(find.byKey(const Key('marker-2026-12-10')), findsOneWidget);
    expect(find.byKey(const Key('marker-2026-12-11')), findsOneWidget);
    expect(find.byKey(const Key('marker-2026-12-12')), findsNothing);
    // The marker sits inside its own day cell.
    expect(
      find.descendant(
        of: _day('2026-12-10'),
        matching: find.byKey(const Key('marker-2026-12-10')),
      ),
      findsOneWidget,
    );
  });

  testWidgets('occupied_day_is_still_selectable', (t) async {
    await _open(t);
    await t.tap(_day('2026-12-10'));
    await t.pump();
    await t.tap(_day('2026-12-12'));
    await t.pump();
    final confirm = t.widget<FilledButton>(find.byKey(const Key('picker-confirm')));
    expect(confirm.onPressed, isNotNull);
  });

  testWidgets('confirming_a_range_that_covers_an_occupied_day_returns_the_range',
      (t) async {
    final result = await _open(t);
    await t.tap(_day('2026-12-09'));
    await t.pump();
    await t.tap(_day('2026-12-12'));
    await t.pump();
    await t.tap(find.byKey(const Key('picker-confirm')));
    await t.pumpAndSettle();
    expect(result.closed, isTrue);
    expect(
      result.range,
      DateTimeRange(start: DateTime(2026, 12, 9), end: DateTime(2026, 12, 12)),
    );
  });

  testWidgets('cancel_returns_null', (t) async {
    final result = await _open(t);
    await t.tap(_day('2026-12-10'));
    await t.pump();
    await t.tap(find.byKey(const Key('picker-cancel')));
    await t.pumpAndSettle();
    expect(result.closed, isTrue);
    expect(result.range, isNull);
  });
}
