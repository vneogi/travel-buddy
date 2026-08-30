import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'core/env.dart';
import 'core/providers.dart';
import 'data/models.dart';
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
    // Start the shared debounce window immediately. Some platforms report an
    // initial `resumed` event before the first frame; that is still the cold
    // start and must not create a second session_start.
    _lastResumeSync = DateTime.now();
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
      if (!shouldEmitSessionStartOnResume(
        lastEmitAt: _lastResumeSync,
        now: now,
        debounce: _resumeDebounce,
      )) {
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
    // Fire-and-forget. Retention instrumentation must never affect app launch.
    () async {
      try {
        final db = container.read(offlineDatabaseProvider);
        final signal = container.read(signalServiceProvider);
        final now = DateTime.now().toUtc();

        // Compute minutes_since_last_open from durable storage.
        final lastStr = await db.getAppValue('last_session_at');
        int? minutesSinceLastOpen;
        if (lastStr != null) {
          final last = DateTime.tryParse(lastStr);
          if (last != null) {
            minutesSinceLastOpen = now.difference(last).inMinutes;
          }
        }

        // Persist current timestamp for next open.
        await db.setAppValue('last_session_at', now.toIso8601String());

        // Best effort only: when a trip route is open, include its ID and
        // derive a client-side day from the cached itinerary. The server
        // overwrites trip_day authoritatively from captured_at.
        final tripId = activeTripIdFromUri(
          appRouter.routeInformationProvider.value.uri,
        );
        final tripDay = tripId == null
            ? null
            : await tripDayFromCachedTrip(db, tripId, now);

        await signal.emitSessionStart(
          coldStart: coldStart,
          minutesSinceLastOpen: minutesSinceLastOpen,
          tripDay: tripDay,
          tripId: tripId,
        );
      } catch (error) {
        debugPrint('[SessionStart] Emit failed: $error');
      }
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

/// Returns the trip ID for itinerary, chat, and driver-card routes.
String? activeTripIdFromUri(Uri uri) {
  final segments = uri.pathSegments;
  if (segments.length < 2 || segments.first != 'trip') return null;
  final tripId = segments[1];
  return tripId.isEmpty ? null : tripId;
}

/// Shared lifecycle debounce decision, extracted for deterministic testing.
bool shouldEmitSessionStartOnResume({
  required DateTime? lastEmitAt,
  required DateTime now,
  required Duration debounce,
}) =>
    lastEmitAt == null || now.difference(lastEmitAt) >= debounce;

/// Computes a best-effort trip day from the earliest cached itinerary node.
///
/// Returns null when the cache is absent or malformed. Signal emission must
/// continue in all cases because the server can still derive an authoritative
/// value when [tripId] is present.
Future<int?> tripDayFromCachedTrip(
  OfflineDatabase db,
  String tripId,
  DateTime capturedAt,
) async {
  try {
    final cachedJson = await db.getCachedTrip(tripId);
    if (cachedJson == null) return null;
    final trip = TripState.fromJson(
      (jsonDecode(cachedJson) as Map).cast<String, dynamic>(),
    );
    if (trip.nodes.isEmpty) return null;
    final start = trip.nodes
        .map((node) => node.scheduledStart)
        .reduce((a, b) => a.isBefore(b) ? a : b);
    final startUtc = start.toUtc();
    final capturedUtc = capturedAt.toUtc();
    final startDate = DateTime.utc(startUtc.year, startUtc.month, startUtc.day);
    final capturedDate = DateTime.utc(
      capturedUtc.year,
      capturedUtc.month,
      capturedUtc.day,
    );
    return capturedDate.difference(startDate).inDays;
  } catch (_) {
    return null;
  }
}
