import 'package:flutter/material.dart';
import '../core/api_exception.dart';
import '../theme/colors.dart';
import '../theme/typography.dart';
import '../theme/spacing.dart';

/// Friendly error state widget. Maps ApiException types to user copy.
class ErrorView extends StatelessWidget {
  final Object error;
  final VoidCallback? onRetry;

  const ErrorView({super.key, required this.error, this.onRetry});

  @override
  Widget build(BuildContext context) {
    final (icon, title, subtitle) = _mapError(error);

    return Center(
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.xl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 48, color: AppColors.muted),
            const SizedBox(height: AppSpacing.base),
            Text(title, style: AppTypography.h2, textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.sm),
            Text(subtitle, style: AppTypography.caption, textAlign: TextAlign.center),
            if (onRetry != null) ...[
              const SizedBox(height: AppSpacing.lg),
              ElevatedButton.icon(
                onPressed: onRetry,
                icon: const Icon(Icons.refresh, size: 18),
                label: const Text('Try again'),
              ),
            ],
          ],
        ),
      ),
    );
  }

  (IconData, String, String) _mapError(Object error) {
    if (error is NetworkException) {
      return (Icons.wifi_off_rounded, 'No connection', error.message);
    }
    if (error is UnauthorizedException) {
      return (Icons.lock_outline, 'Session expired', error.message);
    }
    if (error is ForbiddenException) {
      return (Icons.block_outlined, 'Access denied', error.message);
    }
    if (error is NotFoundException) {
      return (Icons.search_off, 'Not found', error.message);
    }
    if (error is ServerException) {
      return (Icons.cloud_off, 'Server error', error.message);
    }
    return (
      Icons.error_outline,
      'Something went wrong',
      'Please try again. If the problem continues, check your connection.',
    );
  }
}
