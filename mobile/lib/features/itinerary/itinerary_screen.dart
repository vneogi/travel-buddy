import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/activity_card.dart';
import '../booking/add_booking_sheet.dart';
import '../chat/ask_entry_bar.dart';
import '../rescue/hotel_rescue_sheet.dart';
import '../../widgets/reroute_badge.dart';
import '../../widgets/shimmer_card.dart';
import '../../widgets/error_view.dart';
import 'current_window.dart';
import 'itinerary_notifier.dart';
import 'replacement_ref.dart';
import '../alerts/alerts_notifier.dart';
import '../../widgets/alert_card.dart';

/// The hero screen — live timeline of activity cards.
///
/// Reflow strategy: a keyed ListView driven directly by controller state.
/// Each row is keyed by a content-signature, so when the backend returns an
/// updated itinerary (swap / cancel / reroute / time-shift) Flutter rebuilds
/// exactly the changed rows. This is intentionally NOT a hand-rolled
/// AnimatedList diff — that approach had an index-desync crash on the in-place
/// swap/cancel path. Data is always correct here; slide choreography can be
/// layered on later (per-card AnimatedSwitcher / flutter_animate) once it can
/// be verified on a real device.
class ItineraryScreen extends ConsumerWidget {
  final String tripId;
  const ItineraryScreen({super.key, required this.tripId});

  String _sig(TripNode n) =>
      '${n.nodeId}|${n.venueId}|${n.venueName}|${n.scheduledStart.toIso8601String()}|${n.status.name}|${n.isLocked}';

  Future<void> _swap(WidgetRef ref, TripNode node) async {
    final placeRef = node.venueId ?? node.venueName;
    final result = await ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(
          type: EventType.swapActivity,
          message: 'Swap ${node.venueName} for something similar nearby',
          targetNodeId: node.nodeId,
          preferences: {'vibe_tags': node.vibeTags},
        );
    // SPEC-07: emit reroute_accepted with the replacement ref
    if (result != null && result.updatedNodes.isNotEmpty) {
      final replacementRef = replacementRefForSwap(
        originalNodeId: node.nodeId,
        originalVenueKey: placeRef,
        updatedNodes: result.updatedNodes,
      );
      ref.read(signalServiceProvider).emitRerouteAccepted(
            placeRef: placeRef,
            replacementRef: replacementRef,
            tripId: tripId,
          );
    }
  }

  void _cancel(WidgetRef ref, TripNode node) {
    ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(
          type: EventType.cancelActivity,
          message: 'Cancel ${node.venueName}',
          targetNodeId: node.nodeId,
        );
  }

