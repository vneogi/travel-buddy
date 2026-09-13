import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/destination_tz.dart';

void main() {
  group('destinationOffset', () {
    test('Vientiane is UTC+7', () {
      expect(destinationOffset('vientiane_laos'), const Duration(hours: 7));
    });

    test('Dubai is UTC+4', () {
      expect(destinationOffset('dubai_uae'), const Duration(hours: 4));
    });

    test('unknown region returns null', () {
      expect(destinationOffset('atlantis'), isNull);
      expect(destinationOffset(null), isNull);
    });
  });

  group('toDestinationLocal', () {
    test('Vientiane 02:00Z renders 09:00 local', () {
      final utc = DateTime.utc(2026, 9, 15, 2, 0);
      final local = toDestinationLocal(utc, 'vientiane_laos');
      expect(local.hour, 9);
      expect(local.minute, 0);
    });

    test('Dubai 05:00Z renders 09:00 local', () {
      final utc = DateTime.utc(2026, 9, 15, 5, 0);
      final local = toDestinationLocal(utc, 'dubai_uae');
      expect(local.hour, 9);
      expect(local.minute, 0);
    });
  });

  group('formatDestinationTime', () {
    test('formats Vientiane 02:00Z as 09:00', () {
      final utc = DateTime.utc(2026, 9, 15, 2, 0);
      expect(formatDestinationTime(utc, 'vientiane_laos'), '09:00');
    });

    test('formats with leading zeros', () {
      final utc = DateTime.utc(2026, 9, 15, 0, 5); // 07:05 ICT
      expect(formatDestinationTime(utc, 'vientiane_laos'), '07:05');
    });
  });
}
