import 'package:flutter/material.dart';

import '../../core/destination_tz.dart';
import '../../data/models.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';

/// SPEC-42 named slots, in day order (mirrors services.day_slots.SLOT_ORDER).
const kMoveSlotOrder = <String>[
  'morning_tour',
  'lunch',
  'afternoon_evening_tour',
  'dinner',
];

const _foodSlots = {'lunch', 'dinner'};
const _activitySlots = {'morning_tour', 'afternoon_evening_tour'};

const _slotLabels = <String, String>{
  'morning_tour': 'Morning',
  'lunch': 'Lunch',
  'afternoon_evening_tour': 'Afternoon',
  'dinner': 'Dinner',
};

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String moveSlotLabel(String? slot) => _slotLabels[slot] ?? 'Unslotted';

String _iso(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

String moveDateLabel(String iso) {
  final d = DateTime.parse(iso);
  return '${_weekdays[d.weekday - 1]} ${d.day} ${_months[d.month - 1]}';
}

String _localIso(TripNode n) {
  final l = toDestinationLocal(n.scheduledStart, n.geoRegion);
  return _iso(DateTime(l.year, l.month, l.day));
}

/// True for cards that may offer Move: unlocked, non-booking, pending/active.
bool nodeIsMovable(TripNode node) =>
    !node.isLocked &&
    node.nodeKind != 'booking' &&
    (node.status == NodeStatus.pending || node.status == NodeStatus.active);

class MoveOptions {
  final List<String> dates;
  final List<String> slots;
  final String sourceDate;
  final String? sourceSlot;
  const MoveOptions({
    required this.dates,
    required this.slots,
    required this.sourceDate,
    required this.sourceSlot,
  });
}

class MoveChoice {
  final String targetDate;
  final String targetSlot;
  const MoveChoice(this.targetDate, this.targetSlot);

  Map<String, dynamic> toPreferences() => {
        'mode': 'move',
        'target_date': targetDate,
        'target_slot': targetSlot,
      };
}

/// Dates and slots the picker offers. The server re-checks every rule.
MoveOptions moveOptionsFor({
  required TripNode node,
  required List<TripNode> nodes,
  required List<TripSegment> segments,
  CreationContext? creationContext,
}) {
  DateTime? start;
  DateTime? end;
  final cc = creationContext;
  final ccStart = cc?.startDateLocal;
  final ccEnd = cc?.endDateLocal;
  if (ccStart != null && ccEnd != null) {
    start = DateTime.tryParse(ccStart);
    end = DateTime.tryParse(ccEnd);
  }
  if ((start == null || end == null) && segments.isNotEmpty) {
    final starts = segments.map((s) => DateTime.parse(s.startsOn)).toList()..sort();
    final ends = segments.map((s) => DateTime.parse(s.endsOn)).toList()..sort();
    start = starts.first;
    end = ends.last;
  }
  if (start == null || end == null) {
    final ds = nodes.map((n) => DateTime.parse(_localIso(n))).toList()..sort();
    if (ds.isNotEmpty) {
      start = ds.first;
      end = ds.last;
    }
  }

  final dates = <String>[];
  if (start != null && end != null) {
    for (var d = start; !d.isAfter(end); d = DateTime(d.year, d.month, d.day + 1)) {
      dates.add(_iso(d));
    }
  }

  final regions = <String>{
    for (final s in segments) s.geoRegion,
    for (final n in nodes)
      if (n.geoRegion != null) n.geoRegion!,
  };
  final filtered = regions.length > 1
      ? dates
          .where((d) => nodes.any(
              (n) => n.geoRegion == node.geoRegion && _localIso(n) == d))
          .toList()
      : dates;

  final slot = node.slotName;
  final slots = _foodSlots.contains(slot)
      ? kMoveSlotOrder.where(_foodSlots.contains).toList()
      : _activitySlots.contains(slot)
          ? kMoveSlotOrder.where(_activitySlots.contains).toList()
          : List<String>.of(kMoveSlotOrder);

  return MoveOptions(
    dates: filtered,
    slots: slots,
    sourceDate: _localIso(node),
    sourceSlot: slot,
  );
}

/// SPEC-42 Move picker. Pops a [MoveChoice] on confirm, null on cancel.
class MoveSheet extends StatefulWidget {
  final TripNode node;
  final MoveOptions options;
  const MoveSheet({super.key, required this.node, required this.options});

  @override
  State<MoveSheet> createState() => _MoveSheetState();
}

class _MoveSheetState extends State<MoveSheet> {
  String? _date;
  String? _slot;

  bool get _isNoop =>
      _date == widget.options.sourceDate && _slot == widget.options.sourceSlot;

  @override
  Widget build(BuildContext context) {
    final o = widget.options;
    final ready = _date != null && _slot != null && !_isNoop;
    return SafeArea(
      key: const Key('move_sheet_v1'),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.base),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Move ${widget.node.venueName}', style: AppTypography.h2),
            const SizedBox(height: AppSpacing.sm),
            Text('Date', style: AppTypography.label),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                for (final d in o.dates)
                  ChoiceChip(
                    key: Key('move_date_$d'),
                    label: Text(moveDateLabel(d)),
                    selected: _date == d,
                    onSelected: (_) => setState(() => _date = d),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text('Slot', style: AppTypography.label),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                for (final s in o.slots)
                  ChoiceChip(
                    key: Key('move_slot_$s'),
                    label: Text(moveSlotLabel(s)),
                    selected: _slot == s,
                    onSelected: (_) => setState(() => _slot = s),
                  ),
              ],
            ),
            if (_date != null && _slot != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                _isNoop
                    ? '${widget.node.venueName} is already there.'
                    : 'Move ${widget.node.venueName} from '
                        '${moveDateLabel(o.sourceDate)} ${moveSlotLabel(o.sourceSlot)} '
                        'to ${moveDateLabel(_date!)} ${moveSlotLabel(_slot)}?',
                key: const Key('move_confirm_copy'),
                style: AppTypography.body,
              ),
            ],
            const SizedBox(height: AppSpacing.base),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    key: const Key('move_cancel'),
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: ElevatedButton(
                    key: const Key('move_confirm'),
                    onPressed: ready
                        ? () => Navigator.of(context).pop(MoveChoice(_date!, _slot!))
                        : null,
                    child: const Text('Move'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
