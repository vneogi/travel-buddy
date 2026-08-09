import 'package:connectivity_plus/connectivity_plus.dart';

/// Single source of truth for network connectivity state (R5).
///
/// Rules:
/// - ConnectivityResult.none → offline (no network interface)
/// - ConnectivityResult.vpn, ethernet, wifi, mobile, other → online
/// - A device reporting "online" may still be unable to reach our server
///   (DNS failure, VPN tunnel to wrong network, etc). That's NOT "offline" —
///   it's "unreachable server" and requires a different user message.
class ConnectivityHelper {
  final Connectivity _connectivity;

  ConnectivityHelper({Connectivity? connectivity})
      : _connectivity = connectivity ?? Connectivity();

  /// Check current connectivity synchronously from a list of results.
  /// Returns true if any result is NOT none.
  static bool isOnline(List<ConnectivityResult> results) {
    return results.isNotEmpty &&
        results.any((r) => r != ConnectivityResult.none);
  }

  /// Get current connectivity status.
  Future<bool> checkConnectivity() async {
    final results = await _connectivity.checkConnectivity();
    return isOnline(results);
  }

  /// Stream connectivity changes. Emits true/false for online/offline.
  Stream<bool> get onConnectivityChanged {
    return _connectivity.onConnectivityChanged.map(isOnline);
  }
}
