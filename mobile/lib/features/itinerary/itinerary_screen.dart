import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/activity_card.dart';
import '../booking/add_booking_sheet.dart';
import '../chat/ask_entry_bar.dart';
import '../swap_sheet/swap_sheet.dart';
import '../../widgets/reroute_badge.dart';
import '../../widgets/shimmer_card.dart';
import '../../widgets/error_view.dart';
import 'current_window.dart';
import 'date_scope.dart';
import '../../widgets/city_section.dart';
import 'itinerary_notifier.dart';
import 'replacement_ref.dart';
import '../alerts/alerts_notifier.dart';
import '../../widgets/alert_card.dart';
import '../../widgets/departure_banner.dart';
import '../notifications/departure_notifier.dart';

Map<String, dynamic> preferencesForConfirmedSwap(
  TripNode original,
  VenueSearchResult replacement,
) => {
  'replacement_venue_id': replacement.venueId,
  'vibe_tags': original.vibeTags,
};

/// The hero screen — live timeline of activity cards.
///
/// Reflow strategy: a keyed ListView driven directly by controller state.
/// Each row is keyed by a content-signature, so when the backend returns an
/// updated itinerary (swap / cancel / reroute / time-shift) Flutter rebuilds
/// exactly the changed rows. This is intentionally NOT a hand-rolled
/// AnimatedList diff — that approach had an index-desync crash on the in-place
/// swap/cancel path. Data is always correct here; slide choreography can be
/// layered on later (per-card AnimatedSwitcher / flutter_animate) once it can
/// be verified on a real device.
class ItineraryScreen extends ConsumerWidget {
  final String tripId;
  final String? focusNodeId;
  const ItineraryScreen({
    super.key,
    required this.tripId,
    this.focusNodeId,
  });

  String _sig(TripNode n) =>
      '${n.nodeId}|${n.venueId}|${n.venueName}|${n.scheduledStart.toIso8601String()}|${n.status.name}|${n.isLocked}|${n.bookingNotes}|${n.bookingType}';

  /// SPEC-07: Open the swap sheet. No swap_activity until the traveller
  /// confirms a suggestion. Dismiss emits reroute_rejected.
  Future<void> _swap(BuildContext context, WidgetRef ref, TripNode node) async {
    final state = ref.read(itineraryControllerProvider(tripId));
    final tripState = _tripStateForCoords(state, node);
    final sheet = SwapSheet(
      tripId: tripId,
      targetNodeId: node.nodeId,
      tripState: tripState,
    );

    final venue = await showModalBottomSheet<VenueSearchResult>(
      context: context,
      isScrollControlled: true,
      builder: (_) => sheet,
    );

    if (!context.mounted) return;

    final placeRef = node.venueId ?? node.venueName;

    if (venue != null) {
      // --- Confirm path ---
      final result = await ref
          .read(itineraryControllerProvider(tripId).notifier)
          .applyEvent(
            type: EventType.swapActivity,
            message: 'Swap ${node.venueName} for ${venue.name}',
            targetNodeId: node.nodeId,
            preferences: preferencesForConfirmedSwap(node, venue),
          );
      if (result != null && result.updatedNodes.isNotEmpty) {
        final replacement = replacementRefForSwap(
          originalNodeId: node.nodeId,
          originalVenueKey: placeRef,
          updatedNodes: result.updatedNodes,
        );
        ref
            .read(signalServiceProvider)
            .emitRerouteAccepted(
              placeRef: placeRef,
              replacementRef: replacement,
              tripId: tripId,
            );
      }
    } else {
      // --- Dismiss path ---
      final offeredIds = sheet.offeredVenueIds;
      if (offeredIds.isNotEmpty) {
        ref
            .read(signalServiceProvider)
            .emitRerouteRejected(
              placeRef: placeRef,
              rejectedRefs: offeredIds,
              tripId: tripId,
            );
      }
    }
  }

  /// Build a TripState with coords for SwapSheet venue search.
  ///
  /// Uses the [targetNode] coordinates so corridor swaps search the
  /// correct city, not the first segment location.
  TripState _tripStateForCoords(ItineraryState state, TripNode targetNode) {
    return TripState(
      tripId: tripId,
      userId: '',
      nodes: state.nodes,
      geoRegion: targetNode.geoRegion,
      locationLat: targetNode.lat,
      locationLng: targetNode.lng,
    );
  }

