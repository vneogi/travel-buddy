import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/env.dart';
import '../../core/providers.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';
import 'sign_out_controller.dart';

class ProfileScreen extends ConsumerStatefulWidget {
  const ProfileScreen({super.key});

  @override
  ConsumerState<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends ConsumerState<ProfileScreen> {
  Future<void> _signOut() async {
    final ok = await ref.read(signOutControllerProvider.notifier).run();
    if (!mounted) return;
    if (ok.ok) {
      context.go('/');
      return;
    }
    final messenger = ScaffoldMessenger.maybeOf(context);
    messenger?.showSnackBar(
      SnackBar(content: Text(ok.error ?? 'Sign out failed. Please try again.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    final statusAsync = ref.watch(userStatusProvider);
    final deviceId = ref.watch(deviceIdProvider);
    final signingOut = ref.watch(signOutControllerProvider);

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
            // SPEC-09: Device identity (read-only)
            ListTile(
              leading: const Icon(Icons.fingerprint),
              title: const Text('Device ID'),
              subtitle: Text(
                deviceId,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
            const SizedBox(height: AppSpacing.base),
            // SPEC-37: API host diagnostic (hostname only, no credentials)
            ListTile(
              leading: const Icon(Icons.cloud_outlined),
              title: const Text('API Host'),
              subtitle: Text(
                Env.apiHostname,
                style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
              ),
            ),
            const SizedBox(height: AppSpacing.base),
            // Upgrade CTA
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () => context.push('/upgrade'),
                child: const Text('Upgrade to Pro'),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
            // Hidden debug: sync status (SPEC-02 B.5)
            ListTile(
              leading: const Icon(Icons.sync),
              title: const Text('Sync Status'),
              subtitle: const Text('Queue & connectivity debug'),
              trailing: const Icon(Icons.chevron_right),
              onTap: () => context.push('/profile/sync'),
            ),
            const Spacer(),
            TextButton(
              key: const Key('profile_sign_out'),
              onPressed: signingOut ? null : _signOut,
              child: Text(
                signingOut ? 'Signing out…' : 'Sign Out',
                style: TextStyle(color: AppColors.danger),
              ),
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
            width: 80,
            height: 80,
            child: CircularProgressIndicator(
              value: status.used / status.max,
              strokeWidth: 6,
              backgroundColor: AppColors.divider,
              valueColor: const AlwaysStoppedAnimation(AppColors.primary),
            ),
          ),
          const SizedBox(height: AppSpacing.base),
          Text(
            '${status.used}/${status.max} reroutes today',
            style: AppTypography.bodyMedium,
          ),
        ],
      ),
    );
  }
}
