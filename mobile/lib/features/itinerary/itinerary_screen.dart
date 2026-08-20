import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/activity_card.dart';
import '../booking/add_booking_sheet.dart';
import '../../widgets/reroute_badge.dart';
import '../../widgets/shimmer_card.dart';
import '../../widgets/error_view.dart';
import 'itinerary_notifier.dart';
import 'replacement_ref.dart';
import '../../core/providers.dart';

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

  /// SPEC-07: show skip-reason picker, emit node_skipped signal, then cancel.
  void _showSkipReasonPicker(BuildContext context, WidgetRef ref, TripNode node) {
    final placeRef = node.venueId ?? node.venueName;
    showModalBottomSheet<String>(
      context: context,
      builder: (_) => const _SkipReasonSheet(),
    ).then((reason) {
      if (reason != null) {
        ref.read(signalServiceProvider).emitNodeSkipped(
              placeRef: placeRef,
              reason: reason,
              tripId: tripId,
            );
        ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(
              type: EventType.cancelActivity,
              message: 'Skip ${node.venueName} ($reason)',
              targetNodeId: node.nodeId,
            );
      }
    });
  }

  /// SPEC-07: confirm user visited the active node.
  void _confirmVisited(WidgetRef ref, TripNode node) {
    ref.read(signalServiceProvider).emitVisitedConfirmed(
          placeRef: node.venueId ?? node.venueName,
          tripId: tripId,
        );
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

    final state = ref.watch(itineraryControllerProvider(tripId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Your Day', style: AppTypography.h2),
        actions: [
          RerouteBadge(onUpgradeTap: () => context.push('/upgrade')),
          const SizedBox(width: AppSpacing.base),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/trip/$tripId/chat'),
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.chat_bubble_outline, color: Colors.white),
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          showModalBottomSheet(
            context: context,
            isScrollControlled: true,
            builder: (_) => AddBookingSheet(tripId: tripId),
          );
        },
        icon: const Icon(Icons.anchor),
        label: const Text('Add Booking'),
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
                                    key: ValueKey('${_sig(node)}|${state.lovedPlaceRefs.contains(node.venueId ?? node.venueName)}'),
                                    node: node,
                                    nextNode: next,
                                    isLoved: state.lovedPlaceRefs
                                        .contains(node.venueId ?? node.venueName),
                                    onTapSwap: () => _swap(ref, node),
                                    onTapCancel: () => _cancel(ref, node),
                                    onTapVisited: () => _confirmVisited(ref, node),
                                    onTapSkip: () => _showSkipReasonPicker(context, ref, node),
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

  static const _reasons = {
    'too_far': 'Too far away',
    'too_tired': 'Too tired',
    'closed': 'Place is closed',
    'crowded': 'Too crowded',
    'not_interested': 'Not interested',
    'ran_out_of_time': 'Ran out of time',
    'weather': 'Bad weather',
  };

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
          ..._reasons.entries.map((e) => ListTile(
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