  Future<void> _cancel(
    BuildContext context,
    WidgetRef ref,
    TripNode node,
  ) async {
    if (node.isLocked) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Cancel this activity?'),
        content: Text('${node.venueName} will be marked as skipped.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Cancel activity'),
          ),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      final reason = await showModalBottomSheet<String>(
        context: context,
        builder: (_) => const _SkipReasonSheet(),
      );
      if (reason == null || !context.mounted) return;
      await ref
          .read(itineraryControllerProvider(tripId).notifier)
          .applyEvent(
            type: EventType.cancelActivity,
            message: 'Cancel ${node.venueName} ($reason)',
            targetNodeId: node.nodeId,
          );
    }
  }

  void _editBooking(BuildContext context, TripNode node) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => AddBookingSheet(tripId: tripId, editNode: node),
    );
  }

  Future<void> _deleteBooking(
    BuildContext context,
    WidgetRef ref,
    TripNode node,
  ) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Delete booking?'),
        content: Text('Remove ${node.venueName} from your itinerary?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Keep'),
          ),
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: TextButton.styleFrom(foregroundColor: AppColors.danger),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed == true && context.mounted) {
      await ref
          .read(itineraryControllerProvider(tripId).notifier)
          .applyEvent(
            type: EventType.deleteBooking,
            message: 'Delete ${node.venueName}',
            targetNodeId: node.nodeId,
          );
    }
  }

  Future<void> _showOutcomePicker(
    BuildContext context,
    WidgetRef ref,
    TripNode node,
  ) async {
    final decision = await showModalBottomSheet<_OutcomeDecision>(
      context: context,
      builder: (_) => const _OutcomeSheet(),
    );
    if (decision == null || !context.mounted) return;

    final controller = ref.read(itineraryControllerProvider(tripId).notifier);
    if (decision == _OutcomeDecision.visited) {
      await controller.recordVisited(node);
      return;
    }

    final reason = await showModalBottomSheet<String>(
      context: context,
      builder: (_) => const _SkipReasonSheet(),
    );
    if (reason != null) {
      await controller.recordSkipped(node, reason);
    }
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    // Reroute-limit → push upgrade once, then clear the flag.
    ref.listen<ItineraryState>(itineraryControllerProvider(tripId), (
      prev,
      next,
    ) {
      if (next.rerouteLimitHit) {
        ref
            .read(itineraryControllerProvider(tripId).notifier)
            .clearRerouteLimit();
        context.push('/upgrade');
      }
    });

    // SPEC-29: Refresh alerts on screen open (provider auto-fetches on build).
    // Manual refresh + app-resume handled via _AlertsSection.

    final state = ref.watch(itineraryControllerProvider(tripId));

    return Scaffold(
      appBar: AppBar(
        title: Text('Your Trip', style: AppTypography.h2),
        actions: [
          IconButton(
            icon: const Icon(Icons.bookmark_add_outlined),
            tooltip: 'Add Booking',
            onPressed: () {
              showModalBottomSheet(
                context: context,
                isScrollControlled: true,
                builder: (_) => AddBookingSheet(tripId: tripId),
              );
            },
          ),
          RerouteBadge(onUpgradeTap: () => context.push('/upgrade')),
          const SizedBox(width: AppSpacing.base),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => context.push('/trip/$tripId/chat'),
        backgroundColor: AppColors.primary,
        child: const Icon(Icons.chat_bubble_outline, color: Colors.white),
      ),
      bottomNavigationBar: AskEntryBar(
        enabled: !state.processing,
        onSubmit: (question) => context.push(
          '/trip/$tripId/chat?q=${Uri.encodeQueryComponent(question)}',
        ),
      ),
      body: state.loading
          ? const ShimmerList(count: 5)
          : state.error != null
          ? ErrorView(
              error: state.error!,
              onRetry: () =>
                  ref.read(itineraryControllerProvider(tripId).notifier).load(),
            )
          : Column(
              children: [
                // Slim progress bar while an event is in flight (heavy calls).
                if (state.processing)
                  const LinearProgressIndicator(minHeight: 2),
                // "Heads up: ..." scheduler note from the last event.
                if (state.banner != null)
                  _HeadsUpBanner(
                    text: state.banner!,
                    onClose: () => ref
                        .read(itineraryControllerProvider(tripId).notifier)
                        .clearBanner(),
                  ),
                // SPEC-37: Compact schedule warnings summary.
                if (state.scheduleWarnings.isNotEmpty)
                  _ScheduleWarningsBanner(
                    warnings: state.scheduleWarnings,
                    onDismiss: () => ref
                        .read(itineraryControllerProvider(tripId).notifier)
                        .clearScheduleWarnings(),
                  ),
                // SPEC-29: Context alerts above timeline.
                // Non-blocking: itinerary shows immediately; alerts
                // render when available (no spinner replacement).
                ItineraryAlertsSection(
                  tripId: tripId,
                  onScrollToNode: (nodeId) => context.go(
                    '/trip/$tripId?focus=${Uri.encodeQueryComponent(nodeId)}',
                  ),
                  onReviewAlternatives: (nodeId) {
                    final node = state.nodes
                        .where((candidate) => candidate.nodeId == nodeId)
                        .firstOrNull;
                    if (node != null && !node.isLocked) {
                      _swap(context, ref, node);
                    }
                  },
                ),
                Expanded(
                  child: state.segments.isNotEmpty
                          ? _CorridorTimeline(
                              nodes: state.nodes,
                              segments: state.segments,
                              state: state,
                              focusNodeId: focusNodeId,
                              onSwap: (node) => _swap(context, ref, node),
                              onCancel: (node) => _cancel(context, ref, node),
                              onOutcome: (node) =>
                                  _showOutcomePicker(context, ref, node),
                              onLoved: (node) {
                                final placeRef =
                                    node.venueId ?? node.venueName;
                                ref
                                    .read(signalServiceProvider)
                                    .emitUserLoved(
                                      placeRef: placeRef,
                                      tripId: tripId,
                                    );
                                ref
                                    .read(
                                      itineraryControllerProvider(tripId)
                                          .notifier,
                                    )
                                    .markLoved(placeRef);
                              },
                              onEditBooking: (node) =>
                                  _editBooking(context, node),
                              onDeleteBooking: (node) =>
                                  _deleteBooking(context, ref, node),
                              sig: _sig,
                            )
                          : (state.nodes.isEmpty && state.creationContext == null)
                          ? Center(
                              child: Text(
                                'No activities yet.',
                                style: AppTypography.body.copyWith(
                                  color: AppColors.muted,
                                ),
                              ),
                            )
                          : _FocusedDateScopedTimeline(
                              nodes: state.nodes,
                              state: state,
                              creationContext: state.creationContext,
                              focusNodeId: focusNodeId,
                              onSwap: (node) => _swap(context, ref, node),
                              onCancel: (node) => _cancel(context, ref, node),
                              onOutcome: (node) =>
                                  _showOutcomePicker(context, ref, node),
                              onLoved: (node) {
                                final placeRef =
                                    node.venueId ?? node.venueName;
                                ref
                                    .read(signalServiceProvider)
                                    .emitUserLoved(
                                      placeRef: placeRef,
                                      tripId: tripId,
                                    );
                                ref
                                    .read(
                                      itineraryControllerProvider(tripId)
                                          .notifier,
                                    )
                                    .markLoved(placeRef);
                              },
                              onEditBooking: (node) =>
                                  _editBooking(context, node),
                              onDeleteBooking: (node) =>
                                  _deleteBooking(context, ref, node),
                              sig: _sig,
                            ),
                ),
              ],
            ),
    );
  }
}

