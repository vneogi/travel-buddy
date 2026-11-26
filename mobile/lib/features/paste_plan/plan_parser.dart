// SPEC-58 slice 1b: deterministic, on-device plan parser.
//
// Pure: no I/O, no network, no clock. The trip dates are passed in. Raw
// paste text never leaves this function; callers send only stop names.

const int kPlanMaxStops = 60;
const int kPlanMaxDays = 14;

const _months = <String, int>{
  'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
  'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
};

const _weekdays = <String>{
  'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday',
  'mon', 'tue', 'tues', 'wed', 'thu', 'thur', 'thurs', 'fri', 'sat', 'sun',
};

const _bookingWords = <String>[
  'confirmation', 'reservation', 'check-in', 'check in', 'checkin',
  'check-out', 'check out', 'checkout', 'booking ref',
];

/// Client-side slot hint; mirrors the server's slot_from_time windows.
String slotForClockTime(int hour, int minute) {
  final m = hour * 60 + minute;
  if (m < 11 * 60) return 'morning_tour';
  if (m < 14 * 60) return 'lunch';
  if (m < 17 * 60) return 'afternoon_evening_tour';
  return 'dinner';
}

class PlanStop {
  final String name;
  final String? clockTime; // 24h HH:MM; a hint only
  final String? note;
  final int order; // position in the paste

  const PlanStop({required this.name, this.clockTime, this.note, required this.order});

  String? get slotHint {
    final t = clockTime;
    if (t == null) return null;
    final parts = t.split(':');
    return slotForClockTime(int.parse(parts[0]), int.parse(parts[1]));
  }

  Map<String, dynamic> toJson() => {
        'name': name,
        'clock_time': clockTime,
        'note': note,
        'slot_hint': slotHint,
      };
}

class PlanDay {
  /// ISO date inside the trip span, or null for a heading outside it.
  final String? date;
  final String heading;
  final List<PlanStop> stops;

  PlanDay({required this.date, required this.heading}) : stops = <PlanStop>[];

  Map<String, dynamic> toJson() => {
        'date': date,
        'stops': [for (final s in stops) s.toJson()],
      };
}

class PlanParseResult {
  final List<PlanDay> days;
  final List<String> bookingLines;
  final List<String> notUnderstood;
  final String? refusal;

  const PlanParseResult({
    this.days = const [],
    this.bookingLines = const [],
    this.notUnderstood = const [],
    this.refusal,
  });

  bool get isRefused => refusal != null;
  int get stopCount => days.fold(0, (n, d) => n + d.stops.length);

  Map<String, dynamic> toJson() => {
        'days': [for (final d in days) d.toJson()],
        'booking_lines': bookingLines,
        'not_understood': notUnderstood,
      };
}

DateTime _isoDay(String iso) {
  final p = iso.split('-');
  return DateTime.utc(int.parse(p[0]), int.parse(p[1]), int.parse(p[2]));
}

String isoDate(DateTime d) =>
    '${d.year.toString().padLeft(4, '0')}-'
    '${d.month.toString().padLeft(2, '0')}-'
    '${d.day.toString().padLeft(2, '0')}';

bool _inSpan(DateTime d, DateTime start, DateTime end) =>
    !d.isBefore(start) && !d.isAfter(end);

bool looksLikeBooking(String line) {
  final lower = line.toLowerCase();
  if (_bookingWords.any(lower.contains)) return true;
  for (final m in RegExp(r'\b([A-Z]{2})\s?\d{2,4}\b').allMatches(line)) {
    final code = m.group(1)!;
    if (code != 'AM' && code != 'PM') return true;
  }
  return false;
}

/// A heading: (isHeading, date or null when outside the span).
({bool isHeading, String? date})? _parseHeading(String line, DateTime start, DateTime end) {
  final dayN = RegExp(r'^day\s*(\d{1,2})\b\s*[:.\-]?\s*(.*)$', caseSensitive: false)
      .firstMatch(line);
  if (dayN != null) {
    final n = int.parse(dayN.group(1)!);
    final d = start.add(Duration(days: n - 1));
    return (isHeading: true, date: n >= 1 && _inSpan(d, start, end) ? isoDate(d) : null);
  }
  final norm = line.toLowerCase().replaceAll(',', ' ').trim();
  final iso = RegExp(r'^(\d{4})-(\d{2})-(\d{2})\s*(?:[:\-]\s*.*)?$').firstMatch(norm);
  if (iso != null) {
    final d = DateTime.utc(
        int.parse(iso.group(1)!), int.parse(iso.group(2)!), int.parse(iso.group(3)!));
    return (isHeading: true, date: _inSpan(d, start, end) ? isoDate(d) : null);
  }
  final m = RegExp(
    r'^(?:([a-z]+)\s+)?(?:(\d{1,2})(?:st|nd|rd|th)?\s+([a-z]{3,9})|([a-z]{3,9})\s+(\d{1,2})(?:st|nd|rd|th)?)(?:\s+(\d{4}))?\s*(?:[:\-]\s*.*)?$',
  ).firstMatch(norm.replaceAll(RegExp(r'\s+'), ' '));
  if (m == null) return null;
  final weekday = m.group(1);
  if (weekday != null && !_weekdays.contains(weekday)) return null;
  final dayText = m.group(2) ?? m.group(5);
  final monthText = (m.group(3) ?? m.group(4))!;
  final month = _months[monthText.substring(0, 3)];
  if (month == null || dayText == null) return null;
  final day = int.parse(dayText);
  final years = m.group(6) != null ? [int.parse(m.group(6)!)] : [start.year, end.year];
  for (final y in years) {
    final d = DateTime.utc(y, month, day);
    if (d.month == month && _inSpan(d, start, end)) {
      return (isHeading: true, date: isoDate(d));
    }
  }
  return (isHeading: true, date: null);
}

