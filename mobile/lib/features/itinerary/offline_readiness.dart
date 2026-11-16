import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import 'itinerary_notifier.dart';

/// SPEC-56 slice 1: honest status of what is saved on this phone for one
/// trip. Reads only the local cache; never makes a network call.

const String kOfflineStaleNote =
    'Saved more than a day ago. Open this trip with a connection to '
    'refresh it.';
const String kOfflineFootnote =
    'Only what is listed here is saved on this phone. Maps, search and new '
    'suggestions need a connection.';

/// Age wording copied from Home's "Last saved" label.
String savedAgeLabel(DateTime cachedAtUtc, {DateTime? nowUtc}) {
  final now = (nowUtc ?? DateTime.now()).toUtc();
  final age = now.difference(cachedAtUtc.toUtc());
  if (age.inMinutes < 1) return 'just now';
  if (age.inHours < 1) return '${age.inMinutes}m ago';
  if (age.inDays < 1) return '${age.inHours}h ago';
  return '${age.inDays}d ago';
}

/// Distinct place refs, using the same rule as the place pre-cache.
List<String> placeRefsForNodes(List<TripNode> nodes) =>
    nodes.map((n) => n.venueId ?? n.venueName).toSet().toList();

class TripCacheStatus {
  /// When the trip row was saved (UTC), or null when it is not saved.
  final DateTime? cachedAt;
  final int placesCached;
  final int placesTotal;

  const TripCacheStatus({
    required this.cachedAt,
    required this.placesCached,
    required this.placesTotal,
  });

  bool isStale(DateTime nowUtc) {
    final at = cachedAt;
    if (at == null) return false;
    return nowUtc.toUtc().difference(at.toUtc()) >= const Duration(hours: 24);
  }
}

/// Row text for section 1 of the brief.
String offlineStatusText(
  TripCacheStatus status, {
  required bool showingSaved,
  DateTime? nowUtc,
}) {
  final at = status.cachedAt;
  if (at == null) return 'Not saved on this device yet';
  final age = savedAgeLabel(at, nowUtc: nowUtc);
  if (showingSaved) return 'Offline: showing saved trip (saved $age)';
  return 'Saved on this device ($age)';
}

String _two(int v) => v.toString().padLeft(2, '0');

/// Phone-local date and time, e.g. 2026-10-02 14:05.
String _localStamp(DateTime utc) {
  final d = utc.toLocal();
  return '${d.year}-${_two(d.month)}-${_two(d.day)} '
      '${_two(d.hour)}:${_two(d.minute)}';
}

/// Sheet lines, in order, without the button.
List<String> offlineSheetLines(TripCacheStatus? status, {DateTime? nowUtc}) {
  final now = (nowUtc ?? DateTime.now()).toUtc();
  final lines = <String>[];
  if (status != null) {
    final at = status.cachedAt;
    if (at == null) {
      lines.add('Itinerary: not saved on this device yet');
    } else {
      lines.add('Itinerary: saved ${_localStamp(at)}');
      // The place count is read alongside the trip row, so it is only
      // known when the trip row exists.
      if (status.placesTotal > 0) {
        lines.add(
          'Driver cards: ${status.placesCached} of ${status.placesTotal} '
          'stops saved',
        );
      }
      if (status.isStale(now)) lines.add(kOfflineStaleNote);
    }
  }
  lines.add(kOfflineFootnote);
  return lines;
}

/// Local cache status for one trip. Null while the itinerary is loading.
/// Re-reads when the node list changes; invalidate to re-read on demand.
final tripCacheStatusProvider =
    FutureProvider.autoDispose.family<TripCacheStatus?, String>(
  (ref, tripId) async {
    final loading = ref.watch(
      itineraryControllerProvider(tripId).select((s) => s.loading),
    );
    final nodes = ref.watch(
      itineraryControllerProvider(tripId).select((s) => s.nodes),
    );
    if (loading) return null;
    final refs = placeRefsForNodes(nodes);
    final db = ref.read(offlineDatabaseProvider);
    final scope = ref.read(identityCacheScopeProvider);
    final saved = await db.getTripCacheStatus(
      tripId,
      identityScope: scope,
      placeRefs: refs,
    );
    return TripCacheStatus(
      cachedAt: saved?.cachedAt,
      placesCached: saved?.placesCached ?? 0,
      placesTotal: refs.length,
    );
  },
);

/// Status row at the top of the itinerary. Renders nothing while the
/// status is loading or in error. Contains no scrollable.
class OfflineStatusRow extends ConsumerStatefulWidget {
  final String tripId;
  const OfflineStatusRow({super.key, required this.tripId});

  @override
  ConsumerState<OfflineStatusRow> createState() => _OfflineStatusRowState();
}

class _OfflineStatusRowState extends ConsumerState<OfflineStatusRow>
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
      ref.invalidate(tripCacheStatusProvider(widget.tripId));
    }
  }

  void _openSheet() {
    showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (_) => OfflineStatusSheet(tripId: widget.tripId),
    );
  }

  @override
  Widget build(BuildContext context) {
    final showingSaved = ref.watch(
      itineraryControllerProvider(widget.tripId).select((s) => s.showingSaved),
    );
    final async = ref.watch(tripCacheStatusProvider(widget.tripId));
    if (async.hasError) return const SizedBox.shrink();
    final status = async.valueOrNull;
    if (status == null) return const SizedBox.shrink();

    final now = DateTime.now().toUtc();
    final color = status.isStale(now) ? AppColors.warning : AppColors.muted;
    final text = offlineStatusText(
      status,
      showingSaved: showingSaved,
      nowUtc: now,
    );

    return SizedBox(
      width: double.infinity,
      child: Semantics(
        button: true,
        child: InkWell(
          key: const Key('offline_status_row'),
          onTap: _openSheet,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Padding(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.base,
                vertical: AppSpacing.xs,
              ),
              child: Row(
                children: [
                  ExcludeSemantics(
                    child: Icon(
                      showingSaved
                          ? Icons.cloud_off_outlined
                          : Icons.offline_pin_outlined,
                      size: AppSpacing.iconSm,
                      color: color,
                    ),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  Expanded(
                    child: Text(
                      text,
                      softWrap: true,
                      style: AppTypography.caption.copyWith(color: color),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// Detail sheet opened from the status row.
class OfflineStatusSheet extends ConsumerWidget {
  final String tripId;
  const OfflineStatusSheet({super.key, required this.tripId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(tripCacheStatusProvider(tripId)).valueOrNull;
    final now = DateTime.now().toUtc();
    final lines = offlineSheetLines(status, nowUtc: now);
    final stale = status?.isStale(now) ?? false;

    return SafeArea(
      child: SingleChildScrollView(
        key: const Key('offline_status_sheet'),
        padding: const EdgeInsets.all(AppSpacing.base),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (final line in lines)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                child: Text(
                  line,
                  style: line == kOfflineStaleNote && stale
                      ? AppTypography.body.copyWith(color: AppColors.warning)
                      : line == kOfflineFootnote
                          ? AppTypography.caption
                              .copyWith(color: AppColors.muted)
                          : AppTypography.body,
                ),
              ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                key: const Key('offline_status_check_again'),
                onPressed: () =>
                    ref.invalidate(tripCacheStatusProvider(tripId)),
                child: const Text('Check again'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