/// SPEC-31: Flattened date-grouped timeline.
///
/// Builds a single ListView of date-header and ActivityCard items.
/// The `nextNode` spans across date boundaries so the last card in one day
/// still receives the first card of the next day.

/// SPEC-36: Corridor-aware timeline that groups nodes by city segment.
class _CorridorTimeline extends StatefulWidget {
  final List<TripNode> nodes;
  final List<TripSegment> segments;
  final ItineraryState state;
  final String? focusNodeId;
  final void Function(TripNode) onSwap;
  final void Function(TripNode) onCancel;
  final void Function(TripNode) onOutcome;
  final void Function(TripNode) onLoved;
  final void Function(TripNode) onEditBooking;
  final void Function(TripNode) onDeleteBooking;
  final String Function(TripNode) sig;

  const _CorridorTimeline({
    required this.nodes,
    required this.segments,
    required this.state,
    this.focusNodeId,
    required this.onSwap,
    required this.onCancel,
    required this.onOutcome,
    required this.onLoved,
    required this.onEditBooking,
    required this.onDeleteBooking,
    required this.sig,
  });

  @override
  State<_CorridorTimeline> createState() => _CorridorTimelineState();
}

class _CorridorTimelineState extends State<_CorridorTimeline> {
  final Map<String, GlobalKey> _nodeKeys = {};
  String? _lastFocusedNodeId;

