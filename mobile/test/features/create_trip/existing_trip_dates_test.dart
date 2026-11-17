// F3: pure helpers for existing-trip date markers (no pump).
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/create_trip/existing_trip_dates.dart';

TripSummary _trip(String id, DateTime? startsAt, DateTime? endsAt,
        {String region = 'luang_prabang_laos'}) =>
    TripSummary(
      tripId: id,
      geoRegion: region,
      nodeCount: 3,
      bookingCount: 0,
      updatedAt: DateTime.utc(2026, 11, 1),
      startsAt: startsAt,
      endsAt: endsAt,
    );

void main() {
  test('occupiedDaysFromTrips_includes_every_inclusive_day', () {
    // 09:00 local Dec 10 to 17:00 local Dec 12 in Luang Prabang (UTC+7).
    final days = occupiedDaysFromTrips([
      _trip('t1', DateTime.utc(2026, 12, 10, 2), DateTime.utc(2026, 12, 12, 10)),
    ]);
    expect(days, {
      DateTime(2026, 12, 10),
      DateTime(2026, 12, 11),
      DateTime(2026, 12, 12),
    });
  });

  test('occupiedDaysFromTrips_uses_destination_local_dates', () {
    // 18:00 UTC Dec 20 is 01:00 Dec 21 in Luang Prabang: the local day wins.
    final days = occupiedDaysFromTrips([
      _trip('t1', DateTime.utc(2026, 12, 20, 18), DateTime.utc(2026, 12, 20, 19)),
    ]);
    expect(days, {DateTime(2026, 12, 21)});
  });

  test('occupiedDaysFromTrips_skips_trips_missing_a_bound', () {
    final days = occupiedDaysFromTrips([
      _trip('no-start', null, DateTime.utc(2026, 12, 12, 10)),
      _trip('no-end', DateTime.utc(2026, 12, 10, 2), null),
      _trip('empty', null, null),
    ]);
    expect(days, isEmpty);
  });

  test('occupiedDaysFromTrips_swaps_reversed_bounds', () {
    final days = occupiedDaysFromTrips([
      _trip('rev', DateTime.utc(2026, 12, 12, 10), DateTime.utc(2026, 12, 10, 2)),
    ]);
    expect(days, {
      DateTime(2026, 12, 10),
      DateTime(2026, 12, 11),
      DateTime(2026, 12, 12),
    });
  });

  test('rangeOverlapsOccupied_true_on_shared_day_false_otherwise', () {
    final occupied = {DateTime(2026, 12, 10), DateTime(2026, 12, 11)};
    expect(
      rangeOverlapsOccupied(
        DateTimeRange(start: DateTime(2026, 12, 11), end: DateTime(2026, 12, 14)),
        occupied,
      ),
      isTrue,
    );
    expect(
      rangeOverlapsOccupied(
        DateTimeRange(start: DateTime(2026, 12, 12), end: DateTime(2026, 12, 14)),
        occupied,
      ),
      isFalse,
    );
    expect(
      rangeOverlapsOccupied(
        DateTimeRange(start: DateTime(2026, 12, 10), end: DateTime(2026, 12, 10)),
        occupied,
      ),
      isTrue,
    );
  });

  test('overlapReviewNote_empty_when_clear_and_non_empty_when_overlap', () {
    final occupied = {DateTime(2026, 12, 10), DateTime(2026, 12, 11)};
    expect(
      overlapReviewNote(
        DateTimeRange(start: DateTime(2026, 12, 12), end: DateTime(2026, 12, 14)),
        occupied,
      ),
      '',
    );
    final note = overlapReviewNote(
      DateTimeRange(start: DateTime(2026, 12, 9), end: DateTime(2026, 12, 14)),
      occupied,
    );
    expect(note, startsWith('Overlaps with an existing trip'));
    expect(note, 'Overlaps with an existing trip on 2026-12-10 to 2026-12-11.');
    expect(
      overlapReviewNote(
        DateTimeRange(start: DateTime(2026, 12, 11), end: DateTime(2026, 12, 11)),
        occupied,
      ),
      'Overlaps with an existing trip on 2026-12-11.',
    );
  });

  // SPEC-52 acceptance: boundaries and overlaps.
  test('multiple_overlapping_trips_mark_each_day_once', () {
    final days = occupiedDaysFromTrips([
      _trip('t1', DateTime.utc(2026, 12, 10, 2), DateTime.utc(2026, 12, 12, 10)),
      _trip('t2', DateTime.utc(2026, 12, 11, 2), DateTime.utc(2026, 12, 14, 10)),
    ]);
    expect(days, {
      DateTime(2026, 12, 10),
      DateTime(2026, 12, 11),
      DateTime(2026, 12, 12),
      DateTime(2026, 12, 13),
      DateTime(2026, 12, 14),
    });
    expect(days.length, 5);
  });

  test('local_midnight_end_counts_the_local_day', () {
    // Luang Prabang is UTC+7: 16:59 UTC is 23:59 local on Dec 12.
    final before = occupiedDaysFromTrips([
      _trip('t1', DateTime.utc(2026, 12, 10, 2), DateTime.utc(2026, 12, 12, 16, 59)),
    ]);
    expect(before, contains(DateTime(2026, 12, 12)));
    expect(before, isNot(contains(DateTime(2026, 12, 13))));
    // 17:00 UTC is 00:00 local on Dec 13.
    final after = occupiedDaysFromTrips([
      _trip('t1', DateTime.utc(2026, 12, 10, 2), DateTime.utc(2026, 12, 12, 17)),
    ]);
    expect(after, contains(DateTime(2026, 12, 13)));
  });

  test('local_midnight_start_counts_the_local_day_tanzania', () {
    // Zanzibar is UTC+3: 21:00 UTC Dec 26 is 00:00 local on Dec 27.
    final days = occupiedDaysFromTrips([
      _trip(
        't1',
        DateTime.utc(2026, 12, 26, 21),
        DateTime.utc(2026, 12, 27, 15),
        region: 'zanzibar_tanzania',
      ),
    ]);
    expect(days, isNot(contains(DateTime(2026, 12, 26))));
    expect(days, contains(DateTime(2026, 12, 27)));
  });

  test('single_day_trip_marks_one_day', () {
    final days = occupiedDaysFromTrips([
      _trip('t1', DateTime.utc(2026, 12, 15, 2), DateTime.utc(2026, 12, 15, 10)),
    ]);
    expect(days, {DateTime(2026, 12, 15)});
  });
}
