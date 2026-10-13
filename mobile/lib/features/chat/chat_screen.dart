import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:uuid/uuid.dart';
import '../../core/connectivity_helper.dart';
import '../../core/destination_tz.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../offline/offline_database.dart';
import '../../render/offline_state.dart';
import 'ask_bubble.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../itinerary/itinerary_notifier.dart';
import '../itinerary/current_window.dart';

const _uuid = Uuid();

/// Natural language chat. Uses REST POST /trip/event (NO WebSocket).
/// SPEC-25 Phase C: messages persisted to device-local SQLite.
class ChatScreen extends ConsumerStatefulWidget {
  final String tripId;
  final String? initialQuestion;
  final ConnectivityHelper? connectivityOverride;
  /// Optional thread ID to open (from History).
  final String? threadId;
  const ChatScreen({
    super.key,
    required this.tripId,
    this.initialQuestion,
    this.connectivityOverride,
    this.threadId,
  });
  @override
  ConsumerState<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends ConsumerState<ChatScreen> {
  final _controller = TextEditingController();
  final _messages = <_ChatEntry>[];
  bool _isThinking = false;
  late final ConnectivityHelper _connectivity;
  String? _currentThreadId;
  bool _historyLoaded = false;

  OfflineDatabase get _db => ref.read(offlineDatabaseProvider);
  String get _identityScope => ref.read(identityCacheScopeProvider);

  @override
  void initState() {
    super.initState();
    _connectivity = widget.connectivityOverride ?? ConnectivityHelper();
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _loadThread();
      if (!mounted) return;
      final initial = widget.initialQuestion?.trim();
      if (initial != null && initial.isNotEmpty && _messages.isEmpty) {
        _send(initial);
      }
    });
  }

  /// Load the specified thread or the most recent one for this trip.
  Future<void> _loadThread() async {
    final Map<String, dynamic>? thread;
    if (widget.threadId != null) {
      // Load specific thread from History tap.
      final threads = await _db.listAskThreads(
        identityScope: _identityScope,
        tripId: widget.tripId,
      );
      thread = threads.where((t) => t['thread_id'] == widget.threadId).firstOrNull;
    } else {
      thread = await _db.getMostRecentAskThread(
        identityScope: _identityScope,
        tripId: widget.tripId,
      );
    }
    if (thread == null) {
      setState(() => _historyLoaded = true);
      return;
    }
    _currentThreadId = thread['thread_id'] as String;
    final rows = await _db.loadAskMessages(threadId: _currentThreadId!);
    final loaded = <_ChatEntry>[];
    for (final row in rows) {
      final role = row['role'] as String;
      final text = row['text'] as String;
      final envJson = row['envelope_json'] as String?;
      if (role == 'user') {
        loaded.add(_ChatEntry.user(text));
      } else if (envJson != null && envJson.isNotEmpty) {
        try {
          final ask = AskResponse.fromJson(
            jsonDecode(envJson) as Map<String, dynamic>,
          );
          loaded.add(_ChatEntry.askFact(ask, userText: text, fromHistory: true));
        } catch (_) {
          loaded.add(_ChatEntry.plainAssistant(text));
        }
      } else {
        loaded.add(_ChatEntry.plainAssistant(text));
      }
    }
    if (!mounted) return;
    setState(() {
      _messages.addAll(loaded);
      _historyLoaded = true;
    });
  }

  /// Ensure a thread exists for writing; create on first question.
  Future<String> _ensureThread(String firstQuestion) async {
    if (_currentThreadId != null) return _currentThreadId!;
    final threadId = _uuid.v4();
    final title = firstQuestion.length > 60
        ? '${firstQuestion.substring(0, 60)}...'
        : firstQuestion;
    await _db.createAskThread(
      threadId: threadId,
      identityScope: _identityScope,
      tripId: widget.tripId,
      title: title,
    );
    _currentThreadId = threadId;
    return threadId;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Chat', style: AppTypography.h2),
        actions: [
          IconButton(
            key: const Key('chat_history_action'),
            icon: const Icon(Icons.history),
            tooltip: 'History',
            onPressed: _openHistory,
          ),
          IconButton(
            key: const Key('chat_new_conversation'),
            icon: const Icon(Icons.add_comment_outlined),
            tooltip: 'New conversation',
            onPressed: _startNewConversation,
          ),
        ],
      ),
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
                      // Proposals from history are display-only: no confirm/dismiss.
                      final hasLiveProposal = entry.askResponse?.proposal != null &&
                          !entry.fromHistory;
                      return entry.build(
                        onConfirmProposal: hasLiveProposal
                            ? () => _confirmAskProposal(
                                  entry.askResponse!.proposal!,
                                  entry.userText,
                                )
                            : null,
                        onDismissProposal: hasLiveProposal
                            ? () => setState(() => _messages.remove(entry))
                            : null,
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

    // Persist user message.
    final threadId = await _ensureThread(text);
    await _db.insertAskMessage(
      messageId: _uuid.v4(),
      threadId: threadId,
      role: 'user',
      text: text,
    );

    try {
      final intent = classifyAskIntent(text);
      if (intent == AskIntent.multipleChanges) {
        const reply = 'I can safely change one stop at a time. '
            'Try "cancel next stop" or "swap next stop".';
        setState(() {
          _isThinking = false;
          _messages.add(const _ChatEntry.plainAssistant(reply));
        });
        await _db.insertAskMessage(
          messageId: _uuid.v4(),
          threadId: threadId,
          role: 'assistant',
          text: reply,
        );
        return;
      }
      final itState = ref.read(itineraryControllerProvider(widget.tripId));
      final target = nextMovableStop(
        itState.nodes,
        DateTime.now().toUtc(),
        excludedNodeIds: itState.nodeOutcomes.keys.toSet(),
      );
      if (intent != AskIntent.question && target == null) {
        const reply = 'There is no movable upcoming stop to change.';
        setState(() {
          _isThinking = false;
          _messages.add(const _ChatEntry.plainAssistant(reply));
        });
        await _db.insertAskMessage(
          messageId: _uuid.v4(),
          threadId: threadId,
          role: 'assistant',
          text: reply,
        );
        return;
      }
      if (intent == AskIntent.cancelNext) {
        final confirmed = await _confirmCancellation(target!);
        if (!mounted) return;
        if (!confirmed) {
          final reply = 'Kept ${target.venueName}.';
          setState(() {
            _isThinking = false;
            _messages.add(_ChatEntry.plainAssistant(reply));
          });
          await _db.insertAskMessage(
            messageId: _uuid.v4(),
            threadId: threadId,
            role: 'assistant',
            text: reply,
          );
          return;
        }
      }
      final eventType = switch (intent) {
        AskIntent.cancelNext => EventType.cancelActivity,
        AskIntent.swapNext => EventType.swapActivity,
        _ => EventType.askInfo,
      };

      // SPEC-25: Offline ask_info -> refuse; never enqueue.
      // Offline refusal is NOT persisted as an assistant answer.
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
        targetNodeId: target?.nodeId,
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
        final ask = result.askResponse;
        if (eventType == EventType.askInfo) {
          if (ask != null) {
            _messages.add(_ChatEntry.askFact(ask, userText: text));
            // Persist assistant envelope.
            _persistAssistantEnvelope(threadId, ask);
          } else {
            const fallback =
                'I could not complete that request. Please try again.';
            _messages.add(const _ChatEntry.plainAssistant(fallback));
            _db.insertAskMessage(
              messageId: _uuid.v4(),
              threadId: threadId,
              role: 'assistant',
              text: fallback,
            );
          }
        } else if (ask != null) {
          _messages.add(_ChatEntry.askFact(ask, userText: text));
          _persistAssistantEnvelope(threadId, ask);
        } else {
          _messages.add(_ChatEntry.plainAssistant(result.message));
          _db.insertAskMessage(
            messageId: _uuid.v4(),
            threadId: threadId,
            role: 'assistant',
            text: result.message,
          );
        }
      });
    } catch (_) {
      if (!mounted) return;
      const errorMsg =
          'I could not reach Travel Buddy. Check your connection and try again.';
      setState(() {
        _isThinking = false;
        _messages.add(const _ChatEntry.plainAssistant(errorMsg));
      });
      await _db.insertAskMessage(
        messageId: _uuid.v4(),
        threadId: threadId,
        role: 'assistant',
        text: errorMsg,
      );
    }
  }

  /// Persist an AskResponse envelope as an assistant message.
  Future<void> _persistAssistantEnvelope(
    String threadId,
    AskResponse ask,
  ) async {
    await _db.insertAskMessage(
      messageId: _uuid.v4(),
      threadId: threadId,
      role: 'assistant',
      text: ask.answer,
      envelopeJson: jsonEncode(ask.toJson()),
    );
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
    String? resolvedTarget = proposal.targetNodeId.isNotEmpty
        ? proposal.targetNodeId
        : null;
    if (resolvedTarget == null) {
      final itState = ref.read(itineraryControllerProvider(widget.tripId));
      final fallback = nextMovableStop(
        itState.nodes,
        DateTime.now().toUtc(),
        excludedNodeIds: itState.nodeOutcomes.keys.toSet(),
      );
      resolvedTarget = fallback?.nodeId;
    }
    await ref.read(tripEventProvider).sendEvent(
      tripId: widget.tripId,
      type: eventType,
      message: originalText,
      targetNodeId: resolvedTarget,
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

  /// Show the History bottom sheet listing this trip's threads.
  Future<void> _openHistory() async {
    final threads = await _db.listAskThreads(
      identityScope: _identityScope,
      tripId: widget.tripId,
    );
    if (!mounted) return;
    await showModalBottomSheet(
      context: context,
      builder: (ctx) => _ThreadHistorySheet(
        threads: threads,
        currentThreadId: _currentThreadId,
        onSelect: (threadId) {
          Navigator.pop(ctx);
          Navigator.pushReplacement(
            context,
            MaterialPageRoute(
              builder: (_) => ProviderScope(
                parent: ProviderScope.containerOf(context),
                child: ChatScreen(
                  tripId: widget.tripId,
                  threadId: threadId,
                  connectivityOverride: widget.connectivityOverride,
                ),
              ),
            ),
          );
        },
        onDelete: (threadId) async {
          final confirm = await showDialog<bool>(
            context: ctx,
            builder: (dlg) => AlertDialog(
              title: const Text('Delete conversation?'),
              content: const Text('This cannot be undone.'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(dlg, false),
                  child: const Text('Cancel'),
                ),
                TextButton(
                  onPressed: () => Navigator.pop(dlg, true),
                  child: const Text('Delete'),
                ),
              ],
            ),
          );
          if (confirm == true) {
            await _db.deleteAskThread(threadId);
            if (threadId == _currentThreadId) {
              _currentThreadId = null;
              setState(() => _messages.clear());
            }
            if (ctx.mounted) Navigator.pop(ctx);
          }
        },
      ),
    );
  }

  /// Start a fresh thread (clears current messages).
  void _startNewConversation() {
    setState(() {
      _currentThreadId = null;
      _messages.clear();
    });
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
  /// True when loaded from history (proposals are display-only).
  final bool fromHistory;

  const _ChatEntry.user(this.text)
      : kind = _EntryKind.user,
        askResponse = null,
        userText = '',
        fromHistory = false;

  const _ChatEntry.plainAssistant(this.text)
      : kind = _EntryKind.plainAssistant,
        askResponse = null,
        userText = '',
        fromHistory = false;

  const _ChatEntry.askFact(
    AskResponse ask, {
    this.userText = '',
    this.fromHistory = false,
  })  : kind = _EntryKind.askFact,
        text = '',
        askResponse = ask;

  const _ChatEntry.offlineRefuse()
      : kind = _EntryKind.offlineRefuse,
        text = '',
        askResponse = null,
        userText = '',
        fromHistory = false;

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

/// SPEC-25 Phase C: Thread History bottom sheet.
class _ThreadHistorySheet extends StatelessWidget {
  final List<Map<String, dynamic>> threads;
  final String? currentThreadId;
  final void Function(String threadId) onSelect;
  final void Function(String threadId) onDelete;

  const _ThreadHistorySheet({
    required this.threads,
    required this.currentThreadId,
    required this.onSelect,
    required this.onDelete,
  });

  @override
  Widget build(BuildContext context) {
    if (threads.isEmpty) {
      return const SizedBox(
        height: 120,
        child: Center(child: Text('No conversations yet.')),
      );
    }
    return ListView.builder(
      key: const Key('thread_history_list'),
      shrinkWrap: true,
      itemCount: threads.length,
      itemBuilder: (_, i) {
        final t = threads[i];
        final threadId = t['thread_id'] as String;
        final title = t['title'] as String;
        final updatedAt = t['updated_at'] as String;
        final isCurrent = threadId == currentThreadId;
        return ListTile(
          title: Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: isCurrent
                ? AppTypography.body.copyWith(fontWeight: FontWeight.bold)
                : AppTypography.body,
          ),
          subtitle: Text(updatedAt, style: AppTypography.caption),
          trailing: IconButton(
            key: Key('delete_thread_$threadId'),
            icon: const Icon(Icons.delete_outline, size: 20),
            onPressed: () => onDelete(threadId),
          ),
          onTap: () => onSelect(threadId),
        );
      },
    );
  }
}
