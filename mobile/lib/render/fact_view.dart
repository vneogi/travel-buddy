import 'package:flutter/material.dart';
import '../theme/spacing.dart';
import '../theme/typography.dart';
import '../theme/colors.dart';
import 'fact_envelope.dart';
import 'confirm_affordance.dart';
import 'dismiss_handler.dart';
import 'render_strings.dart';

/// The ONLY widget that renders a fact (SPEC-22 decision 2).
///
/// Every call site must pass `envelope:`. No bare-value constructor exists.
/// No `FactView.value(String)`. No optional tier.
///
/// Dismiss: the widget calls onDismiss with its own attribute and a
/// tier-derived kind. Callers pass PromptDismissAdapter.handler.
class FactView extends StatelessWidget {
  final FactEnvelope envelope;
  final String attribute;
  final String? deferralTarget;
  final bool showRecency;
  final VoidCallback? onConfirm;
  final DismissHandler? onDismiss;

  const FactView({
    super.key,
    required this.envelope,
    required this.attribute,
    this.deferralTarget,
    this.showRecency = false,
    this.onConfirm,
    this.onDismiss,
  });

  void _handleDismiss() {
    if (onDismiss == null) return;
    final kind = envelope.tier == FactTier.ask ? 'question_card' : 'deferral';
    onDismiss!(kind: kind, attribute: attribute);
  }

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
        return Text(_valueAsString(), style: AppTypography.body);

      case FactTier.hedge:
        return Text(
          RenderStrings.factHedge(_valueAsString()),
          style: AppTypography.body,
        );

      case FactTier.ask:
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
                RenderStrings.factAskPrompt,
                style: AppTypography.bodyMedium.copyWith(color: AppColors.muted),
              ),
              SizedBox(height: AppSpacing.xs),
              Text(_valueAsString(), style: AppTypography.body),
              SizedBox(height: AppSpacing.sm),
              ConfirmAffordance(onConfirm: onConfirm, onDismiss: _handleDismiss),
            ],
          ),
        );

      case FactTier.defer_:
        return Text(
          RenderStrings.factDeferSee(deferralTarget ?? 'source'),
          style: AppTypography.body.copyWith(color: AppColors.primary),
        );

      case FactTier.refuse:
        return Text(
          RenderStrings.factRefuse,
          style: AppTypography.body.copyWith(color: AppColors.muted),
        );
    }
  }

  Widget _buildRecency() {
    final month = _monthName(envelope.asOf.month);
    return Text(
      RenderStrings.factRecency(month),
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
