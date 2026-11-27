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
  /// SPEC-57 Amendment 2: sourced flat-fare cards (all parsed entries).
  final List<FlatFare> flatFares;

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
    this.flatFares = const [],
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
        flatFares: _flatFares(j['flat_fares']),
      );

  /// True when both fare band ends are present.
  bool get hasFare => fareBandLow != null && fareBandHigh != null;

  /// Scam notes with blank entries removed.
  List<String> get visibleScamNotes =>
      scamNotes.where((n) => n.trim().isNotEmpty).toList();

  /// Flat-fare cards that are complete and valid; the rest are skipped.
  List<FlatFare> get validFlatFares => flatFares.where((f) => f.isValid).toList();
}

/// SPEC-57 Amendment 2: one sourced, dated flat fare for a named route and
/// vehicle. Shown exactly as stored; never computed, rounded or repaired.
class FlatFare {
  final String? route;
  final String? vehicle;
  final String? currency;
  final int? low;
  final int? high;
  final String? basis;
  final String? source;
  final String? surveyedOn;

  const FlatFare({
    this.route,
    this.vehicle,
    this.currency,
    this.low,
    this.high,
    this.basis,
    this.source,
    this.surveyedOn,
  });

  factory FlatFare.fromJson(Map<String, dynamic> j) => FlatFare(
        route: _str(j['route']),
        vehicle: _str(j['vehicle']),
        currency: _str(j['currency']),
        low: _int(j['low']),
        high: _int(j['high']),
        basis: _str(j['basis']),
        source: _str(j['source']),
        surveyedOn: _str(j['surveyed_on']),
      );

  /// Every string non-empty, a 3-letter uppercase currency, whole numbers
  /// with 0 < low <= high, and an ISO surveyed_on date that parses.
  bool get isValid {
    for (final s in [route, vehicle, currency, basis, source, surveyedOn]) {
      if (s == null || s.trim().isEmpty) return false;
    }
    final lo = low, hi = high;
    if (lo == null || hi == null || lo <= 0 || lo > hi) return false;
    if (!RegExp(r'^[A-Z]{3}$').hasMatch(currency!)) return false;
    return _isIsoDate(surveyedOn!);
  }
}

String? _str(Object? v) => v is String ? v : null;

/// Whole numbers only; a fractional or non-numeric value is not repaired.
int? _int(Object? v) => v is int ? v : null;

bool _isIsoDate(String s) {
  final m = RegExp(r'^(\d{4})-(\d{2})-(\d{2})$').firstMatch(s);
  if (m == null) return false;
  final y = int.parse(m.group(1)!), mo = int.parse(m.group(2)!), d = int.parse(m.group(3)!);
  final dt = DateTime.utc(y, mo, d);
  return dt.year == y && dt.month == mo && dt.day == d;
}

List<FlatFare> _flatFares(Object? raw) => raw is List
    ? raw
        .whereType<Map>()
        .map((m) => FlatFare.fromJson(m.cast<String, dynamic>()))
        .toList()
    : const <FlatFare>[];

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
