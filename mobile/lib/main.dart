import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'core/env.dart';
import 'core/providers.dart';
import 'routing/app_router.dart';
import 'theme/app_theme.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();

  // Initialize Supabase (for auth). Skipped gracefully if no URL configured.
  if (Env.supabaseUrl.isNotEmpty && Env.supabaseAnonKey.isNotEmpty) {
    await Supabase.initialize(
      url: Env.supabaseUrl,
      publishableKey: Env.supabaseAnonKey,
    );
  }

  // Create container so we can start the sync engine before runApp.
  final container = ProviderContainer();

  // SPEC-02: Start sync engine — crash recovery + periodic timer + connectivity.
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

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
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
        debugPrint('[App] Resumed — debounced (last sync ${now.difference(_lastResumeSync!).inSeconds}s ago)');
        return;
      }
      _lastResumeSync = now;
      debugPrint('[App] Resumed — triggering sync');
      ProviderScope.containerOf(context).read(syncEngineProvider).triggerSync();
    }
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'Travel Buddy',
      debugShowCheckedModeBanner: false,
      theme: AppTheme.light,
      darkTheme: AppTheme.dark,
      themeMode: ThemeMode.system,
      routerConfig: appRouter,
    );
  }
}
