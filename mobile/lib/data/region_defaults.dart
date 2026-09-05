/// Default coordinates per geo_region code.
///
/// Mirrors config/regions.py on the backend. Used as fallback when
/// TripState.current_context does not carry explicit lat/lng.
class RegionDefaults {
  RegionDefaults._();

  /// Returns the (lat, lng) pair for a known region code, or null if the
  /// region is unknown. Never silently falls back to Dubai for a non-Dubai
  /// trip -- callers must handle null.
  static ({double lat, double lng})? coordsFor(String? geoRegion) {
    if (geoRegion == null) return null;
    return _defaults[geoRegion];
  }

  static const _defaults = <String, ({double lat, double lng})>{
    'dubai_uae': (lat: 25.1972, lng: 55.2744),
    'luang_prabang_laos': (lat: 19.8856, lng: 102.1347),
    'vang_vieng_laos': (lat: 18.9220, lng: 102.4474),
    'vientiane_laos': (lat: 17.9757, lng: 102.6331),
  };
}
