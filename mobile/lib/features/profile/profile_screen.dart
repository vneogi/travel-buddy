import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/providers.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusAsync = ref.watch(userStatusProvider);

    return Scaffold(
      appBar: AppBar(title: Text('Profile', style: AppTypography.h2)),
      body: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          children: [
            // Tier + usage card
            statusAsync.when(
              data: (status) => _UsageCard(status: status),
              loading: () => const CircularProgressIndicator(),
              error: (_, __) => const Text('Could not load status'),
            ),
            const SizedBox(height: AppSpacing.lg),
            // Upgrade CTA
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => context.push('/upgrade'),
                child: const Text('Upgrade to Pro'),
              ),
            ),
            const Spacer(),
            TextButton(
              onPressed: () {
                // TODO: Supabase sign out
                context.go('/onboarding');
              },
              child: Text('Sign Out', style: TextStyle(color: AppColors.danger)),
            ),
          ],
        ),
      ),
    );
  }
}

class _UsageCard extends StatelessWidget {
  final dynamic status;
  const _UsageCard({required this.status});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: AppColors.card,
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        border: Border.all(color: AppColors.divider),
      ),
      child: Column(
        children: [
          Text(
            status.tier.toString().toUpperCase(),
            style: AppTypography.h2.copyWith(color: AppColors.primary),
          ),
          const SizedBox(height: AppSpacing.base),
          // Usage ring
          SizedBox(
            width: 80, height: 80,
            child: CircularProgressIndicator(
              value: status.used / status.max,
              strokeWidth: 6,
              backgroundColor: AppColors.divider,
              valueColor: const AlwaysStoppedAnimation(AppColors.primary),
            ),
          ),
          const SizedBox(height: AppSpacing.md),
          Text(
            '${status.remaining} reroutes remaining',
            style: AppTypography.body,
          ),
          Text(
            '${status.used} / ${status.max} used today',
            style: AppTypography.caption,
          ),
        ],
      ),
    );
  }
}
