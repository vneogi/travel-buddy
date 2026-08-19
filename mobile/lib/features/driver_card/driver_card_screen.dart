import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../../render/fact_envelope.dart';
import '../../render/fact_view.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import 'driver_card_helpers.dart';

/// SPEC-12: Full-screen, high-contrast card shown to drivers.
///
/// Renders 100% offline from SQLite cache_place. Zero network calls.
class DriverCardScreen extends ConsumerStatefulWidget {
  final String tripId;
  final String nodeId;

  const DriverCardScreen({
    super.key,
    required this.tripId,
    required this.nodeId,
  });

  @override
  ConsumerState<DriverCardScreen> createState() => _DriverCardScreenState();
}

class _DriverCardScreenState extends ConsumerState<DriverCardScreen> {
  PlaceDriverCardData? _data;
  bool _loading = true;
  FactTier? _currentTier;
  String? _resolvedLang;
  String? _resolvedValue;
  String? _resolvedSource;

  @override
  void initState() {
    super.initState();
    _loadFromCache();
  }

  Future<void> _loadFromCache() async {
    final db = ref.read(offlineDatabaseProvider);
    final cached = await db.getCachedPlace(widget.nodeId);
    if (cached != null && mounted) {
      final data = PlaceDriverCardData.deserialize(cached);
      final entry = resolvePreferredLocalEntry(
        localizedMap: data.namesLocal,
        geoRegion: data.geoRegion,
      );
      setState(() {
        _data = data;
        _loading = false;
        if (entry != null) {
          _resolvedLang = entry.key;
          _resolvedValue = entry.value['value'] as String?;
          _resolvedSource = entry.value['source'] as String? ?? 'unknown';
          _currentTier = tierForNameSource(_resolvedSource!);
        } else {
          _currentTier = FactTier.refuse;
        }
      });
      // Emit driver_card_shown signal (SPEC-12 decision 10)
      ref.read(signalServiceProvider).emitDriverCardShown(
            placeRef: data.placeRef,
            wasOffline: true,
            nameSource: _resolvedSource ?? 'none',
            tripId: widget.tripId,
          );
    } else if (mounted) {
      setState(() => _loading = false);
    }
  }

  void _onConfirm() {
    if (_data == null || _resolvedLang == null || _resolvedValue == null) return;
    // Emit name_confirmed confirmed
    ref.read(signalServiceProvider).emitNameConfirmed(
          placeRef: _data!.placeRef,
          lang: _resolvedLang!,
          shownValue: _resolvedValue!,
          verdict: 'confirmed',
          tripId: widget.tripId,
        );
    // Update cache to field_verified
    _updateCacheSource('field_verified');
    setState(() => _currentTier = FactTier.assert_);
  }

  void _onReject() {
    if (_data == null || _resolvedLang == null || _resolvedValue == null) return;
    // Emit name_confirmed rejected
    ref.read(signalServiceProvider).emitNameConfirmed(
          placeRef: _data!.placeRef,
          lang: _resolvedLang!,
          shownValue: _resolvedValue!,
          verdict: 'rejected',
          tripId: widget.tripId,
        );
    setState(() => _currentTier = FactTier.refuse);
  }

  Future<void> _updateCacheSource(String newSource) async {
    if (_data == null || _resolvedLang == null) return;
    final updated = Map<String, dynamic>.from(_data!.namesLocal ?? {});
    if (updated[_resolvedLang] is Map) {
      final langEntry = Map<String, dynamic>.from(updated[_resolvedLang] as Map);
      langEntry['source'] = newSource;
      updated[_resolvedLang!] = langEntry;
    }
    final newData = PlaceDriverCardData(
      placeRef: _data!.placeRef,
      venueName: _data!.venueName,
      namesLocal: updated,
      nearestLandmark: _data!.nearestLandmark,
      landmarksLocal: _data!.landmarksLocal,
      lat: _data!.lat,
      lng: _data!.lng,
      microLocation: _data!.microLocation,
      geoRegion: _data!.geoRegion,
    );
    final db = ref.read(offlineDatabaseProvider);
    await db.cachePlace(_data!.placeRef, newData.serialize());
    _resolvedSource = newSource;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.card,
      appBar: AppBar(
        backgroundColor: AppColors.card,
        elevation: 0,
        leading: const BackButton(),
        title: Text('Driver Card', style: AppTypography.h2),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _data == null
              ? Center(
                  child: Text(
                    'Place not cached',
                    style: AppTypography.body.copyWith(color: AppColors.muted),
                  ),
                )
              : _buildCard(),
    );
  }

  Widget _buildCard() {
    final data = _data!;
    final fareBand = resolveFairFareBand(data.geoRegion);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Native script headline via FactView
          _buildNameSection(),
          const SizedBox(height: AppSpacing.lg),
          // Landmark section
          _buildLandmarkSection(data),
          const SizedBox(height: AppSpacing.lg),
          // Roman name + coordinates
          Text(data.venueName, style: AppTypography.h1),
          if (data.lat != null && data.lng != null) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              '${data.lat!.toStringAsFixed(5)}, ${data.lng!.toStringAsFixed(5)}',
              style: AppTypography.bodyMedium,
            ),
          ],
          const SizedBox(height: AppSpacing.lg),
          // Fair fare band
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(AppSpacing.base),
            decoration: BoxDecoration(
              color: AppColors.primaryLight,
              borderRadius: BorderRadius.circular(AppSpacing.radiusCard),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Fair Fare', style: AppTypography.label),
                const SizedBox(height: AppSpacing.xs),
                Text(fareBand, style: AppTypography.bodyMedium),
              ],
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          // Screenshot affordance
          Center(
            child: Text(
              'Screenshot this card for offline safety',
              style: AppTypography.caption,
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          // Disclaimer
          Center(
            child: Text(
              'Venue and fare information is an offline travel aid.',
              style: AppTypography.caption.copyWith(color: AppColors.muted),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNameSection() {
    if (_currentTier == FactTier.refuse || _resolvedValue == null) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Local name not available',
            style: AppTypography.h1.copyWith(color: AppColors.muted),
          ),
          const SizedBox(height: AppSpacing.sm),
          Text(_data!.venueName, style: AppTypography.display),
        ],
      );
    }
    final envelope = FactEnvelope(
      value: _resolvedValue,
      source: _resolvedSource ?? 'unknown',
      confidence: _currentTier == FactTier.assert_ ? 0.95 : 0.5,
      tier: _currentTier!,
      asOf: DateTime.now(),
    );
    return FactView(
      envelope: envelope,
      attribute: 'local_name',
      onConfirm: _currentTier == FactTier.ask ? _onConfirm : null,
      onDismiss: _currentTier == FactTier.ask
          ? ({required String kind, required String attribute}) => _onReject()
          : null,
    );
  }

  Widget _buildLandmarkSection(PlaceDriverCardData data) {
    final landmarkEntry = resolvePreferredLocalEntry(
      localizedMap: data.landmarksLocal,
      geoRegion: data.geoRegion,
    );
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (landmarkEntry != null) ...[
          Text('Landmark', style: AppTypography.label),
          const SizedBox(height: AppSpacing.xs),
          Text(
            landmarkEntry.value['value'] as String? ?? '',
            style: AppTypography.h2,
          ),
        ],
        if (data.nearestLandmark != null) ...[
          const SizedBox(height: AppSpacing.xs),
          Text(
            data.nearestLandmark!,
            style: AppTypography.body.copyWith(color: AppColors.muted),
          ),
        ],
      ],
    );
  }
}
