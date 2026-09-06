import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import '../../widgets/error_view.dart';
import 'home_controller.dart';

class HomeScreen extends ConsumerStatefulWidget {
  const HomeScreen({super.key});

  @override
  ConsumerState<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends ConsumerState<HomeScreen> {
  bool _creating = false;

  @override
  Widget build(BuildContext context) {
    final home = ref.watch(homeSnapshotProvider);
    return Scaffold(
      body: SafeArea(
        child: home.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (error, _) => ErrorView(
            error: error,
            onRetry: () => ref.invalidate(homeSnapshotProvider),
          ),
          data: (snapshot) => ListView(
            padding: const EdgeInsets.all(AppSpacing.lg),
            children: [
              const SizedBox(height: AppSpacing.lg),
              Text('Good morning', style: AppTypography.caption),
              const SizedBox(height: AppSpacing.xs),
              Text('Where to next?', style: AppTypography.display),
              const SizedBox(height: AppSpacing.xl),
              _CreateTripCard(
                creating: _creating,
                onTap: () => _createTrip(snapshot),
              ),
              if (snapshot.supportedCorridors.isNotEmpty) ...[
                const SizedBox(height: AppSpacing.base),
                _CreateCorridorCard(
                  creating: _creating,
                  corridors: snapshot.supportedCorridors,
                  onTap: () => _showCorridorDateForm(snapshot),
                ),
              ],
              if (snapshot.featuredTrip != null) ...[
                const SizedBox(height: AppSpacing.lg),
                _FeaturedTripCard(
                  featured: snapshot.featuredTrip!,
                  fromCache: snapshot.fromCache,
                  cachedAt: snapshot.cachedAt,
                ),
              ],
              const SizedBox(height: AppSpacing.lg),
              Text('Your trips', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.base),
              if (snapshot.fromCache)
                _OfflineHomeNotice(cachedAt: snapshot.cachedAt),
              _TripList(trips: snapshot.trips),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _createTrip(HomeSnapshot snapshot) async {
    final supportedRegions = snapshot.supportedRegions;
    if (_creating || supportedRegions.isEmpty) return;
    final selection = await _showCreateDialog(
      supportedRegions,
      createsAdditionalTrip: snapshot.trips.isNotEmpty,
    );
    if (selection == null) {
      return;
    }
    if (!mounted) return;
    setState(() => _creating = true);
    try {
      final trip = await ref.read(tripRepoProvider).create(
            startDate: selection.$2,
            geoRegion: selection.$1,
          );
      ref.invalidate(homeSnapshotProvider);
      if (mounted) context.go('/trip/${trip.tripId}');
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(error is NetworkException
                ? "Can't reach Travel Buddy \u2014 check your connection."
                : error.message),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              "Couldn't create this trip. Check your connection and try again.",
            ),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }


  Future<void> _showCorridorDateForm(HomeSnapshot snapshot) async {
    if (_creating || snapshot.supportedCorridors.isEmpty) return;
    final corridor = snapshot.supportedCorridors.first;
    final segments = await showModalBottomSheet<List<TripSegment>>(
      context: context,
      isScrollControlled: true,
      builder: (_) => _CorridorDateForm(corridor: corridor),
    );
    if (segments == null || !mounted) return;
    setState(() => _creating = true);
    try {
      final trip = await ref
          .read(tripRepoProvider)
          .corridorCreate(segments: segments);
      ref.invalidate(homeSnapshotProvider);
      if (mounted) context.go('/trip/${trip.tripId}');
    } on ApiException catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(error is NetworkException
                ? "Can't reach Travel Buddy \u2014 check your connection."
                : error.message),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              "Couldn't create this corridor trip. Try again.",
            ),
            behavior: SnackBarBehavior.floating,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<(String, DateTime)?> _showCreateDialog(
    List<String> supportedRegions, {
    required bool createsAdditionalTrip,
  }) async {
    var region = supportedRegions.first;
    var date = DateTime.now().add(const Duration(days: 1));
    return showDialog<(String, DateTime)>(
      context: context,
      builder: (dialogContext) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Create a trip'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (createsAdditionalTrip) ...[
                const Text(
                  'You already have a trip. This will create another one.',
                ),
                const SizedBox(height: AppSpacing.base),
              ],
              DropdownButtonFormField<String>(
                initialValue: region,
                decoration: const InputDecoration(labelText: 'Destination'),
                items: supportedRegions
                    .map(
                      (value) => DropdownMenuItem(
                        value: value,
                        child: Text(_displayRegion(value)),
                      ),
                    )
                    .toList(),
                onChanged: (value) {
                  if (value != null) {
                    setDialogState(() => region = value);
                  }
                },
              ),
              const SizedBox(height: AppSpacing.base),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Start date'),
                subtitle:
                    Text(MaterialLocalizations.of(context).formatMediumDate(date)),
                trailing: const Icon(Icons.calendar_today_outlined),
                onTap: () async {
                  final picked = await showDatePicker(
                    context: context,
                    initialDate: date,
                    firstDate: DateTime.now(),
                    lastDate: DateTime.now().add(const Duration(days: 730)),
                  );
                  if (picked != null) {
                    setDialogState(() => date = picked);
                  }
                },
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogContext),
              child: const Text('Cancel'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(dialogContext, (region, date)),
              child: const Text('Create'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CreateTripCard extends StatelessWidget {
  final VoidCallback? onTap;
  final bool creating;
  const _CreateTripCard({required this.onTap, required this.creating});

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.lg),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [AppColors.primary, AppColors.primaryDark],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            creating
                ? const SizedBox(
                    width: 32,
                    height: 32,
                    child: CircularProgressIndicator(color: Colors.white),
                  )
                : const Icon(
                    Icons.add_circle_outline,
                    color: Colors.white,
                    size: 32,
                  ),
            const SizedBox(height: AppSpacing.md),
            Text(
              creating ? 'Creating your trip\u2026' : 'Create a trip',
              style: AppTypography.h1.copyWith(color: Colors.white),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'Choose a supported destination and start date',
              style: AppTypography.body.copyWith(color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }
}

class _FeaturedTripCard extends StatelessWidget {
  final FeaturedTrip featured;
  final bool fromCache;
  final DateTime? cachedAt;
  const _FeaturedTripCard({
    required this.featured,
    required this.fromCache,
    this.cachedAt,
  });

  @override
  Widget build(BuildContext context) {
    final stop = featured.actionableStop;
    final isActive = featured.isActive;
    final label = isActive ? 'Now' : 'Up next';
    final region = _displayRegion(featured.geoRegion);

    return GestureDetector(
      onTap: () => context.go('/trip/${featured.tripId}'),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.all(AppSpacing.base),
        decoration: BoxDecoration(
          color: AppColors.card,
          border: Border.all(color: AppColors.primary, width: 1.5),
          borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.sm,
                    vertical: AppSpacing.xs,
                  ),
                  decoration: BoxDecoration(
                    color: isActive
                        ? AppColors.primary
                        : AppColors.accent,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    label,
                    style: AppTypography.caption
                        .copyWith(color: Colors.white, fontSize: 11),
                  ),
                ),
                const Spacer(),
                if (fromCache && cachedAt != null)
                  Text(
                    'Cached ${_cacheAge(cachedAt!)}',
                    style: AppTypography.caption
                        .copyWith(color: AppColors.muted, fontSize: 11),
                  ),
              ],
            ),
            const SizedBox(height: AppSpacing.sm),
            Text(region, style: AppTypography.h2),
            if (stop != null) ...[
              const SizedBox(height: AppSpacing.xs),
              Text(
                stop.venueName,
                style: AppTypography.body,
              ),
              Text(
                MaterialLocalizations.of(context)
                    .formatTimeOfDay(
                      TimeOfDay.fromDateTime(stop.scheduledStart.toLocal()),
                    ),
                style: AppTypography.caption
                    .copyWith(color: AppColors.muted),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _TripList extends StatelessWidget {
  final List<TripSummary> trips;
  const _TripList({required this.trips});

  @override
  Widget build(BuildContext context) {
    if (trips.isEmpty) {
      return Center(
        child: Text(
          'No trips yet. Start with your destination and dates.',
          style: AppTypography.body.copyWith(color: AppColors.muted),
          textAlign: TextAlign.center,
        ),
      );
    }
    return ListView.separated(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: trips.length,
      separatorBuilder: (_, __) => const SizedBox(height: AppSpacing.sm),
      itemBuilder: (context, index) {
        final trip = trips[index];
        final dates = trip.startsAt == null
            ? 'Dates not set'
            : MaterialLocalizations.of(context)
                .formatMediumDate(trip.startsAt!.toLocal());
        return Card(
          child: ListTile(
            onTap: () => context.go('/trip/${trip.tripId}'),
            leading: const Icon(Icons.luggage_outlined),
            title: Text(_displayRegion(trip.geoRegion)),
            subtitle: Text(
              '$dates \u00b7 ${trip.nodeCount} stops'
              '${trip.bookingCount > 0 ? ' \u00b7 ${trip.bookingCount} bookings' : ''}',
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                IconButton(
                  tooltip: 'Ask about this trip',
                  onPressed: () => context.push('/trip/${trip.tripId}/chat'),
                  icon: const Icon(Icons.chat_bubble_outline),
                ),
                const Icon(Icons.chevron_right),
              ],
            ),
          ),
        );
      },
    );
  }
}

class _OfflineHomeNotice extends StatelessWidget {
  final DateTime? cachedAt;
  const _OfflineHomeNotice({this.cachedAt});

  @override
  Widget build(BuildContext context) {
    final age = cachedAt == null ? null : _cacheAge(cachedAt!);
    return Container(
        width: double.infinity,
        margin: const EdgeInsets.only(bottom: AppSpacing.sm),
        padding: const EdgeInsets.all(AppSpacing.sm),
        color: AppColors.primaryLight,
        child: Text(
          'Showing saved trips while offline'
          '${age == null ? '.' : ' \u00b7 Cached $age'}',
        ),
      );
  }
}

String _displayRegion(String value) => value
    .split('_')
    .map((part) => part.isEmpty
        ? part
        : '${part.substring(0, 1).toUpperCase()}${part.substring(1)}')
    .join(' ');

String _cacheAge(DateTime cachedAt) {
  final age = DateTime.now().toUtc().difference(cachedAt.toUtc());
  if (age.inMinutes < 1) return 'just now';
  if (age.inHours < 1) return '${age.inMinutes}m ago';
  if (age.inDays < 1) return '${age.inHours}h ago';
  return '${age.inDays}d ago';
}


class _CreateCorridorCard extends StatelessWidget {
  final bool creating;
  final List<SupportedCorridor> corridors;
  final VoidCallback onTap;

  const _CreateCorridorCard({
    required this.creating,
    required this.corridors,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final corridor = corridors.first;
    return Card(
      child: InkWell(
        onTap: creating ? null : onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Row(
            children: [
              const Icon(Icons.route, size: 32),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      corridor.displayName,
                      style: AppTypography.bodyMedium,
                    ),
                    Text(
                      'Multi-city Laos corridor',
                      style: AppTypography.caption,
                    ),
                  ],
                ),
              ),
              if (creating)
                const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              else
                const Icon(Icons.arrow_forward_ios, size: 16),
            ],
          ),
        ),
      ),
    );
  }
}

/// SPEC-36: Independent date-range form for each corridor city.
///
/// Validation rules (all checked live):
///  - Each segment range: 1 to [maxDaysPerSegment] days inclusive.
///  - Total days across all segments: <= [maxDays].
///  - Segments must not overlap: each starts strictly after the prior ends.
///  - Chronological order: start_i+1 > end_i.
class _CorridorDateForm extends StatefulWidget {
  final SupportedCorridor corridor;
  const _CorridorDateForm({required this.corridor});

  @override
  State<_CorridorDateForm> createState() => _CorridorDateFormState();
}

class _CorridorDateFormState extends State<_CorridorDateForm> {
  late final List<DateTimeRange> _ranges;
  bool _submitting = false;

  @override
  void initState() {
    super.initState();
    // Seed with valid non-overlapping 1-day defaults starting tomorrow.
    final tomorrow = DateUtils.dateOnly(
      DateTime.now().add(const Duration(days: 1)),
    );
    _ranges = [];
    var cursor = tomorrow;
    for (var i = 0; i < widget.corridor.geoRegions.length; i++) {
      _ranges.add(DateTimeRange(start: cursor, end: cursor));
      cursor = cursor.add(const Duration(days: 2)); // 1-day gap
    }
  }

  String? _validate() {
    final maxPer = widget.corridor.maxDaysPerSegment;
    final maxTotal = widget.corridor.maxDays;
    var totalDays = 0;
    for (var i = 0; i < _ranges.length; i++) {
      final r = _ranges[i];
      final days = r.end.difference(r.start).inDays + 1;
      if (days < 1) return 'Each city needs at least 1 day.';
      if (days > maxPer) {
        return '${widget.corridor.geoRegions[i]} exceeds $maxPer days.';
      }
      totalDays += days;
      if (i > 0) {
        final prev = _ranges[i - 1];
        if (!r.start.isAfter(prev.end)) {
          return 'Dates overlap or are out of order.';
        }
      }
    }
    if (totalDays > maxTotal) {
      return 'Total $totalDays days exceeds the $maxTotal-day limit.';
    }
    return null;
  }

  String _fmt(DateTime d) =>
      '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Future<void> _pickRange(int index) async {
    final initial = _ranges[index];
    final picked = await showDateRangePicker(
      context: context,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
      initialDateRange: initial,
    );
    if (picked != null && mounted) {
      setState(() => _ranges[index] = picked);
    }
  }

  void _submit() {
    if (_submitting || _validate() != null) return;
    setState(() => _submitting = true);
    final segments = <TripSegment>[];
    for (var i = 0; i < _ranges.length; i++) {
      segments.add(TripSegment(
        geoRegion: widget.corridor.geoRegions[i],
        startsOn: _fmt(_ranges[i].start),
        endsOn: _fmt(_ranges[i].end),
      ));
    }
    Navigator.pop(context, segments);
  }

  @override
  Widget build(BuildContext context) {
    final error = _validate();
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.only(
          left: 16,
          right: 16,
          top: 16,
          bottom: MediaQuery.of(context).viewInsets.bottom + 16,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(
              'Create ${widget.corridor.displayName}',
              style: AppTypography.h2,
            ),
            const SizedBox(height: 4),
            Text(
              'Pick dates for each city (max ${widget.corridor.maxDaysPerSegment} days each, '
              '${widget.corridor.maxDays} total).',
              style: AppTypography.caption,
            ),
            const SizedBox(height: 16),
            for (var i = 0; i < widget.corridor.geoRegions.length; i++) ...[
              _CityDateRow(
                region: widget.corridor.geoRegions[i],
                range: _ranges[i],
                onTap: () => _pickRange(i),
              ),
              if (i < widget.corridor.geoRegions.length - 1)
                const SizedBox(height: 8),
            ],
            if (error != null) ...[
              const SizedBox(height: 12),
              Text(
                error,
                style: AppTypography.caption.copyWith(color: AppColors.danger),
              ),
            ],
            const SizedBox(height: 16),
            FilledButton(
              onPressed: error == null && !_submitting ? _submit : null,
              child: _submitting
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Colors.white,
                      ),
                    )
                  : const Text('Create Laos corridor'),
            ),
          ],
        ),
      ),
    );
  }
}

class _CityDateRow extends StatelessWidget {
  final String region;
  final DateTimeRange range;
  final VoidCallback onTap;

  const _CityDateRow({
    required this.region,
    required this.range,
    required this.onTap,
  });

  String _label(DateTime d) =>
      '${d.day}/${d.month}/${d.year}';

  @override
  Widget build(BuildContext context) {
    final days = range.end.difference(range.start).inDays + 1;
    // Pretty region name: "vientiane_laos" -> "Vientiane"
    final display = region.split('_').first[0].toUpperCase() +
        region.split('_').first.substring(1);
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(8),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
        child: Row(
          children: [
            SizedBox(
              width: 100,
              child: Text(display, style: AppTypography.body),
            ),
            Expanded(
              child: Text(
                '${_label(range.start)} - ${_label(range.end)}  ($days d)',
                style: AppTypography.bodyMedium,
              ),
            ),
            const Icon(Icons.calendar_today, size: 18),
          ],
        ),
      ),
    );
  }
}

