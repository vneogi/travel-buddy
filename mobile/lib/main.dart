import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'core/env.dart';
import 'core/providers.dart';
import 'offline/db_init.dart';
import 'offline/offline_database.dart';
import 'routing/app_router.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  initDatabaseFactory();

  // Initialize Supabase (for auth). Skipped gracefully if no URL configured.
  if (Env.supabaseUrl.isNotEmpty && Env.supabaseAnonKey.isNotEmpty) {
    await Supabase.initialize(
      url: Env.supabaseUrl,
      publishableKey: Env.supabaseAnonKey,
    );
  }

  // Create container so we can resolve identity and start sync before runApp.
  final container = ProviderContainer();

  // SPEC-09: Resolve device identity before anything touches the network.
  // getOrCreate() reads from secure storage or generates a UUID v4.
  final deviceId = await container.read(deviceIdentityProvider).getOrCreate();
  container.read(deviceIdProvider.notifier).state = deviceId;

  // SPEC-02: Start sync engine -- crash recovery + periodic timer + connectivity.
  // Without this call, nothing syncs and inflight rows stay stuck forever.
  await container.read(syncEngineProvider).start();

  runApp(UncontrolledProviderScope(
    container: container,
    child: const TravelBuddyApp(),
  ));
}

class TravelBuddyApp extends StatefulWidget {
  const TravelBuddyApp({super.key});

  @override
  State<TravelBuddyApp> createState() => _TravelBuddyAppState();
}

/// SPEC-02 B.1: sync on app resume (foreground).
/// WidgetsBindingObserver detects lifecycle transitions.
///
/// Debounce: Pixel 9 Pro Fold fires didChangeAppLifecycleState ~3-5 times
/// on fold/unfold (surface recreation). Skip if last sync was <30s ago.
class _TravelBuddyAppState extends State<TravelBuddyApp>
    with WidgetsBindingObserver {
  DateTime? _lastResumeSync;
  static const _resumeDebounce = Duration(seconds: 30);
  bool _coldStartEmitted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // SPEC-30: emit cold-start session_start on first foreground.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_coldStartEmitted) {
        _coldStartEmitted = true;
        _emitSessionStart(
          ProviderScope.containerOf(context),
          coldStart: true,
        );
      }
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      final now = DateTime.now();
      if (_lastResumeSync != null &&
          now.difference(_lastResumeSync!) < _resumeDebounce) {
        return;
      }
      _lastResumeSync = now;
      final container = ProviderScope.containerOf(context);
      container.read(syncEngineProvider).triggerSync();
      _emitSessionStart(container, coldStart: false);
    }
  }

  /// SPEC-30: emit session_start on foreground (cold or resume).
  /// Rides the existing outbox; never blocks the UI thread.
  void _emitSessionStart(
    ProviderContainer container, {
    required bool coldStart,
  }) {
    // Fire-and-forget -- SignalService.emit never throws.
    () async {
      final db = container.read(offlineDatabaseProvider);
      final signal = container.read(signalServiceProvider);

      // Compute minutes_since_last_open from durable storage.
      final lastStr = await db.getAppValue('last_session_at');
      int? minutesSinceLastOpen;
      if (lastStr != null) {
        final last = DateTime.tryParse(lastStr);
        if (last != null) {
          minutesSinceLastOpen =
              DateTime.now().toUtc().difference(last).inMinutes;
        }
      }

      // Persist current timestamp for next open.
      await db.setAppValue(
        'last_session_at',
        DateTime.now().toUtc().toIso8601String(),
      );

      await signal.emitSessionStart(
        coldStart: coldStart,
        minutesSinceLastOpen: minutesSinceLastOpen,
      );
    }();
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Travel Buddy',
      theme: AppTheme.light,
      routerConfig: appRouter,
    );
  }
}
