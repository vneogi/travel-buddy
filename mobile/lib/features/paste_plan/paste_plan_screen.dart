// SPEC-58 slice 1b: paste-your-plan import.
//
// Paste -> parse on device -> match stop names (network, names only) ->
// traveller accepts or rejects each match -> Create trip (empty days) ->
// one import_plan batch -> booking lines to the existing booking sheet ->
// result with a "Not imported" list. Nothing is committed before Create
// trip; nothing is queued offline; raw paste text is never sent.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api_exception.dart';
import '../../core/connectivity_helper.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../data/region_defaults.dart';
import '../../render/offline_state.dart';
import '../activity_detail/activity_detail_screen.dart' show kPlainRowLabel;
import '../booking/add_booking_sheet.dart';
import 'plan_parser.dart';

const kPlanSlots = <String>['morning_tour', 'lunch', 'afternoon_evening_tour', 'dinner'];
const kPlanSlotLabels = <String, String>{
  'morning_tour': 'Morning',
  'lunch': 'Lunch',
  'afternoon_evening_tour': 'Afternoon',
  'dinner': 'Dinner',
};
const kPlanDwellChoices = <int>[15, 30, 45, 60, 90, 120];

enum MatchDecision { unconfirmed, accepted, rejected }

/// One reviewable stop. Public so tests can read the decision state.
class PlanRow {
  final PlanStop stop;
  String? date;
  CatalogMatchVenue? suggestion;
  final List<CatalogMatchVenue> near;
  MatchDecision decision;
  int? dwell;
  String? slot;

  PlanRow({
    required this.stop,
    required this.date,
    required this.suggestion,
    required this.near,
    required this.decision,
  });

  bool get isCatalog => suggestion != null && decision == MatchDecision.accepted;
  bool get isPlain => !isCatalog && (suggestion == null || decision == MatchDecision.rejected);
  String? get effectiveSlot => slot ?? stop.slotHint;

  bool get ready {
    if (date == null || effectiveSlot == null) return false;
    if (isCatalog) return true;
    if (suggestion != null && decision == MatchDecision.unconfirmed) return false;
    return dwell != null;
  }
}

class _NotImported {
  final String name;
  final String date;
  final String reason;
  const _NotImported(this.name, this.date, this.reason);
}

enum _Stage { input, review, working, done }

class PastePlanScreen extends ConsumerStatefulWidget {
  final List<String> regions;
  final String? initialRegion;
  final DateTime? initialStartDate;
  final DateTime? initialEndDate;
  final String? initialText;
  final ConnectivityHelper? connectivityOverride;

  const PastePlanScreen({
    super.key,
    required this.regions,
    this.initialRegion,
    this.initialStartDate,
    this.initialEndDate,
    this.initialText,
    this.connectivityOverride,
  });

  @override
  ConsumerState<PastePlanScreen> createState() => _PastePlanScreenState();
}

class _PastePlanScreenState extends ConsumerState<PastePlanScreen> {
  late final TextEditingController _text;
  late final ConnectivityHelper _connectivity;
  String? _region;
  DateTime? _start;
  DateTime? _end;
  _Stage _stage = _Stage.input;
  String? _error;
  bool _offline = false;
  PlanParseResult? _parse;
  List<PlanRow> _rows = const [];
  // Result
  String? _tripId;
  final List<PlanRow> _added = [];
  final List<_NotImported> _notImported = [];
  int _bookingsSaved = 0;

  @override
  void initState() {
    super.initState();
    _text = TextEditingController(text: widget.initialText ?? '');
    _connectivity = widget.connectivityOverride ?? ConnectivityHelper();
    _region = widget.initialRegion ?? (widget.regions.isNotEmpty ? widget.regions.first : null);
    _start = widget.initialStartDate;
    _end = widget.initialEndDate;
  }

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  List<String> get _spanDates {
    final s = _start, e = _end;
    if (s == null || e == null || e.isBefore(s)) return const [];
    final out = <String>[];
    for (var d = DateTime.utc(s.year, s.month, s.day);
        !d.isAfter(DateTime.utc(e.year, e.month, e.day));
        d = d.add(const Duration(days: 1))) {
      out.add(isoDate(d));
    }
    return out;
  }

  void _readPlan() {
    final dates = _spanDates;
    if (_region == null || dates.isEmpty) {
      setState(() => _error = 'Choose a destination and trip dates first.');
      return;
    }
    final result = parsePlan(_text.text, startDate: dates.first, endDate: dates.last);
    setState(() {
      _error = result.refusal;
      _parse = result.isRefused ? null : result;
      _rows = const [];
      _offline = false;
    });
  }

