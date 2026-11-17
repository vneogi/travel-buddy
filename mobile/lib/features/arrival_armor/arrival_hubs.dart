import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../data/models.dart';

/// SPEC-57 slice 1: arrival hubs bundled with the app. Money and scam fields
/// stay null or empty until owner-surveyed data lands; never invent them.
class ArrivalHub {
  final String id;
  final String label;
  final List<String> geoRegions;
  final List<String> bookingTypes;
  final String? currency;
  final int? fareBandLow;
  final int? fareBandHigh;
  final int? hardCeiling;
  final String? officialOption;
  final List<String> scamNotes;
  final String? surveyedOn;
  final String? source;

  const ArrivalHub({
    required this.id,
    required this.label,
    this.geoRegions = const [],
    this.bookingTypes = const [],
    this.currency,
    this.fareBandLow,
    this.fareBandHigh,
    this.hardCeiling,
    this.officialOption,
    this.scamNotes = const [],
    this.surveyedOn,
    this.source,
  });

  factory ArrivalHub.fromJson(Map<String, dynamic> j) => ArrivalHub(
        id: j['id'] as String,
        label: j['label'] as String,
        geoRegions: _strings(j['geo_regions']),
        bookingTypes: _strings(j['booking_types']),
        currency: j['currency'] as String?,
        fareBandLow: (j['fare_band_low'] as num?)?.toInt(),
        fareBandHigh: (j['fare_band_high'] as num?)?.toInt(),
        hardCeiling: (j['hard_ceiling'] as num?)?.toInt(),
        officialOption: j['official_option'] as String?,
        scamNotes: _strings(j['scam_notes']),
        surveyedOn: j['surveyed_on'] as String?,
        source: j['source'] as String?,
      );

  /// True when both fare band ends are present.
  bool get hasFare => fareBandLow != null && fareBandHigh != null;

  /// Scam notes with blank entries removed.
  List<String> get visibleScamNotes =>
      scamNotes.where((n) => n.trim().isNotEmpty).toList();
}

List<String> _strings(Object? raw) =>
    raw is List ? raw.whereType<String>().toList() : const <String>[];

/// Parse the bundled asset: a JSON object with a `hubs` list.
List<ArrivalHub> parseArrivalHubs(String json) {
  final decoded = jsonDecode(json) as Map<String, dynamic>;
  final hubs = decoded['hubs'] as List? ?? const [];
  return hubs
      .map((h) => ArrivalHub.fromJson((h as Map).cast<String, dynamic>()))
      .toList();
}

/// First hub whose regions include [geoRegion] and whose booking types
/// include [bookingType]. Null when either input is null.
ArrivalHub? hubForBooking({
  required String? geoRegion,
  required String? bookingType,
  required List<ArrivalHub> hubs,
}) {
  if (geoRegion == null || bookingType == null) return null;
  for (final hub in hubs) {
    if (hub.geoRegions.contains(geoRegion) &&
        hub.bookingTypes.contains(bookingType)) {
      return hub;
    }
  }
  return null;
}

/// Earliest hotel booking starting at or after [from]. Ties on start prefer
/// the hotel in [from]'s region, then the lowest nodeId.
TripNode? nextHotelDestination({
  required TripNode from,
  required List<TripNode> nodes,
}) {
  final hotels = nodes
      .where((n) =>
          n.nodeKind == 'booking' &&
          n.bookingType == 'hotel' &&
          !n.scheduledStart.isBefore(from.scheduledStart))
      .toList();
  if (hotels.isEmpty) return null;
  final region = from.geoRegion;
  hotels.sort((a, b) {
    final byStart = a.scheduledStart.compareTo(b.scheduledStart);
    if (byStart != 0) return byStart;
    if (region != null) {
      final aLocal = a.geoRegion == region ? 0 : 1;
      final bLocal = b.geoRegion == region ? 0 : 1;
      if (aLocal != bLocal) return aLocal.compareTo(bLocal);
    }
    return a.nodeId.compareTo(b.nodeId);
  });
  return hotels.first;
}

const String kArrivalHubsAsset = 'assets/arrival_hubs.json';

/// Bundled hubs, loaded once from the asset (no network). Any load or parse
/// failure yields an empty list so the overflow simply hides the entry.
final arrivalHubsProvider = FutureProvider<List<ArrivalHub>>((ref) async {
  try {
    return parseArrivalHubs(await rootBundle.loadString(kArrivalHubsAsset));
  } catch (_) {
    return const <ArrivalHub>[];
  }
});
