// SPEC-10 HITL reflow: "Adjust this day" sheet shown after a booking save
// when the booking squeezes flexible stops. The would-skip preview is
// computed client-side from the proposal and the same intent table the
// server applies on confirm. Nothing changes until Confirm.

import 'package:flutter/material.dart';

import '../../core/destination_tz.dart' show toDestinationLocal;
import '../../data/models.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';

const _slotOrder = ['morning_tour', 'lunch', 'afternoon_evening_tour', 'dinner'];
const _eveningSlots = ['afternoon_evening_tour', 'dinner'];

// Same slot labels as the Move and Add sheets.
const _slotLabels = <String, String>{
  'morning_tour': 'Morning',
  'lunch': 'Lunch',
  'afternoon_evening_tour': 'Afternoon',
  'dinner': 'Dinner',
};

const _intentLabels = <String, String>{
  'conservative': 'Lighter day',
  'restore_evening': 'Show and dinner',
  'restore_morning': 'Keep the morning',
  'keep_open': 'Keep it open',
};

/// Day kind for intent scoping (mirrors services/booking_reflow.py).
enum ReflowDayKind { arrival, morning, other }

String _dateKey(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// Arrival: flight/train at 14:00 or later, or the hotel check-in day at
/// 14:00 or later. Morning: early flight/train or a listed hotel checkout.
ReflowDayKind reflowDayKind(TripNode? booking, String localDate) {
  if (booking == null) return ReflowDayKind.other;
  final start = toDestinationLocal(booking.scheduledStart, booking.geoRegion);
  final type = booking.bookingType;
  if (type == 'hotel') {
    if (_dateKey(start) == localDate) {
      return start.hour >= 14 ? ReflowDayKind.arrival : ReflowDayKind.other;
    }
    return ReflowDayKind.morning;
  }
  final travel = type == 'flight' || type == 'train';
  if (travel && start.hour >= 14) return ReflowDayKind.arrival;
  if (travel && start.hour < 12) return ReflowDayKind.morning;
  return ReflowDayKind.other;
}

/// Remaining slots on [day] for [intent].
List<String> reflowRemaining(
  String intent,
  BookingReflowDay day,
  ReflowDayKind kind,
) {
  final conservative = day.conservativeSlots;
  switch (intent) {
    case 'restore_evening':
      return kind == ReflowDayKind.arrival ? _eveningSlots : conservative;
    case 'restore_morning':
      if (kind != ReflowDayKind.morning || conservative.contains('morning_tour')) {
        return conservative;
      }
      return _slotOrder
          .where((s) => s == 'morning_tour' || conservative.contains(s))
          .toList();
    case 'keep_open':
      return const [];
    default:
      return conservative;
  }
}

bool _isFlexible(TripNode n) =>
    !n.isLocked &&
    n.nodeKind != 'booking' &&
    n.status != NodeStatus.skipped &&
    n.status != NodeStatus.completed &&
    (n.slotName?.isNotEmpty ?? false);

/// Flexible nodes the chosen [intent] would skip, in itinerary order.
List<TripNode> reflowWouldSkip(
  BookingReflow reflow,
  List<TripNode> nodes,
  String intent,
) {
  final booking =
      nodes.where((n) => n.nodeId == reflow.bookingNodeId).firstOrNull;
  final out = <TripNode>[];
  for (final day in reflow.days) {
    final remaining =
        reflowRemaining(intent, day, reflowDayKind(booking, day.localDate));
    for (final n in nodes) {
      if (!_isFlexible(n)) continue;
      final local = toDestinationLocal(n.scheduledStart, n.geoRegion);
      if (_dateKey(local) != day.localDate) continue;
      if (!remaining.contains(n.slotName)) out.add(n);
    }
  }
  return out;
}

class BookingReflowSheet extends StatefulWidget {
  final BookingReflow reflow;
  final List<TripNode> nodes;
  final Future<void> Function(String intent) onConfirm;

  const BookingReflowSheet({
    super.key,
    required this.reflow,
    required this.nodes,
    required this.onConfirm,
  });

  @override
  State<BookingReflowSheet> createState() => _BookingReflowSheetState();
}

class _BookingReflowSheetState extends State<BookingReflowSheet> {
  late String _intent;
  bool _sending = false;

  @override
  void initState() {
    super.initState();
    final reflow = widget.reflow;
    _intent = reflow.intents.contains(reflow.defaultIntent)
        ? reflow.defaultIntent
        : reflow.intents.first;
  }

  String _summary() {
    final booking = widget.nodes
        .where((n) => n.nodeId == widget.reflow.bookingNodeId)
        .firstOrNull;
    final parts = <String>[];
    for (final day in widget.reflow.days) {
      final remaining = reflowRemaining(
        widget.reflow.defaultIntent,
        day,
        reflowDayKind(booking, day.localDate),
      );
      final labels = remaining.map((s) => _slotLabels[s] ?? s).join(', ');
      final shown = labels.isEmpty ? 'Nothing planned' : labels;
      parts.add('${day.localDate}: $shown');
    }
    return parts.join('; ');
  }

  Future<void> _confirm() async {
    setState(() => _sending = true);
    await widget.onConfirm(widget.reflow.defaultIntent); // R17b sabotage
    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final skip = reflowWouldSkip(widget.reflow, widget.nodes, _intent);
    return SafeArea(
      child: Padding(
        key: const Key('booking_reflow_sheet'),
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Adjust this day', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.sm),
              Text(_summary(), style: AppTypography.body),
              const SizedBox(height: AppSpacing.base),
              Wrap(
                spacing: AppSpacing.sm,
                runSpacing: AppSpacing.sm,
                children: [
                  for (final intent in widget.reflow.intents)
                    ChoiceChip(
                      key: Key('booking_reflow_intent_$intent'),
                      label: Text(_intentLabels[intent] ?? intent),
                      selected: _intent == intent,
                      onSelected: _sending
                          ? null
                          : (_) => setState(() => _intent = intent),
                    ),
                ],
              ),
              const SizedBox(height: AppSpacing.base),
              Text(
                skip.isEmpty ? 'Nothing would be skipped' : 'Would be skipped',
                style: AppTypography.label,
              ),
              for (final node in skip)
                Padding(
                  padding: const EdgeInsets.only(top: AppSpacing.xs),
                  child: Text(
                    node.venueName,
                    key: Key('booking_reflow_skip_${node.nodeId}'),
                    style: AppTypography.body,
                  ),
                ),
              const SizedBox(height: AppSpacing.lg),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    key: const Key('booking_reflow_dismiss'),
                    onPressed: _sending ? null : () => Navigator.of(context).pop(),
                    child: const Text('Not now'),
                  ),
                  const SizedBox(width: AppSpacing.sm),
                  FilledButton(
                    key: const Key('booking_reflow_confirm'),
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
