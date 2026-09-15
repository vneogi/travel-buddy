/// On-device provider-aware booking extractor (SPEC-10 remainder).
///
/// Pipeline: normalize -> detect provider -> adapter -> ParsedBooking.
/// Zero network calls. Degrades gracefully to partial/empty -- NEVER throws.

// ===================================================================
// Extraction quality
// ===================================================================

enum ExtractionQuality { full, partial, unknown }

class ExtractedField<T> {
  final T? value;
  final ExtractionQuality quality;

  const ExtractedField(this.value, this.quality);
  const ExtractedField.unknown() : value = null, quality = ExtractionQuality.unknown;
  const ExtractedField.full(T this.value) : quality = ExtractionQuality.full;
  const ExtractedField.partial(T this.value) : quality = ExtractionQuality.partial;

  bool get isPresent => value != null;
}

// ===================================================================
// Provider registry
// ===================================================================

enum BookingProvider { bookingCom, agoda, generic, unknown }

// ===================================================================
// ParsedBooking
// ===================================================================

class ParsedBooking {
  final ExtractedField<String> bookingTypeField;
  final ExtractedField<String> venueNameField;
  final ExtractedField<DateTime> scheduledStartField;
  final ExtractedField<DateTime> checkoutDateField;
  final ExtractedField<int> durationMinutesField;
  final ExtractedField<String> confirmationCodeField;
  final ExtractedField<String> geoRegionField;
  final BookingProvider provider;
  final String importSource;

  const ParsedBooking({
    this.bookingTypeField = const ExtractedField.unknown(),
    this.venueNameField = const ExtractedField.unknown(),
    this.scheduledStartField = const ExtractedField.unknown(),
    this.checkoutDateField = const ExtractedField.unknown(),
    this.durationMinutesField = const ExtractedField.unknown(),
    this.confirmationCodeField = const ExtractedField.unknown(),
    this.geoRegionField = const ExtractedField.unknown(),
    this.provider = BookingProvider.unknown,
    this.importSource = 'manual',
  });

  // Convenience getters for backward compatibility.
  String? get bookingType => bookingTypeField.value;
  String? get venueName => venueNameField.value;
  DateTime? get scheduledStart => scheduledStartField.value;
  DateTime? get checkoutDate => checkoutDateField.value;
  int? get durationMinutes => durationMinutesField.value;
  String? get confirmationCode => confirmationCodeField.value;
  String? get geoRegion => geoRegionField.value;
  String? get notes => null;

  /// True when at least one field has a usable value.
  bool get hasUsefulFields =>
      bookingTypeField.isPresent ||
      venueNameField.isPresent ||
      scheduledStartField.isPresent ||
      checkoutDateField.isPresent ||
      confirmationCodeField.isPresent;

  /// Human-readable list of fields found.
  List<String> get foundFields => [
        if (bookingTypeField.isPresent) 'Booking type',
        if (venueNameField.isPresent) 'Property name',
        if (scheduledStartField.isPresent) 'Check-in',
        if (checkoutDateField.isPresent) 'Check-out',
        if (durationMinutesField.isPresent) 'Duration',
        if (confirmationCodeField.isPresent) 'Confirmation code',
        if (geoRegionField.isPresent) 'Region',
      ];

  /// Human-readable list of fields still required.
  List<String> get missingFields => [
        if (!bookingTypeField.isPresent) 'Booking type',
        if (!venueNameField.isPresent) 'Property name',
        if (!scheduledStartField.isPresent) 'Check-in',
      ];
}

// ===================================================================
// Public entry point
// ===================================================================

/// Zero-network, on-device regex & keyword extractor.
/// Degrades gracefully to partial/empty fields -- NEVER throws on malformed text.
ParsedBooking extractBookingFromText(
  String rawText, {
  String importSource = 'email',
}) {
  if (rawText.trim().isEmpty) {
    return ParsedBooking(importSource: importSource);
  }

  try {
    final normalized = _normalize(rawText);
    final provider = _detectProvider(normalized);
    switch (provider) {
      case BookingProvider.bookingCom:
        return _extractBookingCom(normalized, importSource, provider);
      case BookingProvider.agoda:
        return _extractAgoda(normalized, importSource, provider);
      case BookingProvider.generic:
      case BookingProvider.unknown:
        return _extractGeneric(normalized, importSource, provider);
    }
  } catch (_) {
    return ParsedBooking(importSource: importSource);
  }
}

// ===================================================================
// Text normalizer
// ===================================================================

