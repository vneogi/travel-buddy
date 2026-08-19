/// SPEC-22 localized strings for the render contract.
///
/// Uses generated AppLocalizations when available (flutter gen-l10n).
/// Falls back to English constants for unit tests that run without
/// the full localization delegate.
///
/// When flutter gen-l10n is wired in CI, replace fallbacks with
/// AppLocalizations.of(context)!.factXxx calls in FactView.
class RenderStrings {
  const RenderStrings._();

  // Hedge treatment: qualifier inside the sentence.
  static String factHedge(String value) => 'Travellers usually say $value';

  // Ask treatment: question prompt.
  static const String factAskPrompt = 'Is this still correct?';

  // Defer treatment: labelled link.
  static String factDeferSee(String target) => 'See $target';

  // Refuse treatment: explicit unknown. NEVER empty.
  static const String factRefuse = 'Information not available';

  // Confirm affordance label.
  static const String factConfirm = 'Confirm';

  // Recency label.
  static String factRecency(String month) => 'Confirmed in $month';

  // Offline states.
  static String offlineCached(String when) => 'Cached $when';
  static const String offlineUnavailable = 'Not available offline';
  static const String offlineRetry = 'Retry when online';
}
