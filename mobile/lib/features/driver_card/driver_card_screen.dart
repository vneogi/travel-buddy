import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/providers.dart';
import '../../render/fact_envelope.dart';
import '../../render/fact_view.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import '../../core/disclaimers.dart';
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
  // SPEC-49: hand-to-driver view. Starts off on every open; never persisted.
  bool _showToDriver = false;

  @override
  void initState() {
    super.initState();
    _loadFromCache();
  }

  Future<void> _loadFromCache() async {
    final db = ref.read(offlineDatabaseProvider);
    final cached = await db.getCachedPlace(
      widget.nodeId,
      identityScope: ref.read(identityCacheScopeProvider),
    );
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
    await db.cachePlace(
      _data!.placeRef,
      newData.serialize(),
      identityScope: ref.read(identityCacheScopeProvider),
    );
    _resolvedSource = newSource;
  }

  void _setShowToDriver(bool on) {
    if (_showToDriver == on) return;
    setState(() => _showToDriver = on);
  }

  @override
  Widget build(BuildContext context) {
    // SPEC-49: intercept every pop. While hand-off is on, exit the mode and
    // stay on this screen; otherwise leave the route. canPop is always false
    // so AppBar back and system back take the same path (force-pop when mode
    // is off).
    return PopScope<Object?>(
      canPop: false,
      onPopInvokedWithResult: (didPop, _) {
        if (didPop) return;
        if (_showToDriver) {
          _setShowToDriver(false);
        } else {
          Navigator.of(context).pop();
        }
      },
      child: Scaffold(
        backgroundColor: AppColors.card,
        appBar: _showToDriver
            ? null
            : AppBar(
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
                      style:
                          AppTypography.body.copyWith(color: AppColors.muted),
                    ),
                  )
                : _showToDriver
                    ? _buildHandoff()
                    : _buildCard(),
      ),
    );
  }

  /// SPEC-49: destination name at arm's-length size, the resolved local
  /// landmark when one exists, and one exit control. Nothing else.
  Widget _buildHandoff() {
    final data = _data!;
    final showLocal = _currentTier != FactTier.refuse && _resolvedValue != null;
    final name = showLocal ? _resolvedValue! : data.venueName;
    final nameStyle = showLocal
        ? AppTypography.localScript(_resolvedLang)
        : AppTypography.display;
    final landmarkEntry = resolvePreferredLocalEntry(
      localizedMap: data.landmarksLocal,
      geoRegion: data.geoRegion,
    );
    final landmark = landmarkEntry?.value['value'] as String?;

    return SafeArea(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(AppSpacing.lg),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    name,
                    key: const Key('show_to_driver_name'),
                    softWrap: true,
                    style: nameStyle,
                  ),
                  if (landmark != null && landmark.isNotEmpty) ...[
                    const SizedBox(height: AppSpacing.xl),
                    Text('Landmark', style: AppTypography.label),
                    const SizedBox(height: AppSpacing.xs),
                    Text(
                      landmark,
                      key: const Key('show_to_driver_landmark'),
                      softWrap: true,
                      style: AppTypography.h1,
                    ),
                  ],
                ],
              ),
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(
              AppSpacing.lg,
              0,
              AppSpacing.lg,
              AppSpacing.lg,
            ),
            child: FilledButton(
              key: const Key('show_to_driver_exit'),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(48),
              ),
              onPressed: () => _setShowToDriver(false),
              child: const Text(
                'Done -- return to card',
                textAlign: TextAlign.center,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCard() {
    final data = _data!;
    final mapsUri = buildMapsUri(data.lat, data.lng, label: data.venueName);
    final mapsFallbackUri = buildMapsFallbackUri(data.lat, data.lng);
    final hasCoords = data.lat != null && data.lng != null;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(AppSpacing.lg),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _buildNameSection(),
          const SizedBox(height: AppSpacing.base),
          // SPEC-49: enter the hand-to-driver view. Full-width so the label
          // wraps at large text scale instead of overflowing a Row.
          SizedBox(
            width: double.infinity,
            child: OutlinedButton(
              key: const Key('show_to_driver_enter'),
              style: OutlinedButton.styleFrom(minimumSize: const Size(0, 44)),
              onPressed: () => _setShowToDriver(true),
              child: const Text('Show to driver', textAlign: TextAlign.center),
            ),
          ),
          const SizedBox(height: AppSpacing.lg),
          _buildLandmarkSection(data),
          const SizedBox(height: AppSpacing.lg),
          Text(data.venueName, style: AppTypography.h1),
          if (mapsUri != null) ...[
            const SizedBox(height: AppSpacing.sm),
            // Full-width so the label wraps at large text scale (same
            // overflow trap as the Show-to-driver enter control).
            SizedBox(
              width: double.infinity,
              child: OutlinedButton(
                onPressed: () => _openMaps(mapsUri, mapsFallbackUri),
                child: const Text('Open in Maps', textAlign: TextAlign.center),
              ),
            ),
          ],
          if (hasCoords) ...[
            const SizedBox(height: AppSpacing.sm),
            Text(
              '${data.lat!.toStringAsFixed(5)}, ${data.lng!.toStringAsFixed(5)}',
              style: AppTypography.caption.copyWith(color: AppColors.muted),
            ),
          ],
          const SizedBox(height: AppSpacing.lg),
          Center(
            child: Text(
              'Venue information is an offline travel aid.',
              style: AppTypography.caption.copyWith(color: AppColors.muted),
            ),
          ),
          const SizedBox(height: AppSpacing.sm),
          // SPEC-14: food disclaimer at the point of the recommendation.
          Center(
            child: Text(
              kFoodDisclaimerShort,
              style: AppTypography.caption.copyWith(color: AppColors.muted),
              textAlign: TextAlign.center,
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _openMaps(Uri uri, Uri? fallbackUri) async {
    var opened = false;
    try {
      opened = await launchUrl(uri, mode: LaunchMode.externalApplication);
    } catch (_) {
      opened = false;
    }
    if (!opened && fallbackUri != null) {
      try {
        opened = await launchUrl(
          fallbackUri,
          mode: LaunchMode.externalApplication,
        );
      } catch (_) {
        opened = false;
      }
    }
    if (!opened && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not open Maps on this device.')),
      );
    }
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
      valueStyle: AppTypography.localScript(_resolvedLang),
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
