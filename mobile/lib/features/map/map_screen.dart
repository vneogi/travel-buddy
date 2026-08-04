import 'package:flutter/material.dart';
import '../../theme/colors.dart';
import '../../theme/typography.dart';
import '../../theme/spacing.dart';

/// Placeholder map view. Real google_maps_flutter drops in when key is set.
class MapScreen extends StatelessWidget {
  final String tripId;
  const MapScreen({super.key, required this.tripId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Map', style: AppTypography.h2)),
      body: Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.map_outlined, size: 64, color: AppColors.muted),
            const SizedBox(height: AppSpacing.base),
            Text('Map coming soon', style: AppTypography.body.copyWith(color: AppColors.muted)),
            const SizedBox(height: AppSpacing.sm),
            Text('Venue pins + transit routes', style: AppTypography.caption),
          ],
        ),
      ),
    );
  }
}
