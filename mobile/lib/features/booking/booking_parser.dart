/// On-device regex & keyword extractor for booking data.
///
/// Zero network calls. Degrades gracefully to partial/empty fields -- NEVER throws.
class ParsedBooking {
  final String? bookingType;
  final String? venueName;
  final DateTime? scheduledStart;
  final int? durationMinutes;
  final String? confirmationCode;
  final String? notes;
  final String? geoRegion;
  final String importSource;

  const ParsedBooking({
    this.bookingType,
    this.venueName,
    this.scheduledStart,
    this.durationMinutes,
    this.confirmationCode,
    this.notes,
    this.geoRegion,
    this.importSource = 'manual',
  });
}

/// Zero-network, on-device regex & keyword extractor.
/// Degrades gracefully to partial/empty fields -- NEVER throws on malformed text.
ParsedBooking extractBookingFromText(
  String rawText, {
  String importSource = 'email',
}) {
  if (rawText.trim().isEmpty) {
    return ParsedBooking(importSource: importSource);
  }

  final text = rawText.trim();
  final lower = text.toLowerCase();

  // 1. Detect booking type
  String? bookingType;
  if (lower.contains('flight') ||
      lower.contains('airline') ||
      lower.contains('boarding pass') ||
      lower.contains('terminal')) {
    bookingType = 'flight';
  } else if (lower.contains('hotel') ||
      lower.contains('check-in') ||
      lower.contains('resort') ||
      lower.contains('stay') ||
      lower.contains('reservation details') ||
      lower.contains('nights')) {
    bookingType = 'hotel';
  } else if (lower.contains('train') ||
      lower.contains('railway') ||
      lower.contains('station')) {
    bookingType = 'train';
  } else if (lower.contains('tour') ||
      lower.contains('guide') ||
      lower.contains('excursion')) {
    bookingType = 'tour';
  }

  // 2. Extract confirmation code. Labels are case-insensitive; the code
  // itself is uppercase alphanumeric so "Reservation details" cannot become
  // a PNR.
  final confirmationCode = _extractConfirmationCode(text);

  // 3. Extract title/venue hint. Confirmation emails usually start with a
  // greeting, so a property-specific sentence wins over the first line.
  final lines =
      text.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
  String? venueName;
  final expecting = RegExp(
    r'(?im)^(.{2,80}?)\s+is expecting you on\b',
  ).firstMatch(text);
  if (expecting != null) {
    venueName = expecting.group(1)?.trim();
  } else {
    final bookingAt = RegExp(
      r'(?im)^(?:your\s+)?booking\s+(?:at|with)\s+(.{2,80}?)\s+is confirmed\b',
    ).firstMatch(text);
    venueName = bookingAt?.group(1)?.trim();
  }
  if (venueName == null && lines.isNotEmpty) {
    venueName = lines.firstWhere(
      (line) => !_looksLikeGreeting(line),
      orElse: () => lines.first,
    );
  }
  if (venueName != null && venueName.length > 80) {
    venueName = venueName.substring(0, 80);
  }

  // 4. Parse check-in and checkout locally. DateTime.parse does not accept
  // Booking.com's human date format, so keep this closed English month parser.
  final checkIn = _extractLabeledDate(text, 'check-in') ??
      _extractExpectedDate(text);
  final checkOut = _extractLabeledDate(text, 'check-out');
  final stayMinutes = checkIn != null && checkOut != null
      ? checkOut.difference(checkIn).inMinutes
      : null;
  final geoRegion = _inferGeoRegion(lower);

  return ParsedBooking(
    bookingType: bookingType,
    venueName: venueName,
    scheduledStart: checkIn,
    confirmationCode: confirmationCode,
    durationMinutes: stayMinutes != null && stayMinutes > 0
        ? stayMinutes
        : bookingType == 'hotel'
            ? 480
            : (bookingType == 'flight' ? 180 : 90),
    geoRegion: geoRegion,
    importSource: importSource,
  );
}

final _confirmationLabel = RegExp(
  r'(?:pnr|confirmation\s+(?:code|ref|number)|booking\s+(?:ref|reference|id|number|code)|reservation\s+(?:code|ref|reference)|pin\s*(?:code)?)\s*[:#]?\s*',
  caseSensitive: false,
);
final _confirmationToken = RegExp(r'^[A-Z0-9][A-Z0-9.]{3,19}');

String? _extractConfirmationCode(String text) {
  for (final match in _confirmationLabel.allMatches(text)) {
    final rest = text.substring(match.end).trimLeft();
    final token = _confirmationToken.matchAsPrefix(rest)?.group(0);
    if (token != null) return token;
  }
  return null;
}

String? _inferGeoRegion(String lower) {
  if (lower.contains('vang vieng')) return 'vang_vieng_laos';
  if (lower.contains('luang prabang')) return 'luang_prabang_laos';
  if (lower.contains('vientiane')) return 'vientiane_laos';
  if (lower.contains('dubai')) return 'dubai_uae';
  return null;
}

bool _looksLikeGreeting(String line) {
  final lower = line.toLowerCase();
  return lower.startsWith('thanks ') ||
      lower.startsWith('hello ') ||
      lower.startsWith('dear ') ||
      lower.startsWith('hi ') ||
      lower == 'booking confirmed' ||
      lower == 'reservation details';
}

const _months = <String, int>{
  'jan': 1,
  'january': 1,
  'feb': 2,
  'february': 2,
  'mar': 3,
  'march': 3,
  'apr': 4,
  'april': 4,
  'may': 5,
  'jun': 6,
  'june': 6,
  'jul': 7,
  'july': 7,
  'aug': 8,
  'august': 8,
  'sep': 9,
  'sept': 9,
  'september': 9,
  'oct': 10,
  'october': 10,
  'nov': 11,
  'november': 11,
  'dec': 12,
  'december': 12,
};

DateTime? _extractLabeledDate(String text, String label) {
  final match = RegExp(
    '$label\\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\\s+)?'
    r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})'
    r'(?:\s+\((?:until\s+)?(\d{1,2}):(\d{2}))?',
    caseSensitive: false,
  ).firstMatch(text);
  return _dateFromMatch(match);
}

DateTime? _extractExpectedDate(String text) {
  final match = RegExp(
    r'expecting you on\s+(?:(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,?\s+)?'
    r'(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})',
    caseSensitive: false,
  ).firstMatch(text);
  return _dateFromMatch(match);
}

DateTime? _dateFromMatch(RegExpMatch? match) {
  if (match == null) return null;
  final month = _months[match.group(2)!.toLowerCase()];
  if (month == null) return null;
  final hour = int.tryParse(match.groupCount >= 4 ? match.group(4) ?? '' : '');
  final minute = int.tryParse(match.groupCount >= 5 ? match.group(5) ?? '' : '');
  return DateTime(
    int.parse(match.group(3)!),
    month,
    int.parse(match.group(1)!),
    hour ?? 0,
    minute ?? 0,
  );
}
