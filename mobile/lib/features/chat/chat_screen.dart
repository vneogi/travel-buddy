import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/connectivity_helper.dart';
import '../../core/destination_tz.dart';
import '../../data/models.dart';
import '../../render/offline_state.dart';
import 'ask_bubble.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../itinerary/itinerary_notifier.dart';
import '../itinerary/current_window.dart';

/// Natural language chat. Uses REST POST /trip/event (NO WebSocket).
class ChatScreen extends ConsumerStatefulWidget {
  final String tripId;
  final String? initialQuestion;
  final ConnectivityHelper? connectivityOverride;
  const ChatScreen({
    super.key,
    required this.tripId,
    this.initialQuestion,
    this.connectivityOverride,
  });
  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();
  final _messages = <_ChatEntry>[];
  bool _isThinking = false;
  late final ConnectivityHelper _connectivity;

  @override
  void initState() {
    super.initState();
    _connectivity = widget.connectivityOverride ?? ConnectivityHelper();
    final initial = widget.initialQuestion?.trim();
    if (initial != null && initial.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _send(initial));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Chat', style: AppTypography.h2)),
      body: Column(
        children: [
          Expanded(
            child: _messages.isEmpty
                ? Center(
                    child: Text(
                      'Ask anything about your trip.\n"What are the opening hours?" or "What is nearby?"',
                      style: AppTypography.body.copyWith(color: AppColors.muted),
                      textAlign: TextAlign.center,
                    ),
                  )
                : ListView.builder(
                    reverse: true,
                    padding: const EdgeInsets.all(AppSpacing.base),
                    itemCount: _messages.length,
                    itemBuilder: (_, i) {
                      final entry = _messages[_messages.length - 1 - i];
                      final hasProposal = entry.askResponse?.proposal != null;
                      return entry.build(
                        onConfirmProposal: hasProposal
                            ? () => _confirmAskProposal(
                                  entry.askResponse!.proposal!,
                                  entry.userText,
                                )
                            : null,
                        onDismissProposal: hasProposal ? () {} : null,
                      );
                    },
                  ),
          ),
          if (_isThinking)
            const Padding(
              padding: EdgeInsets.symmetric(horizontal: AppSpacing.base),
              child: _ThinkingBubble(),
            ),
          _InputBar(
            controller: _controller,
            enabled: !_isThinking,
            onSend: _send,
          ),
        ],
      ),
    );
  }

  Future<void> _send([String? suppliedText]) async {
    if (_isThinking) return;
    final text = suppliedText?.trim() ?? _controller.text.trim();
    if (text.isEmpty) return;
    _controller.clear();

    setState(() {
      _messages.add(_ChatEntry.user(text));
      _isThinking = true;
    });

    try {
      final intent = classifyAskIntent(text);
      if (intent == AskIntent.multipleChanges) {
        setState(() {
          _isThinking = false;
          _messages.add(const _ChatEntry.plainAssistant(
            'I can safely change one stop at a time. '
            'Try "cancel next stop" or "swap next stop".',
          ));
        });
        return;
      }
      final itState = ref.read(itineraryControllerProvider(widget.tripId));
      final target = nextMovableStop(
        itState.nodes,
        DateTime.now().toUtc(),
        excludedNodeIds: itState.nodeOutcomes.keys.toSet(),
      );
      if (intent != AskIntent.question && target == null) {
        setState(() {
          _isThinking = false;
          _messages.add(const _ChatEntry.plainAssistant(
            'There is no movable upcoming stop to change.',
          ));
        });
        return;
      }
      if (intent == AskIntent.cancelNext) {
        final confirmed = await _confirmCancellation(target!);
        if (!mounted) return;
        if (!confirmed) {
          setState(() {
            _isThinking = false;
            _messages.add(_ChatEntry.plainAssistant(
              'Kept ${target.venueName}.',
            ));
          });
          return;
        }
      }
      final eventType = switch (intent) {
        AskIntent.cancelNext => EventType.cancelActivity,
        AskIntent.swapNext => EventType.swapActivity,
        _ => EventType.askInfo,
      };

      // SPEC-25: Offline ask_info -> refuse; never enqueue.
      if (eventType == EventType.askInfo) {
        final online = await _connectivity.checkConnectivity();
        if (!mounted) return;
        if (!online) {
          setState(() {
            _isThinking = false;
            _messages.add(const _ChatEntry.offlineRefuse());
          });
          return;
        }
      }

      final result = await ref.read(tripEventProvider).sendEvent(
        tripId: widget.tripId,
        type: eventType,
        message: text,
        targetNodeId: intent == AskIntent.question ? null : target?.nodeId,
      );
      if (!mounted) return;
      setState(() {
        _isThinking = false;
        if (result == null) {
          _messages.add(const _ChatEntry.plainAssistant(
            'I could not complete that request. Please try again.',
          ));
          return;
        }
        // SPEC-25: ask_info with typed envelope -> render via AskBubble.
        final ask = result.askResponse;
        if (eventType == EventType.askInfo) {
          if (ask != null) {
            _messages.add(_ChatEntry.askFact(ask, userText: text));
          } else {
            // askInfo + missing envelope is a client error -- show failure.
            _messages.add(const _ChatEntry.plainAssistant(
              'I could not complete that request. Please try again.',
            ));
          }
        } else if (ask != null) {
          // Non-Ask events that still carry an envelope (unlikely, but safe).
          _messages.add(_ChatEntry.askFact(ask, userText: text));
        } else {
          // Non-Ask events (swap/cancel/add) keep plain text.
          _messages.add(_ChatEntry.plainAssistant(result.message));
        }
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _isThinking = false;
        _messages.add(const _ChatEntry.plainAssistant(
          'I could not reach Travel Buddy. Check your connection and try again.',
        ));
      });
    }
  }

  /// SPEC-25: Confirm a plan-change proposal from Ask.
  Future<void> _confirmAskProposal(
    AskProposal proposal,
    String originalText,
  ) async {
    final eventType = switch (proposal.eventType) {
      ProposalEventType.swapActivity => EventType.swapActivity,
      ProposalEventType.cancelActivity => EventType.cancelActivity,
      ProposalEventType.addActivity => EventType.addActivity,
      ProposalEventType.reroute => EventType.reroute,
    };
    await ref.read(tripEventProvider).sendEvent(
      tripId: widget.tripId,
      type: eventType,
      message: originalText,
      targetNodeId: proposal.targetNodeId.isNotEmpty
          ? proposal.targetNodeId
          : null,
    );
  }

  Future<bool> _confirmCancellation(TripNode target) async {
    final localStart = toDestinationLocal(target.scheduledStart, target.geoRegion);
    final localTime = TimeOfDay.fromDateTime(localStart).format(context);
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => AlertDialog(
        title: const Text('Cancel this stop?'),
        content: Text(
          '${target.venueName} is scheduled for $localTime.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, false),
            child: const Text('Keep it'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(dialogContext, true),
            child: const Text('Cancel this stop'),
          ),
        ],
      ),
    );
    return confirmed ?? false;
  }
}

