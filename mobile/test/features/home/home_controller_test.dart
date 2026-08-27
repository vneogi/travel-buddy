import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mocktail/mocktail.dart';

import 'package:travel_buddy/core/api_exception.dart';
import 'package:travel_buddy/core/providers.dart';
import 'package:travel_buddy/data/repositories.dart';
import 'package:travel_buddy/features/home/home_controller.dart';
import 'package:travel_buddy/offline/offline_database.dart';

class MockTripRepository extends Mock implements TripRepository {}
class MockOfflineDatabase extends Mock implements OfflineDatabase {}

void main() {
  late MockTripRepository repository;
  late MockOfflineDatabase database;

  ProviderContainer container() => ProviderContainer(
        overrides: [
          tripRepoProvider.overrideWithValue(repository),
          offlineDatabaseProvider.overrideWithValue(database),
          identityCacheScopeProvider.overrideWithValue('anonymous:device-a'),
        ],
      );

  setUp(() {
    repository = MockTripRepository();
    database = MockOfflineDatabase();
  });

  test('network failure reads only the current identity cache with age', () async {
    final cachedAt = DateTime.utc(2026, 8, 27, 9);
    when(() => repository.getHomeSnapshot()).thenThrow(const NetworkException());
    when(() => database.getCachedTripList('anonymous:device-a')).thenAnswer(
      (_) async => (
        json: jsonEncode({
          'supported_regions': ['dubai_uae'],
          'trips': [],
        }),
        cachedAt: cachedAt,
      ),
    );
    final scope = container();
    addTearDown(scope.dispose);

    final snapshot = await scope.read(homeSnapshotProvider.future);

    expect(snapshot.fromCache, isTrue);
    expect(snapshot.cachedAt, cachedAt);
    verify(() => database.getCachedTripList('anonymous:device-a')).called(1);
  });

  test('authorization failure never falls back to another cached identity', () async {
    when(() => repository.getHomeSnapshot())
        .thenThrow(const UnauthorizedException());
    final scope = container();
    addTearDown(scope.dispose);

    await expectLater(
      scope.read(homeSnapshotProvider.future),
      throwsA(isA<UnauthorizedException>()),
    );
    verifyNever(() => database.getCachedTripList(any()));
  });
}