String _normalize(String raw) {
  var t = raw;
  // CRLF / CR -> LF
  t = t.replaceAll('\r\n', '\n').replaceAll('\r', '\n');
  // Non-breaking space (U+00A0), narrow no-break space (U+202F)
  t = t.replaceAll('\u00A0', ' ').replaceAll('\u202F', ' ');
  // Smart quotes -> straight
  t = t
      .replaceAll('\u2018', "'")
      .replaceAll('\u2019', "'")
      .replaceAll('\u201C', '"')
      .replaceAll('\u201D', '"');
  // Em-dash / en-dash -> hyphen (only in label contexts)
  t = t.replaceAll('\u2013', '-').replaceAll('\u2014', '-');
  // Collapse repeated horizontal whitespace (not newlines)
  t = t.replaceAll(RegExp(r'[^\S\n]+'), ' ');
  // Forwarded-email quote prefixes (> at line start)
  t = t.replaceAll(RegExp(r'^>+\s?', multiLine: true), '');
  // Normalize label separators: "Check-in:" "Check-in #" "Check-in ="
  // Also normalize "check in" -> "check-in", "check out" -> "check-out"
  // and "arrival" -> "check-in", "departure" -> "check-out" in hotel context
  t = t.replaceAllMapped(
    RegExp(r'\bcheck[\s-]?in\b', caseSensitive: false),
    (m) => 'check-in',
  );
  t = t.replaceAllMapped(
    RegExp(r'\b(?:check[\s-]?out|checkout)\b', caseSensitive: false),
    (m) => 'check-out',
  );
  t = t.replaceAllMapped(
    RegExp(r'\barrival\b', caseSensitive: false),
    (m) => 'check-in',
  );
  t = t.replaceAllMapped(
    RegExp(r'\bdeparture\b', caseSensitive: false),
    (m) => 'check-out',
  );
  return t.trim();
}

// ===================================================================
// Provider detection
// ===================================================================

BookingProvider _detectProvider(String text) {
  final lower = text.toLowerCase();
  if (lower.contains('booking.com') || lower.contains('is expecting you on')) {
    return BookingProvider.bookingCom;
  }
  if (lower.contains('agoda.com') || lower.contains('agoda')) {
    return BookingProvider.agoda;
  }
  // Has labelled fields but unknown provider -> generic
  if (_hasLabelledFields(lower)) {
    return BookingProvider.generic;
  }
  return BookingProvider.unknown;
}

bool _hasLabelledFields(String lower) {
  return lower.contains('check-in') ||
      lower.contains('check-out') ||
      lower.contains('booking id') ||
      lower.contains('confirmation') ||
      lower.contains('reservation');
}

// ===================================================================
// Booking.com adapter
// ===================================================================

ParsedBooking _extractBookingCom(
  String text,
  String importSource,
  BookingProvider provider,
) {
  final lower = text.toLowerCase();
  final bookingType = _detectBookingType(lower);
  final venueName = _extractVenueName(text);
  final code = _extractConfirmationCode(text);
  final checkIn =
      _extractLabeledDate(text, 'check-in') ?? _extractExpectedDate(text);
  final checkOut = _extractLabeledDate(text, 'check-out');
  final duration = _deriveDuration(checkIn, checkOut);
  final geo = _inferGeoRegion(lower);

  return ParsedBooking(
    bookingTypeField: bookingType != null
        ? ExtractedField.full(bookingType)
        : const ExtractedField.unknown(),
    venueNameField: venueName != null
        ? ExtractedField.full(venueName)
        : const ExtractedField.unknown(),
    scheduledStartField: checkIn != null
        ? ExtractedField.full(checkIn)
        : const ExtractedField.unknown(),
    checkoutDateField: checkOut != null && duration != null && duration > 0
        ? ExtractedField.full(checkOut)
        : const ExtractedField.unknown(),
    durationMinutesField: duration != null && duration > 0
        ? ExtractedField.full(duration)
        : const ExtractedField.unknown(),
    confirmationCodeField: code != null
        ? ExtractedField.full(code)
        : const ExtractedField.unknown(),
    geoRegionField: geo != null
        ? ExtractedField.full(geo)
        : const ExtractedField.unknown(),
    provider: provider,
    importSource: importSource,
  );
}

// ===================================================================
// Agoda adapter
// ===================================================================