final _timeRe = RegExp(
  r'^(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm|a\.m\.|p\.m\.)?(?=\s|$|[-:,])',
  caseSensitive: false,
);

PlanStop? _parseStop(String line, int order) {
  var rest = line.replaceFirst(RegExp(r'^(?:[-*+\u2022]|\d{1,2}[.)])\s+'), '').trim();
  String? clock;
  final t = _timeRe.firstMatch(rest);
  if (t != null && (t.group(2) != null || t.group(3) != null)) {
    var h = int.parse(t.group(1)!);
    final min = int.parse(t.group(2) ?? '0');
    final ampm = t.group(3)?.toLowerCase().replaceAll('.', '');
    if (ampm != null) {
      if (h < 1 || h > 12) return null;
      if (ampm == 'pm' && h < 12) h += 12;
      if (ampm == 'am' && h == 12) h = 0;
    }
    if (h > 23 || min > 59) return null;
    clock = '${h.toString().padLeft(2, '0')}:${min.toString().padLeft(2, '0')}';
    rest = rest.substring(t.end).trim().replaceFirst(RegExp(r'^[-:,]+\s*'), '');
  }
  var name = rest;
  String? note;
  final dash = rest.indexOf(' - ');
  final paren = rest.indexOf(' (');
  final cut = [dash, paren].where((i) => i >= 0).fold<int>(-1, (a, b) => a < 0 || b < a ? b : a);
  if (cut >= 0) {
    name = rest.substring(0, cut).trim();
    var tail = rest.substring(cut + (cut == dash ? 3 : 2)).trim();
    if (cut == paren && tail.endsWith(')')) tail = tail.substring(0, tail.length - 1).trim();
    note = tail.isEmpty ? null : tail;
  }
  final lower = name.toLowerCase();
  final words = name.split(RegExp(r'\s+')).where((w) => w.isNotEmpty).length;
  if (name.length < 2 ||
      name.length > 60 ||
      words > 8 ||
      !RegExp(r'\p{L}', unicode: true).hasMatch(name) ||
      lower.contains('http') ||
      lower.contains('www.') ||
      name.endsWith(':') ||
      name.endsWith('?') ||
      name.endsWith('!')) {
    return null;
  }
  return PlanStop(name: name, clockTime: clock, note: note, order: order);
}

/// Parse a pasted plan for a trip from [startDate] to [endDate] (ISO dates).
PlanParseResult parsePlan(String text, {required String startDate, required String endDate}) {
  if (text.trim().isEmpty) {
    return const PlanParseResult(refusal: 'Paste a plan first.');
  }
  final start = _isoDay(startDate);
  final end = _isoDay(endDate);
  final dated = <String, PlanDay>{};
  final outOfSpan = <PlanDay>[];
  final booking = <String>[];
  final unknown = <String>[];
  PlanDay? current;
  var headings = 0;
  var stops = 0;
  for (final raw in text.split(RegExp(r'\r?\n'))) {
    final line = raw.trim();
    if (line.isEmpty) continue;
    if (looksLikeBooking(line)) {
      booking.add(line);
      continue;
    }
    final h = _parseHeading(line, start, end);
    if (h != null) {
      headings++;
      if (headings > kPlanMaxDays) {
        return const PlanParseResult(
          refusal: 'That plan has more than 14 days. Paste up to 14 days at a time.',
        );
      }
      if (h.date == null) {
        unknown.add(line);
        current = PlanDay(date: null, heading: line);
        outOfSpan.add(current);
      } else {
        current = dated.putIfAbsent(h.date!, () => PlanDay(date: h.date, heading: line));
      }
      continue;
    }
    final stop = _parseStop(line, stops);
    if (stop == null) {
      unknown.add(line);
      continue;
    }
    stops++;
    if (stops > kPlanMaxStops) {
      return const PlanParseResult(
        refusal: 'That plan has more than 60 stops. Paste up to 60 stops at a time.',
      );
    }
    current ??= dated.putIfAbsent(isoDate(start), () => PlanDay(date: isoDate(start), heading: ''));
    current.stops.add(stop);
  }
  final days = [
    ...(dated.keys.toList()..sort()).map((k) => dated[k]!),
    ...outOfSpan,
  ].where((d) => d.stops.isNotEmpty).toList();
  return PlanParseResult(days: days, bookingLines: booking, notUnderstood: unknown);
}
