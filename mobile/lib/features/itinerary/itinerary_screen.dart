import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/activity_card.dart';
import '../../widgets/reroute_badge.dart';
import '../../widgets/shimmer_card.dart';
import '../../widgets/error_view.dart';
import 'itinerary_notifier.dart';
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

  void _swap(WidgetRef ref, TripNode node) {
    // TODO(swap-sheet): open SwapSheet and pass the user's chosen vibe_tags.
    // Until then, re-search with the node's own vibes as a sensible default.
    ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(
          type: EventType.swapActivity,
          message: 'Swap ${node.venueName} for something similar nearby',
          targetNodeId: node.nodeId,
          preferences: {'vibe_tags': node.vibeTags},
        );
  }

  void _cancel(WidgetRef ref, TripNode node) {
    ref.read(itineraryControllerProvider(tripId).notifier).applyEvent(
          type: EventType.cancelActivity,
          message: 'Cancel ${node.venueName}',
          targetNodeId: node.nodeId,
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
                                    onTapLoved: () {
                                      final placeRef = node.venueId ?? node.venueName;
                                      ref.read(signalServiceProvider).emit(
                                            signalType: 'user_loved',
                                            placeRef: placeRef,
                                            valueText: 'loved',
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
        color: AppColors.accent.withOpacity(0.12),
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