  @override
  void initState() {
    super.initState();
    _scheduleFocus();
  }

  @override
  void didUpdateWidget(covariant _CorridorTimeline oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusNodeId != widget.focusNodeId ||
        oldWidget.nodes != widget.nodes) {
      _scheduleFocus();
    }
  }

  void _scheduleFocus([int attempt = 0]) {
    final nodeId = widget.focusNodeId;
    if (nodeId == null || nodeId == _lastFocusedNodeId) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final target = _nodeKeys[nodeId]?.currentContext;
      if (target == null) return;
      final renderObject = target.findRenderObject();
      if (renderObject is! RenderBox ||
          !renderObject.hasSize ||
          renderObject.size.height == 0) {
        if (attempt < 3) {
          _scheduleFocus(attempt + 1);
          WidgetsBinding.instance.scheduleFrame();
        }
        return;
      }
      _lastFocusedNodeId = nodeId;
      Scrollable.ensureVisible(
        target,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
        alignment: 0.08,
      );
    });
  }

  @override
  Widget build(BuildContext context) {
    // SPEC-42: use segment dates for full-span corridor rendering.
    final cityGroups = spanAwareCorridorGroups(
      nodes: widget.nodes,
      segments: widget.segments,
    );
    return SingleChildScrollView(
      padding: const EdgeInsets.only(bottom: 120),
      child: Column(
        children: List.generate(
          cityGroups.length,
          (index) => _buildCitySection(
            cityGroups,
            index,
            widget.focusNodeId,
          ),
        ),
      ),
    );
  }

  Widget _buildCitySection(
    List<CorridorCityGroup> cityGroups,
    int index,
    String? focusedNodeId,
  ) {
    final group = cityGroups[index];
    final containsFocusedNode = focusedNodeId != null &&
        group.dayGroups
            .expand((dayGroup) => dayGroup.nodes)
            .any((node) => node.nodeId == focusedNodeId);
    TripNode? nextCityFirst;
    if (index + 1 < cityGroups.length) {
      final nextNodes = cityGroups[index + 1]
          .dayGroups
          .expand((dayGroup) => dayGroup.nodes)
          .toList();
      if (nextNodes.isNotEmpty) nextCityFirst = nextNodes.first;
    }
    return CitySection(
      key: ValueKey(group.geoRegion),
      cityGroup: group,
      forceExpanded: containsFocusedNode,
      childBuilder: (cityGroup) => _DateScopedTimeline(
        nodes: cityGroup.dayGroups.expand((dayGroup) => dayGroup.nodes).toList(),
        state: widget.state,
        onSwap: widget.onSwap,
        onCancel: widget.onCancel,
        onOutcome: widget.onOutcome,
        onLoved: widget.onLoved,
        onEditBooking: widget.onEditBooking,
        onDeleteBooking: widget.onDeleteBooking,
        sig: widget.sig,
        isCorridor: true,
        globalNextNode: nextCityFirst,
        nodeKeys: _nodeKeys,
      ),
    );
  }
}

class _FocusedDateScopedTimeline extends StatefulWidget {
  final List<TripNode> nodes;
  final ItineraryState state;
  final CreationContext? creationContext;
  final String? focusNodeId;
  final void Function(TripNode) onSwap;
  final void Function(TripNode) onCancel;
  final void Function(TripNode) onOutcome;
  final void Function(TripNode) onLoved;
  final void Function(TripNode) onEditBooking;
  final void Function(TripNode) onDeleteBooking;
  final String Function(TripNode) sig;

