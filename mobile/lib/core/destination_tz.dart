/// Lightweight region-to-UTC-offset mapping for destination-local
/// time display.  No heavy timezone package needed -- the backend
/// stores all times in UTC and the app converts for display only.
///
/// To add a region: add it to [_regionOffsets] and the test.


/// Map geo_region identifiers to their UTC offset in hours.
/// DST is not relevant for current corridors (ICT/GST are fixed).
const _regionOffsets = <String, int>{
  'dubai_uae': 4,         // GST  UTC+4
  'vientiane_laos': 7,    // ICT  UTC+7
  'luang_prabang_laos': 7,
  'vang_vieng_laos': 7,
};

/// The UTC offset (as a [Duration]) for a geo_region.
/// Returns null for unknown regions, letting the caller fall back.
Duration? destinationOffset(String? geoRegion) {
  if (geoRegion == null) return null;
  final hours = _regionOffsets[geoRegion];
  if (hours == null) return null;
  return Duration(hours: hours);
}

/// Convert a UTC [DateTime] to destination-local for display.
/// Falls back to the device-local time when the region is unknown.
DateTime toDestinationLocal(DateTime utc, String? geoRegion) {
  final offset = destinationOffset(geoRegion);
  if (offset == null) return utc.toLocal();
  return utc.toUtc().add(offset);
}

/// Format a [DateTime] as HH:MM in the destination timezone.
String formatDestinationTime(DateTime utc, String? geoRegion) {
  final local = toDestinationLocal(utc, geoRegion);
  return '${local.hour.toString().padLeft(2, "0")}:'
      '${local.minute.toString().padLeft(2, "0")}';
}