enum AskIntent { question, cancelNext, swapNext, multipleChanges }

AskIntent classifyAskIntent(String text) {
  final normalized = text.trim().toLowerCase();
  final commandPrefix = r"(?:^|[,;]\s*)(?:please\s+|let'?s\s+)?";
  if (RegExp('$commandPrefix(cancel|skip|remove|swap|change|replace)\\b')
          .hasMatch(normalized) &&
      RegExp(r'\b(next few|several|all)\b').hasMatch(normalized)) {
    return AskIntent.multipleChanges;
  }
  if (RegExp('$commandPrefix(cancel|skip|remove)\\s+(the\\s+)?next(\\s+stop)?\\b')
      .hasMatch(normalized)) {
    return AskIntent.cancelNext;
  }
  if (RegExp('$commandPrefix(swap|change|replace)\\s+(the\\s+)?next(\\s+stop)?\\b')
      .hasMatch(normalized)) {
    return AskIntent.swapNext;
  }
  return AskIntent.question;
}

// ---------------------------------------------------------------------------
// SPEC-25: Chat entry types (user bubble, plain assistant, Ask fact, offline)
// ---------------------------------------------------------------------------

enum _EntryKind { user, plainAssistant, askFact, offlineRefuse }

class _ChatEntry {
  final _EntryKind kind;
  final String text;
  final AskResponse? askResponse;
  /// Original user question text, preserved for plan-change confirm.
  final String userText;

  const _ChatEntry.user(this.text)
      : kind = _EntryKind.user,
        askResponse = null,
        userText = '';

  const _ChatEntry.plainAssistant(this.text)
      : kind = _EntryKind.plainAssistant,
        askResponse = null,
        userText = '';

  const _ChatEntry.askFact(AskResponse ask, {this.userText = ''})
      : kind = _EntryKind.askFact,
        text = '',
        askResponse = ask;