  const _FocusedDateScopedTimeline({
    required this.nodes,
    required this.state,
    this.creationContext,
    this.focusNodeId,
    required this.onSwap,
    required this.onCancel,
    required this.onOutcome,
    required this.onLoved,
    required this.onEditBooking,
    required this.onDeleteBooking,
    required this.sig,
  });

  @override
  State<_FocusedDateScopedTimeline> createState() =>
      _FocusedDateScopedTimelineState();
}

class _FocusedDateScopedTimelineState
    extends State<_FocusedDateScopedTimeline> {
  final Map<String, GlobalKey> _nodeKeys = {};
  String? _lastFocusedNodeId;

  @override
  void initState() {
    super.initState();
    _scheduleFocus();
  }

  @override
  void didUpdateWidget(covariant _FocusedDateScopedTimeline oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.focusNodeId != widget.focusNodeId ||
        oldWidget.nodes != widget.nodes) {
      _scheduleFocus();
    }
  }

  void _scheduleFocus([int attempt = 0]) {
    final nodeId = widget.focusNodeId;
    if (nodeId == null || nodeId == _lastFocusedNodeId) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final target = _nodeKeys[nodeId]?.currentContext;
      if (target == null) return;
      final renderObject = target.findRenderObject();
      if (renderObject is! RenderBox ||
          !renderObject.hasSize ||
          renderObject.size.height == 0) {
        if (attempt < 3) {
          _scheduleFocus(attempt + 1);
          WidgetsBinding.instance.scheduleFrame();
        }
        return;
      }
      _lastFocusedNodeId = nodeId;
      Scrollable.ensureVisible(
        target,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
        alignment: 0.08,
      );
    });
  }

  @override
  Widget build(BuildContext context) => _DateScopedTimeline(
        nodes: widget.nodes,
        state: widget.state,
        creationContext: widget.creationContext,
        onSwap: widget.onSwap,
        onCancel: widget.onCancel,
        onOutcome: widget.onOutcome,
        onLoved: widget.onLoved,
        onEditBooking: widget.onEditBooking,
        onDeleteBooking: widget.onDeleteBooking,
        sig: widget.sig,
        nodeKeys: _nodeKeys,
      );
}

class _DateScopedTimeline extends StatelessWidget {
  final List<TripNode> nodes;
  final ItineraryState state;
  final CreationContext? creationContext;
  final void Function(TripNode) onSwap;
  final void Function(TripNode) onCancel;
  final void Function(TripNode) onOutcome;
  final void Function(TripNode) onLoved;
  final void Function(TripNode) onEditBooking;
  final void Function(TripNode) onDeleteBooking;
  final String Function(TripNode) sig;
  final bool isCorridor;
  final TripNode? globalNextNode;
  final Map<String, GlobalKey>? nodeKeys;

  const _DateScopedTimeline({
    required this.nodes,
    required this.state,
    this.creationContext,
    required this.onSwap,
    required this.onCancel,
    required this.onOutcome,
    required this.onLoved,
    required this.onEditBooking,
    required this.onDeleteBooking,
    required this.sig,
    this.isCorridor = false,
    this.globalNextNode,
    this.nodeKeys,
  });

