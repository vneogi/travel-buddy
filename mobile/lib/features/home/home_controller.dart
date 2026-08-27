import 'dart:convert';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models.dart';

final homeSnapshotProvider = FutureProvider.autoDispose<HomeSnapshot>((ref) async {
  final repository = ref.watch(tripRepoProvider);
  final database = ref.watch(offlineDatabaseProvider);
  final cacheScope = ref.watch(identityCacheScopeProvider);

  try {
    final snapshot = await repository.getHomeSnapshot();
    try {
      await database.cacheTripList(
        cacheScope,
        jsonEncode(snapshot.toJson()),
      );
    } catch (_) {
      // A cache write must never turn a successful network response into an
      // error or stale fallback.
    }
    return snapshot;
  } on NetworkException {
    final cached = await database.getCachedTripList(cacheScope);
    if (cached == null) rethrow;
    return HomeSnapshot.fromJson(
      (jsonDecode(cached.json) as Map).cast<String, dynamic>(),
      fromCache: true,
      cachedAt: cached.cachedAt,
    );
  }
});
