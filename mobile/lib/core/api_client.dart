import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'env.dart';
import 'api_exception.dart';

/// Returns the current Supabase access token, or null in dev.
typedef TokenProvider = Future<String?> Function();

/// Central HTTP client. Handles auth injection and error mapping.
///
/// SPEC-43 Gap 1: the only credential is `Bearer <access_token>` from a
/// server-issued Supabase session (anonymous or signed-in). With no token,
/// Authorization is omitted and the server answers 401. The device UUID is a
/// local diagnostic id only and is never sent as a credential.
class ApiClient {
  final Dio dio;

  ApiClient({
    required TokenProvider tokenProvider,
    @visibleForTesting Dio? dioOverride,
  }) : dio = dioOverride ??
            Dio(BaseOptions(
              baseUrl: '${Env.apiBaseUrl}/api/v1',
              connectTimeout: const Duration(seconds: 10),
              receiveTimeout: const Duration(seconds: 30),
              contentType: 'application/json',
            )) {
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: (options, handler) async {
        final token = await tokenProvider();
        if (token != null && token.isNotEmpty) {
          options.headers['Authorization'] = 'Bearer $token';
        } else {
          options.headers.remove('Authorization');
        }
        handler.next(options);
      },
    ));
  }

  Future<dynamic> get(String path, {Map<String, dynamic>? query}) =>
      _wrap(() => dio.get(path, queryParameters: query));

  Future<dynamic> post(String path, {Object? body}) =>
      _wrap(() => dio.post(path, data: body));

  Future<dynamic> _wrap(Future<Response<dynamic>> Function() call) async {
    try {
      final res = await call();
      return res.data;
    } on DioException catch (e) {
      throw _map(e);
    }
  }

  ApiException _map(DioException e) {
    final code = e.response?.statusCode;
    final data = e.response?.data;
    if (code == 401) return const UnauthorizedException();
    if (code == 403) {
      final detail = (data is Map) ? data['detail'] : null;
      if (detail is Map && detail['error'] == 'daily_reroute_limit_reached') {
        return RerouteLimitException(
          detail['message']?.toString() ?? 'Daily reroute limit reached.',
        );
      }
      return const ForbiddenException();
    }
    if (code == 404) return const NotFoundException();
    if (code == 422 && data is Map) {
      final detail = data['detail'];
      if (detail is Map) {
        final errorCode = detail['error']?.toString();
        final message = detail['message']?.toString();
        if (errorCode == 'unsupported_region') {
          return UnsupportedRegionException(
            message ?? 'Travel Buddy is not ready for that destination yet.',
          );
        }
        // Surface all typed 422 detail.message responses
        if (message != null) {
          return ValidationException(message);
        }
      }
    }
    if (code == 503) {
      final detail = (data is Map) ? data['detail'] : null;
      if (detail is Map && detail['error'] == 'weather_provider_unavailable') {
        return WeatherUnavailableException(
          detail['message']?.toString() ??
              'Weather data temporarily unavailable.',
        );
      }
    }
    if (code != null && code >= 500) return const ServerException();
    if (e.type == DioExceptionType.connectionError ||
        e.type == DioExceptionType.connectionTimeout ||
        e.type == DioExceptionType.receiveTimeout ||
        e.type == DioExceptionType.sendTimeout ||
        e.type == DioExceptionType.unknown) {
      return const NetworkException();
    }
    return const ServerException();
  }
}
