// SPEC-42 unknown-time excursion: "Make room for this" review. Lists the
// stops the window would skip. Nothing changes until Confirm resends the
// same Add with confirm_skip_node_ids.

import 'package:flutter/material.dart';

import '../../data/models.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';

/// What the window Add callback returns: a result, or refusal copy.
class ExcursionSubmitOutcome {
  final TripEventResult? result;
  final String? error;
  const ExcursionSubmitOutcome({this.result, this.error});
}

/// Pops the confirm outcome, or null on Not now (no event sent).
class ExcursionReviewSheet extends StatefulWidget {
  final ExcursionReview review;
  final List<TripNode> nodes;
  final Future<ExcursionSubmitOutcome> Function() onConfirm;

  const ExcursionReviewSheet({
    super.key,
    required this.review,
    required this.nodes,
    required this.onConfirm,
  });

  @override
  State<ExcursionReviewSheet> createState() => _ExcursionReviewSheetState();
}

class _ExcursionReviewSheetState extends State<ExcursionReviewSheet> {
  bool _sending = false;

  Future<void> _confirm() async {
    setState(() => _sending = true);
    final outcome = await widget.onConfirm();
    if (mounted) Navigator.of(context).pop(outcome);
  }

  @override
  Widget build(BuildContext context) {
    final byId = {for (final n in widget.nodes) n.nodeId: n};
    return SafeArea(
      child: Padding(
        key: const Key('excursion_review_sheet'),
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Make room for this', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.sm),
              Text('These stops would be skipped:', style: AppTypography.body),
              for (final id in widget.review.skipNodeIds)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.xs),
                  child: Text(
                    byId[id]?.venueName ?? 'A stop on this day',
                    key: Key('excursion_review_skip_$id'),
                    style: AppTypography.body,
                  ),
                ),
              const SizedBox(height: AppSpacing.lg),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    key: const Key('excursion_review_dismiss'),
                    onPressed: _sending ? null : () => Navigator.of(context).pop(),
                    child: const Text('Not now'),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  FilledButton(
                    key: const Key('excursion_review_confirm'),
                    onPressed: _sending ? null : _confirm,
                    child: const Text('Confirm'),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
