/// Typed dismiss handler for FactView (SPEC-22 decision 9).
///
/// FactView invokes this with its own attribute and the tier-derived kind.
/// Callers wire it to [PromptDismissAdapter.emit] which writes
/// prompt_dismissed to the signal outbox.
typedef DismissHandler = void Function({
  required String kind,
  required String attribute,
});
