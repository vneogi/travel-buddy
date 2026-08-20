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
  final String importSource;

  const ParsedBooking({
    this.bookingType,
    this.venueName,
    this.scheduledStart,
    this.durationMinutes,
    this.confirmationCode,
    this.notes,
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
      lower.contains('stay')) {
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

  // 2. Extract confirmation code
  String? confirmationCode;
  final codeRegex = RegExp(
    r'(?:pnr|confirmation|booking\s*(?:ref|id|number|code)?|reservation\s*#?)\s*[:#]?\s*([A-Z0-9]{5,10})',
    caseSensitive: false,
  );
  final codeMatch = codeRegex.firstMatch(text);
  if (codeMatch != null) {
    confirmationCode = codeMatch.group(1);
  }

  // 3. Extract title/venue hint
  String? venueName;
  final lines =
      text.split('\n').map((l) => l.trim()).where((l) => l.isNotEmpty).toList();
  if (lines.isNotEmpty) {
    venueName =
        lines.first.length <= 50 ? lines.first : lines.first.substring(0, 50);
  }

  return ParsedBooking(
    bookingType: bookingType,
    venueName: venueName,
    confirmationCode: confirmationCode,
    durationMinutes:
        bookingType == 'hotel' ? 480 : (bookingType == 'flight' ? 180 : 90),
    importSource: importSource,
  );
}
