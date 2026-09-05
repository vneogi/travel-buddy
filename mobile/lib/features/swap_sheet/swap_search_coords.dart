import '../../data/models.dart';
import '../../data/region_defaults.dart';

/// Resolve lat/lng for swap venue search from the trip, never silently
/// substituting Dubai for a non-Dubai region.
({double lat, double lng})? resolveSwapSearchCoords(TripState ts) {
  if (ts.locationLat != null && ts.locationLng != null) {
    final isDubaiDefault =
        ts.locationLat == 25.1972 && ts.locationLng == 55.2744;
    if (!isDubaiDefault || ts.geoRegion == 'dubai_uae') {
      return (lat: ts.locationLat!, lng: ts.locationLng!);
    }
  }
  return RegionDefaults.coordsFor(ts.geoRegion);
}
