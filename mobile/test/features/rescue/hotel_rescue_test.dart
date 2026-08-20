import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:travel_buddy/data/models.dart';
import 'package:travel_buddy/features/rescue/hotel_rescue_sheet.dart';

TripNode _node(String name, {String nodeKind = 'activity', String? bookingType}) =>
    TripNode(
      nodeId: name,
      venueName: name,
      scheduledStart: DateTime(2026, 10, 5, 9),
      durationMinutes: 90,
      isLocked: nodeKind == 'booking',
      status: NodeStatus.pending,
      vibeTags: const [],
      nodeKind: nodeKind,
      bookingType: bookingType,
    );

void main() {
  group('findHotelNode', () {
    // Sabotage 2: return null even when hotel exists -> this FAILS
    test('identifies hotel booking type', () {
      final nodes = [
        _node('EK501', nodeKind: 'booking', bookingType: 'flight'),
        _node('Hilton Dubai', nodeKind: 'booking', bookingType: 'hotel'),
        _node('Gold Souk'),
      ];
      final hotel = findHotelNode(nodes);
      expect(hotel, isNotNull);
      expect(hotel!.venueName, equals('Hilton Dubai'));
    });

    test('identifies venue with hotel keyword fallback', () {
      final nodes = [
        _node('Morning Market'),
        _node('Maison Souvannaphoum Hotel'),
        _node('Night Bazaar'),
      ];
      final hotel = findHotelNode(nodes);
      expect(hotel, isNotNull);
      expect(hotel!.venueName, equals('Maison Souvannaphoum Hotel'));
    });

    test('returns null when no hotel exists', () {
      final nodes = [
        _node('Cafe Latte'),
        _node('Museum Tour'),
      ];
      expect(findHotelNode(nodes), isNull);
    });

    test('identifies hotel booking with non-generic name (e.g. Villa Maly)', () {
      final nodes = [
        _node('Villa Maly', nodeKind: 'booking', bookingType: 'hotel'),
        _node('Night Market'),
      ];
      final hotel = findHotelNode(nodes);
      expect(hotel, isNotNull);
      expect(hotel!.venueName, equals('Villa Maly'));
    });
  });

  group('TripState serialization', () {
    test('toJson and fromJson roundtrip cleanly', () {
      final trip = TripState(
        tripId: 'trip_1',
        userId: 'user_1',
        mood: 'relaxed',
        nodes: [
          TripNode(
            nodeId: 'n1',
            venueName: 'Hilton',
            scheduledStart: DateTime.utc(2026, 10, 5, 14),
            durationMinutes: 480,
            isLocked: true,
            status: NodeStatus.pending,
            vibeTags: const ['luxury'],
            nodeKind: 'booking',
            bookingType: 'hotel',
            confirmationCode: 'HTL123',
            importSource: 'email',
          ),
        ],
      );

      final json = trip.toJson();
      final restored = TripState.fromJson(json);

      expect(restored.tripId, equals('trip_1'));
      expect(restored.userId, equals('user_1'));
      expect(restored.mood, equals('relaxed'));
      expect(restored.nodes, hasLength(1));
      expect(restored.nodes.first.venueName, equals('Hilton'));
      expect(restored.nodes.first.nodeKind, equals('booking'));
      expect(restored.nodes.first.bookingType, equals('hotel'));
      expect(restored.nodes.first.confirmationCode, equals('HTL123'));

      // Verify JSON can be encoded/decoded (SQLite roundtrip)
      final encoded = jsonEncode(json);
      final decoded = jsonDecode(encoded) as Map<String, dynamic>;
      final restored2 = TripState.fromJson(decoded);
      expect(restored2.nodes.first.venueName, equals('Hilton'));
    });
  });
}
