import 'package:flutter/material.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

/// Plan comparison + paywall. RevenueCat activates when keys are set.
class UpgradeScreen extends StatelessWidget {
  const UpgradeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Go Pro', style: AppTypography.h2)),
      body: Padding(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          children: [
            const SizedBox(height: AppSpacing.xl),
            Text('Unlock the full experience', style: AppTypography.h1, textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.xl),
            _PlanCard(
              title: 'Pro Monthly',
              price: '\$4.99/mo',
              features: const ['50 reroutes/day', 'GPT-4o responses', 'No sponsored results', 'Priority support'],
              isPrimary: true,
            ),
            const SizedBox(height: AppSpacing.base),
            _PlanCard(
              title: 'Pro Yearly',
              price: '\$39.99/yr',
              features: const ['Everything in Monthly', '2 months free'],
              isPrimary: false,
            ),
            const Spacer(),
            Text(
              'Payments powered by RevenueCat. Cancel anytime.',
              style: AppTypography.caption,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: AppSpacing.lg),
          ],
        ),
      ),
    );
  }
}

class _PlanCard extends StatelessWidget {
  final String title, price;
  final List<String> features;
  final bool isPrimary;
  const _PlanCard({required this.title, required this.price, required this.features, required this.isPrimary});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(AppSpacing.lg),
      decoration: BoxDecoration(
        color: isPrimary ? AppColors.primary.withValues(alpha: 0.05) : AppColors.card,
        borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
        border: Border.all(
          color: isPrimary ? AppColors.primary : AppColors.divider,
          width: isPrimary ? 2 : 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(title, style: AppTypography.h2),
              Text(price, style: AppTypography.h2.copyWith(color: AppColors.primary)),
            ],
          ),
          const SizedBox(height: AppSpacing.md),
          ...features.map((f) => Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.xs),
            child: Row(
              children: [
                Icon(Icons.check_circle, size: 16, color: AppColors.success),
                const SizedBox(width: AppSpacing.sm),
                Text(f, style: AppTypography.body),
              ],
            ),
          )),
          if (isPrimary) ...[
            const SizedBox(height: AppSpacing.base),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  // TODO: RevenueCat purchase
                },
                child: const Text('Subscribe'),
              ),
            ),
          ],
        ],
      ),
    );
  }
}
