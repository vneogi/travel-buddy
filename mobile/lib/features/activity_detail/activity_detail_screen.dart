import 'package:flutter/material.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

/// SPEC-07: Activity detail with Swap and Cancel wired to callbacks.
class ActivityDetailScreen extends StatelessWidget {
  final TripNode node;
  final VoidCallback? onSwap;
  final VoidCallback? onCancel;
  const ActivityDetailScreen({
    super.key,
    required this.node,
    this.onSwap,
    this.onCancel,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(node.venueName, style: AppTypography.h2)),
      body: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Venue hero placeholder
            Container(
              height: 200,
              width: double.infinity,
              decoration: BoxDecoration(
                color: AppColors.primaryLight,
                borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
              ),
              child: const Icon(Icons.place, size: 48, color: AppColors.primary),
            ),
            const SizedBox(height: AppSpacing.lg),
            if (node.microLocation != null)
              Text(node.microLocation!, style: AppTypography.caption),
            const SizedBox(height: AppSpacing.sm),
            if (node.openingHours != null)
              Text('Hours: ${node.openingHours}', style: AppTypography.body),
            const SizedBox(height: AppSpacing.base),
            Wrap(
              spacing: AppSpacing.sm,
              children: node.vibeTags.map((t) => Chip(label: Text(t))).toList(),
            ),
            const Spacer(),
            if (!node.isLocked) ...[
              Row(
                children: [
                  Expanded(
                    child: ElevatedButton(
                      onPressed: onSwap,
                      child: const Text('Swap'),
                    ),
                  ),
                  const SizedBox(width: AppSpacing.md),
                  Expanded(
                    child: OutlinedButton(
                      onPressed: onCancel,
                      child: const Text('Cancel'),
                    ),
                  ),
                ],
              ),
            ] else
              Center(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(Icons.lock, size: 16, color: AppColors.accent),
                    const SizedBox(width: AppSpacing.sm),
                    Text('Locked reservation', style: AppTypography.label),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
