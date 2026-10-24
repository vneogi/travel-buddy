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

/// What the empty-day sheet pops on confirm.
abstract class EmptyDayAddChoice {
  String get venueName;
  Map<String, dynamic> toPreferences();
}

/// Traveller-stated stay lengths for a place not in the catalog.
const kUncataloguedDwellChoices = <int>[15, 30, 45, 60, 90, 120];

/// SPEC-42 trip-private Add: no venue_id, no client timestamp.
class UncataloguedAddChoice implements EmptyDayAddChoice {
  final String name;
  final String targetDate;
  final String targetSlot;
  final int dwellMinutes;
  final String? microLocation;
  const UncataloguedAddChoice({
    required this.name,
    required this.targetDate,
    required this.targetSlot,
    required this.dwellMinutes,
    this.microLocation,
  });

  @override
  String get venueName => name;

  @override
  Map<String, dynamic> toPreferences() => {
        'mode': 'uncatalogued_add',
        'name': name,
        'target_date': targetDate,
        'target_slot': targetSlot,
        'typical_dwell_minutes': dwellMinutes,
        if (microLocation != null && microLocation!.isNotEmpty)
          'micro_location': microLocation,
      };
}

class DirectAddChoice implements EmptyDayAddChoice {
  final String venueId;
  final String targetDate;
  final String targetSlot;
  @override
  final String venueName;
  const DirectAddChoice({
    required this.venueId,
    required this.targetDate,
    required this.targetSlot,
    required this.venueName,
  });

  @override
  Map<String, dynamic> toPreferences() => {
        'mode': 'direct_add',
        'venue_id': venueId,
        'target_date': targetDate,
        'target_slot': targetSlot,
      };
}

/// Empty-day Add: slot -> server candidates -> explicit confirm.
/// Pops an [EmptyDayAddChoice] on confirm, null on cancel.
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
  // SPEC-42 trip-private path.
  bool _private = false;
  int? _dwell;
  final _nameCtl = TextEditingController();
  final _microCtl = TextEditingController();

  @override
  void dispose() {
    _nameCtl.dispose();
    _microCtl.dispose();
    super.dispose();
  }

  String get _name => _nameCtl.text.trim().split(RegExp(r'\s+')).join(' ');
  bool get _privateReady =>
      _slot != null && _dwell != null && _name.length >= 2 && _name.length <= 80;

  String get _micro => _microCtl.text.trim();

  Widget _privateForm() {
    final slot = _slot!;
    return Column(
      key: const Key('uncatalogued_add_form'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        TextField(
          key: const Key('uncatalogued_add_name'),
          controller: _nameCtl,
          maxLength: 80,
          decoration: const InputDecoration(labelText: 'Place name'),
          onChanged: (_) => setState(() {}),
        ),
        const SizedBox(height: AppSpacing.xs),
        Text('How long will you stay?', style: AppTypography.body),
        Wrap(
          spacing: AppSpacing.xs,
          runSpacing: AppSpacing.xs,
          children: [
            for (final m in kUncataloguedDwellChoices)
              ChoiceChip(
                key: Key('uncatalogued_add_dwell_$m'),
                label: Text('$m min'),
                selected: _dwell == m,
                onSelected: (_) => setState(() => _dwell = m),
              ),
          ],
        ),
        TextField(
          key: const Key('uncatalogued_add_micro'),
          controller: _microCtl,
          decoration: const InputDecoration(labelText: 'Area (optional)'),
          onChanged: (_) => setState(() {}),
        ),
        if (_privateReady) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(
            'Add $_name on ${widget.targetDate} ${directAddSlotLabel(slot)} '
            'for $_dwell min? This place is only on this trip.',
            key: const Key('uncatalogued_add_confirm_copy'),
            style: AppTypography.body,
          ),
        ],
        const SizedBox(height: AppSpacing.base),
        Row(
          children: [
            Expanded(
              child: OutlinedButton(
                key: const Key('uncatalogued_add_cancel'),
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Cancel'),
              ),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: ElevatedButton(
                key: const Key('uncatalogued_add_confirm'),
                onPressed: !_privateReady
                    ? null
                    : () => Navigator.of(context).pop(UncataloguedAddChoice(
                          name: _name,
                          targetDate: widget.targetDate,
                          targetSlot: slot,
                          dwellMinutes: _dwell!,
                          microLocation: _micro.isEmpty ? null : _micro,
                        )),
                child: const Text('Add'),
              ),
            ),
          ],
        ),
      ],
    );
  }

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
            if (_private && _slot != null) _privateForm() else ...[
            _body(),
            if (_slot != null)
              TextButton(
                key: const Key('uncatalogued_add_open'),
                onPressed: () => setState(() {
                  _private = true;
                  _selected = null;
                }),
                child: const Text('Not in the list? Add a place not in the catalog'),
              ),
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
          ],
        ),
      ),
    );
  }
}
