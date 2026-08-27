import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:google_fonts/google_fonts.dart';

/// Widget tests must not wait on font HTTP or plugin channels.
Future<void> testExecutable(FutureOr<void> Function() testMain) async {
  GoogleFonts.config.allowRuntimeFetching = false;
  HttpOverrides.global = _DenyHttpOverrides();
  TestWidgetsFlutterBinding.ensureInitialized();
  await testMain();
}

class _DenyHttpOverrides extends HttpOverrides {
  @override
  HttpClient createHttpClient(SecurityContext? context) => _DenyHttpClient();
}

class _DenyHttpClient extends Fake implements HttpClient {
  @override
  Duration? connectionTimeout = const Duration(milliseconds: 1);

  @override
  Duration idleTimeout = const Duration(milliseconds: 1);

  @override
  bool autoUncompress = true;

  @override
  Future<HttpClientRequest> getUrl(Uri url) =>
      Future<HttpClientRequest>.error(
        SocketException('HTTP disabled in tests: $url'),
      );

  @override
  Future<HttpClientRequest> openUrl(String method, Uri url) =>
      Future<HttpClientRequest>.error(
        SocketException('HTTP disabled in tests: $url'),
      );

  @override
  void close({bool force = false}) {}
}
