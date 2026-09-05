import '../../data/models.dart';

// SPEC-31: Date-scoped itinerary grouping.

/// A calendar-date bucket of trip nodes.
class ItineraryDayGroup {
  final DateTime date;
  final List<TripNode> nodes;

  const ItineraryDayGroup({required this.date, required this.nodes});
}

/// Group `nodes` by the calendar date on their `scheduledStart`.
///
/// Date key uses year/month/day directly -- no toLocal or toUtc call.
/// Preserves input order: nodes within a day keep the server-provided
/// sequence, and groups appear in the order of their first node.
/// The input list is never sorted or mutated.
List<ItineraryDayGroup> groupNodesByCalendarDate(List<TripNode> nodes) {
  final result = <ItineraryDayGroup>[];
  int? currentKey;
  List<TripNode>? currentNodes;

  for (final node in nodes) {
    final key = _dateKey(node.scheduledStart);
    if (key != currentKey) {
      if (currentNodes != null) {
        result.add(ItineraryDayGroup(
          date: _dateFromKey(currentKey!),
          nodes: List<TripNode>.unmodifiable(currentNodes),
        ));
      }
      currentKey = key;
      currentNodes = [node];
    } else {
      currentNodes!.add(node);
    }
  }
  if (currentNodes != null) {
    result.add(ItineraryDayGroup(
      date: _dateFromKey(currentKey!),
      nodes: List<TripNode>.unmodifiable(currentNodes),
    ));
  }
  return result;
}

// ---- private helpers ----

int _dateKey(DateTime dt) => dt.year * 10000 + dt.month * 100 + dt.day;

DateTime _dateFromKey(int key) =>
    DateTime(key ~/ 10000, (key ~/ 100) % 100, key % 100);