  @override
  Widget build(BuildContext context) {
    // SPEC-42: render every date in the trip span, including empty days.
    final List<ItineraryDayGroup> groups;
    final ctx = creationContext;
    if (!isCorridor &&
        ctx != null &&
        ctx.startDateLocal != null &&
        ctx.endDateLocal != null) {
      groups = spanAwareDayGroups(
        nodes: nodes,
        startLocal: DateTime.parse(ctx.startDateLocal!),
        endLocal: DateTime.parse(ctx.endDateLocal!),
      );
    } else {
      groups = groupNodesByCalendarDate(nodes);
    }

    // Build a flat list of view items: headers + cards.
    final items = <_TimelineItem>[];
    for (final group in groups) {
      items.add(_TimelineItem.header(group.date));
      if (group.nodes.isEmpty) {
        items.add(_TimelineItem.emptyDay());
      } else {
        for (final node in group.nodes) {
          items.add(_TimelineItem.card(node));
        }
      }
    }

    final children = List<Widget>.generate(items.length, (i) {
        final item = items[i];
        if (item.isHeader) {
          return _DateHeader(date: item.date!);
        }
        if (item.isEmptyDay) {
          return const _EmptyDayCard();
        }
        final node = item.node!;
        // nextNode: next card-type item in the flat list (skipping headers),
        // which crosses date boundaries.
        TripNode? next;
        for (var j = i + 1; j < items.length; j++) {
          if (!items[j].isHeader && !items[j].isEmptyDay) {
            next = items[j].node;
            break;
          }
        }
        // Cross-city boundary: use globally-ordered next from corridor.
        next ??= globalNextNode;

        return KeyedSubtree(
          key: nodeKeys?.putIfAbsent(node.nodeId, () => GlobalKey()),
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder: (child, anim) =>
                FadeTransition(opacity: anim, child: child),
            child: ActivityCard(
              key: ValueKey(
                '${sig(node)}|'
                '${state.lovedPlaceRefs.contains(node.venueId ?? node.venueName)}|'
                '${state.nodeOutcomes[node.nodeId]?.outcome}|'
                '${state.nodeOutcomes[node.nodeId]?.reason}|'
                '${state.outcomeRecordingNodeIds.contains(node.nodeId)}',
              ),
              node: node,
              nextNode: next,
              isLoved: state.lovedPlaceRefs.contains(
                node.venueId ?? node.venueName,
              ),
              recordedOutcome: state.nodeOutcomes[node.nodeId],
              isRecordingOutcome: state.outcomeRecordingNodeIds.contains(
                node.nodeId,
              ),
              onTapSwap: state.processing ? null : () => onSwap(node),
              onTapCancel: state.processing ? null : () => onCancel(node),
              onTapEditBooking:
                  (!state.processing && node.nodeKind == 'booking')
                      ? () => onEditBooking(node)
                      : null,
              onTapDeleteBooking:
                  (!state.processing && node.nodeKind == 'booking')
                      ? () => onDeleteBooking(node)
                      : null,
              onTapRecordOutcome:
                  state.processing ? null : () => onOutcome(node),
              onTapLoved: () => onLoved(node),
            ),
          ),
        );
      });
    final content = Column(children: children);
    if (isCorridor) {
      return Padding(
        padding: const EdgeInsets.only(
          top: AppSpacing.base,
          bottom: 100,
        ),
        child: content,
      );
    }
    return SingleChildScrollView(
      padding: const EdgeInsets.only(
        top: AppSpacing.base,
        bottom: 100,
      ),
      child: content,
    );
  }
}

/// A flat-list item: date header, node card, or empty-day marker.
class _TimelineItem {
  final DateTime? date;
  final TripNode? node;
  final bool isEmptyDay;

  const _TimelineItem._({this.date, this.node, this.isEmptyDay = false});

  factory _TimelineItem.header(DateTime date) => _TimelineItem._(date: date);
  factory _TimelineItem.card(TripNode node) => _TimelineItem._(node: node);
  factory _TimelineItem.emptyDay() =>
      const _TimelineItem._(isEmptyDay: true);

  bool get isHeader => date != null && !isEmptyDay;
}

/// SPEC-42: placeholder for an empty day in a sparse itinerary.
class _EmptyDayCard extends StatelessWidget {
  const _EmptyDayCard();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(
        horizontal: AppSpacing.base,
        vertical: AppSpacing.sm,
      ),
      child: Text(
        'Open day',
        style: Theme.of(context)
            .textTheme
            .bodySmall
            ?.copyWith(color: Colors.grey),
      ),
    );
  }
}

/// Calendar-date section header.
class _DateHeader extends StatelessWidget {
  final DateTime date;
  const _DateHeader({required this.date});

  static const _weekdays = [
    'Monday',
    'Tuesday',
    'Wednesday',
    'Thursday',
    'Friday',
    'Saturday',
    'Sunday',
  ];

  static const _months = [
    'January',
    'February',
    'March',
    'April',
    'May',
    'June',
    'July',
    'August',
    'September',
    'October',
    'November',
    'December',
  ];

  @override
  Widget build(BuildContext context) {
    final weekday = _weekdays[date.weekday - 1];
    final day = date.day;
    final month = _months[date.month - 1];
    final year = date.year;
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        AppSpacing.base,
        AppSpacing.lg,
        AppSpacing.base,
        AppSpacing.sm,
      ),
      child: Text(
        '$weekday, $day $month $year',
        style: AppTypography.label.copyWith(color: AppColors.muted),
      ),
    );
  }
}

