import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/shimmer_card.dart';
import 'swap_search_coords.dart';

export 'swap_search_coords.dart';

/// SPEC-07: Bottom sheet with RAG venue suggestions for swapping an activity.
///
/// Returns [VenueSearchResult] when a venue is confirmed, or null when the
/// sheet is dismissed (drag-down, back, Cancel). The caller inspects the
/// result to decide whether to send swap_activity + reroute_accepted (non-null)
/// or reroute_rejected (null).
///
/// [offeredVenueIds] is populated once venues load, so the caller can read
/// it from the key after the sheet closes.
class SwapSheet extends ConsumerStatefulWidget {
  final String tripId;
  final String targetNodeId;
  final TripState tripState;

  /// Populated by initState after venue search completes. Read by the
  /// caller for the reroute_rejected payload.
  final List<String> offeredVenueIds = [];

  SwapSheet({
    super.key,
    required this.tripId,
    required this.targetNodeId,
    required this.tripState,
  });

  @override
  ConsumerState<SwapSheet> createState() => SwapSheetState();
}

class SwapSheetState extends ConsumerState<SwapSheet> {
  List<VenueSearchResult>? _venues;
  final Set<String> _selectedVibes = {};
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _loadVenues();
  }

  Future<void> _loadVenues() async {
    try {
      final coords = _resolveCoords();
      if (coords == null) {
        setState(() {
          _error = 'Could not determine your location for this trip.';
          _loading = false;
        });
        return;
      }
      final results = await ref
          .read(tripRepoProvider)
          .searchVenues(
            query: 'nearby activity',
            lat: coords.lat,
            lng: coords.lng,
          );
      if (!mounted) return;
      final target = widget.tripState.nodes
          .where((node) => node.nodeId == widget.targetNodeId)
          .firstOrNull;
      final alternatives = results
          .where(
            (venue) =>
                venue.venueId != target?.venueId &&
                venue.name.toLowerCase() !=
                    target?.venueName.toLowerCase(),
          )
          .toList();
      setState(() {
        _venues = alternatives;
        _loading = false;
      });
      widget.offeredVenueIds
        ..clear()
        ..addAll(alternatives.map((v) => v.venueId));
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load suggestions. Check your connection.';
        _loading = false;
      });
    }
  }

  ({double lat, double lng})? _resolveCoords() =>
      resolveSwapSearchCoords(widget.tripState);

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      initialChildSize: 0.85,
      maxChildSize: 0.9,
      minChildSize: 0.3,
      builder: (_, scrollController) => Container(
        decoration: const BoxDecoration(
          color: AppColors.card,
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(AppSpacing.radiusSheet),
          ),
        ),
        child: Column(
          children: [
            // Drag handle
            Container(
              margin: const EdgeInsets.only(top: AppSpacing.md),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: AppColors.divider,
                borderRadius: BorderRadius.circular(2),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Row(
                children: [
                  Expanded(child: Text('Swap to...', style: AppTypography.h2)),
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    child: const Text('Cancel'),
                  ),
                ],
              ),
            ),
            if (!_loading && _availableVibes.isNotEmpty)
              SizedBox(
                height: 36,
                child: ListView(
                  scrollDirection: Axis.horizontal,
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.base,
                  ),
                  children: _availableVibes
                      .map(
                        (vibe) => Padding(
                          padding: const EdgeInsets.only(right: AppSpacing.sm),
                          child: FilterChip(
                            label: Text(vibe.replaceAll('_', ' ')),
                            selected: _selectedVibes.contains(vibe),
                            onSelected: (selected) {
                              setState(() {
                                if (selected) {
                                  _selectedVibes.add(vibe);
                                } else {
                                  _selectedVibes.remove(vibe);
                                }
                              });
                            },
                          ),
                        ),
                      )
                      .toList(),
                ),
              ),
            if (!_loading && _availableVibes.isNotEmpty)
              const SizedBox(height: AppSpacing.base),
            Expanded(child: _buildContent(scrollController)),
          ],
        ),
      ),
    );
  }

  Widget _buildContent(ScrollController scrollController) {
    if (_loading) {
      return const ShimmerList(count: 3);
    }
    if (_error != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Text(
            _error!,
            style: AppTypography.body.copyWith(color: AppColors.muted),
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    final venues = _visibleVenues;
    if (venues.isEmpty) {
      return Center(
        child: Text(
          _selectedVibes.isEmpty
              ? 'No alternative venues found nearby.'
              : 'No alternatives match these filters.',
          style: AppTypography.body.copyWith(color: AppColors.muted),
        ),
      );
    }
    return ListView.separated(
      controller: scrollController,
      padding: const EdgeInsets.symmetric(horizontal: AppSpacing.base),
      itemCount: venues.length,
      separatorBuilder: (_, __) => const Divider(height: 1),
      itemBuilder: (_, i) {
        final v = venues[i];
        return Material(
          color: Colors.transparent,
          child: ListTile(
            title: Row(
              children: [
                Expanded(child: Text(v.name, style: AppTypography.body)),
                // SPEC-17 decision 15: label boosted results.
                if (v.sponsoredBoostApplied)
                  Container(
                    margin: const EdgeInsets.only(left: AppSpacing.sm),
                    padding: const EdgeInsets.symmetric(
                      horizontal: AppSpacing.sm,
                      vertical: 2,
                    ),
                    decoration: BoxDecoration(
                      color: AppColors.sponsoredBg,
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      'Sponsored',
                      style: AppTypography.caption.copyWith(
                        color: AppColors.sponsoredText,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
              ],
            ),
            subtitle: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  v.microLocation,
                  style: AppTypography.caption.copyWith(color: AppColors.muted),
                ),
                // SPEC-17 decision 15: explain ranking influence.
                if (v.sponsoredBoostApplied)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: Text(
                      'Paid placement influenced this ranking.',
                      style: AppTypography.caption.copyWith(
                        color: AppColors.muted,
                        fontStyle: FontStyle.italic,
                      ),
                    ),
                  ),
                if (v.vibeTags.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: AppSpacing.xs),
                    child: Wrap(
                      spacing: AppSpacing.xs,
                      children: v.vibeTags
                          .take(3)
                          .map(
                            (t) => Chip(
                              label: Text(
                                t,
                                style: AppTypography.caption.copyWith(
                                  fontSize: 11,
                                ),
                              ),
                              materialTapTargetSize:
                                  MaterialTapTargetSize.shrinkWrap,
                              visualDensity: VisualDensity.compact,
                            ),
                          )
                          .toList(),
                    ),
                  ),
              ],
            ),
            trailing: const Icon(Icons.swap_horiz, color: AppColors.primary),
            onTap: () => Navigator.of(context).pop(v),
          ),
        );
      },
    );
  }

  List<String> get _availableVibes {
    final values = (_venues ?? [])
        .expand((venue) => venue.vibeTags)
        .where((tag) => tag.trim().isNotEmpty)
        .toSet()
        .toList()
      ..sort();
    return values.take(8).toList();
  }

  List<VenueSearchResult> get _visibleVenues {
    final venues = _venues ?? [];
    if (_selectedVibes.isEmpty) return venues;
    return venues
        .where(
          (venue) =>
              venue.vibeTags.any((tag) => _selectedVibes.contains(tag)),
        )
        .toList();
  }
}
