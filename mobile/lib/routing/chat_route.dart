/// SPEC-43 Gap 12: chat route without question text in the URI.
///
/// The Ask question travels in GoRouter `extra` only. Query strings are
/// logged, shared, and restored; `extra` is not part of the location.
library;

/// Typed `extra` for `/trip/:tripId/chat`. Used only by this route.
class ChatRouteExtra {
  const ChatRouteExtra({this.initialQuestion});

  final String? initialQuestion;
}

/// Production location for trip chat. Never carries a query string.
String chatRoutePath(String tripId) => '/trip/$tripId/chat';

/// Initial question from a route `extra`. Missing or wrong type -> null.
/// Never reads `state.uri.queryParameters['q']` (fail closed).
String? chatInitialQuestionFromExtra(Object? extra) =>
    extra is ChatRouteExtra ? extra.initialQuestion : null;
