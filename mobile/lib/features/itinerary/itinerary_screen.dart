import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/activity_card.dart';
import '../../widgets/reroute_badge.dart';
import '../../widgets/shimmer_card.dart';
import '../../widgets/error_view.dart';
import 'itinerary_notifier.dart';

/// The hero screen — live timeline of activity cards that reflows on events.
class ItineraryScreen extends ConsumerWidget {
  final String tripId;
  const ItineraryScreen({super.key, required this.tripId});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tripAsync = ref.watch(tripProvider(tripId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Your Day', style: AppTypography.h2),
        actions: [
          RerouteBadge(onUpgradeTap: () => context.push('/upgrade')),
          const SizedBox(width: AppSpacing.base),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/trip/\$tripId/chat'),
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.chat_bubble_outline, color: Colors.white),
      ),
      body: tripAsync.when(
        data: (trip) => _TripTimeline(trip: trip, tripId: tripId),
        loading: () => const ShimmerList(count: 5),
        error: (e, _) => ErrorView(
          error: e,
          onRetry: () => ref.invalidate(tripProvider(tripId)),
        ),
      ),
    );
  }
}

class _TripTimeline extends StatelessWidget {
  final TripState trip;
  final String tripId;
  const _TripTimeline({required this.trip, required this.tripId});

  @override
  Widget build(BuildContext context) {
    if (trip.nodes.isEmpty) {
      return Center(
        child: Text(
          'No activities yet.',
          style: AppTypography.body.copyWith(color: AppColors.muted),
        ),
      );
    }

    return AnimatedList(
      key: ValueKey(tripId),
      initialItemCount: trip.nodes.length,
      padding: const EdgeInsets.only(
        top: AppSpacing.base,
        bottom: 100, // space for FAB
      ),
      itemBuilder: (context, index, animation) {
        final node = trip.nodes[index];
        final next = index < trip.nodes.length - 1 ? trip.nodes[index + 1] : null;
        return SizeTransition(
          sizeFactor: animation,
          child: ActivityCard(
            node: node,
            nextNode: next,
            onTapSwap: () {
              // TODO: open swap sheet for this node
            },
          ),
        );
      },
    );
  }
}
