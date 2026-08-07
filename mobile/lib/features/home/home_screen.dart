import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

class HomeScreen extends ConsumerWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
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
              Text('Where to in Dubai?', style: AppTypography.display),
              const SizedBox(height: AppSpacing.xl),
              // Create trip card
              _CreateTripCard(
                onTap: () async {
                  final repo = ref.read(tripRepoProvider);
                  final trip = await repo.create(startDate: DateTime.now());
                  if (context.mounted) context.push('/trip/${trip.tripId}');
                },
              ),
              const SizedBox(height: AppSpacing.xl),
              // Saved trips section (placeholder for now)
              Text('Your trips', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.base),
              Expanded(
                child: Center(
                  child: Text(
                    'Your upcoming trips will appear here.',
                    style: AppTypography.body.copyWith(color: AppColors.muted),
                    textAlign: TextAlign.center,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _CreateTripCard extends StatelessWidget {
  final VoidCallback onTap;
  const _CreateTripCard({required this.onTap});

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
            const Icon(Icons.add_circle_outline, color: Colors.white, size: 32),
            const SizedBox(height: AppSpacing.md),
            Text(
              'Create Dubai Trip',
              style: AppTypography.h1.copyWith(color: Colors.white),
            ),
            const SizedBox(height: AppSpacing.xs),
            Text(
              'AI builds your itinerary in seconds',
              style: AppTypography.body.copyWith(color: Colors.white70),
            ),
          ],
        ),
      ),
    );
  }
}
