import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import 'arrival_hubs.dart';

const String kArrivalFareCaption = 'Guides only -- confirm before you pay.';
const String kArrivalEmptyHub = 'No verified fare or tip sheet for this hub yet.';
/// SPEC-57 Amendment 2: caption under the Typical fares section.
const String kFlatFareCaption = 'Guides only. Agree the price before you get in.';

/// SPEC-57 slice 1: captain view for one arrival hub. Reads only the bundled
/// asset; no network call, no brightness or orientation change.
class ArrivalArmorScreen extends ConsumerWidget {
  final String tripId;
  final String hubId;

  /// Driver Card place ref of the next hotel; null or empty hides the button.
  final String? hotelRef;

  /// Tests may inject a parsed hub instead of loading the asset.
  final ArrivalHub? hub;

  const ArrivalArmorScreen({
    super.key,
    required this.tripId,
    required this.hubId,
    this.hotelRef,
    this.hub,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final injected = hub;
    Widget body;
    if (injected != null) {
      body = _body(context, injected);
    } else {
      final hubs = ref.watch(arrivalHubsProvider);
      body = hubs.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => _body(context, null),
        data: (list) {
          ArrivalHub? match;
          for (final h in list) {
            if (h.id == hubId) {
              match = h;
              break;
            }
          }
          return _body(context, match);
        },
      );
    }
    return Scaffold(
      backgroundColor: AppColors.surface,
      appBar: AppBar(
        leading: const BackButton(),
        title: Text('Arrival armor', style: AppTypography.h2),
      ),
      body: body,
    );
  }

  Widget _body(BuildContext context, ArrivalHub? hub) {
    final ref = hotelRef;
    final fareHub = (hub != null && hub.hasFare) ? hub : null;
    final notes = hub?.visibleScamNotes ?? const <String>[];
    final currency = hub?.currency ?? '';
    final official = hub?.officialOption;
    final source = hub?.source;
    final surveyed = hub?.surveyedOn;
    final hasOfficial = official != null && official.trim().isNotEmpty;
    final hasSource = source != null &&
        source.trim().isNotEmpty &&
        surveyed != null &&
        surveyed.trim().isNotEmpty;
    final cards = hub?.validFlatFares ?? const <FlatFare>[];

    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(AppSpacing.lg),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (hub != null)
              Text(
                hub.label,
                key: const Key('arrival_hub_label'),
                style: AppTypography.h1,
              ),
            if (fareHub != null) ...[
              const SizedBox(height: AppSpacing.lg),
              Text('Fair fare guide', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.xs),
              Text(
                '${fareHub.fareBandLow} - ${fareHub.fareBandHigh} $currency',
                key: const Key('arrival_fare_band'),
                style: AppTypography.body,
              ),
              if (fareHub.hardCeiling != null)
                Text(
                  'Walk-away above ${fareHub.hardCeiling} $currency',
                  key: const Key('arrival_fare_ceiling'),
                  style: AppTypography.body,
                ),
              const SizedBox(height: AppSpacing.sm),
              Text(
                kArrivalFareCaption,
                style: AppTypography.caption.copyWith(color: AppColors.muted),
              ),
            ],
            // SPEC-57 Amendment 1: official option and source show with or
            // without fare bands.
            // R17c sabotage: official option only inside the fare-band block.
            if (hasOfficial && fareHub != null) ...[
              const SizedBox(height: AppSpacing.base),
              Text('Official option',
                  key: const Key('arrival_official_heading'), style: AppTypography.h2),
              const SizedBox(height: AppSpacing.xs),
              Text(official, key: const Key('arrival_official_text'), style: AppTypography.body),
            ],
            if (hasSource && fareHub != null)
              Text(
                'Source: $source ($surveyed)',
                key: const Key('arrival_source'),
                style: AppTypography.caption.copyWith(color: AppColors.muted),
              ),
            // SPEC-57 Amendment 2: sourced flat-fare cards, shown as stored.
            if (cards.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.lg),
              Column(
                key: const Key('arrival_flat_fares'),
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Typical fares', style: AppTypography.h2),
                  const SizedBox(height: AppSpacing.xs),
                  for (var i = 0; i < cards.length; i++)
                    Padding(
                      key: Key('flat_fare_$i'),
                      padding: const EdgeInsets.only(bottom: AppSpacing.sm),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(cards[i].route!, style: AppTypography.body),
                          Text(cards[i].vehicle!, style: AppTypography.body),
                          Text(
                            '${cards[i].low} - ${cards[i].high} ${cards[i].currency}',
                            style: AppTypography.body,
                          ),
                          Text(cards[i].basis!, style: AppTypography.body),
                          Text(
                            'Source: ${cards[i].source} (${cards[i].surveyedOn})',
                            style: AppTypography.caption.copyWith(color: AppColors.muted),
                          ),
                        ],
                      ),
                    ),
                  Text(
                    kFlatFareCaption,
                    style: AppTypography.caption.copyWith(color: AppColors.muted),
                  ),
                ],
              ),
            ],
            if (notes.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.lg),
              Text('Watch for', style: AppTypography.h2),
              const SizedBox(height: AppSpacing.xs),
              for (final note in notes)
                Padding(
                  padding: const EdgeInsets.only(bottom: AppSpacing.xs),
                  child: Text('- $note', style: AppTypography.body),
                ),
            ],
            if (fareHub == null && notes.isEmpty && !hasOfficial && cards.isEmpty) ...[
              const SizedBox(height: AppSpacing.lg),
              Text(
                kArrivalEmptyHub,
                key: const Key('arrival_empty_hub'),
                style: AppTypography.body.copyWith(color: AppColors.muted),
              ),
            ],
            if (ref != null && ref.isNotEmpty) ...[
              const SizedBox(height: AppSpacing.xl),
              FilledButton(
                key: const Key('arrival_open_driver_card'),
                style: FilledButton.styleFrom(
                  minimumSize: const Size.fromHeight(48),
                ),
                onPressed: () => context.push('/trip/$tripId/card/$ref'),
                child: const Text('Open driver card for hotel'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
