import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../data/models.dart';
import '../../features/direct_add/direct_add_sheet.dart'
    show directAddSlotLabel, kDirectAddSlots, kExcursionWindows;
import '../../features/driver_card/driver_card_helpers.dart'
    show buildMapsFallbackUri, buildMapsUri;
import '../../features/itinerary/micro_location_label.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

/// SPEC-45: slot or window label from the node, using the labels the app
/// already shows (window first; never a raw slug). Null for bookings.
String? placeSlotLabel(TripNode node) {
  final window = node.timeWindow;
  if (window != null) return kExcursionWindows[window];
  final slot = node.slotName;
  if (slot != null && kDirectAddSlots.contains(slot)) {
    return directAddSlotLabel(slot);
  }
  return null;
}

/// SPEC-45: true when Open in Maps has something to open.
bool placeHasMapsTarget(TripNode node) =>
    (node.lat != null && node.lng != null) || node.venueName.trim().isNotEmpty;

/// SPEC-45: open the node in a maps app. Coordinates when both are set,
/// otherwise a search on the venue name. Only runs on a tap.
Future<void> openPlaceInMaps(BuildContext context, TripNode node) async {
  Uri? uri = buildMapsUri(node.lat, node.lng, label: node.venueName);
  Uri? fallback = buildMapsFallbackUri(node.lat, node.lng);
  if (uri == null) {
    final name = node.venueName.trim();
    uri = Uri.parse('geo:0,0?q=${Uri.encodeComponent(name)}');
    fallback = Uri.https('www.openstreetmap.org', '/search', {'query': name});
  }
  final messenger = ScaffoldMessenger.maybeOf(context);
  var opened = false;
  try {
    opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
  } catch (_) {
    opened = false;
  }
  if (!opened && fallback != null) {
    try {
      opened = await launchUrl(fallback, mode: LaunchMode.externalApplication);
    } catch (_) {
      opened = false;
    }
  }
  if (!opened) {
    messenger?.showSnackBar(
      const SnackBar(content: Text('Could not open Maps on this device.')),
    );
  }
}

/// SPEC-45: push the Driver card on the same path the card overflow uses.
/// The trip id is read at tap time from the router's current location
/// (this screen is a page-less MaterialPageRoute, where GoRouterState.of
/// never resolves and spins). With no router or no trip id nothing happens.
void openPlaceDriverCard(BuildContext context, TripNode node) {
  final router = GoRouter.maybeOf(context);
  final tripId =
      router?.routerDelegate.currentConfiguration.pathParameters['tripId'];
  if (router == null || tripId == null || tripId.isEmpty) {
    debugPrint('[ActivityDetailScreen] no tripId in route; driver card not opened');
    return;
  }
  router.push('/trip/$tripId/card/${node.venueId ?? node.venueName}');
}

/// SPEC-45: Love on the details screen. Shows filled once loved; the
/// callback is the parent's (this widget never emits a signal).
class DetailLoveButton extends StatefulWidget {
  final bool isLoved;
  final VoidCallback onLoved;
  const DetailLoveButton({super.key, required this.isLoved, required this.onLoved});

  @override
  State<DetailLoveButton> createState() => _DetailLoveButtonState();
}

class _DetailLoveButtonState extends State<DetailLoveButton> {
  late bool _loved = widget.isLoved;

  @override
  Widget build(BuildContext context) {
    return OutlinedButton.icon(
      key: const Key('detail_love'),
      style: _actionStyle,
      onPressed: _loved
          ? null
          : () {
              setState(() => _loved = true);
              widget.onLoved();
            },
      icon: Icon(
        _loved ? Icons.favorite : Icons.favorite_border,
        color: _loved ? AppColors.danger : null,
      ),
      label: Text(_loved ? 'Loved' : 'Love'),
    );
  }
}

final ButtonStyle _actionStyle = OutlinedButton.styleFrom(
  minimumSize: const Size(44, 44),
);

