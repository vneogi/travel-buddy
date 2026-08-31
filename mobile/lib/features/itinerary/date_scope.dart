import '../../data/models.dart';

/// SPEC-31: Date-scoped itinerary grouping and hotel-stay rescue selection.

/// A calendar-date bucket of trip nodes.
class ItineraryDayGroup {
  final DateTime date;
  final List<TripNode> nodes;

  const ItineraryDayGroup({required this.date, required this.nodes});
}

/// Group [nodes] by the calendar date on their [scheduledStart].
///
/// Date key uses year/month/day directly -- no [toLocal] or [toUtc] call.
/// Preserves input order: nodes within a day keep the server-provided
/// sequence, and groups appear in the order of their first node.
/// The input list is never sorted or mutated.
List<ItineraryDayGroup> groupNodesByCalendarDate(List<TripNode> nodes) {
  final groups = <int, List<TripNode>>{};
  final order = <int>[];
  for (final node in nodes) {
    final key = _dateKey(node.scheduledStart);
    if (!groups.containsKey(key)) {
      groups[key] = [];
      order.add(key);
    }
    groups[key]!.add(node);
  }
  return [
    for (final key in order)
      ItineraryDayGroup(
        date: _dateFromKey(key),
        nodes: List<TripNode>.unmodifiable(groups[key]!),
      ),
  ];
}

/// Whether [node] represents a hotel-like accommodation.
///
/// Matches booking_type == 'hotel' first, then falls back to a
/// case-insensitive name check for hotel, resort, hostel, villa,
/// or guesthouse.
bool isHotelLikeNode(TripNode node) {
  if (node.bookingType == 'hotel') return true;
  final name = node.venueName.toLowerCase();
  return name.contains('hotel') ||
      name.contains('resort') ||
      name.contains('hostel') ||
      name.contains('villa') ||
      name.contains('guesthouse');
}

/// Select the best accommodation for Hotel Rescue.
///
/// A hotel-like node occupies `[start, start + duration)`.
///
/// Precedence:
/// 1. Active stay containing [now] (latest start wins on overlap).
/// 2. Earliest future stay.
/// 3. Most recently ended elapsed stay (latest end wins).
/// 4. null.
///
/// Does not depend on list order.
TripNode? selectRescueStay(List<TripNode> nodes, DateTime now) {
  final hotels = nodes.where(isHotelLikeNode).toList();
  if (hotels.isEmpty) return null;

  // Partition into active, future, elapsed.
  TripNode? bestActive;
  TripNode? bestFuture;
  TripNode? bestElapsed;

  for (final h in hotels) {
    final start = h.scheduledStart;
    final end = start.add(Duration(minutes: h.durationMinutes));

    if (!now.isBefore(start) && now.isBefore(end)) {
      // Active: [start, end) contains now.
      if (bestActive == null ||
          start.isAfter(bestActive.scheduledStart)) {
        bestActive = h;
      }
    } else if (now.isBefore(start)) {
      // Future.
      if (bestFuture == null ||
          start.isBefore(bestFuture.scheduledStart)) {
        bestFuture = h;
      }
    } else {
      // Elapsed: now >= end.
      final bestEnd = bestElapsed == null
          ? null
          : bestElapsed.scheduledStart
              .add(Duration(minutes: bestElapsed.durationMinutes));
      if (bestEnd == null || end.isAfter(bestEnd)) {
        bestElapsed = h;
      }
    }
  }

  return bestActive ?? bestFuture ?? bestElapsed;
}

// ---- private helpers ----

int _dateKey(DateTime dt) => dt.year * 10000 + dt.month * 100 + dt.day;

DateTime _dateFromKey(int key) =>
    DateTime(key ~/ 10000, (key ~/ 100) % 100, key % 100);