/// SPEC-37: Compact schedule warnings.  Shows "N schedule issues - Review"
/// and opens a bottom sheet with the full list on tap.
class _ScheduleWarningsBanner extends StatelessWidget {
  final List<String> warnings;
  final VoidCallback? onDismiss;
  const _ScheduleWarningsBanner({required this.warnings, this.onDismiss});

  @override
  Widget build(BuildContext context) {
    final count = warnings.length;
    final label = count == 1
        ? '1 schedule issue'
        : '$count schedule issues';
    return GestureDetector(
      onTap: () => _showWarningsSheet(context),
      child: Container(
        width: double.infinity,
        color: AppColors.accent.withValues(alpha: 0.08),
        padding: const EdgeInsets.symmetric(
          horizontal: AppSpacing.base,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: [
            const Icon(Icons.warning_amber_rounded, size: 18, color: AppColors.accent),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                '$label \u2013 Review',
                style: AppTypography.caption.copyWith(
                  color: AppColors.accent,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
            const Icon(Icons.chevron_right, size: 18, color: AppColors.accent),
            if (onDismiss != null)
              IconButton(
                icon: const Icon(Icons.close, size: 16),
                onPressed: onDismiss,
                visualDensity: VisualDensity.compact,
                padding: EdgeInsets.zero,
                constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              ),
          ],
        ),
      ),
    );
  }

  void _showWarningsSheet(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
      ),
      isScrollControlled: true,
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.4,
        maxChildSize: 0.8,
        minChildSize: 0.2,
        expand: false,
        builder: (_, scrollController) => Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: ListView(
            controller: scrollController,
            shrinkWrap: true,
            children: [
              Text('Schedule Issues', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.base),
              for (final w in warnings) ...[
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text('\u2022 ', style: TextStyle(fontSize: 14)),
                    Expanded(
                      child: Text(w, style: AppTypography.body),
                    ),
                  ],
                ),
                const SizedBox(height: AppSpacing.sm),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _HeadsUpBanner extends StatelessWidget {
  final String text;
  final VoidCallback onClose;
  const _HeadsUpBanner({required this.text, required this.onClose});

  @override
  Widget build(BuildContext context) => Container(
    width: double.infinity,
    color: AppColors.accent.withValues(alpha: 0.12),
    padding: const EdgeInsets.symmetric(
      horizontal: AppSpacing.base,
      vertical: AppSpacing.sm,
    ),
    child: Row(
      children: [
        const Icon(Icons.info_outline, size: 18, color: AppColors.accent),
        const SizedBox(width: AppSpacing.sm),
        Expanded(child: Text(text, style: AppTypography.caption)),
        IconButton(
          icon: const Icon(Icons.close, size: 16),
          onPressed: onClose,
          visualDensity: VisualDensity.compact,
        ),
      ],
    ),
  );
}

/// SPEC-07: Bottom sheet presenting the closed set of skip reasons.
/// Returns the selected reason string or null if dismissed.
class _SkipReasonSheet extends StatelessWidget {
  const _SkipReasonSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView(
        shrinkWrap: true,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.base),
            child: Text('Why are you skipping?', style: AppTypography.h2),
          ),
          ...skipReasonLabels.entries.map(
            (e) => ListTile(
              leading: const Icon(Icons.arrow_forward_ios, size: 14),
              title: Text(e.value),
              onTap: () => Navigator.pop(context, e.key),
            ),
          ),
          const SizedBox(height: AppSpacing.base),
        ],
      ),
    );
  }
}

enum _OutcomeDecision { visited, skipped }

class _OutcomeSheet extends StatelessWidget {
  const _OutcomeSheet();

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.all(AppSpacing.base),
            child: Text('Did this happen?', style: AppTypography.h2),
          ),
          ListTile(
            leading: const Icon(Icons.check_circle_outline),
            title: const Text('Yes, I went'),
            onTap: () => Navigator.pop(context, _OutcomeDecision.visited),
          ),
          ListTile(
            leading: const Icon(Icons.skip_next),
            title: const Text('No, I skipped it'),
            onTap: () => Navigator.pop(context, _OutcomeDecision.skipped),
          ),
          ListTile(
            leading: const Icon(Icons.schedule),
            title: const Text('Not sure yet'),
            onTap: () => Navigator.pop(context),
          ),
          const SizedBox(height: AppSpacing.base),
        ],
      ),
    );
  }
}

