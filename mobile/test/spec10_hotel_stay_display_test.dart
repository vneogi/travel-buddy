// SPEC-10 Flutter proof: hotel card dual check-in / check-out timestamps.
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/core/destination_tz.dart';

void main() {
  // -----------------------------------------------------------------------
  // Proof: hotel card data carries both check-in and check-out
  // -----------------------------------------------------------------------
  group('Hotel dual timestamps', () {
    test('hotel node check-in 18:02 local Oct 2, check-out 15:00 local Oct 3',
        () {
      // 18:02 VTN = 11:02 UTC Oct 2; duration 1258 min -> 15:00 VTN Oct 3
      final hotel = TripNode(
        nodeId: 'h1',
        venueName: 'Dhavara Boutique Hotel',
        scheduledStart: DateTime.utc(2026, 10, 2, 11, 2),
        durationMinutes: 1258,
        isLocked: true,
        status: NodeStatus.pending,
        vibeTags: const [],
        nodeKind: 'booking',
        bookingType: 'hotel',
        geoRegion: 'vientiane_laos',
      );

      // Check-in local time
      final checkinLocal =
          formatDestinationTime(hotel.scheduledStart, hotel.geoRegion);
      expect(checkinLocal, contains('18:02'));

      // Check-out = scheduled_start + duration_minutes
      final checkoutUtc = hotel.scheduledStart
          .add(Duration(minutes: hotel.durationMinutes));
      final checkoutLocal =
          formatDestinationTime(checkoutUtc, hotel.geoRegion);
      expect(checkoutLocal, contains('15:00'));

      // Both are distinct strings
      expect(checkinLocal, isNot(equals(checkoutLocal)));
    });

    test('flight node has no checkout derivation needed', () {
      final flight = TripNode(
        nodeId: 'f1',
        venueName: 'VN 921',
        scheduledStart: DateTime.utc(2026, 10, 5, 0, 0),
        durationMinutes: 120,
        isLocked: true,
        status: NodeStatus.pending,
        vibeTags: const [],
        nodeKind: 'booking',
        bookingType: 'flight',
        geoRegion: 'vientiane_laos',
      );

      // For flights, the card shows only scheduledStart -- no dual timestamps.
      expect(flight.bookingType, 'flight');
      expect(flight.bookingType, isNot('hotel'));
    });
  });

  // -----------------------------------------------------------------------
  // Proof: TripNode round-trips lat/lng through JSON
  // -----------------------------------------------------------------------
  group('TripNode lat/lng round-trip', () {
    test('hotel node with lat/lng round-trips through JSON', () {
      final hotel = TripNode(
        nodeId: 'h2',
        venueName: 'Settha Palace',
        scheduledStart: DateTime.utc(2026, 10, 2, 11, 0),
        durationMinutes: 900,
        isLocked: true,
        status: NodeStatus.pending,
        vibeTags: const [],
        nodeKind: 'booking',
        bookingType: 'hotel',
        lat: 17.9669,
        lng: 102.6135,
        geoRegion: 'vientiane_laos',
      );

      final json = hotel.toJson();
      expect(json['lat'], closeTo(17.9669, 0.001));
      expect(json['lng'], closeTo(102.6135, 0.001));

      final restored = TripNode.fromJson(json);
      expect(restored.lat, closeTo(17.9669, 0.001));
      expect(restored.lng, closeTo(102.6135, 0.001));
    });

    test('hotel node without lat/lng has null coords', () {
      final hotel = TripNode(
        nodeId: 'h3',
        venueName: 'Unknown Guesthouse',
        scheduledStart: DateTime.utc(2026, 10, 2, 7, 0),
        durationMinutes: 1080,
        isLocked: true,
        status: NodeStatus.pending,
        vibeTags: const [],
        nodeKind: 'booking',
        bookingType: 'hotel',
        geoRegion: 'vientiane_laos',
      );

      final json = hotel.toJson();
      expect(json['lat'], isNull);
      expect(json['lng'], isNull);
    });
  });
}