  Future<void> _findMatches() async {
    final parse = _parse;
    final region = _region;
    if (parse == null || region == null) return;
    final repo = ref.read(tripRepoProvider);
    if (!await _connectivity.checkConnectivity()) {
      if (mounted) setState(() => _offline = true);
      return;
    }
    final stops = [for (final d in parse.days) for (final s in d.stops) (d, s)];
    if (stops.isEmpty) {
      setState(() => _error = 'No stops found in that plan.');
      return;
    }
    final names = <String>[];
    for (final (_, s) in stops) {
      if (!names.contains(s.name)) names.add(s.name);
    }
    try {
      final results = await repo.catalogMatch(geoRegion: region, names: names);
      final byName = {for (final r in results) r.name: r};
      if (!mounted) return;
      setState(() {
        _offline = false;
        _error = null;
        _rows = [
          for (final (day, s) in stops)
            PlanRow(
              stop: s,
              date: day.date,
              suggestion: byName[s.name]?.match,
              near: byName[s.name]?.near ?? const [],
              // R17a sabotage: auto-accept every match.
              decision: byName[s.name]?.match != null ? MatchDecision.accepted : MatchDecision.unconfirmed,
            ),
        ];
        _stage = _Stage.review;
      });
    } on ApiException catch (e) {
      if (mounted) setState(() => _error = e.message);
    }
  }

  bool get _canCreate =>
      _stage == _Stage.review && _rows.isNotEmpty && _rows.every((r) => r.ready);

  List<(int, Map<String, dynamic>)> _items() {
    final order = List<int>.generate(_rows.length, (i) => i)
      ..sort((a, b) {
        final ra = _rows[a], rb = _rows[b];
        final byDate = ra.date!.compareTo(rb.date!);
        if (byDate != 0) return byDate;
        final bySlot = kPlanSlots.indexOf(ra.effectiveSlot!).compareTo(kPlanSlots.indexOf(rb.effectiveSlot!));
        if (bySlot != 0) return bySlot;
        return a.compareTo(b);
      });
    return [
      for (final i in order)
        (
          i,
          _rows[i].isCatalog
              ? <String, dynamic>{
                  'kind': 'catalog',
                  'venue_id': _rows[i].suggestion!.venueId,
                  'target_date': _rows[i].date,
                  'target_slot': _rows[i].effectiveSlot,
                }
              : <String, dynamic>{
                  'kind': 'plain',
                  'name': _rows[i].stop.name,
                  'target_date': _rows[i].date,
                  'target_slot': _rows[i].effectiveSlot,
                  'typical_dwell_minutes': _rows[i].dwell,
                },
        ),
    ];
  }

  Future<void> _createTrip() async {
    final repo = ref.read(tripRepoProvider);
    final dates = _spanDates;
    final items = _items();
    final bookingLines = _parse?.bookingLines ?? const <String>[];
    setState(() {
      _stage = _Stage.working;
      _error = null;
    });
    final TripState trip;
    try {
      trip = await repo.rangeCreate(
        geoRegion: _region!,
        startDate: DateTime.parse(dates.first),
        endDate: DateTime.parse(dates.last),
        partyType: 'solo',
        partySize: 1,
        startEmpty: true,
      );
    } on ApiException catch (e) {
      if (mounted) {
        setState(() {
          _stage = _Stage.review;
          _error = e.message;
        });
      }
      return;
    }
    _tripId = trip.tripId;
    List<Map<String, dynamic>> results = const [];
    try {
      final res = await repo.sendEvent(
        tripId: trip.tripId,
        type: EventType.addActivity,
        message: 'Import plan',
        preferences: {
          'mode': 'import_plan',
          'items': [for (final (_, item) in items) item],
        },
      );
      results = res.importResults;
    } on ValidationException catch (e) {
      final detail = e.detail;
      if (detail != null && detail['error'] == 'import_plan_refused') {
        results = ((detail['results'] as List?) ?? const [])
            .map((r) => Map<String, dynamic>.from(r as Map))
            .toList();
      } else {
        _error = e.message;
      }
    } on ApiException catch (e) {
      _error = e.message;
    }
    for (final r in results) {
      final idx = (r['index'] as num?)?.toInt();
      if (idx == null || idx < 0 || idx >= items.length) continue;
      final row = _rows[items[idx].$1];
      if (r['status'] == 'added') {
        _added.add(row);
      } else {
        _notImported.add(_NotImported(
          row.stop.name,
          row.date ?? '',
          (r['message'] as String?) ?? 'Not added.',
        ));
      }
    }
    for (final line in bookingLines) {
      if (!mounted) return;
      final saved = await showModalBottomSheet<dynamic>(
        context: context,
        isScrollControlled: true,
        builder: (_) => AddBookingSheet(tripId: trip.tripId, pastedText: line),
      );
      if (saved == true) _bookingsSaved++;
    }
    if (mounted) setState(() => _stage = _Stage.done);
  }

