/// SPEC-25: Public Ask bubble widget for Chat.
///
/// Renders the backend answer text directly (no RenderStrings.factHedge,
/// no RenderStrings.factRefuse). Shows source_class/path as caption.
/// dish_fact shows food_disclaimer. plan_change + proposal shows
/// ConfirmAffordance. Wire 'assert' tier is downgraded to hedge treatment.
import 'package:flutter/material.dart';
import '../../data/models.dart';
import '../../render/confirm_affordance.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

/// The ONLY widget that renders an Ask response in Chat.
///
/// Public so tests can pump it directly. Keyed per the brief:
/// - `ask_fact_view`: catalog / trip / miss (not plan-change)
/// - `ask_plan_change_confirm`: plan-change with proposal
class AskBubble extends StatelessWidget {
  final AskResponse askResponse;
  final VoidCallback? onConfirm;
  final VoidCallback? onDismiss;

  const AskBubble({
    super.key,
    required this.askResponse,
    this.onConfirm,
    this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    final ask = askResponse;
    final isPlanChange =
        ask.intent == 'plan_change' && ask.proposal != null;
    final showDisclaimer =
        ask.intent == 'dish_fact' && ask.foodDisclaimer != null;
    final caption =
        ask.sourceClass.isNotEmpty ? ask.sourceClass : ask.path;

    return Container(
      key: Key(isPlanChange ? 'ask_plan_change_confirm' : 'ask_fact_view'),
      padding: const EdgeInsets.all(AppSpacing.md),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        border: Border.all(color: AppColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Answer body text -- always shown verbatim.
          if (ask.answer.isNotEmpty)
            Text(ask.answer, style: AppTypography.body),

          // Caption: source_class or path.
          if (caption.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                caption,
                style: AppTypography.caption.copyWith(
                  color: AppColors.muted,
                ),
              ),
            ),

          // Food disclaimer -- dish_fact only.
          if (showDisclaimer)
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.xs),
              child: Text(
                ask.foodDisclaimer!,
                style: AppTypography.caption.copyWith(
                  color: AppColors.muted,
                  fontStyle: FontStyle.italic,
                ),
              ),
            ),

          // Plan-change confirm -- only with known proposal.
          if (isPlanChange && _isKnownEventType(ask.proposal!.eventType))
            Padding(
              padding: const EdgeInsets.only(top: AppSpacing.sm),
              child: ConfirmAffordance(
                onConfirm: onConfirm,
                onDismiss: onDismiss,
              ),
            ),
        ],
      ),
    );
  }

  static bool _isKnownEventType(String eventType) {
    const known = {
      'swap_activity',
      'cancel_activity',
      'add_activity',
      'reroute',
    };
    return known.contains(eventType);
  }
}
