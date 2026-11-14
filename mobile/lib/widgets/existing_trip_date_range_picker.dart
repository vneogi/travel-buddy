import 'package:flutter/material.dart';

/// F3: a small range calendar that marks days already covered by other trips.
///
/// Stock [showDateRangePicker] cannot decorate individual days, so this sheet
/// draws its own month grid (Monday first, fixed, locale-independent).
/// Occupied days carry a small dot under the day number and stay selectable:
/// the marker informs, it never blocks an overlapping trip. Days outside
/// [firstDate]..[lastDate] are dimmed and not selectable.
Future<DateTimeRange?> showExistingTripDateRangePicker({
  required BuildContext context,
  required DateTime firstDate,
  required DateTime lastDate,
  DateTimeRange? initialDateRange,
  Set<DateTime> occupiedDays = const {},
}) {
  return showModalBottomSheet<DateTimeRange>(
    context: context,
    isScrollControlled: true,
    builder: (_) => _RangeSheet(
      firstDate: DateUtils.dateOnly(firstDate),
      lastDate: DateUtils.dateOnly(lastDate),
      initialDateRange: initialDateRange,
      occupiedDays: {for (final d in occupiedDays) DateUtils.dateOnly(d)},
    ),
  );
}

const _monthNames = [
  'January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December',
];
const _weekdayLabels = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

String _iso(DateTime d) =>
    '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

class _RangeSheet extends StatefulWidget {
  final DateTime firstDate;
  final DateTime lastDate;
  final DateTimeRange? initialDateRange;
  final Set<DateTime> occupiedDays;

  const _RangeSheet({
    required this.firstDate,
    required this.lastDate,
    required this.initialDateRange,
    required this.occupiedDays,
  });

  @override
  State<_RangeSheet> createState() => _RangeSheetState();
}

class _RangeSheetState extends State<_RangeSheet> {
  DateTime? _start;
  DateTime? _end;
  late DateTime _month; // first day of the visible month

  @override
  void initState() {
    super.initState();
    final initial = widget.initialDateRange;
    if (initial != null) {
      _start = DateUtils.dateOnly(initial.start);
      _end = DateUtils.dateOnly(initial.end);
    }
    final anchor = _start ?? widget.firstDate;
    _month = DateTime(anchor.year, anchor.month);
  }

  bool _selectable(DateTime d) =>
      !d.isBefore(widget.firstDate) && !d.isAfter(widget.lastDate);

  void _tap(DateTime d) {
    setState(() {
      if (_start == null || _end != null || d.isBefore(_start!)) {
        _start = d;
        _end = null;
      } else {
        _end = d;
      }
    });
  }

  void _shiftMonth(int delta) =>
      setState(() => _month = DateTime(_month.year, _month.month + delta));

  @override
  Widget build(BuildContext context) {
    final canPrev = DateTime(_month.year, _month.month)
        .isAfter(DateTime(widget.firstDate.year, widget.firstDate.month));
    final canNext = DateTime(_month.year, _month.month)
        .isBefore(DateTime(widget.lastDate.year, widget.lastDate.month));
    final complete = _start != null && _end != null;
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Row(
              children: [
                IconButton(
                  key: const Key('picker-prev'),
                  icon: const Icon(Icons.chevron_left),
                  onPressed: canPrev ? () => _shiftMonth(-1) : null,
                ),
                Expanded(
                  child: Text(
                    '${_monthNames[_month.month - 1]} ${_month.year}',
                    key: const Key('picker-month'),
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                ),
                IconButton(
                  key: const Key('picker-next'),
                  icon: const Icon(Icons.chevron_right),
                  onPressed: canNext ? () => _shiftMonth(1) : null,
                ),
              ],
            ),
            Row(
              children: [
                for (final label in _weekdayLabels)
                  Expanded(
                    child: Center(
                      child: Text(label, style: Theme.of(context).textTheme.bodySmall),
                    ),
                  ),
              ],
            ),
            const SizedBox(height: 4),
            ..._weeks(context),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                TextButton(
                  key: const Key('picker-cancel'),
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel'),
                ),
                const SizedBox(width: 8),
                FilledButton(
                  key: const Key('picker-confirm'),
                  onPressed: complete
                      ? () => Navigator.pop(
                            context,
                            DateTimeRange(start: _start!, end: _end!),
                          )
                      : null,
                  child: const Text('Confirm'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  List<Widget> _weeks(BuildContext context) {
    final leading = _month.weekday - 1; // Monday first
    final daysInMonth = DateTime(_month.year, _month.month + 1, 0).day;
    final cells = <DateTime?>[
      for (var i = 0; i < leading; i++) null,
      for (var d = 1; d <= daysInMonth; d++) DateTime(_month.year, _month.month, d),
    ];
    while (cells.length % 7 != 0) {
      cells.add(null);
    }
    return [
      for (var row = 0; row < cells.length ~/ 7; row++)
        Row(
          children: [
            for (final day in cells.sublist(row * 7, row * 7 + 7))
              Expanded(child: day == null ? const SizedBox(height: 44) : _dayCell(context, day)),
          ],
        ),
    ];
  }

  Widget _dayCell(BuildContext context, DateTime day) {
    final scheme = Theme.of(context).colorScheme;
    final selectable = _selectable(day);
    final isEndpoint = day == _start || day == _end;
    final inRange =
        _start != null && _end != null && day.isAfter(_start!) && day.isBefore(_end!);
    final occupied = widget.occupiedDays.contains(day);
    final textColor = !selectable
        ? Theme.of(context).disabledColor
        : isEndpoint
            ? scheme.onPrimary
            : scheme.onSurface;
    return InkWell(
      key: Key('day-${_iso(day)}'),
      onTap: selectable ? () => _tap(day) : null,
      customBorder: const CircleBorder(),
      child: SizedBox(
        height: 44,
        child: Container(
          margin: const EdgeInsets.all(2),
          decoration: BoxDecoration(
            color: isEndpoint
                ? scheme.primary
                : inRange
                    ? scheme.primaryContainer
                    : null,
            shape: BoxShape.circle,
          ),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text('${day.day}', style: TextStyle(color: textColor)),
              const SizedBox(height: 2),
              if (occupied)
                Container(
                  key: Key('marker-${_iso(day)}'),
                  width: 4,
                  height: 4,
                  decoration: BoxDecoration(
                    color: isEndpoint ? scheme.onPrimary : scheme.primary,
                    shape: BoxShape.circle,
                  ),
                )
              else
                const SizedBox(height: 4),
            ],
          ),
        ),
      ),
    );
  }
}