/// SPEC-07 / SPEC-45: activity detail with sourced node fields and actions.
class ActivityDetailScreen extends StatelessWidget {
  final TripNode node;
  final VoidCallback? onSwap;
  final VoidCallback? onCancel;
  final VoidCallback? onMove; // SPEC-42
  final VoidCallback? onLoved; // SPEC-45: the itinerary's love callback
  final bool isLoved;
  const ActivityDetailScreen({
    super.key,
    required this.node,
    this.onSwap,
    this.onCancel,
    this.onMove,
    this.onLoved,
    this.isLoved = false,
  });

  bool get _isBooking => node.isLocked || node.nodeKind == 'booking';
  bool get _isDone =>
      node.status == NodeStatus.completed || node.status == NodeStatus.skipped;

  Widget _row(String key, String text, TextStyle style) => Padding(
        padding: const EdgeInsets.only(bottom: AppSpacing.sm),
        child: Text(text, key: Key(key), style: style),
      );

  @override
  Widget build(BuildContext context) {
    final friendlyLocation = friendlyMicroLocation(node.microLocation);
    final slotLabel = placeSlotLabel(node);
    final landmark = node.nearestLandmark?.trim();
    final editable = !_isBooking && !_isDone;
    return Scaffold(
      appBar: AppBar(title: Text(node.venueName, style: AppTypography.h2)),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Venue hero placeholder
            Container(
              height: 200,
              width: double.infinity,
              decoration: BoxDecoration(
                color: AppColors.primaryLight,
                borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
              ),
              child: const Icon(Icons.place, size: 48, color: AppColors.primary),
            ),
            const SizedBox(height: AppSpacing.lg),
            // SPEC-45 item 4: friendly micro_location only
            if (friendlyLocation != null)
              _row('detail_neighbourhood', friendlyLocation, AppTypography.caption),
            if (slotLabel != null) _row('detail_slot', slotLabel, AppTypography.body),
            _row('detail_dwell', '${node.durationMinutes} min', AppTypography.body),
            if (node.openingHours != null)
              _row('detail_hours', 'Hours: ${node.openingHours}', AppTypography.body),
            if (landmark != null && landmark.isNotEmpty)
              _row('detail_landmark', 'Landmark: $landmark', AppTypography.body),
            const SizedBox(height: AppSpacing.sm),
            // All vibe tags on details (card shows max 2).
            Wrap(
              spacing: AppSpacing.sm,
              children: node.vibeTags.map((t) => Chip(label: Text(t))).toList(),
            ),
            const SizedBox(height: AppSpacing.lg),
            if (_isBooking)
              Padding(
                padding: const EdgeInsets.only(bottom: AppSpacing.md),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.lock, size: 16, color: AppColors.accent),
                    const SizedBox(width: AppSpacing.sm),
                    Text('Locked reservation', style: AppTypography.label),
                  ],
                ),
              ),
            Wrap(
              spacing: AppSpacing.sm,
              runSpacing: AppSpacing.sm,
              children: [
                // R17a sabotage: Open in Maps and Driver card omitted.
                if (editable && onSwap != null)
                  OutlinedButton.icon(
                    key: const Key('detail_swap'),
                    style: _actionStyle,
                    onPressed: onSwap,
                    icon: const Icon(Icons.swap_horiz),
                    label: const Text('Swap'),
                  ),
                if (editable && onCancel != null)
                  OutlinedButton.icon(
                    key: const Key('detail_cancel'),
                    style: _actionStyle,
                    onPressed: onCancel,
                    icon: const Icon(Icons.cancel_outlined),
                    label: const Text('Skip / Cancel'),
                  ),
                // SPEC-42: Move keeps its existing key move_detail_<id>.
                if (!_isBooking &&
                    onMove != null &&
                    (node.status == NodeStatus.pending ||
                        node.status == NodeStatus.active))
                  OutlinedButton.icon(
                    key: Key('move_detail_${node.nodeId}'),
                    style: _actionStyle,
                    onPressed: onMove,
                    icon: const Icon(Icons.event_repeat),
                    label: const Text('Move'),
                  ),
                if (editable && onLoved != null)
                  DetailLoveButton(isLoved: isLoved, onLoved: onLoved!),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
