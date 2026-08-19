/// Client-side interruption budget (SPEC-22 decision 8).
///
/// Defaults (not spec-numbered; may change):
///   - Cap: 3 granted interruptions per local calendar day
///   - Minimum gap: 30 minutes between grants
///   - After dismiss: suppress 120 minutes
///
/// Categories are opaque strings (question_card, checklist).
/// No public "forceShow" bypass. Persist in process memory only for this PR.
class InterruptionBudget {
  final DateTime Function() _now;

  // Defaults
  static const int _dailyCap = 3;
  static const Duration _minGap = Duration(minutes: 30);
  static const Duration _dismissSuppression = Duration(minutes: 120);

  // State (process lifetime)
  final List<DateTime> _grants = [];
  DateTime? _lastDismiss;

  InterruptionBudget({DateTime Function()? now}) : _now = now ?? DateTime.now;

  /// Request an interruption slot. Returns true if granted.
  bool request({required String category}) {
    final now = _now();

    // Dismiss suppression
    if (_lastDismiss != null && now.difference(_lastDismiss!) < _dismissSuppression) {
      return false;
    }

    // Count grants today (local calendar day)
    final todayGrants = _grants.where((g) =>
        g.year == now.year && g.month == now.month && g.day == now.day).toList();
    if (todayGrants.length >= _dailyCap) {
      return false;
    }

    // Min gap
    if (_grants.isNotEmpty && now.difference(_grants.last) < _minGap) {
      return false;
    }

    _grants.add(now);
    return true;
  }

  /// Record a dismissal (user closed an interruptive prompt).
  void dismiss() {
    _lastDismiss = _now();
  }
}
