import '../../data/models.dart';
import '../../data/region_defaults.dart';

/// Resolve lat/lng for swap venue search.
///
/// When [targetNode] is provided (corridor trips), prefer its own coordinates
/// so a Luang Prabang card searches around Luang Prabang, not Vientiane.
/// Falls back to trip-level coords, then region defaults.
({double lat, double lng})? resolveSwapSearchCoords(
  TripState ts, {
  TripNode? targetNode,
}) {
  // 1. Target node's own coordinates (corridor-safe).
  if (targetNode != null &&
      targetNode.lat != null &&
      targetNode.lng != null) {
    return (lat: targetNode.lat!, lng: targetNode.lng!);
  }

  // 2. Trip-level hint (single-city path).
  if (ts.locationLat != null && ts.locationLng != null) {
    final isDubaiDefault =
        ts.locationLat == 25.1972 && ts.locationLng == 55.2744;
    if (!isDubaiDefault || ts.geoRegion == 'dubai_uae') {
      return (lat: ts.locationLat!, lng: ts.locationLng!);
    }
  }

  // 3. Region defaults for the target node's city, then trip geo_region.
  final region = targetNode?.geoRegion ?? ts.geoRegion;
  return RegionDefaults.coordsFor(region);
}
