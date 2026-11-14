import 'package:flutter/material.dart';

import '../../core/destination_tz.dart';
import '../../data/models.dart';

// F3: days already covered by the traveller's other trips.
//
// These are activity-span days from the trip-list projection: each trip's
// [TripSummary.startsAt] / [TripSummary.endsAt] are the min / max of its
// scheduled node times, not the dates chosen on the create form. A sparse
// trip can therefore under-mark days that have no nodes yet. Days are
// destination-local and date-only, so an evening node that crosses local
// midnight lands on the right day. Markers are informational and never block
// creating an overlapping trip.

/// Inclusive date-only days covered by [trips].
Set<DateTime> occupiedDaysFromTrips(Iterable<TripSummary> trips) {
  final days = <DateTime>{};
  for (final trip in trips) {
    final startsAt = trip.startsAt;
    final endsAt = trip.endsAt;
    if (startsAt == null || endsAt == null) continue;
    var start = DateUtils.dateOnly(toDestinationLocal(startsAt, trip.geoRegion));
    var end = DateUtils.dateOnly(toDestinationLocal(endsAt, trip.geoRegion));
    if (end.isBefore(start)) {
      final swap = start;
      start = end;
      end = swap;
    }
    days.addAll(_daysInclusive(start, end));
  }
  return days;
}

/// True when [range] shares any date-only day with [occupied].
bool rangeOverlapsOccupied(DateTimeRange range, Set<DateTime> occupied) {
  return _overlapDays(range, occupied).isNotEmpty;
}

/// Short, non-blocking review copy. Empty string when no overlap.
String overlapReviewNote(DateTimeRange range, Set<DateTime> occupied) {
  final overlap = _overlapDays(range, occupied);
  if (overlap.isEmpty) return '';
  final first = _fmt(overlap.first);
  final last = _fmt(overlap.last);
  final span = first == last ? first : '$first to $last';
  return 'Overlaps with an existing trip on $span.';
}

List<DateTime> _overlapDays(DateTimeRange range, Set<DateTime> occupied) {
  if (occupied.isEmpty) return const [];
  final start = DateUtils.dateOnly(range.start);
  final end = DateUtils.dateOnly(range.end);
  return _daysInclusive(start, end).where(occupied.contains).toList();
}

/// Calendar days from [start] to [end] inclusive (date-only, DST-safe).
List<DateTime> _daysInclusive(DateTime start, DateTime end) {
  final out = <DateTime>[];
  var day = DateTime(start.year, start.month, start.day);
  while (!day.isAfter(end)) {
    out.add(day);
    day = DateTime(day.year, day.month, day.day + 1);
  }
  return out;
}

String _fmt(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
