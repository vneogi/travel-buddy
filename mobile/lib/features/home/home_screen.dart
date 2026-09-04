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
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.lg),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: AppSpacing.lg),
              Text('Good morning', style: AppTypography.caption),
              const SizedBox(height: AppSpacing.xs),
              Text('Where to next?', style: AppTypography.display),
              const SizedBox(height: AppSpacing.xl),
              home.maybeWhen(
                data: (snapshot) => _CreateTripCard(
                  creating: _creating,
                  onTap: () => _createTrip(snapshot),
                ),
                orElse: () => const _CreateTripCard(
                  creating: false,
                  onTap: null,
                ),
              ),
              const SizedBox(height: AppSpacing.xl),
              Text('Your trips', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.base),
              Expanded(
                child: home.when(
                  loading: () =>
                      const Center(child: CircularProgressIndicator()),
                  error: (error, _) => ErrorView(
                    error: error,
                    onRetry: () => ref.invalidate(homeSnapshotProvider),
                  ),
                  data: (snapshot) => Column(
                    children: [
                      if (snapshot.fromCache)
                        _OfflineHomeNotice(cachedAt: snapshot.cachedAt),
                      Expanded(child: _TripList(trips: snapshot.trips)),
                    ],
                  ),
                ),
              ),
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
