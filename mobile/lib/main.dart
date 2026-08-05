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
      anonKey: Env.supabaseAnonKey,
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
class _TravelBuddyAppState extends State<TravelBuddyApp>
    with WidgetsBindingObserver {
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
      // App returned to foreground — trigger sync (SPEC-02 B.1)
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