/// SPEC-29: Non-blocking alert section above the timeline.
///
/// Renders alert cards when data is available. Does NOT show a spinner
/// or replace the itinerary while loading.
class ItineraryAlertsSection extends ConsumerStatefulWidget {
  final String tripId;
  final void Function(String nodeId)? onScrollToNode;
  final void Function(String nodeId)? onReviewAlternatives;
  const ItineraryAlertsSection({
    super.key,
    required this.tripId,
    this.onScrollToNode,
    this.onReviewAlternatives,
  });

  @override
  ConsumerState<ItineraryAlertsSection> createState() =>
      _ItineraryAlertsSectionState();
}

class _ItineraryAlertsSectionState extends ConsumerState<ItineraryAlertsSection>
    with WidgetsBindingObserver {
  late DateTime _lastRefreshAttempt;

  @override
  void initState() {
    super.initState();
    _lastRefreshAttempt = DateTime.now();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final now = DateTime.now();
    if (state == AppLifecycleState.resumed &&
        alertResumeRefreshDue(_lastRefreshAttempt, now)) {
      _lastRefreshAttempt = now;
      // Refresh both alerts and departure notifications with same debounce.
      ref.read(alertsNotifierProvider(widget.tripId).notifier).refresh();
      ref.read(departureNotifierProvider(widget.tripId).notifier).refresh();
    }
  }

  @override
  Widget build(BuildContext context) {
    final alertsAsync = ref.watch(alertsNotifierProvider(widget.tripId));
    final departureAsync = ref.watch(departureNotifierProvider(widget.tripId));

    final departureState = departureAsync.valueOrNull;
    final departureBanner = departureState?.visible;
    final hasDeparture = departureBanner != null;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        // SPEC-35: Departure banner above weather cards.
        if (hasDeparture)
          DepartureBanner(
            candidate: departureBanner,
            onDismiss: () => ref
                .read(departureNotifierProvider(widget.tripId).notifier)
                .dismiss(departureBanner.notificationId),
            onTapNodeId: widget.onScrollToNode,
          ),
        // SPEC-29 weather cards: hidden while departure banner is visible.
        if (!hasDeparture)
          alertsAsync.when(
            loading: () => const SizedBox.shrink(),
            error: (_, __) => const SizedBox.shrink(),
            data: (alertsState) {
              final visible = alertsState.visible;
              if (visible.isEmpty) return const SizedBox.shrink();
              return Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  for (final alert in visible)
                    AlertCard(
                      alert: alert,
                      onViewStop: alert.affectedNodeIds.isEmpty ||
                              widget.onScrollToNode == null
                          ? null
                          : () => widget.onScrollToNode!(
                                alert.affectedNodeIds.first,
                              ),
                      onReviewAlternatives:
                          alert.suggestedAction == 'review_outdoor_plans' &&
                                  alert.affectedNodeIds.isNotEmpty &&
                                  widget.onReviewAlternatives != null
                              ? () => widget.onReviewAlternatives!(
                                    alert.affectedNodeIds.first,
                                  )
                              : null,
                      onDismiss: () => ref
                          .read(alertsNotifierProvider(widget.tripId).notifier)
                          .dismiss(alert.alertId),
                    ),
                ],
              );
            },
          ),
        // Shared refresh button: refreshes both alerts and notifications.
        if (hasDeparture ||
            (alertsAsync.valueOrNull?.visible.isNotEmpty ?? false))
          Align(
            alignment: Alignment.centerRight,
            child: IconButton(
              icon: (alertsAsync.valueOrNull?.loading ?? false)
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : const Icon(Icons.refresh, size: 18),
              tooltip: 'Refresh alerts',
              onPressed: (alertsAsync.valueOrNull?.loading ?? false)
                  ? null
                  : () {
                      ref
                          .read(alertsNotifierProvider(widget.tripId).notifier)
                          .refresh();
                      ref
                          .read(
                            departureNotifierProvider(widget.tripId).notifier,
                          )
                          .refresh();
                    },
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
          ),
      ],
    );
  }
}
