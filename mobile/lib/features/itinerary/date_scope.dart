import '../../core/destination_tz.dart';
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
/// Date key converts to destination-local so that a Vientiane 02:00 UTC
/// node (= 09:00 ICT, same calendar day) is grouped correctly even when
/// the device timezone is IST (+5:30, which would place it on the wrong
/// calendar date).
/// Preserves input order: nodes within a day keep the server-provided
/// sequence, and groups appear in the order of their first node.
/// The input list is never sorted or mutated.
List<ItineraryDayGroup> groupNodesByCalendarDate(List<TripNode> nodes) {
  final result = <ItineraryDayGroup>[];
  int? currentKey;
  List<TripNode>? currentNodes;

  for (final node in nodes) {
    final local = toDestinationLocal(node.scheduledStart, node.geoRegion);
    final key = _dateKey(local);
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

/// SPEC-10: Presentation-layer grouping that expands hotel bookings across
/// every destination-local covered night [check-in date, checkout date).
///
/// The same TripNode object (same node_id) appears in every covered date
/// group.  Flights, trains, tours, and ordinary activities remain on
/// their single scheduledStart date.
///
/// Uses a bucket map so that a hotel spanning Oct 2-4 places the node
/// into the Oct 2 and Oct 3 buckets.  This may merge non-contiguous
/// same-date inputs (unlike [groupNodesByCalendarDate] which preserves
/// A/B/A ordering).  That is acceptable for the presentation layer.
List<ItineraryDayGroup> groupNodesByCalendarDateWithHotelStays(
    List<TripNode> nodes) {
  final buckets = <int, List<TripNode>>{};
  final keyOrder = <int>[];

  for (final node in nodes) {
    final dates = _coveredDateKeys(node);
    for (final key in dates) {
      if (!buckets.containsKey(key)) {
        buckets[key] = [];
        keyOrder.add(key);
      }
      buckets[key]!.add(node);
    }
  }

  return keyOrder
      .map((key) => ItineraryDayGroup(
            date: _dateFromKey(key),
            nodes: List<TripNode>.unmodifiable(buckets[key]!),
          ))
      .toList();
}

/// Return the date keys a node covers.
///
/// Hotels: [check-in local date, checkout local date) — one key per
/// covered night.  Everything else: a single key for scheduledStart.
List<int> _coveredDateKeys(TripNode node) {
  final local = toDestinationLocal(node.scheduledStart, node.geoRegion);
  final startKey = _dateKey(local);
  if (node.nodeKind != 'booking' || node.bookingType != 'hotel') {
    return [startKey];
  }
  final checkoutUtc =
      node.scheduledStart.add(Duration(minutes: node.durationMinutes));
  final checkoutLocal = toDestinationLocal(checkoutUtc, node.geoRegion);
  final endKey = _dateKey(checkoutLocal);
  if (endKey <= startKey) return [startKey];
  final keys = <int>[];
  var cursor = _dateFromKey(startKey);
  final endDate = _dateFromKey(endKey);
  while (cursor.isBefore(endDate)) {
    keys.add(_dateKey(cursor));
    cursor = cursor.add(const Duration(days: 1));
  }
  return keys;
}

// ---- private helpers ----

int _dateKey(DateTime dt) => dt.year * 10000 + dt.month * 100 + dt.day;

DateTime _dateFromKey(int key) =>
    DateTime(key ~/ 10000, (key ~/ 100) % 100, key % 100);


String _effectiveSegmentEndDate(String endsOn, List<TripNode> segNodes, String geoRegion) {
  var best = DateTime.parse(endsOn);
  for (final node in segNodes) {
    if (node.nodeKind == 'booking' && node.bookingType == 'hotel') {
      final checkout = toDestinationLocal(
        node.scheduledStart.add(Duration(minutes: node.durationMinutes)),
        geoRegion,
      );
      final checkoutDate = DateTime(checkout.year, checkout.month, checkout.day);
      if (checkoutDate.isAfter(best)) {
        best = checkoutDate;
      }
    }
  }
  final mm = best.month.toString().padLeft(2, '0');
  final dd = best.day.toString().padLeft(2, '0');
  return '${best.year}-$mm-$dd';
}


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
/// Preserves input node order and delegates to
/// [groupNodesByCalendarDateWithHotelStays] so multi-night hotels appear
/// on every covered date.
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
    final dayGroups = groupNodesByCalendarDateWithHotelStays(segNodes);
    final displayName = regionDisplayNames[seg.geoRegion] ?? seg.geoRegion;
    result.add(CorridorCityGroup(
      geoRegion: seg.geoRegion,
      displayName: displayName,
      dateRange: '${seg.startsOn} - ${_effectiveSegmentEndDate(seg.endsOn, segNodes, seg.geoRegion)}',
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
      dayGroups: groupNodesByCalendarDateWithHotelStays(remainingNodes),
    ));
  }

  return result;
}



/// SPEC-42: Build day groups for the entire trip span, including empty days.
///
/// Walks every calendar date from [startLocal] to [endLocal] inclusive.
/// Days with nodes get their nodes; days without get an empty group.
/// This ensures the UI renders date headers for all dates in the span.
/// Uses [groupNodesByCalendarDateWithHotelStays] so multi-night hotels
/// appear on every covered date.
List<ItineraryDayGroup> spanAwareDayGroups({
  required List<TripNode> nodes,
  required DateTime startLocal,
  required DateTime endLocal,
}) {
  final populated = groupNodesByCalendarDateWithHotelStays(nodes);
  final byKey = <int, ItineraryDayGroup>{};
  for (final g in populated) {
    byKey[_dateKey(g.date)] = g;
  }

  final result = <ItineraryDayGroup>[];
  var cursor = DateTime(startLocal.year, startLocal.month, startLocal.day);
  final end = DateTime(endLocal.year, endLocal.month, endLocal.day);
  while (!cursor.isAfter(end)) {
    final key = _dateKey(cursor);
    result.add(byKey[key] ??
        ItineraryDayGroup(date: cursor, nodes: const []));
    cursor = cursor.add(const Duration(days: 1));
  }
  return result;
}


/// SPEC-42: Corridor variant -- build span-aware day groups for each segment
/// using TripSegment.startsOn/endsOn, not creationContext.
List<CorridorCityGroup> spanAwareCorridorGroups({
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
    // Parse segment dates to derive the full local span.
    final sd = DateTime.parse(seg.startsOn);
    final ed = DateTime.parse(seg.endsOn);
    final dayGroups = spanAwareDayGroups(
      nodes: segNodes,
      startLocal: sd,
      endLocal: ed,
    );
    final displayName = regionDisplayNames[seg.geoRegion] ?? seg.geoRegion;
    result.add(CorridorCityGroup(
      geoRegion: seg.geoRegion,
      displayName: displayName,
      dateRange: '${seg.startsOn} - ${_effectiveSegmentEndDate(seg.endsOn, segNodes, seg.geoRegion)}',
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
      dayGroups: groupNodesByCalendarDateWithHotelStays(remainingNodes),
    ));
  }

  return result;
}
