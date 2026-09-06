import 'package:flutter/material.dart';

import '../data/departure_notification.dart';
import '../theme/colors.dart';
import '../theme/spacing.dart';
import '../theme/typography.dart';

/// SPEC-35 Phase A2: Compact departure reminder banner above the timeline.
///
/// Paints server title and message exactly. Does not invent traffic or rain copy.
/// Tap scrolls to node_id if present; does not open maps, request location, swap, or cancel.
class DepartureBanner extends StatelessWidget {
  final NotificationCandidate candidate;
  final VoidCallback? onDismiss;
  final ValueChanged<String>? onTapNodeId;

  const DepartureBanner({
    super.key,
    required this.candidate,
    this.onDismiss,
    this.onTapNodeId,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      color: AppColors.primary.withAlpha(20),
      margin: const EdgeInsets.symmetric(
        horizontal: AppSpacing.base,
        vertical: AppSpacing.xs,
      ),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        side: BorderSide(color: AppColors.primary.withAlpha(80)),
      ),
      child: InkWell(
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        onTap: onTapNodeId != null
            ? () => onTapNodeId!(candidate.nodeId)
            : null,
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.sm),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(
                Icons.directions_car_outlined,
                color: AppColors.primary,
                size: AppSpacing.iconSm,
              ),
              const SizedBox(width: AppSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(candidate.title, style: AppTypography.body),
                    const SizedBox(height: AppSpacing.xs),
                    Text(candidate.message, style: AppTypography.caption),
                    if (_captionText != null) ...[
                      const SizedBox(height: AppSpacing.xs),
                      Text(
                        _captionText!,
                        style: AppTypography.caption.copyWith(
                          color: AppColors.muted,
                        ),
                      ),
                    ],
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
      ),
    );
  }

  /// Optional caption: route source, plus weather source when present.
  String? get _captionText {
    final route = candidate.evidence.route;
    if (route == null) return null;
    final parts = <String>[route.source];
    final weather = candidate.evidence.weather;
    if (weather != null) {
      parts.add(weather.source);
    }
    return parts.join(' + ');
  }
}
