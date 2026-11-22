// SPEC-25 trip-optional Ask (slice 2): ask about a place with no trip.
//
// Region comes from the picker (default: the most recently updated trip's
// region when it is supported). Offline sends are refused with the same
// view the trip chat uses and never reach the repository. Messages live in
// widget state only: no persistence, no thread history.

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/connectivity_helper.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../data/region_defaults.dart';
import '../../render/offline_state.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import '../chat/ask_bubble.dart';
import '../chat/ask_entry_bar.dart';
import '../home/home_controller.dart';

/// Default region: the geoRegion of the trip with the latest updatedAt,
/// when that code is supported; otherwise no selection.
String? defaultAskRegion(HomeSnapshot snapshot) {
  if (snapshot.trips.isEmpty) return null;
  final latest = snapshot.trips.reduce(
    (a, b) => b.updatedAt.isAfter(a.updatedAt) ? b : a,
  );
  return snapshot.supportedRegions.contains(latest.geoRegion)
      ? latest.geoRegion
      : null;
}

enum _AskEntryKind { question, answer, offline, error }

class _AskEntry {
  final _AskEntryKind kind;
  final String text;
  final AskResponse? response;
  const _AskEntry(this.kind, {this.text = '', this.response});
}

class TripOptionalAskScreen extends ConsumerStatefulWidget {
  final ConnectivityHelper? connectivityOverride;

  const TripOptionalAskScreen({super.key, this.connectivityOverride});

  @override
  ConsumerState<TripOptionalAskScreen> createState() =>
      _TripOptionalAskScreenState();
}

class _TripOptionalAskScreenState extends ConsumerState<TripOptionalAskScreen> {
  String? _picked;
  bool _sending = false;
  final _entries = <_AskEntry>[];

  Future<bool> _isOnline() =>
      (widget.connectivityOverride ?? ConnectivityHelper()).checkConnectivity();

  Future<void> _send(String question, String region) async {
    setState(() => _entries.add(_AskEntry(_AskEntryKind.question, text: question)));
    // SPEC-25: offline Ask is refused; never enqueued, never sent.
    if (!await _isOnline()) {
      if (mounted) setState(() => _entries.add(const _AskEntry(_AskEntryKind.offline)));
      return;
    }
    if (!mounted) return;
    setState(() => _sending = true);
    try {
      final response = await ref
          .read(tripRepoProvider)
          .askWithoutTrip(question: question, geoRegion: region);
      if (!mounted) return;
      setState(() {
        _entries.add(_AskEntry(_AskEntryKind.answer, response: response));
        _sending = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _entries.add(const _AskEntry(_AskEntryKind.error));
        _sending = false;
      });
    }
  }

  Widget _entry(_AskEntry entry) {
    switch (entry.kind) {
      case _AskEntryKind.question:
        return Align(
          alignment: Alignment.centerRight,
          child: Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: Text(entry.text, style: AppTypography.body),
          ),
        );
      case _AskEntryKind.answer:
        final response = entry.response!;
        return Padding(
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              AskBubble(askResponse: response),
              if (response.fallbackReason == 'no_trip')
                TextButton(
                  key: const Key('ask_start_trip'),
                  onPressed: () => context.push('/trip/create'),
                  child: const Text('Start a trip'),
                ),
            ],
          ),
        );
      case _AskEntryKind.offline:
        return Align(
          key: const Key('ask_offline_refuse'),
          alignment: Alignment.centerLeft,
          child: Container(
            margin: const EdgeInsets.only(bottom: AppSpacing.sm),
            constraints: const BoxConstraints(maxWidth: 280),
            child: const OfflineStateView(
              state: OfflineState.unavailable,
              child: SizedBox.shrink(),
            ),
          ),
        );
      case _AskEntryKind.error:
        return Padding(
          key: const Key('ask_error'),
          padding: const EdgeInsets.only(bottom: AppSpacing.sm),
          child: Text(
            "Couldn't get an answer right now. Please try again.",
            style: AppTypography.body,
          ),
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final home = ref.watch(homeSnapshotProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Ask')),
      body: home.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (_, __) => const Center(child: Text('Could not load places.')),
        data: (snapshot) {
          final region = _picked ?? defaultAskRegion(snapshot);
          return Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.all(AppSpacing.base),
                child: DropdownButton<String>(
                  key: const Key('ask_region_picker'),
                  isExpanded: true,
                  value: region,
                  hint: const Text('Choose a place'),
                  items: [
                    for (final code in snapshot.supportedRegions)
                      DropdownMenuItem(value: code, child: Text(regionDisplayName(code))),
                  ],
                  onChanged: (code) => setState(() => _picked = code),
                ),
              ),
              if (region == null)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: AppSpacing.base),
                  child: Text(
                    'Pick a place first.',
                    key: const Key('ask_pick_place_hint'),
                    style: AppTypography.caption,
                  ),
                ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.all(AppSpacing.base),
                  children: [for (final e in _entries) _entry(e)],
                ),
              ),
              AskEntryBar(
                enabled: region != null && !_sending,
                hintText: 'Ask about a place, food or local rules',
                onSubmit: (question) {
                  if (region != null) _send(question, region);
                },
              ),
            ],
          );
        },
      ),
    );
  }
}