  Future<void> _showOutcomePicker(
    BuildContext context,
    WidgetRef ref,
    TripNode node,
  ) async {
    final decision = await showModalBottomSheet<_OutcomeDecision>(
      context: context,
      builder: (_) => const _OutcomeSheet(),
    );
    if (decision == null || !context.mounted) return;

    final controller =
        ref.read(itineraryControllerProvider(tripId).notifier);
    if (decision == _OutcomeDecision.visited) {
      await controller.recordVisited(node);
      return;
    }

    final reason = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => const _SkipReasonSheet(),
    );
    if (reason != null) {
      await controller.recordSkipped(node, reason);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Reroute-limit → push upgrade once, then clear the flag.
    ref.listen<ItineraryState>(itineraryControllerProvider(tripId), (prev, next) {
      if (next.rerouteLimitHit) {
        ref.read(itineraryControllerProvider(tripId).notifier).clearRerouteLimit();
        context.push('/upgrade');
      }
    });

    // SPEC-29: Refresh alerts on screen open (provider auto-fetches on build).
    // Manual refresh + app-resume handled via _AlertsSection.

    final state = ref.watch(itineraryControllerProvider(tripId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Your Day', style: AppTypography.h2),
        actions: [
          IconButton(
            icon: const Icon(Icons.shield_outlined),
            tooltip: 'Hotel Rescue',
            onPressed: () => openHotelRescue(
              context,
              tripId: tripId,
              nodes: state.nodes,
            ),
          ),
          IconButton(
            icon: const Icon(Icons.bookmark_add_outlined),
            tooltip: 'Add Booking',
            onPressed: () {
              showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                builder: (_) => AddBookingSheet(tripId: tripId),
              );
            },
          ),
          RerouteBadge(onUpgradeTap: () => context.push('/upgrade')),
          const SizedBox(width: AppSpacing.base),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/trip/$tripId/chat'),
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.chat_bubble_outline, color: Colors.white),
      ),
      bottomNavigationBar: AskEntryBar(
        enabled: !state.processing,
        onSubmit: (question) => context.push(
          '/trip/$tripId/chat?q=${Uri.encodeQueryComponent(question)}',
        ),
      ),
      body: state.loading
          ? const ShimmerList(count: 5)
          : state.error != null
              ? ErrorView(
                  error: state.error!,
                  onRetry: () =>
                      ref.read(itineraryControllerProvider(tripId).notifier).load(),
                )
              : Column(
                  children: [
                    // Slim progress bar while an event is in flight (heavy calls).
                    if (state.processing)
                      const LinearProgressIndicator(minHeight: 2),
                    // "Heads up: ..." scheduler note from the last event.
                    if (state.banner != null)
                      _HeadsUpBanner(
                        text: state.banner!,
                        onClose: () => ref
                            .read(itineraryControllerProvider(tripId).notifier)
                            .clearBanner(),
                      ),
                    // SPEC-29: Context alerts above timeline.
                    // Non-blocking: itinerary shows immediately; alerts
                    // render when available (no spinner replacement).
                    _AlertsSection(tripId: tripId),
                    Expanded(
                      child: state.nodes.isEmpty
                          ? Center(
                              child: Text(
                                'No activities yet.',
                                style: AppTypography.body
                                    .copyWith(color: AppColors.muted),
                              ),
                            )
                          : ListView.builder(
                              itemCount: state.nodes.length,
                              padding: const EdgeInsets.only(
                                top: AppSpacing.base,
                                bottom: 100, // space for FAB
                              ),
                              itemBuilder: (context, i) {
                                final node = state.nodes[i];
                                final next = i < state.nodes.length - 1
                                    ? state.nodes[i + 1]
                                    : null;
                                // Signature key → row rebuilds when its content
                                // changes (swap/time-shift/status), stays stable
                                // otherwise. Smooth 200ms cross-fade on change.
                                return AnimatedSwitcher(
                                  duration: const Duration(milliseconds: 220),
                                  transitionBuilder: (child, anim) =>
                                      FadeTransition(opacity: anim, child: child),
                                  child: ActivityCard(
                                    // Key includes loved flag — without it the
                                    // AnimatedSwitcher won't rebuild when only
                                    // isLoved changes, and the heart stays unfilled.
                                    key: ValueKey(
                                      '${_sig(node)}|'
                                      '${state.lovedPlaceRefs.contains(node.venueId ?? node.venueName)}|'
                                      '${state.nodeOutcomes[node.nodeId]?.outcome}|'
                                      '${state.nodeOutcomes[node.nodeId]?.reason}|'
                                      '${state.outcomeRecordingNodeIds.contains(node.nodeId)}',
                                    ),
                                    node: node,
                                    nextNode: next,
                                    isLoved: state.lovedPlaceRefs
                                        .contains(node.venueId ?? node.venueName),
                                    recordedOutcome:
                                        state.nodeOutcomes[node.nodeId],
                                    isRecordingOutcome: state
                                        .outcomeRecordingNodeIds
                                        .contains(node.nodeId),
                                    onTapSwap: state.processing
                                        ? null
                                        : () => _swap(ref, node),
                                    onTapCancel: state.processing
                                        ? null
                                        : () => _cancel(ref, node),
                                    onTapRecordOutcome: state.processing
                                        ? null
                                        : () => _showOutcomePicker(
                                              context,
                                              ref,
                                              node,
                                            ),
                                    onTapLoved: () {
                                      final placeRef = node.venueId ?? node.venueName;
                                      ref.read(signalServiceProvider).emitUserLoved(
                                            placeRef: placeRef,
                                            tripId: tripId,
                                          );
                                      ref
                                          .read(itineraryControllerProvider(tripId).notifier)
                                          .markLoved(placeRef);
                                    },
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
    );
  }
}

class _HeadsUpBanner extends StatelessWidget {
  final String text;
  final VoidCallback onClose;
  const _HeadsUpBanner({required this.text, required this.onClose});

  @override
  Widget build(BuildContext context) => Container(
        width: double.infinity,
        color: AppColors.accent.withValues(alpha: 0.12),
        padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.base, vertical: AppSpacing.sm),
        child: Row(
          children: [
            const Icon(Icons.info_outline, size: 18, color: AppColors.accent),
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: Text(text, style: AppTypography.caption)),
            IconButton(
              icon: const Icon(Icons.close, size: 16),
              onPressed: onClose,
              visualDensity: VisualDensity.compact,
            ),
          ],
        ),
      );
}

/// SPEC-07: Bottom sheet presenting the closed set of skip reasons.
/// Returns the selected reason string or null if dismissed.
class _SkipReasonSheet extends StatelessWidget {
  const _SkipReasonSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.base),
            child: Text('Why are you skipping?', style: AppTypography.h2),
          ),
          ...skipReasonLabels.entries.map((e) => ListTile(
                leading: const Icon(Icons.arrow_forward_ios, size: 14),
                title: Text(e.value),
                onTap: () => Navigator.pop(context, e.key),
              )),
          const SizedBox(height: AppSpacing.base),
        ],
      ),
    );
  }
}

