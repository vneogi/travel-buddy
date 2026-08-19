import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/api_client.dart';

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

    ApiClient _buildClient({
      required Future<String?> Function() tokenProvider,
      required Future<String> Function() deviceIdProvider,
    }) {
      final client = ApiClient(
        tokenProvider: tokenProvider,
        deviceIdProvider: deviceIdProvider,
        dioOverride: testDio,
      );
      // Append capture AFTER the auth interceptor that ApiClient just added.
      client.dio.interceptors.add(capture);
      return client;
    }

    test('sends Anonymous <uuid> when tokenProvider returns null', () async {
      const deviceId = 'aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee';

      final client = _buildClient(
        tokenProvider: () async => null,
        deviceIdProvider: () async => deviceId,
      );

      try {
        await client.get('/test');
      } catch (_) {
        // Expected: capture rejects -> ApiClient._map -> ServerException
      }

      expect(capture.lastRequest, isNotNull,
          reason: 'Request must have been intercepted');
      expect(
        capture.lastRequest!.headers['Authorization'],
        equals('Anonymous aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee'),
      );
    });

    test('sends Anonymous when tokenProvider returns empty string', () async {
      const deviceId = 'aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee';

      final client = _buildClient(
        tokenProvider: () async => '',
        deviceIdProvider: () async => deviceId,
      );

      try {
        await client.get('/health');
      } catch (_) {}

      expect(capture.lastRequest, isNotNull);
      expect(
        capture.lastRequest!.headers['Authorization'],
        equals('Anonymous aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee'),
      );
    });

    test('sends Bearer when tokenProvider returns a JWT', () async {
      const deviceId = 'aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee';
      const jwt = 'eyJhbGciOiJIUzI1NiJ9.test.signature';

      final client = _buildClient(
        tokenProvider: () async => jwt,
        deviceIdProvider: () async => deviceId,
      );

      try {
        await client.post('/signals', body: {'signals': []});
      } catch (_) {}

      expect(capture.lastRequest, isNotNull);
      expect(
        capture.lastRequest!.headers['Authorization'],
        equals('Bearer eyJhbGciOiJIUzI1NiJ9.test.signature'),
      );
      expect(
        capture.lastRequest!.headers['Authorization']
            .toString()
            .contains('Anonymous'),
        isFalse,
        reason: 'Anonymous must not appear when Bearer is active',
      );
    });
  });
}
