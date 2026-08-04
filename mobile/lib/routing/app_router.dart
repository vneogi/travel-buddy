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

/// True only when Supabase was actually initialized (real creds configured).
bool get _supabaseReady =>
    Env.supabaseUrl.isNotEmpty && Env.supabaseAnonKey.isNotEmpty;

final appRouter = GoRouter(
  initialLocation: '/',
  redirect: (context, state) {
    // Dev mode: Supabase not initialized → no auth gate. Let the app render so
    // it can run against the backend using the X-Debug-User-Id header.
    if (!_supabaseReady) return null;

    final session = Supabase.instance.client.auth.currentSession;
    final isAuth = session != null;
    final isOnboarding = state.matchedLocation == '/onboarding';

    if (!isAuth && !isOnboarding) return '/onboarding';
    if (isAuth && isOnboarding) return '/';
    return null;
  },
  routes: [
    GoRoute(
      path: '/onboarding',
      builder: (_, __) => const OnboardingScreen(),
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
