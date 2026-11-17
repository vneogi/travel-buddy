import 'package:flutter/material.dart';

import '../../core/destination_tz.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import '../itinerary/micro_location_label.dart';

/// SPEC-50 slice 1: compare the current stop with one swap candidate.
/// Shows only fields the server already sent. No score, rank or claim.

const String kSwapChecksCopy =
    "Passed the server's opening-hours and reachability checks for this slot.";
const String kSwapSponsoredCopy =
    'Sponsored option: paid placement can affect its position.';
const String kSwapAreaMissing = 'Area: not available';
const String kSwapVibesMissing = 'Vibes: not available';

/// One comparison row. [label] null means the row is a single fixed line.
class SwapComparisonRow {
  final String id;
  final String? label;
  final String text;
  const SwapComparisonRow({required this.id, this.label, required this.text});

  String get plainText => label == null ? text : '$label  $text';
}

/// Rows in display order. Pure: no clock, no I/O.
List<SwapComparisonRow> swapComparisonRows({
  required TripNode current,
  required VenueSearchResult option,
}) {
  final end =
      current.scheduledStart.add(Duration(minutes: current.durationMinutes));
  final start = formatDestinationTime(current.scheduledStart, current.geoRegion);
  final until = formatDestinationTime(end, current.geoRegion);

  final rawArea = option.microLocation.trim();
  final area = rawArea.isEmpty
      ? null
      : (friendlyMicroLocation(rawArea) ?? rawArea);
  final vibes = option.vibeTags
      .map((t) => t.trim())
      .where((t) => t.isNotEmpty)
      .take(4)
      .toList();

  return [
    SwapComparisonRow(
      id: 'now',
      label: 'Now',
      text: '${current.venueName}  $start to $until',
    ),
    SwapComparisonRow(id: 'option', label: 'Option', text: option.name),
    area == null
        ? const SwapComparisonRow(id: 'area', text: kSwapAreaMissing)
        : SwapComparisonRow(id: 'area', label: 'Area', text: area),
    vibes.isEmpty
        ? const SwapComparisonRow(id: 'vibes', text: kSwapVibesMissing)
        : SwapComparisonRow(id: 'vibes', label: 'Vibes', text: vibes.join(', ')),
    const SwapComparisonRow(id: 'checks', text: kSwapChecksCopy),
    if (option.sponsoredBoostApplied)
      const SwapComparisonRow(id: 'ranking', text: kSwapSponsoredCopy),
  ];
}

/// The comparison panel. Every row is one Text.rich so exact venue-name
/// finders elsewhere in the sheet stay single-match.
class SwapComparisonPanel extends StatelessWidget {
  final TripNode current;
  final VenueSearchResult option;

  /// Null disables Next option.
  final VoidCallback? onNextOption;

  const SwapComparisonPanel({
    super.key,
    required this.current,
    required this.option,
    required this.onNextOption,
  });

  @override
  Widget build(BuildContext context) {
    final rows = swapComparisonRows(current: current, option: option);
    final muted = AppTypography.caption.copyWith(color: AppColors.muted);
    final maxHeight = MediaQuery.sizeOf(context).height * 0.3;

    return Semantics(
      key: const Key('swap_comparison'),
      container: true,
      label: 'Comparison: current stop and option',
      child: Container(
        margin: const EdgeInsets.fromLTRB(
          AppSpacing.base,
          0,
          AppSpacing.base,
          AppSpacing.sm,
        ),
        decoration: BoxDecoration(
          color: AppColors.card,
          border: Border.all(color: AppColors.divider),
          borderRadius: BorderRadius.circular(AppSpacing.radiusChip),
        ),
        // Rows may scroll under the height cap; Next stays pinned below
        // so it stays tappable when Checks or Ranking wrap tall.
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            ConstrainedBox(
              constraints: BoxConstraints(
                maxHeight: (maxHeight - 48).clamp(48.0, maxHeight),
              ),
              child: SingleChildScrollView(
                padding: const EdgeInsets.fromLTRB(
                  AppSpacing.md,
                  AppSpacing.sm,
                  AppSpacing.md,
                  0,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    for (final row in rows)
                      Padding(
                        padding:
                            const EdgeInsets.only(bottom: AppSpacing.xs),
                        child: Text.rich(
                          TextSpan(
                            children: [
                              if (row.label != null)
                                TextSpan(
                                  text: '${row.label}  ',
                                  style: muted,
                                ),
                              TextSpan(
                                text: row.text,
                                style: row.label == null
                                    ? muted
                                    : (row.id == 'now' ||
                                            row.id == 'option'
                                        ? AppTypography.label
                                        : AppTypography.caption),
                              ),
                            ],
                          ),
                          key: Key('swap_comparison_${row.id}'),
                          maxLines: 3,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            Align(
              alignment: Alignment.centerRight,
              child: TextButton(
                key: const Key('swap_next_option'),
                style: TextButton.styleFrom(
                  minimumSize: const Size(0, 44),
                ),
                onPressed: onNextOption,
                child: const Text('Next option'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