  const _ChatEntry.offlineRefuse()
      : kind = _EntryKind.offlineRefuse,
        text = '',
        askResponse = null,
        userText = '';

  Widget build({
    VoidCallback? onConfirmProposal,
    VoidCallback? onDismissProposal,
  }) {
    switch (kind) {
      case _EntryKind.user:
        return _textBubble(text, isUser: true);
      case _EntryKind.plainAssistant:
        return _textBubble(text, isUser: false);
      case _EntryKind.offlineRefuse:
        return Align(
          key: const Key('ask_offline_refuse'),
          alignment: Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: AppSpacing.sm),
            constraints: const BoxConstraints(maxWidth: 280),
            child: const OfflineStateView(
              state: OfflineState.unavailable,
              child: SizedBox.shrink(),
            ),
          ),
        );
      case _EntryKind.askFact:
        return _buildAskFact(onConfirmProposal, onDismissProposal);
    }
  }

  Widget _buildAskFact(
    VoidCallback? onConfirmProposal,
    VoidCallback? onDismissProposal,
  ) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: AppSpacing.sm),
        constraints: const BoxConstraints(maxWidth: 280),
        child: AskBubble(
          askResponse: askResponse!,
          onConfirm: onConfirmProposal,
          onDismiss: onDismissProposal,
        ),
      ),
    );
  }

  static Widget _textBubble(String text, {required bool isUser}) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: AppSpacing.sm),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.base,
          vertical: AppSpacing.md,
        ),
        constraints: const BoxConstraints(maxWidth: 280),
        decoration: BoxDecoration(
          color: isUser ? AppColors.primary : AppColors.card,
          borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
          border: isUser ? null : Border.all(color: AppColors.divider),
        ),
        child: Text(
          text,
          style: AppTypography.body.copyWith(
            color: isUser ? Colors.white : AppColors.ink,
          ),
        ),
      ),
    );
  }
}

class _ThinkingBubble extends StatelessWidget {
  const _ThinkingBubble();
  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: Alignment.centerLeft,
      child: Container(
        margin: const EdgeInsets.only(bottom: AppSpacing.sm),
        padding: const EdgeInsets.all(AppSpacing.md),
        decoration: BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
          border: Border.all(color: AppColors.divider),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: List.generate(3, (i) => Padding(
            padding: const EdgeInsets.symmetric(horizontal: 2),
            child: _AnimatedDot(delay: i * 150),
          )),
        ),
      ),
    );
  }
}


class _InputBar extends StatelessWidget {
  final TextEditingController controller;
  final bool enabled;
  final VoidCallback onSend;
  const _InputBar({
    required this.controller,
    required this.enabled,
    required this.onSend,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.base,
        vertical: AppSpacing.sm,
      ),
      decoration: BoxDecoration(
        color: AppColors.card,
        border: Border(top: BorderSide(color: AppColors.divider)),
      ),
      child: SafeArea(
        top: false,
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: controller,
                enabled: enabled,
                textInputAction: TextInputAction.send,
                onSubmitted: (_) => onSend(),
                decoration: InputDecoration(
                  hintText: 'Ask anything about your trip...',
                  hintStyle: AppTypography.body.copyWith(color: AppColors.muted),
                  border: InputBorder.none,
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.md,
                    vertical: AppSpacing.sm,
                  ),
                ),
                style: AppTypography.body,
              ),
            ),
            IconButton(
              onPressed: enabled ? onSend : null,
              icon: Icon(
                Icons.send_rounded,
                color: enabled ? AppColors.primary : AppColors.muted,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _AnimatedDot extends StatefulWidget {
  final int delay;
  const _AnimatedDot({required this.delay});
  @override
  State<_AnimatedDot> createState() => _AnimatedDotState();
}

class _AnimatedDotState extends State<_AnimatedDot>
    with SingleTickerProviderStateMixin {
  late final AnimationController _ctrl;
  @override
  void initState() {
    super.initState();
    _ctrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 600),
    );
    _ctrl.value = widget.delay / 600;
    _ctrl.repeat(reverse: true);
  }
  @override
  void dispose() { _ctrl.dispose(); super.dispose(); }
  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _ctrl,
      builder: (_, __) => Opacity(
        opacity: 0.3 + 0.7 * _ctrl.value,
        child: Container(
          width: 8, height: 8,
          decoration: BoxDecoration(
            color: AppColors.muted,
            shape: BoxShape.circle,
          ),
        ),
      ),
    );
  }
}
