import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:flutter/services.dart';
import 'dart:math' as math;
import '../core/destination_tz.dart';
import '../data/models.dart';
import '../features/itinerary/current_window.dart';
import '../features/itinerary/micro_location_label.dart';
import '../offline/offline_database.dart';
import '../theme/colors.dart';
import '../theme/typography.dart';
import '../theme/spacing.dart';

/// Returns the appropriate icon for a booking type (SPEC-10).
IconData _bookingIcon(String? bookingType) {
  switch (bookingType) {
    case 'flight':
      return Icons.flight_takeoff;
    case 'hotel':
      return Icons.hotel;
    case 'train':
      return Icons.train;
    case 'tour':
      return Icons.explore;
    default:
      return Icons.bookmark_border;
  }
}

/// Title-case booking type label for the badge.
String _bookingLabel(String? bookingType) {
  switch (bookingType) {
    case 'flight':
      return 'Flight';
    case 'hotel':
      return 'Hotel';
    case 'train':
      return 'Train';
    case 'tour':
      return 'Tour';
    default:
      return 'Booking';
  }
}

int _hotelNights(TripNode node) {
  final checkIn = toDestinationLocal(node.scheduledStart, node.geoRegion);
  final checkout = toDestinationLocal(
    node.scheduledStart.add(Duration(minutes: node.durationMinutes)),
    node.geoRegion,
  );
  final startDate = DateTime(checkIn.year, checkIn.month, checkIn.day);
  final endDate = DateTime(checkout.year, checkout.month, checkout.day);
  return math.max(1, endDate.difference(startDate).inDays);
}

const _weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const _months = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String _dayMonth(DateTime dt) => '${dt.day} ${_months[dt.month - 1]}';

/// Format as "Fri 2 Oct, 12:00" in destination-local.
String _dateTime(DateTime utc, String? geoRegion) {
  final local = toDestinationLocal(utc, geoRegion);
  final wd = _weekdays[local.weekday - 1];
  final dm = '${local.day} ${_months[local.month - 1]}';
  final hm = '${local.hour.toString().padLeft(2, "0")}:'
      '${local.minute.toString().padLeft(2, "0")}';
  return '$wd $dm, $hm';
}

String _hotelStaySummary(TripNode node) {
  final nights = _hotelNights(node);
  final checkout = toDestinationLocal(
    node.scheduledStart.add(Duration(minutes: node.durationMinutes)),
    node.geoRegion,
  );
  final noun = nights == 1 ? 'night' : 'nights';
  return '$nights $noun \u00b7 checkout ${_dayMonth(checkout)}';
}

/// Timeline activity card. Shows venue, time, vibe chips, transit.
/// Locked cards resist swipe (haptic + padlock shake).
class ActivityCard extends StatelessWidget {
  final TripNode node;
  final TripNode? nextNode;
  final VoidCallback? onTapSwap;
  final VoidCallback? onTapCancel;
  final VoidCallback? onTapLoved;
  final VoidCallback? onTapRecordOutcome;
  final VoidCallback? onTapEditBooking;
  final VoidCallback? onTapDeleteBooking;
  final VoidCallback? onTapDetails;
  final bool isLoved; // filled heart once the user has loved this venue
  final NodeOutcome? recordedOutcome;
  final bool isRecordingOutcome;
  final bool isContinuation; // true for repeated hotel coverage dates
  final DateTime? now; // injectable for tests

  const ActivityCard({
    super.key,
    required this.node,
    this.nextNode,
    this.onTapSwap,
    this.onTapCancel,
    this.onTapLoved,
    this.onTapRecordOutcome,
    this.isLoved = false,
    this.recordedOutcome,
    this.isRecordingOutcome = false,
    this.onTapEditBooking,
    this.onTapDeleteBooking,
    this.onTapDetails,
    this.isContinuation = false,
    this.now,
  });

