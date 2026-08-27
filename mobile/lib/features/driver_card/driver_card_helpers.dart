import 'dart:convert';

import '../../data/models.dart';
import '../../render/fact_envelope.dart';

/// SPEC-12 Decision 4: ordered language preference per region.
List<String> languagePriority(String? geoRegion) {
  final region = (geoRegion ?? '').toLowerCase();
  if (region.contains('laos')) return const ['lo', 'th', 'en'];
  if (region.contains('dubai')) return const ['ar', 'en'];
  return const ['en'];
}

/// Walks the region language priority list and returns the first
/// matching entry from [localizedMap] where value is non-empty.
MapEntry<String, Map<String, dynamic>>? resolvePreferredLocalEntry({
  required Map<String, dynamic>? localizedMap,
  required String? geoRegion,
}) {
  if (localizedMap == null || localizedMap.isEmpty) return null;
  final priority = languagePriority(geoRegion);
  for (final lang in priority) {
    final entry = localizedMap[lang];
    if (entry is Map<String, dynamic>) {
      final value = entry['value'];
      if (value is String && value.isNotEmpty) {
        return MapEntry(lang, entry);
      }
    }
  }
  return null;
}

/// SPEC-12 Decision 3 + SPEC-22: provenance to FactTier.
FactTier tierForNameSource(String source) {
  switch (source) {
    case 'wikidata':
    case 'osm':
    case 'official':
    case 'manual':
    case 'field_verified':
      return FactTier.assert_;
    case 'generated':
      return FactTier.ask;
    default:
      return FactTier.refuse;
  }
}

/// Offline map hand-off. `geo:` opens the device map app on Android without a
/// Google dependency; coordinates stay on the card as the last-resort fallback.
Uri? buildMapsUri(double? lat, double? lng) {
  if (lat == null || lng == null) return null;
  return Uri.parse('geo:$lat,$lng?q=$lat,$lng');
}

/// Data class for offline driver card rendering from SQLite cache_place.
class PlaceDriverCardData {
  final String placeRef;
  final String venueName;
  final Map<String, dynamic>? namesLocal;
  final String? nearestLandmark;
  final Map<String, dynamic>? landmarksLocal;
  final double? lat;
  final double? lng;
  final String? microLocation;
  final String? geoRegion;

  const PlaceDriverCardData({
    required this.placeRef,
    required this.venueName,
    this.namesLocal,
    this.nearestLandmark,
    this.landmarksLocal,
    this.lat,
    this.lng,
    this.microLocation,
    this.geoRegion,
  });

  factory PlaceDriverCardData.fromTripNode(TripNode node) {
    return PlaceDriverCardData(
      placeRef: node.venueId ?? node.venueName,
      venueName: node.venueName,
      namesLocal: node.namesLocal,
      nearestLandmark: node.nearestLandmark,
      landmarksLocal: node.landmarksLocal,
      lat: node.lat,
      lng: node.lng,
      microLocation: node.microLocation,
      geoRegion: node.geoRegion,
    );
  }

  factory PlaceDriverCardData.fromJson(Map<String, dynamic> j) {
    return PlaceDriverCardData(
      placeRef: j['place_ref'] as String,
      venueName: j['venue_name'] as String,
      namesLocal: (j['names_local'] as Map?)?.cast<String, dynamic>(),
      nearestLandmark: j['nearest_landmark'] as String?,
      landmarksLocal: (j['landmarks_local'] as Map?)?.cast<String, dynamic>(),
      lat: (j['lat'] as num?)?.toDouble(),
      lng: (j['lng'] as num?)?.toDouble(),
      microLocation: j['micro_location'] as String?,
      geoRegion: j['geo_region'] as String?,
    );
  }

  Map<String, dynamic> toJson() => {
        'place_ref': placeRef,
        'venue_name': venueName,
        'names_local': namesLocal,
        'nearest_landmark': nearestLandmark,
        'landmarks_local': landmarksLocal,
        'lat': lat,
        'lng': lng,
        'micro_location': microLocation,
        'geo_region': geoRegion,
      };

  String serialize() => jsonEncode(toJson());

  static PlaceDriverCardData deserialize(String data) =>
      PlaceDriverCardData.fromJson(jsonDecode(data) as Map<String, dynamic>);
}
