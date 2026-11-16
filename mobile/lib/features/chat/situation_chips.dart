import 'package:flutter/material.dart';

import '../../theme/spacing.dart';

/// SPEC-53 slice 1: a fixed, named bundle of What Now settings.
///
/// Each chip sends the same What Now request as the sheet, through the same
/// path. Values must stay inside WhatNowRequest.ALLOWED_* in
/// services/ask_service.py. Labels make no claim the engine does not compute.
class SituationChip {
  final String id;
  final String label;
  final int availableMinutes;
  final String energy;
  final String walking;
  final String intent;

  const SituationChip({
    required this.id,
    required this.label,
    required this.availableMinutes,
    required this.energy,
    required this.walking,
    required this.intent,
  });

  /// The What Now preferences map; context_node_id only when given.
  Map<String, dynamic> preferences({String? contextNodeId}) => {
        'mode': 'what_now',
        'available_minutes': availableMinutes,
        'energy': energy,
        'walking': walking,
        'intent': intent,
        if (contextNodeId != null) 'context_node_id': contextNodeId,
      };
}

const List<SituationChip> kSituationChips = [
  SituationChip(
    id: 'quick_break',
    label: 'Quick break',
    availableMinutes: 90,
    energy: 'low',
    walking: 'short',
    intent: 'anything',
  ),
  SituationChip(
    id: 'low_energy',
    label: 'Low energy',
    availableMinutes: 90,
    energy: 'low',
    walking: 'short',
    intent: 'quiet',
  ),
  SituationChip(
    id: 'indoors',
    label: 'Indoors',
    availableMinutes: 90,
    energy: 'normal',
    walking: 'short',
    intent: 'shelter',
  ),
  SituationChip(
    id: 'food',
    label: 'Something to eat',
    availableMinutes: 90,
    energy: 'normal',
    walking: 'normal',
    intent: 'food',
  ),
];

/// Horizontally scrolling row of one-tap situation chips.
class SituationChipRow extends StatelessWidget {
  final bool enabled;
  final ValueChanged<SituationChip> onSelected;

  const SituationChipRow({
    super.key,
    required this.enabled,
    required this.onSelected,
  });

  static const double minTapHeight = 44;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.base,
        AppSpacing.xs,
        AppSpacing.base,
        0,
      ),
      child: SingleChildScrollView(
        key: const Key('situation_chip_row'),
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (var i = 0; i < kSituationChips.length; i++) ...[
              if (i > 0) const SizedBox(width: AppSpacing.sm),
              ConstrainedBox(
                constraints: const BoxConstraints(minHeight: minTapHeight),
                child: ActionChip(
                  key: Key('situation_chip_${kSituationChips[i].id}'),
                  label: Text(kSituationChips[i].label),
                  materialTapTargetSize: MaterialTapTargetSize.padded,
                  onPressed: enabled
                      ? () => onSelected(kSituationChips[i])
                      : null,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