  @override
  Widget build(BuildContext context) {
    final currentTime = now ?? DateTime.now();
    final isActive = nodeIsCurrentWindow(node, currentTime);
    final isCompleted = node.status == NodeStatus.completed;
    final isSkipped = node.status == NodeStatus.skipped;
    final canRecordOutcome =
        nodeCanRecordOutcome(node, currentTime, recordedOutcome);
    final friendlyLocation = friendlyMicroLocation(node.microLocation);

    return Dismissible(
      key: ValueKey(node.nodeId),
      direction: node.isLocked
          ? DismissDirection.none
          : DismissDirection.endToStart,
      confirmDismiss: (_) async {
        if (node.isLocked) {
          HapticFeedback.mediumImpact();
          return false;
        }
        onTapSwap?.call();
        return false; // handle via callback, don't remove
      },
      background: Container(
        alignment: Alignment.centerRight,
        padding: const EdgeInsets.only(right: AppSpacing.lg),
        color: AppColors.primary.withValues(alpha: 0.1),
        child: const Icon(Icons.swap_horiz, color: AppColors.primary),
      ),
      child: GestureDetector(
        onTap: onTapDetails,
        child: Container(
          margin: const EdgeInsets.symmetric(
            horizontal: AppSpacing.base,
            vertical: AppSpacing.xs,
          ),
          decoration: BoxDecoration(
            color: AppColors.card,
            borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
            border: isActive
                ? Border(left: BorderSide(color: AppColors.accent, width: 4))
                : node.isLocked
                    ? Border.all(color: AppColors.accent.withValues(alpha: 0.3))
                    : null,
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.04),
                blurRadius: 8,
                offset: const Offset(0, 2),
              ),
            ],
          ),
          child: Opacity(
            opacity: isCompleted || isSkipped ? 0.5 : 1.0,
            child: Padding(
              padding: const EdgeInsets.all(AppSpacing.base),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Time rail
                  SizedBox(
                    width: 68,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // SPEC-45 item 6: hotels show destination-local date+time
                        if (node.nodeKind == 'booking' &&
                            node.bookingType == 'hotel') ...[
                          Text(
                            'Check-in',
                            style: AppTypography.caption.copyWith(
                              color: AppColors.muted,
                              fontSize: 9,
                            ),
                          ),
                          Text(
                            _dateTime(node.scheduledStart, node.geoRegion),
                            style: AppTypography.label.copyWith(fontSize: 11),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            'Check-out',
                            style: AppTypography.caption.copyWith(
                              color: AppColors.muted,
                              fontSize: 9,
                            ),
                          ),
                          Text(
                            _dateTime(
                              node.scheduledStart
                                  .add(Duration(minutes: node.durationMinutes)),
                              node.geoRegion,
                            ),
                            style: AppTypography.label.copyWith(fontSize: 11),
                          ),
                        // SPEC-41: locked non-hotel shows exact time (no slot).
                        ] else if (node.isLocked ||
                            node.slotName == null) ...[
                          Text(
                            _formatTime(node.scheduledStart),
                            style: AppTypography.label,
                          ),
                        // SPEC-41: unlocked flexible node shows slot label only.
                        ] else ...[
                          Text(
                            _slotLabel(node.slotName!),
                            style: AppTypography.caption.copyWith(
                              color: AppColors.muted,
                              fontSize: 11,
                            ),
                            // Slot label must not wrap.
                            softWrap: false,
                            overflow: TextOverflow.clip,
                          ),
                        ],
                        // SPEC-45 R3: visible NOW badge for current stop.
                        // Applies to all card types including hotels.
                        if (isActive)
                          Container(
                            margin: const EdgeInsets.only(top: 4),
                            padding: const EdgeInsets.symmetric(
                              horizontal: 6,
                              vertical: 2,
                            ),
                            decoration: BoxDecoration(
                              color: AppColors.accent,
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              'NOW',
                              style: AppTypography.caption.copyWith(
                                color: Colors.white,
                                fontWeight: FontWeight.w700,
                                fontSize: 10,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: AppSpacing.base),
                  // Content
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Title row: venue name + lock + booking icon + swap + overflow
                        Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Expanded(
                              child: Text(
                                node.venueName,
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                                style: isSkipped
                                    ? AppTypography.h2.copyWith(
                                        decoration: TextDecoration.lineThrough)
                                    : AppTypography.h2,
                              ),
                            ),
                            if (node.isLocked)
                              Icon(Icons.lock, size: 16, color: AppColors.accent),
                            // SPEC-10: booking type icon
                            if (node.nodeKind == 'booking')
                              Padding(
                                padding: const EdgeInsets.only(left: 4),
                                child: Icon(
                                  _bookingIcon(node.bookingType),
                                  size: 16,
                                  color: AppColors.accent,
                                ),
                              ),
                            // SPEC-45 item 3: one inline Swap (44dp target)
                            if (onTapSwap != null &&
                                !node.isLocked &&
                                !isCompleted &&
                                !isSkipped)
                              SizedBox(
                                width: 44,
                                height: 44,
                                child: IconButton(
                                  icon: const Icon(Icons.swap_horiz, size: 20),
                                  color: AppColors.primary,
                                  tooltip: 'Swap this activity',
                                  padding: EdgeInsets.zero,
                                  onPressed: () {
                                    HapticFeedback.lightImpact();
                                    onTapSwap!.call();
                                  },
                                ),
                              ),
                            // SPEC-45 item 3: overflow for remaining actions
                            _buildOverflowMenu(context, isCompleted, isSkipped),
                          ],
                        ),
                        // SPEC-45 item 4: booking badge (title case, no debug chrome)
                        if (node.nodeKind == 'booking') ...[
                          Padding(
                            padding: const EdgeInsets.only(top: 4),
                            child: Container(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 8,
                                vertical: 2,
                              ),
                              decoration: BoxDecoration(
                                color: AppColors.accent.withValues(alpha: 0.1),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                _bookingLabel(node.bookingType),
                                style: AppTypography.caption.copyWith(
                                  color: AppColors.accent,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ),
                          ),
                          if (!isContinuation) ...[
                            Padding(
                              padding: const EdgeInsets.only(top: AppSpacing.xs),
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (onTapEditBooking != null)
                                    TextButton.icon(
                                      onPressed: onTapEditBooking,
                                      icon: const Icon(Icons.edit, size: 16),
                                      label: const Text('Edit'),
                                    ),
                                  if (onTapDeleteBooking != null)
                                    TextButton.icon(
                                      onPressed: onTapDeleteBooking,
                                      icon: const Icon(Icons.delete_outline, size: 16),
                                      label: const Text('Delete'),
                                      style: TextButton.styleFrom(
                                        foregroundColor: AppColors.danger,
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          ] else if (node.bookingType == 'hotel') ...[
                            Padding(
                              padding: const EdgeInsets.only(top: AppSpacing.xs),
                              child: Text(
                                'Continued stay',
                                style: AppTypography.caption.copyWith(
                                  color: AppColors.muted,
                                  fontStyle: FontStyle.italic,
                                ),
                              ),
                            ),
                          ],
                        ],
                        // SPEC-45 item 4: friendly micro_location (never snake_case)
                        if (friendlyLocation != null) ...[
                          const SizedBox(height: AppSpacing.xs),
                          Text(friendlyLocation, style: AppTypography.caption),
                        ],
                        if (node.nodeKind == 'booking' &&
                            node.bookingType == 'hotel') ...[
                          const SizedBox(height: AppSpacing.xs),
                          Text(_hotelStaySummary(node), style: AppTypography.caption),
                        ],
                        if (node.bookingNotes != null &&
                            node.bookingNotes!.isNotEmpty) ...[
                          const SizedBox(height: AppSpacing.xs),
                          Text(node.bookingNotes!, style: AppTypography.caption),
                        ],
                        // SPEC-45 item 3: max 2 vibe chips on card; rest on details.
                        if (node.vibeTags.isNotEmpty) ...[
                          const SizedBox(height: AppSpacing.sm),
                          Wrap(
                            spacing: AppSpacing.xs,
                            runSpacing: AppSpacing.xs,
                            children: [
                              ...node.vibeTags.take(2).map((tag) => _VibeChip(tag)),
                              if (node.vibeTags.length > 2)
                                _VibeChip('+${node.vibeTags.length - 2}'),
                            ],
                          ),
                        ],
                        if (recordedOutcome != null) ...[
                          const SizedBox(height: AppSpacing.sm),
                          Text(
                            recordedOutcome!.wasVisited
                                ? 'Visited'
                                : 'Skipped: ${skipReasonLabels[recordedOutcome!.reason] ?? recordedOutcome!.reason}',
                            style: AppTypography.caption.copyWith(
                              color: AppColors.ink,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ] else if (canRecordOutcome &&
                            onTapRecordOutcome != null) ...[
                          const SizedBox(height: AppSpacing.sm),
                          OutlinedButton(
                            onPressed: isRecordingOutcome
                                ? null
                                : () {
                                    HapticFeedback.lightImpact();
                                    onTapRecordOutcome!.call();
                                  },
                            child: Text(
                              isRecordingOutcome
                                  ? 'Saving outcome...'
                                  : 'Did this happen?',
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// SPEC-45 item 3: overflow menu for skip/cancel, love, driver card.
  Widget _buildOverflowMenu(
    BuildContext context,
    bool isCompleted,
    bool isSkipped,
  ) {
    final items = <PopupMenuEntry<String>>[];

    if (onTapCancel != null && !node.isLocked && !isCompleted && !isSkipped) {
      items.add(const PopupMenuItem(
        value: 'cancel',
        child: ListTile(
          leading: Icon(Icons.cancel_outlined, size: 20),
          title: Text('Skip / Cancel'),
          dense: true,
          contentPadding: EdgeInsets.zero,
        ),
      ));
    }

    if (onTapLoved != null && !isCompleted && !isSkipped) {
      items.add(PopupMenuItem(
        value: 'love',
        child: ListTile(
          leading: Icon(
            isLoved ? Icons.favorite : Icons.favorite_border,
            size: 20,
            color: isLoved ? AppColors.danger : null,
          ),
          title: Text(isLoved ? 'Loved' : 'Love this place'),
          dense: true,
          contentPadding: EdgeInsets.zero,
        ),
      ));
    }

    // Driver card -- always available
    items.add(const PopupMenuItem(
      value: 'driver',
      child: ListTile(
        leading: Icon(Icons.directions_car_outlined, size: 20),
        title: Text('Driver card'),
        dense: true,
        contentPadding: EdgeInsets.zero,
      ),
    ));

    if (items.isEmpty) return const SizedBox.shrink();

    return SizedBox(
      width: 44,
      height: 44,
      child: PopupMenuButton<String>(
        icon: const Icon(Icons.more_vert, size: 20),
        tooltip: 'More actions',
        padding: EdgeInsets.zero,
        onSelected: (value) {
          HapticFeedback.lightImpact();
          switch (value) {
            case 'cancel':
              onTapCancel?.call();
            case 'love':
              onTapLoved?.call();
            case 'driver':
              final tripId =
                  GoRouterState.of(context).pathParameters['tripId'] ?? '';
              context.push(
                '/trip/$tripId/card/${node.venueId ?? node.venueName}',
              );
          }
        },
        itemBuilder: (_) => items,
      ),
    );
  }

  String _formatTime(DateTime dt) =>
      formatDestinationTime(dt, node.geoRegion);

  /// Human-readable label for a named day slot (SPEC-41).
  String _slotLabel(String slotName) {
    switch (slotName) {
      case 'morning_tour':
        return 'Morning';
      case 'lunch':
        return 'Lunch';
      case 'afternoon_evening_tour':
        return 'Afternoon';
      case 'dinner':
        return 'Dinner';
      default:
        return slotName;
    }
  }
}

class _VibeChip extends StatelessWidget {
  final String label;
  const _VibeChip(this.label);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppColors.primaryLight,
        borderRadius: BorderRadius.circular(AppSpacing.radiusChip),
      ),
      child: Text(
        label,
        style: AppTypography.caption.copyWith(
          color: AppColors.primaryDark,
          fontSize: 11,
        ),
      ),
    );
  }
}
