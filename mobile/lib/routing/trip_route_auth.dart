/// SPEC-43 Gap 12: refuse a trip route the current identity does not own.
///
/// Sibling of [redirectForAuth]. Auth and ownership stay separate.
library;

import 'package:flutter/foundation.dart';

/// Trip id from a router location, or null when the location is not a
/// trip route. Ignores the query string.
///
/// `/trip/<id>`, `/trip/<id>/chat`, `/trip/<id>/card/<nodeId>` -> id.
/// `/trip/create`, `/`, `/profile`, `/onboarding` -> null.
String? tripIdFromLocation(String location) {
  final uri = Uri.tryParse(location);
  if (uri == null) return null;
  final segments = uri.pathSegments.where((s) => s.isNotEmpty).toList();
  if (segments.length < 2 || segments.first != 'trip') return null;
  final id = segments[1];
  if (id == 'create') return null;
  return id;
}

/// Owned-trip-id catalog for the current identity.
///
/// `loaded` is false until the first home snapshot (network or cache) or
/// a successful trip load. Gap 6 sign-out clears it.
class OwnedTripCatalog extends ChangeNotifier {
  bool _loaded = false;
  final Set<String> _ids = <String>{};

  bool get loaded => _loaded;
  Set<String> get ids => Set.unmodifiable(_ids);

  /// Replace the owned set (home snapshot) and mark loaded.
  void replaceAll(Iterable<String> ids) {
    final next = ids.where((id) => id.isNotEmpty).toSet();
    if (_loaded && setEquals(next, _ids)) return;
    _ids
      ..clear()
      ..addAll(next);
    _loaded = true;
    notifyListeners();
  }

  /// Add one owned id (just-created trip, successful trip load).
  void add(String tripId) {
    if (tripId.isEmpty) return;
    final changed = _ids.add(tripId) || !_loaded;
    _loaded = true;
    if (changed) notifyListeners();
  }

  /// Forget everything (identity change). Back to not loaded.
  void clear() {
    if (!_loaded && _ids.isEmpty) return;
    _ids.clear();
    _loaded = false;
    notifyListeners();
  }
}

/// Process-wide catalog read by the app router redirect.
final ownedTripCatalog = OwnedTripCatalog();

/// Ownership redirect for a router location.
///
/// No trip id -> null. Catalog not loaded -> null (do not block first
/// paint). Loaded and owned -> null. Loaded and not owned -> '/'.
String? redirectForTripOwnership({
  required String location,
  required bool catalogLoaded,
  required Set<String> ownedTripIds,
}) {
  final tripId = tripIdFromLocation(location);
  if (tripId == null) return null;
  if (!catalogLoaded) return null;
  if (ownedTripIds.contains(tripId)) return null;
  return '/';
}
