import 'package:flutter/material.dart';
import '../theme/spacing.dart';
import '../theme/typography.dart';

/// One-tap confirm control (SPEC-22 decision 2, SPEC-12 shared later).
///
/// No TextField. No "edit". Confirm calls onConfirm only.
class ConfirmAffordance extends StatelessWidget {
  final VoidCallback? onConfirm;
  final VoidCallback? onDismiss;

  const ConfirmAffordance({super.key, this.onConfirm, this.onDismiss});

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        TextButton(
          onPressed: onConfirm,
          child: Text('Confirm', style: AppTypography.body2),
        ),
        SizedBox(width: AppSpacing.sm),
        if (onDismiss != null)
          IconButton(
            icon: const Icon(Icons.close, size: AppSpacing.base),
            onPressed: onDismiss,
            tooltip: 'Dismiss',
          ),
      ],
    );
  }
}
