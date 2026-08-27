/// Typed API exceptions for clean UI error handling.
sealed class ApiException implements Exception {
  final String message;
  const ApiException(this.message);
  @override
  String toString() => message;
}

class UnauthorizedException extends ApiException {
  const UnauthorizedException([super.m = 'Please sign in again.']);
}

class ForbiddenException extends ApiException {
  const ForbiddenException([super.m = 'You don\'t have access to that.']);
}

class NotFoundException extends ApiException {
  const NotFoundException([super.m = 'Not found.']);
}

class ServerException extends ApiException {
  const ServerException([super.m = 'Something went wrong. Try again.']);
}

class NetworkException extends ApiException {
  const NetworkException([super.m = 'No connection. Check your network.']);
}

class UnsupportedRegionException extends ApiException {
  const UnsupportedRegionException([
    super.m = 'Travel Buddy is not ready for that destination yet.',
  ]);
}

/// Lever 1: raised on HTTP 403 with error == "daily_reroute_limit_reached".
/// The UI should show the upgrade CTA, not a generic error.
class RerouteLimitException extends ApiException {
  const RerouteLimitException([super.m = 'Daily reroute limit reached.']);
}
