import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/api_exception.dart';

// ---------------------------------------------------------------------------
// Interceptor that captures the final request headers then rejects (no HTTP).
// Added AFTER ApiClient's own auth interceptor via dioOverride so the
// Authorization header is already set when we inspect it.
// ---------------------------------------------------------------------------
class _CaptureInterceptor extends Interceptor {
  RequestOptions? lastRequest;

  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    lastRequest = options;
    handler.reject(DioException(
      requestOptions: options,
      type: DioExceptionType.cancel,
      message: 'captured',
    ));
  }
}

void main() {
  group('ApiClient auth headers (R17: real production path)', () {
    late _CaptureInterceptor capture;
    late Dio testDio;

    setUp(() {
      capture = _CaptureInterceptor();
      testDio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
    });

    ApiClient buildClient(Future<String?> Function() tokenProvider) {
      final client = ApiClient(tokenProvider: tokenProvider, dioOverride: testDio);
      // Append capture AFTER the auth interceptor that ApiClient just added.
      client.dio.interceptors.add(capture);
      return client;
    }

    test('omits Authorization (never Anonymous) when token is null', () async {
      final client = buildClient(() async => null);
      try {
        await client.get('/test');
      } catch (_) {}
      expect(capture.lastRequest, isNotNull);
      expect(capture.lastRequest!.headers.containsKey('Authorization'), isFalse);
    });

    test('omits Authorization (never Anonymous) when token is empty', () async {
      final client = buildClient(() async => '');
      try {
        await client.get('/health');
      } catch (_) {}
      expect(capture.lastRequest, isNotNull);
      expect(capture.lastRequest!.headers.containsKey('Authorization'), isFalse);
    });

    test('sends Bearer when tokenProvider returns a JWT', () async {
      const jwt = 'eyJhbGciOiJSUzI1NiJ9.test.signature';
      final client = buildClient(() async => jwt);
      try {
        await client.post('/signals', body: {'signals': []});
      } catch (_) {}
      expect(capture.lastRequest, isNotNull);
      expect(
        capture.lastRequest!.headers['Authorization'],
        equals('Bearer eyJhbGciOiJSUzI1NiJ9.test.signature'),
      );
    });
  });

  test('maps Chrome failed-to-fetch unknown errors to NetworkException', () async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
    final client = ApiClient(
      tokenProvider: () async => null,
      dioOverride: dio,
    );
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) => handler.reject(
          DioException(
            requestOptions: options,
            type: DioExceptionType.unknown,
            message: 'Failed to fetch',
          ),
        ),
      ),
    );

    await expectLater(
      client.get('/health'),
      throwsA(isA<NetworkException>()),
    );
  });

  test('maps unsupported region response to actionable exception', () async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
    final client = ApiClient(
      tokenProvider: () async => null,
      dioOverride: dio,
    );
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) => handler.reject(
          DioException(
            requestOptions: options,
            response: Response(
              requestOptions: options,
              statusCode: 422,
              data: {
                'detail': {
                  'error': 'unsupported_region',
                  'message': 'Travel Buddy is not ready for Paris yet.',
                },
              },
            ),
            type: DioExceptionType.badResponse,
          ),
        ),
      ),
    );

    await expectLater(
      client.post('/trip/create', body: const {}),
      throwsA(
        isA<UnsupportedRegionException>().having(
          (error) => error.message,
          'message',
          contains('Paris'),
        ),
      ),
    );
  });

  test('maps weather 503 to WeatherUnavailableException', () async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
    final client = ApiClient(
      tokenProvider: () async => null,
      dioOverride: dio,
    );
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) => handler.reject(
          DioException(
            requestOptions: options,
            response: Response(
              requestOptions: options,
              statusCode: 503,
              data: {
                'detail': {
                  'error': 'weather_provider_unavailable',
                  'message': 'Weather data temporarily unavailable.',
                },
              },
            ),
            type: DioExceptionType.badResponse,
          ),
        ),
      ),
    );

    await expectLater(
      client.get('/trip/t1/alerts'),
      throwsA(isA<WeatherUnavailableException>()),
    );
  });

  test('maps typed 422 over_capacity to ValidationException', () async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
    final client = ApiClient(
      tokenProvider: () async => null,
      dioOverride: dio,
    );
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) => handler.reject(
          DioException(
            requestOptions: options,
            response: Response(
              requestOptions: options,
              statusCode: 422,
              data: {
                'detail': {
                  'error': 'over_capacity',
                  'message': 'Maximum 5 days for luang_prabang_laos, requested 8.',
                },
              },
            ),
            type: DioExceptionType.badResponse,
          ),
        ),
      ),
    );

    await expectLater(
      client.post('/trip/create', body: const {}),
      throwsA(
        isA<ValidationException>().having(
          (e) => e.message,
          'message',
          'Maximum 5 days for luang_prabang_laos, requested 8.',
        ),
      ),
    );
  });

  test('maps typed 422 invalid_interests to ValidationException', () async {
    final dio = Dio(BaseOptions(baseUrl: 'http://localhost:9999/api/v1'));
    final client = ApiClient(
      tokenProvider: () async => null,
      dioOverride: dio,
    );
    dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) => handler.reject(
          DioException(
            requestOptions: options,
            response: Response(
              requestOptions: options,
              statusCode: 422,
              data: {
                'detail': {
                  'error': 'invalid_interests',
                  'message':
                      'interest_ids must be a list of strings, got null',
                },
              },
            ),
            type: DioExceptionType.badResponse,
          ),
        ),
      ),
    );

    await expectLater(
      client.post('/trip/create', body: const {}),
      throwsA(
        isA<ValidationException>().having(
          (e) => e.message,
          'message',
          contains('interest_ids'),
        ),
      ),
    );
  });
}
