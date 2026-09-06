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

/// SPEC-36: A city section in a corridor itinerary.
class CorridorCityGroup {
  final String geoRegion;
  final String displayName;
  final String dateRange;
  final List<ItineraryDayGroup> dayGroups;

  const CorridorCityGroup({
    required this.geoRegion,
    required this.displayName,
    required this.dateRange,
    required this.dayGroups,
  });

  /// True when every node in the section ends before [now].
  bool isPast(DateTime now) {
    for (final day in dayGroups) {
      for (final node in day.nodes) {
        final end = node.scheduledStart.add(
          Duration(minutes: node.durationMinutes),
        );
        if (!end.isBefore(now)) return false;
      }
    }
    return dayGroups.isNotEmpty;
  }
}

/// Region code to display name mapping.
///
/// Shared by [groupNodesByCorridor] and the corridor date form.
const regionDisplayNames = {
  'dubai_uae': 'Dubai',
  'luang_prabang_laos': 'Luang Prabang',
  'vang_vieng_laos': 'Vang Vieng',
  'vientiane_laos': 'Vientiane',
};

/// SPEC-36: Group corridor nodes by city segment, then by date within each.
///
/// Follows TripState.segments order; never alphabetical.
/// Nodes with unknown region go to 'Other stops'.
/// Preserves input node order and delegates to [groupNodesByCalendarDate].
List<CorridorCityGroup> groupNodesByCorridor({
  required List<TripNode> nodes,
  required List<TripSegment> segments,
}) {
  final result = <CorridorCityGroup>[];
  final usedNodeIndexes = <int>{};

  for (final seg in segments) {
    final segNodes = <TripNode>[];
    for (var i = 0; i < nodes.length; i++) {
      if (usedNodeIndexes.contains(i)) continue;
      if (nodes[i].geoRegion == seg.geoRegion) {
        segNodes.add(nodes[i]);
        usedNodeIndexes.add(i);
      }
    }
    final dayGroups = groupNodesByCalendarDate(segNodes);
    final displayName = regionDisplayNames[seg.geoRegion] ?? seg.geoRegion;
    result.add(CorridorCityGroup(
      geoRegion: seg.geoRegion,
      displayName: displayName,
      dateRange: '${seg.startsOn} - ${seg.endsOn}',
      dayGroups: dayGroups,
    ));
  }

  // Other stops: nodes not matched to any segment
  final remainingNodes = <TripNode>[];
  for (var i = 0; i < nodes.length; i++) {
    if (!usedNodeIndexes.contains(i)) {
      remainingNodes.add(nodes[i]);
    }
  }
  if (remainingNodes.isNotEmpty) {
    result.add(CorridorCityGroup(
      geoRegion: 'other',
      displayName: 'Other stops',
      dateRange: '',
      dayGroups: groupNodesByCalendarDate(remainingNodes),
    ));
  }

  return result;
}

