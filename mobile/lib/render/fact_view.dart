import 'package:flutter/material.dart';
import '../theme/spacing.dart';
import '../theme/typography.dart';
import '../theme/colors.dart';
import 'fact_envelope.dart';
import 'confirm_affordance.dart';

/// The ONLY widget that renders a fact (SPEC-22 decision 2).
///
/// Every call site must pass `envelope:`. No bare-value constructor exists.
/// No `FactView.value(String)`. No optional tier.
class FactView extends StatelessWidget {
  final FactEnvelope envelope;
  final String attribute;
  final String? deferralTarget;
  final bool showRecency;
  final VoidCallback? onConfirm;
  final VoidCallback? onDismiss;

  const FactView({
    super.key,
    required this.envelope,
    required this.attribute,
    this.deferralTarget,
    this.showRecency = false,
    this.onConfirm,
    this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        _buildTierContent(),
        if (showRecency && envelope.tier != FactTier.refuse)
          Padding(
            padding: EdgeInsets.only(top: AppSpacing.xs),
            child: _buildRecency(),
          ),
      ],
    );
  }

  Widget _buildTierContent() {
    switch (envelope.tier) {
      case FactTier.assert_:
        // Plain text. No badge, no icon, no colour callout.
        return Text(
          _valueAsString(),
          style: AppTypography.body,
        );

      case FactTier.hedge:
        // Qualifier inside the sentence.
        return Text.rich(TextSpan(
          style: AppTypography.body,
          children: [
            TextSpan(
              text: 'Travellers usually say ',
              style: AppTypography.body.copyWith(color: AppColors.muted),
            ),
            TextSpan(text: _valueAsString()),
          ],
        ));

      case FactTier.ask:
        // Question card with confirm affordance.
        return Container(
          padding: EdgeInsets.all(AppSpacing.md),
          decoration: BoxDecoration(
            border: Border.all(color: AppColors.divider),
            borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Is this still correct?',
                style: AppTypography.body2.copyWith(color: AppColors.muted),
              ),
              SizedBox(height: AppSpacing.xs),
              Text(_valueAsString(), style: AppTypography.body),
              SizedBox(height: AppSpacing.sm),
              ConfirmAffordance(onConfirm: onConfirm, onDismiss: onDismiss),
            ],
          ),
        );

      case FactTier.defer_:
        // Labelled link. No value displayed.
        return Text.rich(TextSpan(
          style: AppTypography.body,
          children: [
            const TextSpan(text: 'See '),
            TextSpan(
              text: deferralTarget ?? 'source',
              style: AppTypography.body.copyWith(color: AppColors.primary),
            ),
          ],
        ));

      case FactTier.refuse:
        // Explicit unknown. Never empty/whitespace.
        return Text(
          'Information not available',
          style: AppTypography.body.copyWith(color: AppColors.muted),
        );
    }
  }

  Widget _buildRecency() {
    final month = _monthName(envelope.asOf.month);
    return Text(
      'Confirmed in $month',
      style: AppTypography.caption.copyWith(color: AppColors.subtle),
    );
  }

  String _valueAsString() {
    final v = envelope.value;
    if (v == null) return '';
    if (v is String) return v;
    return v.toString();
  }

  static String _monthName(int month) {
    const months = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December',
    ];
    return months[month - 1];
  }
}
