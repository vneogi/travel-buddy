import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../data/models.dart';
import '../theme/colors.dart';
import '../theme/typography.dart';
import '../theme/spacing.dart';

/// Timeline activity card. Shows venue, time, vibe chips, transit.
/// Locked cards resist swipe (haptic + padlock shake).
class ActivityCard extends StatelessWidget {
  final TripNode node;
  final TripNode? nextNode;
  final VoidCallback? onTapSwap;
  final VoidCallback? onTapCancel;
  final VoidCallback? onTapLoved;
  final bool isThinking; // show shimmer for heavy model calls
  final bool isLoved; // filled heart once the user has loved this venue

  const ActivityCard({
    super.key,
    required this.node,
    this.nextNode,
    this.onTapSwap,
    this.onTapCancel,
    this.onTapLoved,
    this.isThinking = false,
    this.isLoved = false,
  });

  @override
  Widget build(BuildContext context) {
    final isActive = node.status == NodeStatus.active;
    final isCompleted = node.status == NodeStatus.completed;
    final isSkipped = node.status == NodeStatus.skipped;

    return Dismissible(
      key: ValueKey(node.nodeId),
      direction: node.isLocked
          ? DismissDirection.none
          : DismissDirection.endToStart,
      confirmDismiss: (_) async {
        if (node.isLocked) {
          HapticFeedback.mediumImpact();
          return false;
        }
        onTapSwap?.call();
        return false; // handle via callback, don't remove
      },
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: AppSpacing.lg),
        color: AppColors.primary.withValues(alpha: 0.1),
        child: const Icon(Icons.swap_horiz, color: AppColors.primary),
      ),
      child: Container(
        margin: const EdgeInsets.symmetric(
          horizontal: AppSpacing.base,
          vertical: AppSpacing.xs,
        ),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
          border: isActive
              ? Border(left: BorderSide(color: AppColors.accent, width: 4))
              : node.isLocked
                  ? Border.all(color: AppColors.accent.withValues(alpha: 0.3))
                  : null,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: 0.04),
              blurRadius: 8,
              offset: const Offset(0, 2),
            ),
          ],
        ),
        child: Opacity(
          opacity: isCompleted || isSkipped ? 0.5 : 1.0,
          child: Padding(
            padding: const EdgeInsets.all(AppSpacing.base),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Time rail
                SizedBox(
                  width: 52,
                  child: Column(
                    children: [
                      Text(
                        _formatTime(node.scheduledStart),
                        style: AppTypography.counter.copyWith(
                          color: isActive ? AppColors.accent : AppColors.muted,
                        ),
                      ),
                      if (isActive)
                        Container(
                          margin: const EdgeInsets.only(top: AppSpacing.xs),
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.accent,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            'NOW',
                            style: AppTypography.caption.copyWith(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(width: AppSpacing.md),
                // Content
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              node.venueName,
                              style: isSkipped
                                  ? AppTypography.h2.copyWith(
                                      decoration: TextDecoration.lineThrough)
                                  : AppTypography.h2,
                            ),
                          ),
                          if (node.isLocked)
                            Icon(Icons.lock, size: 16, color: AppColors.accent),
                          // Visible swap affordance — swipe still works, but the
                          // gesture alone was undiscoverable.
                          if (onTapSwap != null && !node.isLocked && !isCompleted && !isSkipped)
                            IconButton(
                              icon: const Icon(Icons.swap_horiz, size: 20),
                              color: AppColors.primary,
                              tooltip: 'Swap this activity',
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                              onPressed: () {
                                HapticFeedback.lightImpact();
                                onTapSwap!.call();
                              },
                            ),
                          if (onTapLoved != null && !isCompleted && !isSkipped)
                            IconButton(
                              icon: Icon(
                                isLoved ? Icons.favorite : Icons.favorite_border,
                                size: 20,
                              ),
                              color: isLoved ? AppColors.danger : AppColors.muted,
                              tooltip: isLoved ? 'Loved' : 'Love this place',
                              visualDensity: VisualDensity.compact,
                              padding: EdgeInsets.zero,
                              constraints: const BoxConstraints(minWidth: 36, minHeight: 36),
                              onPressed: () {
                                HapticFeedback.lightImpact();
                                onTapLoved!.call();
                              },
                            ),
                        ],
                      ),
                      if (node.microLocation != null) ...[
                        const SizedBox(height: AppSpacing.xs),
                        Text(node.microLocation!, style: AppTypography.caption),
                      ],
                      if (node.vibeTags.isNotEmpty) ...[
                        const SizedBox(height: AppSpacing.sm),
                        Wrap(
                          spacing: AppSpacing.xs,
                          runSpacing: AppSpacing.xs,
                          children: node.vibeTags.map((tag) => _VibeChip(tag)).toList(),
                        ),
                      ],
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _formatTime(DateTime dt) =>
      '${dt.hour.toString().padLeft(2, "0")}:${dt.minute.toString().padLeft(2, "0")}';
}

class _VibeChip extends StatelessWidget {
  final String label;
  const _VibeChip(this.label);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(AppSpacing.radiusChip),
      ),
      child: Text(
        label,
        style: AppTypography.caption.copyWith(
          color: AppColors.primaryDark,
          fontSize: 11,
        ),
      ),
    );
  }
}
