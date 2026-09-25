// SPEC-45 R2: Production warning helpers.
//
// Public so that tests can directly exercise the same code path
// used by _ScheduleWarningsBanner inside ItineraryScreen.

import 'package:flutter/material.dart';
import '../../core/destination_tz.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';

/// Extract a single-quoted venue name from the start of a warning string.
/// e.g. "'Joma Bakery' is closed..." -> "Joma Bakery"
String? extractQuotedVenue(String warning) {
  final match = RegExp(r"^'([^']+)'").firstMatch(warning);
  return match?.group(1);
}

/// Match a quoted venue name to a TripNode by exact venueName.
TripNode? matchWarningToNode(String warning, List<TripNode> nodes) {
  final venue = extractQuotedVenue(warning);
  if (venue == null) return null;
  for (final node in nodes) {
    if (node.venueName == venue) return node;
  }
  return null;
}

/// Format a destination-local date as "Fri, 2 Oct".
String warningLocalDate(TripNode node) {
  final local = toDestinationLocal(node.scheduledStart, node.geoRegion);
  const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];
  return '${weekdays[local.weekday - 1]}, ${local.day} ${months[local.month - 1]}';
}

/// A single warning row. Shows:
/// - Matched node: venue name (bold), destination-local date, reason,
///   and "Open stop" which fires [onFocusNode] with the node ID.
/// - Unmatched: the raw warning text and "Dismiss" which fires [onDismiss].
class WarningRow extends StatelessWidget {
  final String warning;
  final List<TripNode> nodes;
  final void Function(String nodeId)? onFocusNode;
  final VoidCallback? onDismiss;

  const WarningRow({
    super.key,
    required this.warning,
    required this.nodes,
    this.onFocusNode,
    this.onDismiss,
  });

  @override
  Widget build(BuildContext context) {
    final matchedNode = matchWarningToNode(warning, nodes);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(top: 2, right: 8),
          child: Icon(
            Icons.warning_amber_rounded,
            size: 16,
            color: AppColors.accent,
          ),
        ),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (matchedNode != null) ...[
                Text(
                  matchedNode.venueName,
                  style: AppTypography.body.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  warningLocalDate(matchedNode),
                  style: AppTypography.caption.copyWith(
                    color: AppColors.muted,
                  ),
                ),
              ],
              Text(warning, style: AppTypography.body),
            ],
          ),
        ),
        // Action: Open stop (focus) or Dismiss.
        SizedBox(
          height: 44,
          child: matchedNode != null && onFocusNode != null
              ? TextButton(
                  onPressed: () => onFocusNode!(matchedNode.nodeId),
                  child: const Text('Open stop'),
                )
              : TextButton(
                  // Unmatched: dismiss clears all schedule warnings.
                  onPressed: onDismiss,
                  child: const Text('Dismiss'),
                ),
        ),
      ],
    );
  }
}