enum _OutcomeDecision { visited, skipped }

class _OutcomeSheet extends StatelessWidget {
  const _OutcomeSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.base),
            child: Text('Did this happen?', style: AppTypography.h2),
          ),
          ListTile(
            leading: const Icon(Icons.check_circle_outline),
            title: const Text('Yes, I went'),
            onTap: () => Navigator.pop(context, _OutcomeDecision.visited),
          ),
          ListTile(
            leading: const Icon(Icons.skip_next),
            title: const Text('No, I skipped it'),
            onTap: () => Navigator.pop(context, _OutcomeDecision.skipped),
          ),
          ListTile(
            leading: const Icon(Icons.schedule),
            title: const Text('Not sure yet'),
            onTap: () => Navigator.pop(context),
          ),
          const SizedBox(height: AppSpacing.base),
        ],
      ),
    );
  }
}


/// SPEC-29: Non-blocking alert section above the timeline.
///
/// Renders alert cards when data is available. Does NOT show a spinner
/// or replace the itinerary while loading.
class _AlertsSection extends ConsumerStatefulWidget {
  final String tripId;
  const _AlertsSection({required this.tripId});

  @override
  ConsumerState<_AlertsSection> createState() => _AlertsSectionState();
}

class _AlertsSectionState extends ConsumerState<_AlertsSection>
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
      ref.read(alertsNotifierProvider(widget.tripId).notifier).refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    final alertsAsync = ref.watch(alertsNotifierProvider(widget.tripId));

    return alertsAsync.when(
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
      data: (alertsState) {
        final visible = alertsState.visible;
        if (visible.isEmpty) return const SizedBox.shrink();
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Manual refresh action
            Align(
              alignment: Alignment.centerRight,
              child: IconButton(
                icon: alertsState.loading
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.refresh, size: 18),
                tooltip: 'Refresh alerts',
                onPressed: alertsState.loading
                    ? null
                    : () => ref
                        .read(alertsNotifierProvider(widget.tripId).notifier)
                        .refresh(),
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
            ),
            for (final alert in visible)
              AlertCard(
                alert: alert,
                onDismiss: () => ref
                    .read(alertsNotifierProvider(widget.tripId).notifier)
                    .dismiss(alert.alertId),
              ),
          ],
        );
      },
    );
  }
}