ParsedBooking _extractAgoda(
  String text,
  String importSource,
  BookingProvider provider,
) {
  final lower = text.toLowerCase();
  final bookingType = _detectBookingType(lower);

  // Agoda: "Your booking at PROPERTY is confirmed"
  String? venueName = _extractVenueName(text);
  if (venueName == null) {
    final agodaAt = RegExp(
      r'(?:your\s+)?(?:booking|reservation)\s+(?:at|for)\s+(.{2,80}?)\s+(?:is|has been)\s+confirmed',
      caseSensitive: false,
    ).firstMatch(text);
    venueName = agodaAt?.group(1)?.trim();
  }

  final code = _extractConfirmationCode(text);
  final checkIn = _extractLabeledDate(text, 'check-in') ??
      _extractIsoDate(text, 'check-in');
  final checkOut = _extractLabeledDate(text, 'check-out') ??
      _extractIsoDate(text, 'check-out');
  final duration = _deriveDuration(checkIn, checkOut);
  final geo = _inferGeoRegion(lower);

  return ParsedBooking(
    bookingTypeField: bookingType != null
        ? ExtractedField.full(bookingType)
        : const ExtractedField.unknown(),
    venueNameField: venueName != null
        ? ExtractedField.full(venueName)
        : const ExtractedField.unknown(),
    scheduledStartField: checkIn != null
        ? ExtractedField.full(checkIn)
        : const ExtractedField.unknown(),
    checkoutDateField: checkOut != null && duration != null && duration > 0
        ? ExtractedField.full(checkOut)
        : const ExtractedField.unknown(),
    durationMinutesField: duration != null && duration > 0
        ? ExtractedField.full(duration)
        : const ExtractedField.unknown(),
    confirmationCodeField: code != null
        ? ExtractedField.full(code)
        : const ExtractedField.unknown(),
    geoRegionField: geo != null
        ? ExtractedField.full(geo)
        : const ExtractedField.unknown(),
    provider: provider,
    importSource: importSource,
  );
}

// ===================================================================
// Generic / unknown adapter
// ===================================================================

ParsedBooking _extractGeneric(
  String text,
  String importSource,
  BookingProvider provider,
) {
  final lower = text.toLowerCase();
  final bookingType = _detectBookingType(lower);
  final venueName = _extractVenueName(text);
  final code = _extractConfirmationCode(text);
  final checkIn = _extractLabeledDate(text, 'check-in') ??
      _extractExpectedDate(text) ??
      _extractIsoDate(text, 'check-in');
  final checkOut = _extractLabeledDate(text, 'check-out') ??
      _extractIsoDate(text, 'check-out');
  final duration = _deriveDuration(checkIn, checkOut);
  final geo = _inferGeoRegion(lower);

  return ParsedBooking(
    bookingTypeField: bookingType != null
        ? ExtractedField.full(bookingType)
        : const ExtractedField.unknown(),
    venueNameField: venueName != null
        ? ExtractedField.full(venueName)
        : const ExtractedField.unknown(),
    scheduledStartField: checkIn != null
        ? ExtractedField.full(checkIn)
        : const ExtractedField.unknown(),
    checkoutDateField: checkOut != null && duration != null && duration > 0
        ? ExtractedField.full(checkOut)
        : const ExtractedField.unknown(),
    durationMinutesField: duration != null && duration > 0
        ? ExtractedField.full(duration)
        : const ExtractedField.unknown(),
    confirmationCodeField: code != null
        ? ExtractedField.full(code)
        : const ExtractedField.unknown(),
    geoRegionField: geo != null
        ? ExtractedField.full(geo)
        : const ExtractedField.unknown(),
    provider: provider,
    importSource: importSource,
  );
}

// ===================================================================
// Shared extraction helpers
// ===================================================================

String? _detectBookingType(String lower) {
  if (lower.contains('flight') ||
      lower.contains('airline') ||
      lower.contains('boarding pass') ||
      lower.contains('terminal')) {
    return 'flight';
  }
  if (lower.contains('hotel') ||
      lower.contains('check-in') ||
      lower.contains('resort') ||
      lower.contains('nights')) {
    return 'hotel';
  }
  if (lower.contains('train') ||
      lower.contains('railway') ||
      lower.contains('station')) {
    return 'train';
  }
  if (lower.contains('tour') ||
      lower.contains('guide') ||
      lower.contains('excursion')) {
    return 'tour';
  }
  // Unknown booking type remains null -- never default to Flight.
  return null;
}