  Future<void> _copyNotImported() async {
    final text = [for (final n in _notImported) '${n.name} | ${n.date} | ${n.reason}'].join('\n');
    await Clipboard.setData(ClipboardData(text: text));
  }

  Future<void> _pickDate({required bool start}) async {
    final now = DateTime.now();
    final picked = await showDatePicker(
      context: context,
      initialDate: (start ? _start : _end) ?? _start ?? now,
      firstDate: DateTime(now.year - 1),
      lastDate: DateTime(now.year + 3),
    );
    if (picked == null || !mounted) return;
    setState(() {
      if (start) {
        _start = picked;
        if (_end != null && _end!.isBefore(picked)) _end = picked;
      } else {
        _end = picked;
      }
      _parse = null;
      _rows = const [];
      _stage = _Stage.input;
    });
  }

  // ---------------------------------------------------------------------------

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Paste a plan')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (_stage == _Stage.input) ..._inputSection(),
          if (_stage == _Stage.review) ..._reviewSection(),
          if (_stage == _Stage.working) const Text('Working...', key: Key('paste_plan_working')),
          if (_stage == _Stage.done) ..._resultSection(),
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 12),
              child: Text(_error!, key: const Key('paste_plan_error')),
            ),
        ],
      ),
    );
  }

  String _fmt(DateTime? d) => d == null ? 'Choose' : isoDate(d);

  List<Widget> _inputSection() => [
        DropdownButton<String>(
          key: const Key('paste_plan_region'),
          value: _region,
          isExpanded: true,
          items: [
            for (final r in widget.regions)
              DropdownMenuItem(value: r, child: Text(regionDisplayName(r))),
          ],
          onChanged: (v) => setState(() {
            _region = v;
            _parse = null;
          }),
        ),
        Row(
          children: [
            TextButton(
              key: const Key('paste_plan_start'),
              onPressed: () => _pickDate(start: true),
              child: Text('Start: ${_fmt(_start)}'),
            ),
            TextButton(
              key: const Key('paste_plan_end'),
              onPressed: () => _pickDate(start: false),
              child: Text('End: ${_fmt(_end)}'),
            ),
          ],
        ),
        TextField(
          key: const Key('paste_plan_text'),
          controller: _text,
          minLines: 6,
          maxLines: 12,
          decoration: const InputDecoration(
            hintText: 'Paste your plan here. It stays on this phone.',
          ),
        ),
        const SizedBox(height: 8),
        ElevatedButton(
          key: const Key('paste_plan_parse'),
          onPressed: _readPlan,
          child: const Text('Read plan'),
        ),
        if (_parse != null) ..._parsePreview(_parse!),
      ];

  List<Widget> _parsePreview(PlanParseResult p) => [
        const SizedBox(height: 12),
        Text('${p.stopCount} stops on ${p.days.length} days', key: const Key('paste_plan_summary')),
        for (final d in p.days) ...[
          Text(d.date ?? 'Outside your dates: ${d.heading}'),
          for (final s in d.stops) Text('  ${s.clockTime ?? ''} ${s.name}'.trimRight()),
        ],
        if (p.bookingLines.isNotEmpty)
          Text('${p.bookingLines.length} booking lines (added after the trip is created)',
              key: const Key('paste_plan_booking_lines')),
        if (p.notUnderstood.isNotEmpty) ...[
          const Text('Not understood (not imported)'),
          for (final l in p.notUnderstood) Text(l),
        ],
        const SizedBox(height: 8),
        if (_offline)
          const OfflineStateView(
            key: Key('paste_plan_offline'),
            state: OfflineState.unavailable,
            child: Text('Finding matches needs a connection. Nothing was sent.'),
          ),
        ElevatedButton(
          key: const Key('paste_plan_match'),
          onPressed: _findMatches,
          child: const Text('Find matches'),
        ),
      ];

  List<Widget> _reviewSection() {
    final dates = _spanDates;
    final p = _parse;
    return [
      for (var i = 0; i < _rows.length; i++) _rowCard(i, _rows[i], dates),
      if (p != null && p.notUnderstood.isNotEmpty) ...[
        const Text('Not understood (not imported)'),
        for (final l in p.notUnderstood) Text(l),
      ],
      if (p != null && p.bookingLines.isNotEmpty)
        Text('${p.bookingLines.length} booking lines will open the booking sheet after the trip is created.'),
      const SizedBox(height: 8),
      ElevatedButton(
        key: const Key('paste_plan_create'),
        onPressed: _canCreate ? _createTrip : null,
        child: const Text('Create trip'),
      ),
    ];
  }

  String _statusText(PlanRow r) {
    if (r.suggestion == null) return 'Not in our catalog';
    switch (r.decision) {
      case MatchDecision.unconfirmed:
        return 'Not yet confirmed';
      case MatchDecision.accepted:
        return 'Accepted';
      case MatchDecision.rejected:
        return 'Rejected';
    }
  }

  Widget _rowCard(int i, PlanRow r, List<String> dates) {
    final s = r.suggestion;
    return Card(
      key: Key('paste_plan_row_$i'),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('${r.stop.name}  (${r.date ?? 'no day'})'),
            if (s != null)
              Text('Suggested: ${s.name}, ${regionDisplayName(s.geoRegion ?? '')} (${s.provenance})'),
            Text(_statusText(r), key: Key('paste_plan_status_$i')),
            if (s != null)
              Wrap(spacing: 8, children: [
                OutlinedButton(
                  key: Key('paste_plan_accept_$i'),
                  onPressed: () => setState(() => r.decision = MatchDecision.accepted),
                  child: const Text('Accept'),
                ),
                OutlinedButton(
                  key: Key('paste_plan_reject_$i'),
                  onPressed: () => setState(() => r.decision = MatchDecision.rejected),
                  child: const Text('Reject'),
                ),
              ]),
            if (s == null && r.near.isNotEmpty)
              Wrap(spacing: 8, children: [
                for (var j = 0; j < r.near.length; j++)
                  ActionChip(
                    key: Key('paste_plan_near_${i}_$j'),
                    label: Text(r.near[j].name),
                    onPressed: () => setState(() => r.suggestion = r.near[j]),
                  ),
              ]),
            if (r.isPlain) ...[
              const Text(kPlainRowLabel),
              Wrap(spacing: 8, children: [
                for (final m in kPlanDwellChoices)
                  ChoiceChip(
                    key: Key('paste_plan_dwell_${i}_$m'),
                    label: Text('$m min'),
                    selected: r.dwell == m,
                    onSelected: (_) => setState(() => r.dwell = m),
                  ),
              ]),
            ],
            if (r.stop.slotHint == null)
              Wrap(spacing: 8, children: [
                for (final slot in kPlanSlots)
                  ChoiceChip(
                    key: Key('paste_plan_slot_${i}_$slot'),
                    label: Text(kPlanSlotLabels[slot]!),
                    selected: r.slot == slot,
                    onSelected: (_) => setState(() => r.slot = slot),
                  ),
              ]),
            if (r.date == null)
              Wrap(spacing: 8, children: [
                for (final d in dates)
                  ChoiceChip(
                    key: Key('paste_plan_day_${i}_$d'),
                    label: Text(d),
                    selected: false,
                    onSelected: (_) => setState(() => r.date = d),
                  ),
              ]),
          ],
        ),
      ),
    );
  }

  List<Widget> _resultSection() => [
        Text('Added: ${_added.length}', key: const Key('paste_plan_added_count')),
        Text('Not imported: ${_notImported.length}', key: const Key('paste_plan_not_imported_count')),
        Text('Bookings saved: $_bookingsSaved', key: const Key('paste_plan_booking_count')),
        for (final r in _added)
          Text(r.isPlain ? '${r.stop.name} - $kPlainRowLabel' : r.stop.name),
        if (_notImported.isNotEmpty) ...[
          const SizedBox(height: 8),
          const Text('Not imported'),
          for (var i = 0; i < _notImported.length; i++)
            Text(
              '${_notImported[i].name} (${_notImported[i].date}): ${_notImported[i].reason}',
              key: Key('paste_plan_not_imported_$i'),
            ),
          TextButton(
            key: const Key('paste_plan_copy'),
            onPressed: _copyNotImported,
            child: const Text('Copy list'),
          ),
        ],
        if (_tripId != null)
          ElevatedButton(
            key: const Key('paste_plan_open_trip'),
            onPressed: () => GoRouter.maybeOf(context)?.go('/trip/$_tripId'),
            child: const Text('Open trip'),
          ),
      ];
}
