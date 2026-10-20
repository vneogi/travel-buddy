import 'package:flutter/material.dart';

import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';

const _reasonCopy = <String, String>{
  'fits_available_window': 'Fits your time',
  'open_for_planned_time': 'Open then',
  'keeps_next_booking_reachable': 'Keeps next booking reachable',
  'matches_requested_type': 'Matches your request',
  'matches_trip_interest': 'Matches trip interests',
  'same_neighbourhood': 'Same area',
  'short_walk_from_context': 'Short walk',
  'lower_typical_dwell': 'Lower dwell',
  'indoor_option': 'Indoor option',
};

const _unknownCopy = <String, String>{
  'price': 'Price unknown',
  'live_crowds': 'Live crowds unknown',
  'traffic': 'Traffic unknown',
  'opening_hours': 'Hours unknown',
  'walking_time': 'Walking time unknown',
  'typical_dwell': 'Dwell unknown',
};

class WhatNowBubble extends StatelessWidget {
  final AskResponse askResponse;
  final bool fromHistory;
  final void Function(WhatNowCandidate candidate)? onAddToPlan;
  const WhatNowBubble({
    super.key,
    required this.askResponse,
    this.fromHistory = false,
    this.onAddToPlan,
  });

  @override
  Widget build(BuildContext context) {
    final whatNow = askResponse.whatNow!;
    return Container(
      key: const Key('what_now_bubble'),
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
          Text(whatNow.contextLabel, style: AppTypography.label),
          if (askResponse.answer.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(askResponse.answer, style: AppTypography.body),
          ],
          const SizedBox(height: AppSpacing.sm),
          for (final candidate in whatNow.candidates) ...[
            _CandidateCard(
              candidate: candidate,
              showAddToPlan: !fromHistory && onAddToPlan != null,
              onAddToPlan: onAddToPlan,
            ),
            if (candidate != whatNow.candidates.last)
              const SizedBox(height: AppSpacing.sm),
          ],
        ],
      ),
    );
  }
}

class _CandidateCard extends StatelessWidget {
  final WhatNowCandidate candidate;
  final bool showAddToPlan;
  final void Function(WhatNowCandidate candidate)? onAddToPlan;
  const _CandidateCard({
    required this.candidate,
    this.showAddToPlan = false,
    this.onAddToPlan,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      key: Key('what_now_candidate_${candidate.venueId}'),
      padding: const EdgeInsets.all(AppSpacing.sm),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        border: Border.all(color: AppColors.divider),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(candidate.name, style: AppTypography.bodyMedium),
          if (candidate.microLocationDisplay.isNotEmpty)
            Text(candidate.microLocationDisplay,
                style: AppTypography.caption.copyWith(color: AppColors.muted)),
          if (candidate.typicalDwellMinutes != null)
            Text('${candidate.typicalDwellMinutes} min dwell',
                style: AppTypography.caption),
          if (candidate.reasonCodes.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Wrap(spacing: AppSpacing.xs, runSpacing: AppSpacing.xs, children: [
              for (final code in candidate.reasonCodes)
                _Pill(key: Key('what_now_reason_${candidate.venueId}_$code'),
                    label: _reasonCopy[code] ?? code),
            ]),
          ],
          if (candidate.unknownFields.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.xs),
            Wrap(spacing: AppSpacing.xs, runSpacing: AppSpacing.xs, children: [
              for (final field in candidate.unknownFields)
                _Pill(key: Key('what_now_unknown_${candidate.venueId}_$field'),
                    label: _unknownCopy[field] ?? field,
                    foreground: AppColors.muted, background: AppColors.card),
            ]),
          ],
          const SizedBox(height: AppSpacing.sm),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextButton(
                key: Key('what_now_details_${candidate.venueId}'),
                onPressed: () => showModalBottomSheet(
                  context: context,
                  builder: (_) => Padding(
                    key: Key('what_now_detail_sheet_${candidate.venueId}'),
                    padding: const EdgeInsets.all(AppSpacing.base),
                    child: SafeArea(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(candidate.name, style: AppTypography.h2),
                          if (candidate.microLocationDisplay.isNotEmpty)
                            Text(candidate.microLocationDisplay, style: AppTypography.body),
                          if (candidate.category.isNotEmpty)
                            Text('Category: ${candidate.category}', style: AppTypography.body),
                          if (candidate.typicalDwellMinutes != null)
                            Text('Typical dwell: ${candidate.typicalDwellMinutes} min',
                                style: AppTypography.body),
                        ],
                      ),
                    ),
                  ),
                ),
                child: const Text('View details'),
              ),
              if (showAddToPlan) ...[
                const SizedBox(width: AppSpacing.sm),
                ElevatedButton(
                  key: Key('what_now_add_${candidate.venueId}'),
                  onPressed: () => onAddToPlan?.call(candidate),
                  child: const Text('Add to plan'),
                ),
              ],
            ],
          ),

        ],
      ),
    );
  }
}

class _Pill extends StatelessWidget {
  final String label;
  final Color? foreground;
  final Color? background;
  const _Pill({super.key, required this.label, this.foreground, this.background});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.sm, vertical: AppSpacing.xs),
      decoration: BoxDecoration(
        color: background ?? AppColors.primary.withOpacity(0.08),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label,
          style: AppTypography.caption.copyWith(color: foreground ?? AppColors.primary)),
    );
  }
}
