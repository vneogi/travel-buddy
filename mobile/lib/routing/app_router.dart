import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import '../core/env.dart';
import '../features/onboarding/onboarding_screen.dart';
import '../features/home/home_screen.dart';
import '../features/itinerary/itinerary_screen.dart';
import '../features/chat/chat_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/upgrade/upgrade_screen.dart';
import '../features/debug/sync_status_screen.dart';
import '../features/driver_card/driver_card_screen.dart';
import 'redirect_for_auth.dart';

/// True only when Supabase was actually initialized (real creds configured).
bool get _supabaseReady =>
    Env.supabaseUrl.isNotEmpty && Env.supabaseAnonKey.isNotEmpty;

final appRouter = GoRouter(
  initialLocation: '/',
  redirect: (context, state) {
    final session = _supabaseReady
        ? Supabase.instance.client.auth.currentSession
        : null;
    return redirectForAuth(
      supabaseReady: _supabaseReady,
      hasSession: session != null,
      location: state.matchedLocation,
    );
  },
  routes: [
    GoRoute(
      path: '/onboarding',
      builder: (_, __) => const OnboardingScreen(),
    ),
    GoRoute(
      path: '/trip/:tripId/card/:nodeId',
      builder: (_, state) => DriverCardScreen(
        tripId: state.pathParameters['tripId']!,
        nodeId: state.pathParameters['nodeId']!,
      ),
    ),
    ShellRoute(
      builder: (_, state, child) => _AppShell(child: child),
      routes: [
        GoRoute(
          path: '/',
          builder: (_, __) => const HomeScreen(),
        ),
        GoRoute(
          path: '/trip/:tripId',
          builder: (_, state) => ItineraryScreen(
            tripId: state.pathParameters['tripId']!,
          ),
        ),
        GoRoute(
          path: '/trip/:tripId/chat',
          builder: (_, state) => ChatScreen(
            tripId: state.pathParameters['tripId']!,
          ),
        ),
        GoRoute(
          path: '/profile',
          builder: (_, __) => const ProfileScreen(),
        ),
        GoRoute(
          path: '/upgrade',
          builder: (_, __) => const UpgradeScreen(),
        ),
        GoRoute(
          path: '/profile/sync',
          builder: (_, __) => const SyncStatusScreen(),
        ),
      ],
    ),
  ],
);

/// Bottom navigation shell.
class _AppShell extends StatelessWidget {
  final Widget child;
  const _AppShell({required this.child});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: child,
      bottomNavigationBar: NavigationBar(
        selectedIndex: _currentIndex(context),
        onDestinationSelected: (i) => _navigate(context, i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.explore), label: 'Trips'),
          NavigationDestination(icon: Icon(Icons.person_outline), label: 'Profile'),
        ],
      ),
    );
  }

  int _currentIndex(BuildContext context) {
    final loc = GoRouterState.of(context).matchedLocation;
    if (loc.startsWith('/profile')) return 1;
    return 0;
  }

  void _navigate(BuildContext context, int index) {
    switch (index) {
      case 0: context.go('/');
      case 1: context.go('/profile');
    }
  }
}
