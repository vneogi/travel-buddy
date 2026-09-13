/// SPEC-36: Collapsible city section for corridor itineraries.
///
/// Shows a header with city name, date range, and a chevron.
/// Starts collapsed when all nodes in the section end before [DateTime.now()].
import 'package:flutter/material.dart';

import '../features/itinerary/date_scope.dart';

/// A collapsible city section in a corridor itinerary.
///
/// Header always visible. Children (day groups + cards) expand/collapse.
/// Starts collapsed when [isPast] returns true.
class CitySection extends StatefulWidget {
  final CorridorCityGroup cityGroup;
  final Widget Function(CorridorCityGroup group) childBuilder;
  final bool forceExpanded;

  const CitySection({
    required this.cityGroup,
    required this.childBuilder,
    this.forceExpanded = false,
    super.key,
  });

  @override
  State<CitySection> createState() => _CitySectionState();
}

class _CitySectionState extends State<CitySection> {
  late bool _expanded;

  @override
  void initState() {
    super.initState();
    _expanded =
        widget.forceExpanded || !widget.cityGroup.isPast(DateTime.now().toUtc());
  }

  @override
  void didUpdateWidget(covariant CitySection oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.forceExpanded && !oldWidget.forceExpanded && !_expanded) {
      setState(() => _expanded = true);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        InkWell(
          onTap: () => setState(() => _expanded = !_expanded),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        widget.cityGroup.displayName,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (widget.cityGroup.dateRange.isNotEmpty)
                        Text(
                          widget.cityGroup.dateRange,
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.outline,
                          ),
                        ),
                    ],
                  ),
                ),
                AnimatedRotation(
                  turns: _expanded ? 0.5 : 0.0,
                  duration: const Duration(milliseconds: 200),
                  child: Icon(
                    Icons.expand_more,
                    color: theme.colorScheme.outline,
                  ),
                ),
              ],
            ),
          ),
        ),
        AnimatedCrossFade(
          firstChild: widget.childBuilder(widget.cityGroup),
          secondChild: const SizedBox.shrink(),
          crossFadeState:
              _expanded ? CrossFadeState.showFirst : CrossFadeState.showSecond,
          duration: const Duration(milliseconds: 200),
        ),
      ],
    );
  }
}
