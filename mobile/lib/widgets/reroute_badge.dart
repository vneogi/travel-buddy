import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../core/providers.dart';
import '../theme/colors.dart';
import '../theme/typography.dart';
import '../theme/spacing.dart';

/// Pill showing "3 left today". Color shifts: teal >=3, amber 1-2, danger 0.
/// At 0 becomes an "Upgrade" button.
class RerouteBadge extends ConsumerWidget {
  final VoidCallback? onUpgradeTap;
  const RerouteBadge({super.key, this.onUpgradeTap});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(userStatusProvider);

    return statusAsync.when(
      data: (status) {
        final remaining = status.remaining;
        final color = remaining >= 3
            ? AppColors.primary
            : remaining >= 1
                ? AppColors.warning
                : AppColors.danger;

        if (remaining == 0) {
          return GestureDetector(
            onTap: onUpgradeTap,
            child: Container(
              padding: const EdgeInsets.symmetric(
                horizontal: AppSpacing.md,
                vertical: AppSpacing.sm,
              ),
              decoration: BoxDecoration(
                color: AppColors.danger.withOpacity(0.1),
                borderRadius: BorderRadius.circular(AppSpacing.radiusChip),
                border: Border.all(color: AppColors.danger.withOpacity(0.3)),
              ),
              child: Text(
                'Upgrade',
                style: AppTypography.counter.copyWith(color: AppColors.danger),
              ),
            ),
          );
        }

        return Container(
          padding: const EdgeInsets.symmetric(
            horizontal: AppSpacing.md,
            vertical: AppSpacing.sm,
          ),
          decoration: BoxDecoration(
            color: color.withOpacity(0.1),
            borderRadius: BorderRadius.circular(AppSpacing.radiusChip),
          ),
          child: Text(
            '$remaining left today',
            style: AppTypography.counter.copyWith(color: color),
          ),
        );
      },
      loading: () => const SizedBox.shrink(),
      error: (_, __) => const SizedBox.shrink(),
    );
  }
}
