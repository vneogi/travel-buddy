import 'package:flutter/material.dart';
import '../theme/spacing.dart';
import '../theme/typography.dart';
import '../theme/colors.dart';

/// Three-state connectivity/cache model (SPEC-22 decision 7).
enum OfflineState { live, cached, unavailable }

/// Renders child wrapped in offline context. No AppColors.danger for offline.
///
/// - live: just the child
/// - cached: child + recency note; retry is a secondary text button, not primary
/// - unavailable: explicit empty-cache copy; no danger red
///
/// NOTE: ErrorView is still used for server/unreachable errors.
/// OfflineStateView is for designed offline (airplane mode, no cache).
class OfflineStateView extends StatelessWidget {
  final OfflineState state;
  final Widget child;
  final String? cachedAt;
  final VoidCallback? onRetry;

  const OfflineStateView({
    super.key,
    required this.state,
    required this.child,
    this.cachedAt,
    this.onRetry,
  });

  @override
  Widget build(BuildContext context) {
    switch (state) {
      case OfflineState.live:
        return child;
      case OfflineState.cached:
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            child,
            SizedBox(height: AppSpacing.sm),
            Row(
              children: [
                Icon(Icons.cloud_off, size: AppSpacing.base, color: AppColors.muted),
                SizedBox(width: AppSpacing.xs),
                if (cachedAt != null)
                  Text('Cached $cachedAt', style: AppTypography.caption),
                const Spacer(),
                if (onRetry != null)
                  TextButton(
                    onPressed: onRetry,
                    child: Text('Retry', style: AppTypography.caption),
                  ),
              ],
            ),
          ],
        );
      case OfflineState.unavailable:
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.cloud_off, size: AppSpacing.xl, color: AppColors.muted),
            SizedBox(height: AppSpacing.sm),
            Text(
              'Not available offline',
              style: AppTypography.body2.copyWith(color: AppColors.muted),
            ),
            if (onRetry != null)
              Padding(
                padding: EdgeInsets.only(top: AppSpacing.sm),
                child: TextButton(
                  onPressed: onRetry,
                  child: Text('Retry when online', style: AppTypography.caption),
                ),
              ),
          ],
        );
    }
  }
}
