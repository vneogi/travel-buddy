import '../services/signal_service.dart';

/// Adapter: bridges FactView typed dismiss into SignalService.emit.
///
/// Pass [handler] as FactView's onDismiss. The adapter owns the
/// payload shape; the widget never builds the signal map.
class PromptDismissAdapter {
  final SignalService _signals;
  final String placeRef;

  PromptDismissAdapter(this._signals, {required this.placeRef});

  void handler({required String kind, required String attribute}) {
    _signals.emit(
      signalType: 'prompt_dismissed',
      placeRef: placeRef,
      valueJson: {'kind': kind, 'attribute': attribute},
    );
  }
}
