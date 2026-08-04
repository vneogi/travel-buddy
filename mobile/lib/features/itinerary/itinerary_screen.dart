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

class ItineraryScreen extends ConsumerStatefulWidget {
  final String tripId;
  const ItineraryScreen({super.key, required this.tripId});
  @override
  ConsumerState<ItineraryScreen> createState() => _ItineraryScreenState();
}

class _ItineraryScreenState extends ConsumerState<ItineraryScreen> {
  final _listKey = GlobalKey<AnimatedListState>();
  final List<TripNode> _shown = [];
  bool _seeded = false;

  String _sig(TripNode n) =>
      '${n.nodeId}|${n.venueId}|${n.venueName}|${n.scheduledStart.toIso8601String()}|${n.status.name}|${n.isLocked}';

  void _reconcile(List<TripNode> next) {
    final list = _listKey.currentState;
    if (list == null) {
      setState(() {
        _shown
          ..clear()
          ..addAll(next);
      });
      return;
    }
    const dOut = Duration(milliseconds: 200);
    const dIn = Duration(milliseconds: 260);

    // 1) Remove nodes no longer present (top-down).
    final nextIds = next.map((n) => n.nodeId).toSet();
    for (var i = _shown.length - 1; i >= 0; i--) {
      if (!nextIds.contains(_shown[i].nodeId)) {
        final removed = _shown.removeAt(i);
        list.removeItem(i, (c, a) => _tile(removed, a), duration: dOut);
      }
    }
    // 2) Walk target order: insert missing / move reorders / replace changed.
    for (var i = 0; i < next.length; i++) {
      final want = next[i];
      if (i >= _shown.length || _shown[i].nodeId != want.nodeId) {
        final at = _shown.indexWhere((n) => n.nodeId == want.nodeId);
        if (at > i) {
          // reorder: pull it from its old slot first (animate out)
          final moved = _shown.removeAt(at);
          list.removeItem(at, (c, a) => _tile(moved, a), duration: dOut);
        }
        _shown.insert(i, want);
        list.insertItem(i, duration: dIn);
      } else if (_sig(_shown[i]) != _sig(want)) {
        // same id & position, content changed (swap venue / shifted time):
        // remove+insert in place so the row rebuilds and cross-fades.
        _shown[i] = want;
        list.removeItem(i, (c, a) => _tile(want, a), duration: dOut);
        list.insertItem(i, duration: dIn);
      }
    }
    setState(() {}); // reflect any trailing state
  }

  Widget _tile(TripNode node, Animation<double> anim) {
    final idx = _shown.indexWhere((n) => n.nodeId == node.nodeId);
    final next = (idx >= 0 && idx < _shown.length - 1) ? _shown[idx + 1] : null;
    return SizeTransition(
      sizeFactor: anim,
      child: FadeTransition(
        opacity: anim,
        child: ActivityCard(
          node: node,
          nextNode: next,
          onTapSwap: () => _swap(node),
          onTapCancel: () => _cancel(node),
        ),
      ),
    );
  }

  void _swap(TripNode node) {
    // TODO(swap-sheet): open SwapSheet and pass the user's chosen vibe_tags.
    // Until then, re-search with the node's own vibes as a sensible default.
    ref.read(itineraryControllerProvider(widget.tripId).notifier).applyEvent(
          type: EventType.swapActivity,
          message: 'Swap ${node.venueName} for something similar nearby',
          targetNodeId: node.nodeId,
          preferences: {'vibe_tags': node.vibeTags},
        );
  }

  void _cancel(TripNode node) {
    ref.read(itineraryControllerProvider(widget.tripId).notifier).applyEvent(
          type: EventType.cancelActivity,
          message: 'Cancel ${node.venueName}',
          targetNodeId: node.nodeId,
        );
  }

  @override
  Widget build(BuildContext context) {
    final tripId = widget.tripId;
    ref.listen<ItineraryState>(itineraryControllerProvider(tripId), (prev, next) {
      if (next.rerouteLimitHit) {
        ref.read(itineraryControllerProvider(tripId).notifier).clearRerouteLimit();
        context.push('/upgrade');
      }
      if (_seeded) _reconcile(next.nodes);
    });

    final state = ref.watch(itineraryControllerProvider(tripId));

    // Seed the backing list once, without animation, on first data.
    if (!_seeded && !state.loading && state.error == null) {
      _shown
        ..clear()
        ..addAll(state.nodes);
      _seeded = true;
    }
    if (state.loading) _seeded = false; // re-seed after a retry

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
                    if (state.processing) const LinearProgressIndicator(minHeight: 2),
                    if (state.banner != null)
                      _HeadsUpBanner(
                        text: state.banner!,
                        onClose: () => ref
                            .read(itineraryControllerProvider(tripId).notifier)
                            .clearBanner(),
                      ),
                    Expanded(
                      child: _shown.isEmpty
                          ? Center(
                              child: Text('No activities yet.',
                                  style: AppTypography.body
                                      .copyWith(color: AppColors.muted)),
                            )
                          : AnimatedList(
                              key: _listKey,
                              initialItemCount: _shown.length,
                              padding: const EdgeInsets.only(
                                  top: AppSpacing.base, bottom: 100),
                              itemBuilder: (c, i, anim) => _tile(_shown[i], anim),
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
