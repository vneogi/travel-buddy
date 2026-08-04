import 'package:flutter/material.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/shimmer_card.dart';

/// Bottom sheet with RAG venue suggestions for swapping an activity.
class SwapSheet extends StatelessWidget {
  final String tripId;
  final String targetNodeId;
  const SwapSheet({super.key, required this.tripId, required this.targetNodeId});

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.6,
      maxChildSize: 0.9,
      minChildSize: 0.3,
      builder: (_, scrollController) => Container(
        decoration: const BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppSpacing.radiusSheet),
          ),
        ),
        child: Column(
          children: [
            // Drag handle
            Container(
              margin: const EdgeInsets.only(top: AppSpacing.md),
              width: 40, height: 4,
              decoration: BoxDecoration(
                color: AppColors.divider,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Text('Swap to...', style: AppTypography.h2),
            ),
            // Vibe filter chips
            SizedBox(
              height: 36,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.base),
                children: ['premium', 'cultural', 'outdoor', 'family', 'nightlife']
                    .map((v) => Padding(
                          padding: const EdgeInsets.only(right: AppSpacing.sm),
                          child: FilterChip(label: Text(v), onSelected: (_) {}),
                        ))
                    .toList(),
              ),
            ),
            const SizedBox(height: AppSpacing.base),
            // Suggestions (placeholder - will wire to venues/search)
            const Expanded(child: ShimmerList(count: 3)),
          ],
        ),
      ),
    );
  }
}
