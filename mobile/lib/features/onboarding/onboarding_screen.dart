import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

class OnboardingScreen extends StatefulWidget {
  const OnboardingScreen({super.key});
  @override
  State<OnboardingScreen> createState() => _OnboardingScreenState();
}

class _OnboardingScreenState extends State<OnboardingScreen> {
  final _controller = PageController();
  int _page = 0;
  String? _selectedMood;

  final _moods = ['Exploratory', 'Relaxed', 'Energetic', 'Cultural'];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.surface,
      body: SafeArea(
        child: Column(
          children: [
            // Progress dots
            Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(3, (i) => _Dot(active: i == _page)),
              ),
            ),
            Expanded(
              child: PageView(
                controller: _controller,
                onPageChanged: (i) => setState(() => _page = i),
                children: [
                  _WelcomePage(),
                  _MoodPage(
                    moods: _moods,
                    selected: _selectedMood,
                    onSelect: (m) => setState(() => _selectedMood = m),
                  ),
                  _AuthPage(onContinue: () => context.go('/')),
                ],
              ),
            ),
            // Next button
            Padding(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _page < 2
                      ? () => _controller.nextPage(
                            duration: const Duration(milliseconds: 280),
                            curve: Curves.easeOutCubic,
                          )
                      : () => context.go('/'),
                  child: Text(_page < 2 ? 'Next' : 'Get Started'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _Dot extends StatelessWidget {
  final bool active;
  const _Dot({required this.active});
  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      width: active ? 24 : 8,
      height: 8,
      decoration: BoxDecoration(
        color: active ? AppColors.primary : AppColors.divider,
        borderRadius: BorderRadius.circular(4),
      ),
    );
  }
}

class _WelcomePage extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(Icons.flight_takeoff, size: 64, color: AppColors.primary),
          const SizedBox(height: AppSpacing.lg),
          Text('Your Dubai\nTravel Companion', style: AppTypography.display, textAlign: TextAlign.center),
          const SizedBox(height: AppSpacing.base),
          Text(
            'A living itinerary that self-corrects when plans change.',
            style: AppTypography.body.copyWith(color: AppColors.muted),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _MoodPage extends StatelessWidget {
  final List<String> moods;
  final String? selected;
  final ValueChanged<String> onSelect;
  const _MoodPage({required this.moods, required this.selected, required this.onSelect});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text('What\'s your vibe?', style: AppTypography.h1),
          const SizedBox(height: AppSpacing.xl),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.md,
            children: moods.map((m) => ChoiceChip(
              label: Text(m),
              selected: selected == m,
              onSelected: (_) => onSelect(m),
              selectedColor: AppColors.primaryLight,
            )).toList(),
          ),
        ],
      ),
    );
  }
}

class _AuthPage extends StatelessWidget {
  final VoidCallback onContinue;
  const _AuthPage({required this.onContinue});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(AppSpacing.xl),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Text('Almost there', style: AppTypography.h1),
          const SizedBox(height: AppSpacing.base),
          Text(
            'Sign in to save your trips and sync across devices.',
            style: AppTypography.body.copyWith(color: AppColors.muted),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: AppSpacing.xl),
          // Placeholder — Supabase Auth will be wired here
          OutlinedButton.icon(
            onPressed: onContinue, // Skip auth for now
            icon: const Icon(Icons.email_outlined),
            label: const Text('Continue with Email'),
          ),
          const SizedBox(height: AppSpacing.md),
          TextButton(
            onPressed: onContinue,
            child: const Text('Skip for now'),
          ),
        ],
      ),
    );
  }
}
