import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../data/models.dart';
import '../features/itinerary/date_scope.dart';
import '../theme/colors.dart';
import '../theme/typography.dart';

/// SPEC-36: Independent date-range form for each corridor city.
///
/// Validation rules (all checked live):
///  - Each segment range: 1 to [maxDaysPerSegment] days inclusive.
///  - Total days across all segments: <= [maxDays].
///  - Segments must not overlap: each starts strictly after the prior ends.
///  - Chronological order: start_i+1 > end_i.
class CorridorDateForm extends StatefulWidget {
  final SupportedCorridor corridor;
  const CorridorDateForm({super.key, required this.corridor});

  @override
  State<CorridorDateForm> createState() => CorridorDateFormState();
}

class CorridorDateFormState extends State<CorridorDateForm> {
  late final List<DateTimeRange> _ranges;
  bool _submitting = false;

  /// Test-only: replace date ranges and rebuild.
  @visibleForTesting
  void setRangesForTest(List<DateTimeRange> ranges) {
    setState(() {
      _ranges.clear();
      _ranges.addAll(ranges);
    });
  }

  @override
  void initState() {
    super.initState();
    // Seed with valid non-overlapping 1-day defaults starting tomorrow.
    final tomorrow = DateUtils.dateOnly(
      DateTime.now().add(const Duration(days: 1)),
    );
    _ranges = [];
    var cursor = tomorrow;
    for (var i = 0; i < widget.corridor.geoRegions.length; i++) {
      _ranges.add(DateTimeRange(start: cursor, end: cursor));
      cursor = cursor.add(const Duration(days: 2)); // 1-day gap
    }
  }

  String? _validate() {
    final maxPer = widget.corridor.maxDaysPerSegment;
    final maxTotal = widget.corridor.maxDays;
    var totalDays = 0;
    for (var i = 0; i < _ranges.length; i++) {
      final r = _ranges[i];
      final days = r.end.difference(r.start).inDays + 1;
      if (days < 1) return 'Each city needs at least 1 day.';
      if (days > maxPer) {
        return '${widget.corridor.geoRegions[i]} exceeds $maxPer days.';
      }
      totalDays += days;
      if (i > 0) {
        final prev = _ranges[i - 1];
        if (!r.start.isAfter(prev.end)) {
          return 'Dates overlap or are out of order.';
        }
      }
    }
    if (totalDays > maxTotal) {
      return 'Total $totalDays days exceeds the $maxTotal-day limit.';
    }
    return null;
  }

  String _fmt(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _pickRange(int index) async {
    final initial = _ranges[index];
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
      initialDateRange: initial,
    );
    if (picked != null && mounted) {
      setState(() => _ranges[index] = picked);
    }
  }

  void _submit() {
    if (_submitting || _validate() != null) return;
    setState(() => _submitting = true);
    final segments = <TripSegment>[];
    for (var i = 0; i < _ranges.length; i++) {
      segments.add(TripSegment(
        geoRegion: widget.corridor.geoRegions[i],
        startsOn: _fmt(_ranges[i].start),
        endsOn: _fmt(_ranges[i].end),
      ));
    }
    Navigator.pop(context, segments);
  }

  @override
  Widget build(BuildContext context) {
    final error = _validate();
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 16,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Create ${widget.corridor.displayName}',
              style: AppTypography.h2,
            ),
            const SizedBox(height: 4),
            Text(
              'Pick dates for each city (max ${widget.corridor.maxDaysPerSegment} days each, '
              '${widget.corridor.maxDays} total).',
              style: AppTypography.caption,
            ),
            const SizedBox(height: 16),
            for (var i = 0; i < widget.corridor.geoRegions.length; i++) ...[
              _CityDateRow(
                region: widget.corridor.geoRegions[i],
                range: _ranges[i],
                onTap: () => _pickRange(i),
              ),
              if (i < widget.corridor.geoRegions.length - 1)
                const SizedBox(height: 8),
            ],
            if (error != null) ...[
              const SizedBox(height: 12),
              Text(
                error,
                style: AppTypography.caption.copyWith(color: AppColors.danger),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: error == null && !_submitting ? _submit : null,
              child: _submitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Text('Create Laos corridor'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CityDateRow extends StatelessWidget {
  final String region;
  final DateTimeRange range;
  final VoidCallback onTap;

  const _CityDateRow({
    required this.region,
    required this.range,
    required this.onTap,
  });

  String _label(DateTime d) =>
      '${d.day}/${d.month}/${d.year}';

  @override
  Widget build(BuildContext context) {
    final days = range.end.difference(range.start).inDays + 1;
    final display = regionDisplayNames[region] ?? region;
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        child: Row(
          children: [
            SizedBox(
              width: 100,
              child: Text(display, style: AppTypography.body),
            ),
            Expanded(
              child: Text(
                '${_label(range.start)} - ${_label(range.end)}  ($days d)',
                style: AppTypography.bodyMedium,
              ),
            ),
            const Icon(Icons.calendar_today, size: 18),
          ],
        ),
      ),
    );
  }
}
