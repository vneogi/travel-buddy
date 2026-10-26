// SPEC-43 Gap 12: refuse another identity's trip route.
//
// Pure helpers only. No widgets, no SQLite, no network.

import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/routing/trip_route_auth.dart';

OwnedTripCatalog _loadedWith(Iterable<String> ids) =>
    OwnedTripCatalog()..replaceAll(ids);

String? _redirect(OwnedTripCatalog catalog, String location) =>
    redirectForTripOwnership(
      location: location,
      catalogLoaded: catalog.loaded,
      ownedTripIds: catalog.ids,
    );

void main() {
  test('test_foreign_trip_deep_link_is_refused', () {
    final catalog = _loadedWith(['trip-owned']);
    expect(catalog.loaded, isTrue);

    expect(_redirect(catalog, '/trip/trip-foreign'), '/');
    expect(_redirect(catalog, '/trip/trip-foreign/chat'), '/');
    expect(_redirect(catalog, '/trip/trip-foreign/card/node-1'), '/');
    expect(_redirect(catalog, '/trip/trip-foreign?focus=node-1'), '/');
  });

  test('owned trip paths are allowed', () {
    final catalog = _loadedWith(['trip-owned']);
    expect(_redirect(catalog, '/trip/trip-owned'), isNull);
    expect(_redirect(catalog, '/trip/trip-owned/chat'), isNull);
    expect(_redirect(catalog, '/trip/trip-owned/card/node-1'), isNull);
    expect(_redirect(catalog, '/trip/trip-owned?focus=node-1'), isNull);
  });

  test('non-trip routes and /trip/create are never ownership-redirected', () {
    final catalog = _loadedWith(['trip-owned']);
    for (final loc in ['/trip/create', '/', '/profile', '/onboarding']) {
      expect(_redirect(catalog, loc), isNull, reason: loc);
    }
  });

  test('catalog not loaded does not block a foreign path', () {
    final catalog = OwnedTripCatalog();
    expect(catalog.loaded, isFalse);
    expect(_redirect(catalog, '/trip/trip-foreign'), isNull);
  });

  test('tripIdFromLocation', () {
    expect(tripIdFromLocation('/trip/create'), isNull);
    expect(tripIdFromLocation('/'), isNull);
    expect(tripIdFromLocation('/profile'), isNull);
    expect(tripIdFromLocation('/onboarding'), isNull);
    expect(tripIdFromLocation('/trip/abc'), 'abc');
    expect(tripIdFromLocation('/trip/abc/chat'), 'abc');
    expect(tripIdFromLocation('/trip/abc/card/node-1'), 'abc');
    expect(tripIdFromLocation('/trip/abc?focus=node-1'), 'abc');
  });

  test('add before go lets a just-created trip through', () {
    final catalog = _loadedWith(['trip-owned']);
    expect(_redirect(catalog, '/trip/trip-new'), '/');
    catalog.add('trip-new');
    expect(_redirect(catalog, '/trip/trip-new'), isNull);
  });

  test('clear forgets the prior identity and returns to not loaded', () {
    final catalog = _loadedWith(['trip-owned']);
    catalog.clear();
    expect(catalog.loaded, isFalse);
    expect(catalog.ids, isEmpty);
    catalog.replaceAll(['trip-other']);
    expect(_redirect(catalog, '/trip/trip-owned'), '/');
  });

  test('catalog notifies listeners on change only', () {
    final catalog = OwnedTripCatalog();
    var notified = 0;
    catalog.addListener(() => notified++);
    catalog.replaceAll(['a']);
    catalog.replaceAll(['a']);
    catalog.add('a');
    catalog.add('b');
    catalog.clear();
    expect(notified, 3);
  });
}
