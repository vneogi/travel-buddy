import 'package:flutter/material.dart';

import '../../data/models.dart';
import '../../data/repositories.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';

/// SPEC-42 named slots in day order (mirrors services.day_slots.SLOT_ORDER).
const kDirectAddSlots = <String>[
  'morning_tour',
  'lunch',
  'afternoon_evening_tour',
  'dinner',
];

const _slotLabels = <String, String>{
  'morning_tour': 'Morning',
  'lunch': 'Lunch',
  'afternoon_evening_tour': 'Afternoon',
  'dinner': 'Dinner',
};

String directAddSlotLabel(String slot) => _slotLabels[slot] ?? slot;

/// YYYY-MM-DD for a calendar date (no clock / timezone math).
String directAddIsoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

/// Destination-local HH:MM straight from the server's offset ISO string.
String plannedLocalTime(String plannedStart) =>
    plannedStart.length >= 16 ? plannedStart.substring(11, 16) : plannedStart;

class DirectAddChoice {
  final String venueId;
  final String targetDate;
  final String targetSlot;
  final String venueName;
  const DirectAddChoice({
    required this.venueId,
    required this.targetDate,
    required this.targetSlot,
    required this.venueName,
  });

  Map<String, dynamic> toPreferences() => {
        'mode': 'direct_add',
        'venue_id': venueId,
        'target_date': targetDate,
        'target_slot': targetSlot,
      };
}

/// Empty-day Add: slot -> server candidates -> explicit confirm.
/// Pops a [DirectAddChoice] on confirm, null on cancel.
class DirectAddSheet extends StatefulWidget {
  final String tripId;
  final String targetDate;
  final TripRepository repo;
  const DirectAddSheet({
    super.key,
    required this.tripId,
    required this.targetDate,
    required this.repo,
  });

  @override
  State<DirectAddSheet> createState() => _DirectAddSheetState();
}

class _DirectAddSheetState extends State<DirectAddSheet> {
  String? _slot;
  bool _loading = false;
  bool _error = false;
  AddCandidatesResult? _result;
  AddCandidate? _selected;
  int _request = 0;

  Future<void> _load(String slot) async {
    final request = ++_request;
    setState(() {
      _slot = slot;
      _loading = true;
      _error = false;
      _result = null;
      _selected = null;
    });
    try {
      final result = await widget.repo.addCandidates(
        tripId: widget.tripId,
        targetDate: widget.targetDate,
        targetSlot: slot,
      );
      if (!mounted || request != _request) return;
      setState(() {
        _result = result;
        _loading = false;
      });
    } catch (_) {
      if (!mounted || request != _request) return;
      setState(() {
        _error = true;
        _loading = false;
      });
    }
  }

  Widget _body() {
    if (_slot == null) {
      return Text('Pick a slot to see places that fit.', style: AppTypography.body);
    }
    if (_loading) {
      return const Padding(
        key: Key('direct_add_loading'),
        padding: EdgeInsets.all(AppSpacing.base),
        child: Center(child: CircularProgressIndicator()),
      );
    }
    if (_error) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text("Couldn't load places. Check your connection.",
              key: const Key('direct_add_error'), style: AppTypography.body),
          TextButton(
            key: const Key('direct_add_retry'),
            onPressed: () => _load(_slot!),
            child: const Text('Retry'),
          ),
        ],
      );
    }
    final result = _result;
    if (result == null) return const SizedBox.shrink();
    if (result.candidates.isEmpty) {
      return Text(
        result.refusalCopy ?? 'No catalog places fit that slot on this day.',
        key: const Key('direct_add_refusal'),
        style: AppTypography.body,
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final c in result.candidates)
          ListTile(
            key: Key('direct_add_candidate_${c.venueId}'),
            selected: _selected?.venueId == c.venueId,
            title: Text(c.name),
            subtitle: Text([
              if (c.microLocation != null && c.microLocation!.isNotEmpty) c.microLocation!,
              plannedLocalTime(c.plannedStart),
              '${c.typicalDwellMinutes} min',
            ].join(' \u00b7 ')),
            onTap: () => setState(() => _selected = c),
          ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final selected = _selected;
    return SafeArea(
      key: const Key('direct_add_sheet_v1'),
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.base),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Add activity', style: AppTypography.h2),
            const SizedBox(height: AppSpacing.sm),
            Wrap(
              spacing: AppSpacing.xs,
              runSpacing: AppSpacing.xs,
              children: [
                for (final s in kDirectAddSlots)
                  ChoiceChip(
                    key: Key('direct_add_slot_$s'),
                    label: Text(directAddSlotLabel(s)),
                    selected: _slot == s,
                    onSelected: (_) => _load(s),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            _body(),
            if (selected != null && _slot != null) ...[
              const SizedBox(height: AppSpacing.sm),
              Text(
                'Add ${selected.name} on ${widget.targetDate} '
                '${directAddSlotLabel(_slot!)} at '
                '${plannedLocalTime(selected.plannedStart)} '
                'for ${selected.typicalDwellMinutes} min?',
                key: const Key('direct_add_confirm_copy'),
                style: AppTypography.body,
              ),
            ],
            const SizedBox(height: AppSpacing.base),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    key: const Key('direct_add_cancel'),
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: AppSpacing.sm),
                Expanded(
                  child: ElevatedButton(
                    key: const Key('direct_add_confirm'),
                    onPressed: (selected == null || _slot == null)
                        ? null
                        : () => Navigator.of(context).pop(DirectAddChoice(
                              venueId: selected.venueId,
                              targetDate: widget.targetDate,
                              targetSlot: _slot!,
                              venueName: selected.name,
                            )),
                    child: const Text('Add'),
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
