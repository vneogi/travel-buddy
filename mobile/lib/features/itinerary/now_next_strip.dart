import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/destination_tz.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import 'current_window.dart';

/// SPEC-48 slice 1: compact NOW / UP NEXT strip at the top of the
/// itinerary. Pure selection from the node list; no network, no cache read.

typedef GlanceStops = ({TripNode? now, TripNode? next});

/// Clock for the strip. Tests override it.
final glanceClockProvider =
    Provider<DateTime Function()>((ref) => () => DateTime.now().toUtc());

bool _isHotelStay(TripNode node) =>
    node.nodeKind == 'booking' && node.bookingType == 'hotel';

/// Pick the current stop and the next stop.
///
/// Completed and skipped stops are ignored. Input order is not assumed:
/// stops are ordered by scheduledStart, ties by original list order.
/// A hotel stay is never `now` (its window spans the stay) but its
/// check-in can be `next`.
GlanceStops glanceStops(List<TripNode> nodes, DateTime nowUtc) {
  final now = nowUtc.toUtc();
  final ordered = <({int index, TripNode node})>[
    for (var i = 0; i < nodes.length; i++)
      if (nodes[i].status != NodeStatus.completed &&
          nodes[i].status != NodeStatus.skipped)
        (index: i, node: nodes[i]),
  ]..sort((a, b) {
      final byStart = a.node.scheduledStart.compareTo(b.node.scheduledStart);
      return byStart != 0 ? byStart : a.index.compareTo(b.index);
    });

  TripNode? current;
  for (final entry in ordered) {
    if (!_isHotelStay(entry.node) && nodeIsCurrentWindow(entry.node, now)) {
      current = entry.node;
      break;
    }
  }

  TripNode? next;
  for (final entry in ordered) {
    if (identical(entry.node, current)) continue;
    if (entry.node.scheduledStart.isAfter(now)) {
      next = entry.node;
      break;
    }
  }
  return (now: current, next: next);
}

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec',
];

/// `until HH:MM`: end of the stop in destination-local time.
String glanceNowTime(TripNode node) {
  final end = node.scheduledStart.add(Duration(minutes: node.durationMinutes));
  return 'until ${formatDestinationTime(end, node.geoRegion)}';
}

/// `HH:MM` when the stop is on the same destination-local day as
/// [nowUtc]; otherwise `Www D Mmm, HH:MM`.
String glanceNextTime(TripNode node, DateTime nowUtc) {
  final start = toDestinationLocal(node.scheduledStart, node.geoRegion);
  final today = toDestinationLocal(nowUtc, node.geoRegion);
  final time = formatDestinationTime(node.scheduledStart, node.geoRegion);
  final sameDay = start.year == today.year &&
      start.month == today.month &&
      start.day == today.day;
  if (sameDay) return time;
  return '${_weekdays[start.weekday - 1]} ${start.day} '
      '${_months[start.month - 1]}, $time';
}

/// The strip. Renders nothing when there is no current or next stop.
class NowNextStrip extends ConsumerStatefulWidget {
  final List<TripNode> nodes;
  final ValueChanged<String> onFocusNode;

  const NowNextStrip({
    super.key,
    required this.nodes,
    required this.onFocusNode,
  });

  @override
  ConsumerState<NowNextStrip> createState() => _NowNextStripState();
}

class _NowNextStripState extends ConsumerState<NowNextStrip>
    with WidgetsBindingObserver {
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _ticker = Timer.periodic(const Duration(minutes: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _ticker?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final nowUtc = ref.watch(glanceClockProvider)();
    final stops = glanceStops(widget.nodes, nowUtc);
    final current = stops.now;
    final next = stops.next;
    if (current == null && next == null) return const SizedBox.shrink();

    return Column(
      key: const Key('glance_strip'),
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (current != null)
          _row(
            key: const Key('glance_now_row'),
            node: current,
            badge: 'NOW',
            badgeColor: AppColors.accent,
            badgeTextColor: Colors.white,
            time: glanceNowTime(current),
            semanticsLabel:
                'Now: ${current.venueName}, ${glanceNowTime(current)}',
          ),
        if (next != null)
          _row(
            key: const Key('glance_next_row'),
            node: next,
            badge: 'UP NEXT',
            badgeColor: AppColors.primaryLight,
            badgeTextColor: AppColors.primaryDark,
            time: glanceNextTime(next, nowUtc),
            semanticsLabel:
                'Up next: ${next.venueName}, ${glanceNextTime(next, nowUtc)}',
          ),
      ],
    );
  }

  Widget _row({
    required Key key,
    required TripNode node,
    required String badge,
    required Color badgeColor,
    required Color badgeTextColor,
    required String time,
    required String semanticsLabel,
  }) {
    void onTap() => widget.onFocusNode(node.nodeId);
    return Semantics(
      key: key,
      container: true,
      button: true,
      label: semanticsLabel,
      excludeSemantics: true,
      onTap: onTap,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 44),
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppSpacing.base,
              vertical: AppSpacing.xs,
            ),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 6,
                    vertical: 2,
                  ),
                  decoration: BoxDecoration(
                    color: badgeColor,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    badge,
                    style: AppTypography.caption.copyWith(
                      color: badgeTextColor,
                      fontWeight: FontWeight.w700,
                      fontSize: 10,
                    ),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: Text.rich(
                    TextSpan(
                      children: [
                        TextSpan(
                          text: node.venueName,
                          style: AppTypography.label,
                        ),
                        TextSpan(
                          text: '  $time',
                          style: AppTypography.caption
                              .copyWith(color: AppColors.muted),
                        ),
                      ],
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