/// Extracts venue name using provider-specific patterns.
/// Never falls back to "first non-greeting line" -- that is unsafe.
String? _extractVenueName(String text) {
  // Pattern 1: "PROPERTY is expecting you on" (Booking.com)
  final expecting = RegExp(
    r'^(.{2,80}?)\s+is expecting you on\b',
    caseSensitive: false,
    multiLine: true,
  ).firstMatch(text);
  if (expecting != null) {
    final name = expecting.group(1)?.trim();
    if (name != null && !_isNonVenueLine(name)) return name;
  }

  // Pattern 2: "booking at/with PROPERTY is confirmed"
  final bookingAt = RegExp(
    r'(?:your\s+)?(?:booking|reservation)\s+(?:at|with|for)\s+(.{2,80}?)\s+(?:is|has been)\s+confirmed\b',
    caseSensitive: false,
    multiLine: true,
  ).firstMatch(text);
  if (bookingAt != null) {
    final name = bookingAt.group(1)?.trim();
    if (name != null && !_isNonVenueLine(name)) return name;
  }

  // Pattern 3: "Property: NAME" or "Hotel: NAME"
  final propertyLabel = RegExp(
    r'(?:property|hotel|accommodation)\s*[:=]\s*(.{2,80})',
    caseSensitive: false,
  ).firstMatch(text);
  if (propertyLabel != null) {
    final name = propertyLabel.group(1)?.trim();
    if (name != null && !_isNonVenueLine(name)) return name;
  }

  // No safe venue name found. Return null -- never use first-line fallback.
  return null;
}

/// Returns true for lines that must never become venueName.
bool _isNonVenueLine(String line) {
  final lower = line.toLowerCase().trim();
  if (lower.isEmpty || lower.length < 2) return true;
  // Greetings
  if (lower.startsWith('thanks ') ||
      lower.startsWith('hello ') ||
      lower.startsWith('dear ') ||
      lower.startsWith('hi ') ||
      lower.startsWith('hey ')) {
    return true;
  }
  // Common non-venue lines
  if (lower == 'booking confirmed' ||
      lower == 'reservation details' ||
      lower.startsWith('reservation details')) {
    return true;
  }
  // URLs
  if (lower.startsWith('http://') || lower.startsWith('https://')) return true;
  // Footer / account / self-service text
  if (lower.contains('manage your booking') ||
      lower.contains('customer service') ||
      lower.contains('unsubscribe') ||
      lower.contains('privacy policy') ||
      lower.contains('sign in to') ||
      lower.contains('view your booking') ||
      lower.contains('download the app')) {
    return true;
  }
  // Passenger name pattern: "Passenger: Name"
  if (RegExp(r'^(?:passenger|guest|traveller|traveler)\s*:', caseSensitive: false)
      .hasMatch(lower)) {
    return true;
  }
  // Booking ID sentence: "Your booking ID is ..."
  if (RegExp(r'booking\s+(?:id|reference|code|number)', caseSensitive: false)
      .hasMatch(lower)) {
    return true;
  }
  return false;
}

int? _deriveDuration(DateTime? checkIn, DateTime? checkOut) {
  if (checkIn == null || checkOut == null) return null;
  final minutes = checkOut.difference(checkIn).inMinutes;
  return minutes > 0 ? minutes : null;
}

final _confirmationLabel = RegExp(
  r'(?:\bpnr\b|\bconfirmation\s+(?:code|number|reference|ref)\b|\bbooking\s+(?:reference|number|code|id|ref)\b|\breservation\s+(?:reference|number|code|ref)\b|\bpin(?:\s+code)?\b)\s*(?:is\s+|[:#=]\s*)',
  caseSensitive: false,
);
final _confirmationToken = RegExp(r'^[A-Z0-9][A-Z0-9.]{3,19}');

String? _extractConfirmationCode(String text) {
  for (final match in _confirmationLabel.allMatches(text)) {
    final rest = text.substring(match.end).trimLeft();
    final token = _confirmationToken.matchAsPrefix(rest)?.group(0);
    if (token != null) {
      // Strip trailing sentence punctuation (but preserve internal dots)
      final cleaned = token.replaceAll(RegExp(r'[.]+$'), '');
      if (cleaned.length >= 4) return cleaned;
    }
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

/// Extracts ISO-ish dates: "check-in 2026-10-04" or "check-in: 04/10/2026"
DateTime? _extractIsoDate(String text, String label) {
  // ISO: 2026-10-04
  final iso = RegExp(
    '$label\\s*[:#=]?\\s*(\\d{4})-(\\d{2})-(\\d{2})',
    caseSensitive: false,
  ).firstMatch(text);
  if (iso != null) {
    return DateTime(
      int.parse(iso.group(1)!),
      int.parse(iso.group(2)!),
      int.parse(iso.group(3)!),
    );
  }
  return null;
}

DateTime? _dateFromMatch(RegExpMatch? match) {
  if (match == null) return null;
  final month = _months[match.group(2)!.toLowerCase()];
  if (month == null) return null;
  final hour =
      int.tryParse(match.groupCount >= 4 ? match.group(4) ?? '' : '');
  final minute =
      int.tryParse(match.groupCount >= 5 ? match.group(5) ?? '' : '');
  return DateTime(
    int.parse(match.group(3)!),
    month,
    int.parse(match.group(1)!),
    hour ?? 0,
    minute ?? 0,
  );
}
