import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../data/models.dart';
import '../itinerary/date_scope.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import '../booking/add_booking_sheet.dart';

/// Finds the best accommodation for Hotel Rescue using date-aware selection.
///
/// Delegates to `selectRescueStay` which applies the SPEC-31 precedence:
/// active stay, then earliest future, then most recently elapsed.
/// `now` defaults to `DateTime.now()` for production; tests inject it.
TripNode? findHotelNode(List<TripNode> nodes, {DateTime? now}) {
  return selectRescueStay(nodes, now ?? DateTime.now());
}

/// Helper to execute <= 2-tap hotel rescue navigation.
void openHotelRescue(
  BuildContext context, {
  required String tripId,
  required List<TripNode> nodes,
}) {
  final hotel = findHotelNode(nodes);
  if (hotel != null) {
    // 1-tap direct path: open full-screen driver card for the hotel
    final placeRef = hotel.venueId ?? hotel.venueName;
    context.push('/trip/$tripId/card/$placeRef');
  } else {
    // 2-tap path: show rescue sheet with honest empty state & add hotel action
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (_) => HotelRescueSheet(tripId: tripId, availableNodes: nodes),
    );
  }
}

/// Honest, calm emergency sheet when no hotel is saved yet.
class HotelRescueSheet extends StatelessWidget {
  final String tripId;
  final List<TripNode> availableNodes;

  const HotelRescueSheet({
    super.key,
    required this.tripId,
    required this.availableNodes,
  });

  @override
  Widget build(BuildContext context) {
    final otherPlaces =
        availableNodes.where((n) => n.venueName.isNotEmpty).toList();

    return Padding(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.shield_outlined, color: AppColors.accent, size: 24),
              const SizedBox(width: AppSpacing.sm),
              Text('Hotel Rescue', style: AppTypography.h2),
            ],
          ),
          const SizedBox(height: AppSpacing.base),
          Text(
            'No hotel saved yet.',
            style: AppTypography.bodyMedium,
          ),
          const SizedBox(height: AppSpacing.xs),
          Text(
            'Save your hotel address so you can show taxi drivers even with no internet connection.',
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
          const SizedBox(height: AppSpacing.lg),
          SizedBox(
            width: double.infinity,
            child: FilledButton.icon(
              onPressed: () {
                Navigator.of(context).pop();
                showModalBottomSheet(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => AddBookingSheet(
                    tripId: tripId,
                    initialBookingType: 'hotel',
                  ),
                );
              },
              icon: const Icon(Icons.hotel),
              label: const Text('Add Hotel Booking'),
            ),
          ),
          if (otherPlaces.isNotEmpty) ...[
            const SizedBox(height: AppSpacing.lg),
            const Divider(),
            const SizedBox(height: AppSpacing.sm),
            Text('Or show a driver another saved stop:',
                style: AppTypography.label),
            const SizedBox(height: AppSpacing.sm),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 180),
              child: ListView.builder(
                shrinkWrap: true,
                itemCount: otherPlaces.length,
                itemBuilder: (context, i) {
                  final place = otherPlaces[i];
                  return ListTile(
                    dense: true,
                    contentPadding: EdgeInsets.zero,
                    leading: const Icon(Icons.place_outlined, size: 20),
                    title:
                        Text(place.venueName, style: AppTypography.bodyMedium),
                    trailing: const Icon(Icons.chevron_right, size: 18),
                    onTap: () {
                      Navigator.of(context).pop();
                      final placeRef = place.venueId ?? place.venueName;
                      context.push('/trip/$tripId/card/$placeRef');
                    },
                  );
                },
              ),
            ),
          ],
          const SizedBox(height: AppSpacing.base),
        ],
      ),
    );
  }
}
