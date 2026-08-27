import 'package:flutter/material.dart';

import '../data/context_alert.dart';
import '../theme/colors.dart';
import '../theme/spacing.dart';
import '../theme/typography.dart';

/// SPEC-29: Compact alert card shown above the itinerary timeline.
class AlertCard extends StatelessWidget {
  final ContextAlert alert;
  final VoidCallback? onDismiss;

  const AlertCard({super.key, required this.alert, this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(alert.severity);
    final icon = _severityIcon(alert.severity);
    final ago = _timeAgo(alert.sourceUpdatedAt);

    return Card(
      color: color.withAlpha(20),
      margin: const EdgeInsets.symmetric(
        horizontal: AppSpacing.base,
        vertical: AppSpacing.xs,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        side: BorderSide(color: color.withAlpha(80)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(AppSpacing.sm),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, color: color, size: AppSpacing.iconSm),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(alert.message, style: AppTypography.body),
                  const SizedBox(height: AppSpacing.xs),
                  Text(
                    'OpenWeather - Updated $ago',
                    style: AppTypography.caption,
                  ),
                ],
              ),
            ),
            if (onDismiss != null)
              IconButton(
                icon: const Icon(Icons.close, size: 16),
                onPressed: onDismiss,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(),
              ),
          ],
        ),
      ),
    );
  }

  Color _severityColor(String severity) {
    switch (severity) {
      case 'warning':
        return AppColors.danger;
      case 'advisory':
        return AppColors.warning;
      default:
        return AppColors.accent;
    }
  }

  IconData _severityIcon(String severity) {
    switch (severity) {
      case 'warning':
        return Icons.warning_amber_rounded;
      case 'advisory':
        return Icons.info_outline;
      default:
        return Icons.thermostat;
    }
  }

  String _timeAgo(DateTime dt) {
    final diff = DateTime.now().toUtc().difference(dt);
    if (diff.inMinutes < 1) return 'just now';
    if (diff.inMinutes < 60) return '${diff.inMinutes} min ago';
    return '${diff.inHours} hr ago';
  }
}
