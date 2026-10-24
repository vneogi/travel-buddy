// SPEC-43 Gap 1: the app sends only a server-issued Bearer token, never the
// device UUID. No live Supabase, no network, no pumpAndSettle.

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:travel_buddy/core/anon_session.dart';
import 'package:travel_buddy/core/api_client.dart';
import 'package:travel_buddy/core/providers.dart';

class _Capture extends Interceptor {
  final requests = <RequestOptions>[];
  @override
  void onRequest(RequestOptions options, RequestInterceptorHandler handler) {
    requests.add(options);
    handler.reject(DioException(
      requestOptions: options,
      type: DioExceptionType.cancel,
      message: 'captured',
    ));
  }
}

class _FakeAuth implements AnonAuth {
  bool session;
  final bool fail;
  int signIns = 0;
  _FakeAuth({this.session = false, this.fail = false});

  @override
  bool get hasSession => session;

  @override
  Future<void> signInAnonymously() async {
    signIns++;
    if (fail) throw Exception('anonymous sign-ins are disabled');
    session = true;
  }

  @override
  Future<void> signOut() async {
    session = false;
  }
}

const _deviceUuid = 'aaaaaaaa-bbbb-4ccc-9ddd-eeeeeeeeeeee';

({ApiClient client, _Capture capture}) _build(
  Future<String?> Function() token, {
  Map<String, dynamic>? baseHeaders,
}) {
  final capture = _Capture();
  final dio = Dio(BaseOptions(
    baseUrl: 'http://localhost:9999/api/v1',
    headers: baseHeaders,
  ));
  final client = ApiClient(tokenProvider: token, dioOverride: dio);
  client.dio.interceptors.add(capture);
  return (client: client, capture: capture);
}

Future<void> _hit(ApiClient c) async {
  for (final call in [
    () => c.get('/user/status'),
    () => c.get('/trip/t1', query: {'a': 1}),
    () => c.post('/trip/event', body: {'x': 1}),
  ]) {
    try {
      await call();
    } catch (_) {}
  }
}

void _expectNoAnonymous(List<RequestOptions> reqs) {
  for (final r in reqs) {
    final v = r.headers['Authorization']?.toString() ?? '';
    expect(v.toLowerCase().contains('anonymous'), isFalse);
    expect(v.contains(_deviceUuid), isFalse);
  }
}

void main() {
  group('ApiClient credential', () {
    test('with a token every request sends Bearer, never Anonymous', () async {
      final b = _build(() async => 'header.payload.sig');
      await _hit(b.client);
      expect(b.capture.requests, hasLength(3));
      for (final r in b.capture.requests) {
        expect(r.headers['Authorization'], 'Bearer header.payload.sig');
      }
      _expectNoAnonymous(b.capture.requests);
    });

    test('null token omits Authorization and never sends Anonymous', () async {
      final b = _build(() async => null);
      await _hit(b.client);
      for (final r in b.capture.requests) {
        expect(r.headers.containsKey('Authorization'), isFalse);
      }
      _expectNoAnonymous(b.capture.requests);
    });

    test('empty token omits Authorization even if a stale header was set', () async {
      final b = _build(
        () async => '',
        baseHeaders: {'Authorization': 'Anonymous $_deviceUuid'},
      );
      await _hit(b.client);
      for (final r in b.capture.requests) {
        expect(r.headers.containsKey('Authorization'), isFalse);
      }
      _expectNoAnonymous(b.capture.requests);
    });

    test('token switches mid-session: later requests use the new Bearer', () async {
      String? token;
      final b = _build(() async => token);
      try {
        await b.client.get('/user/status');
      } catch (_) {}
      token = 'refreshed.jwt.sig';
      try {
        await b.client.get('/user/status');
      } catch (_) {}
      expect(b.capture.requests.first.headers.containsKey('Authorization'), isFalse);
      expect(b.capture.requests.last.headers['Authorization'], 'Bearer refreshed.jwt.sig');
    });
  });

  group('providers without Supabase configured (widget-test path)', () {
    test('tokenProvider yields null and apiClient sends no Authorization', () async {
      final container = ProviderContainer();
      addTearDown(container.dispose);
      expect(await container.read(tokenProvider)(), isNull);
      final api = container.read(apiClientProvider);
      final capture = _Capture();
      api.dio.interceptors.add(capture);
      try {
        await api.get('/user/status');
      } catch (_) {}
      expect(capture.requests.single.headers.containsKey('Authorization'), isFalse);
    });
  });

  group('ensureAnonymousSession', () {
    test('no session -> exactly one anonymous sign-in', () async {
      final auth = _FakeAuth();
      expect(await ensureAnonymousSession(auth), isTrue);
      expect(auth.signIns, 1);
    });

    test('existing session is reused; no second account minted', () async {
      final auth = _FakeAuth(session: true);
      expect(await ensureAnonymousSession(auth), isTrue);
      expect(await ensureAnonymousSession(auth), isTrue);
      expect(auth.signIns, 0);
    });

    test('relaunch after first sign-in does not sign in again', () async {
      final auth = _FakeAuth();
      await ensureAnonymousSession(auth);
      await ensureAnonymousSession(auth);
      expect(auth.signIns, 1);
    });

    test('sign-in failure returns false and does not throw', () async {
      final auth = _FakeAuth(fail: true);
      expect(await ensureAnonymousSession(auth), isFalse);
      expect(auth.signIns, 1);
    });
  });
}
