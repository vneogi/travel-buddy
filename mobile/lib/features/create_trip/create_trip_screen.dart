import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';
import '../home/home_controller.dart';

/// Signature matching [showDateRangePicker] for test injection.
typedef DateRangePickerBuilder = Future<DateTimeRange?> Function({
  required BuildContext context,
  required DateTime firstDate,
  required DateTime lastDate,
  DateTimeRange? initialDateRange,
});

/// SPEC-40: Five-step guided trip creation wizard.
///
/// Loads [homeSnapshotProvider] for server-advertised options.
/// Steps: destination, dates, party, interests, review.
/// Back preserves entered values. Success opens the fetched itinerary.
class CreateTripScreen extends ConsumerStatefulWidget {
  /// Optional override for date picker. Defaults to [showDateRangePicker].
  final DateRangePickerBuilder? datePickerBuilder;

  const CreateTripScreen({super.key, this.datePickerBuilder});

  @override
  ConsumerState<CreateTripScreen> createState() => _CreateTripScreenState();
}

class _CreateTripScreenState extends ConsumerState<CreateTripScreen> {
  int _step = 0;
  bool _submitting = false;
  String? _errorMessage;

  // Step 1: Destination
  String? _selectedRegion;

  // Step 2: Dates
  DateTimeRange? _dateRange;

  // Step 3: Party
  String _partyType = 'solo';
  int _partySize = 1;

  // Step 4: Interests
  final Set<String> _selectedInterests = {};

  /// Returns the server-advertised max days for [region], or null if the
  /// region is not in the options map.  Never invents a fallback.
  int? _maxDaysFor(String? region, CreateTripOptions? opts) {
    if (region == null || opts == null) return null;
    return opts.maxDaysByRegion[region]; // null when absent
  }

  /// Calendar-day count: pure UTC arithmetic, no DST dependency.
  static int _calendarDays(DateTimeRange range) {
    final s = range.start;
    final e = range.end;
    return (DateTime.utc(e.year, e.month, e.day)
                .difference(DateTime.utc(s.year, s.month, s.day))
                .inDays) +
        1;
  }

  static const _stepTitles = [
    'Where are you going?',
    'When?',
    'Who is travelling?',
    'Trip interests',
    'Review & create',
  ];

  bool _canProceed(CreateTripOptions? opts) {
    switch (_step) {
      case 0:
        // Must have a region AND that region must have a known max
        return _selectedRegion != null;
      case 1:
        return _dateRange != null;
      case 2:
        return true;
      case 3:
        return true;
      case 4:
        return !_submitting;
      default:
        return false;
    }
  }

  void _next() {
    if (_step < 4) {
      setState(() {
        _step++;
        _errorMessage = null;
      });
    } else {
      _submit();
    }
  }

  void _back() {
    if (_step > 0) {
      setState(() {
        _step--;
        _errorMessage = null;
      });
    } else {
      Navigator.of(context).maybePop();
    }
  }

  /// When destination changes, invalidate dates if above new max.
  void _onDestinationChanged(String? region, CreateTripOptions? opts) {
    setState(() {
      _selectedRegion = region;
      // SPEC-42: no catalog-derived date cap invalidation.
      // Only sanity-bound check remains in the picker.
    });
  }

  /// Clamp/reset party size on type change.
  void _onPartyTypeChanged(String type) {
    setState(() {
      _partyType = type;
      if (type == 'solo') {
        _partySize = 1;
      } else if (type == 'couple') {
        _partySize = 2;
      } else if (_partySize < 2) {
        _partySize = 3;
      }
    });
  }

  Future<void> _submit() async {
    if (_submitting) return;
    setState(() {
      _submitting = true;
      _errorMessage = null;
    });

    try {
      final trip = await ref.read(tripRepoProvider).rangeCreate(
            geoRegion: _selectedRegion!,
            startDate: _dateRange!.start,
            endDate: _dateRange!.end,
            partyType: _partyType,
            partySize: _partySize,
            interestIds: _selectedInterests.toList(),
          );
      ref.invalidate(homeSnapshotProvider);
      if (!mounted) return;
      context.go('/trip/${trip.tripId}');
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        _errorMessage = e.message;
        _submitting = false;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() {
        _errorMessage = 'Something went wrong. Please try again.';
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final snapshot = ref.watch(homeSnapshotProvider);

    return snapshot.when(
      loading: () => const Scaffold(
        body: Center(child: CircularProgressIndicator()),
      ),
      error: (e, _) => Scaffold(
        appBar: AppBar(title: const Text('Create trip')),
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Text('Could not load trip options.'),
              const SizedBox(height: AppSpacing.base),
              ElevatedButton(
                onPressed: () => ref.invalidate(homeSnapshotProvider),
                child: const Text('Retry'),
              ),
            ],
          ),
        ),
      ),
      data: (home) {
        if (home.createTripOptions == null) {
          return _buildUnavailable();
        }
        return _buildWizard(home);
      },
    );
  }

  /// Shown when [CreateTripOptions] is missing (old/offline snapshot or
  /// mid-refresh state change).  Offers Back + Retry, no wizard chrome.
  Widget _buildUnavailable() {
    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: () => Navigator.of(context).maybePop(),
        ),
        title: const Text('Create trip'),
      ),
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off, size: 48, color: Colors.grey),
            const SizedBox(height: AppSpacing.base),
            const Text('Trip creation is currently unavailable.'),
            const SizedBox(height: AppSpacing.base),
            ElevatedButton(
              onPressed: () => ref.invalidate(homeSnapshotProvider),
              child: const Text('Retry'),
            ),
            const SizedBox(height: AppSpacing.sm),
            OutlinedButton(
              onPressed: () => Navigator.of(context).maybePop(),
              child: const Text('Back'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildWizard(HomeSnapshot home) {
    final opts = home.createTripOptions;
    final regions = home.supportedRegions;
    final partyOptions = opts?.partyTypes ?? const [];
    final interestOptions = opts?.interests ?? const [];

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back),
          onPressed: _back,
        ),
        title: Text(_stepTitles[_step]),
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(4),
          child: LinearProgressIndicator(
            value: (_step + 1) / 5,
            backgroundColor: AppColors.divider,
            valueColor:
                const AlwaysStoppedAnimation<Color>(AppColors.primary),
          ),
        ),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(AppSpacing.base),
                child: _buildStep(
                  regions: regions,
                  opts: opts,
                  partyOptions: partyOptions,
                  interestOptions: interestOptions,
                ),
              ),
            ),
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.base),
                child: Text(
                  _errorMessage!,
                  style: const TextStyle(color: AppColors.danger),
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.base),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  key: const Key('create_trip_submit'),
                  onPressed: _canProceed(opts) ? _next : null,
                  child: _submitting
                      ? const SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(
                              strokeWidth: 2, color: Colors.white),
                        )
                      : Text(_step < 4 ? 'Next' : 'Create trip'),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStep({
    required List<String> regions,
    required CreateTripOptions? opts,
    required List<PartyOption> partyOptions,
    required List<InterestOption> interestOptions,
  }) {
    switch (_step) {
      case 0:
        return _DestinationStep(
          regions: regions,
          selected: _selectedRegion,
          onChanged: (r) => _onDestinationChanged(r, opts),
        );
      case 1:
        return _DatesStep(
          sanityDays: opts?.tripSpanSanityDays ?? 90,
          dateRange: _dateRange,
          onChanged: (r) => setState(() => _dateRange = r),
          pickerBuilder: widget.datePickerBuilder,
        );
      case 2:
        return _PartyStep(
          partyOptions: partyOptions,
          partyType: _partyType,
          partySize: _partySize,
          onTypeChanged: _onPartyTypeChanged,
          onSizeChanged: (s) => setState(() => _partySize = s),
        );
      case 3:
        return _InterestsStep(
          interestOptions: interestOptions,
          selected: _selectedInterests,
          onToggle: (id, on) {
            setState(() {
              if (on && _selectedInterests.length < 3) {
                _selectedInterests.add(id);
              } else {
                _selectedInterests.remove(id);
              }
            });
          },
        );
      case 4:
        return _ReviewStep(
          region: _selectedRegion,
          dateRange: _dateRange,
          partyType: _partyType,
          partySize: _partySize,
          selectedInterests: _selectedInterests,
          partyOptions: partyOptions,
          interestOptions: interestOptions,
        );
      default:
        return const SizedBox.shrink();
    }
  }
}

// ---------------------------------------------------------------------------
// Step widgets
// ---------------------------------------------------------------------------

const _displayNames = {
  'dubai_uae': 'Dubai',
  'luang_prabang_laos': 'Luang Prabang',
  'vang_vieng_laos': 'Vang Vieng',
  'vientiane_laos': 'Vientiane',
};

class _DestinationStep extends StatelessWidget {
  final List<String> regions;
  final String? selected;
  final ValueChanged<String?> onChanged;
  const _DestinationStep({
    required this.regions,
    required this.selected,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Choose your destination',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        ...regions.map((r) {
          return Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.sm),
            child: RadioListTile<String>(
              title: Text(_displayNames[r] ?? r),
              value: r,
              groupValue: selected,
              onChanged: onChanged,
              shape: RoundedRectangleBorder(
                borderRadius:
                    BorderRadius.circular(AppSpacing.radiusCard),
              ),
              tileColor: selected == r
                  ? AppColors.primaryLight
                  : AppColors.card,
            ),
          );
        }),
      ],
    );
  }
}

class _DatesStep extends StatelessWidget {
  final int sanityDays;
  final DateTimeRange? dateRange;
  final ValueChanged<DateTimeRange?> onChanged;
  final DateRangePickerBuilder? pickerBuilder;
  const _DatesStep({
    required this.sanityDays,
    required this.dateRange,
    required this.onChanged,
    this.pickerBuilder,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Pick your dates',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            icon: const Icon(Icons.calendar_today),
            label: Text(dateRange == null
                ? 'Select date range'
                : '${_fmt(dateRange!.start)} - ${_fmt(dateRange!.end)}'),
            onPressed: () => _pick(context),
          ),
        ),
        if (dateRange != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(
            '${_CreateTripScreenState._calendarDays(dateRange!)} days',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    );
  }

  Future<void> _pick(BuildContext context) async {
    final now = DateUtils.dateOnly(DateTime.now());
    final picker = pickerBuilder ?? showDateRangePicker;
    final picked = await picker(
      context: context,
      firstDate: now,
      lastDate: DateTime(now.year + 1, now.month, now.day),
      initialDateRange: dateRange,
    );
    if (picked == null) return;
    final days = _CreateTripScreenState._calendarDays(picked);
    if (days > sanityDays) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Trip cannot exceed $sanityDays days')),
        );
      }
      return;
    }
    onChanged(picked);
  }

  String _fmt(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';
}

class _PartyStep extends StatelessWidget {
  final List<PartyOption> partyOptions;
  final String partyType;
  final int partySize;
  final ValueChanged<String> onTypeChanged;
  final ValueChanged<int> onSizeChanged;
  const _PartyStep({
    required this.partyOptions,
    required this.partyType,
    required this.partySize,
    required this.onTypeChanged,
    required this.onSizeChanged,
  });

  @override
  Widget build(BuildContext context) {
    final showSlider =
        partyType != 'solo' && partyType != 'couple';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...partyOptions.map((p) => Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: RadioListTile<String>(
                title: Text(p.label),
                value: p.id,
                groupValue: partyType,
                onChanged: (v) {
                  if (v != null) onTypeChanged(v);
                },
                shape: RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusCard),
                ),
                tileColor: partyType == p.id
                    ? AppColors.primaryLight
                    : AppColors.card,
              ),
            )),
        if (showSlider) ...[
          const SizedBox(height: AppSpacing.base),
          Text('Party size',
              style: Theme.of(context).textTheme.titleSmall),
          Slider(
            value: partySize.clamp(2, 12).toDouble(),
            min: 2,
            max: 12,
            divisions: 10,
            label: '$partySize',
            onChanged: (v) => onSizeChanged(v.round()),
          ),
        ],
      ],
    );
  }
}

class _InterestsStep extends StatelessWidget {
  final List<InterestOption> interestOptions;
  final Set<String> selected;
  final void Function(String id, bool on) onToggle;
  const _InterestsStep({
    required this.interestOptions,
    required this.selected,
    required this.onToggle,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('What does this trip want more of?',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.xs),
        Text('Choose up to 3, or skip for balanced',
            style: Theme.of(context).textTheme.bodySmall),
        const SizedBox(height: AppSpacing.base),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.sm,
          children: interestOptions.map((interest) {
            final isOn = selected.contains(interest.id);
            return FilterChip(
              label: Text(interest.label),
              selected: isOn,
              onSelected: (on) => onToggle(interest.id, on),
              selectedColor: AppColors.primaryLight,
              checkmarkColor: AppColors.primary,
            );
          }).toList(),
        ),
      ],
    );
  }
}

class _ReviewStep extends StatelessWidget {
  final String? region;
  final DateTimeRange? dateRange;
  final String partyType;
  final int partySize;
  final Set<String> selectedInterests;
  final List<PartyOption> partyOptions;
  final List<InterestOption> interestOptions;
  const _ReviewStep({
    required this.region,
    required this.dateRange,
    required this.partyType,
    required this.partySize,
    required this.selectedInterests,
    required this.partyOptions,
    required this.interestOptions,
  });

  @override
  Widget build(BuildContext context) {
    final partyLabel = partyOptions
        .where((p) => p.id == partyType)
        .map((p) => p.label)
        .firstOrNull ?? partyType;
    final interestLabels = interestOptions
        .where((i) => selectedInterests.contains(i.id))
        .map((i) => i.label)
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Review your trip',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        _row('Destination', _displayNames[region] ?? region ?? ''),
        if (dateRange != null)
          _row('Dates',
              '${_fmtDate(dateRange!.start)} - ${_fmtDate(dateRange!.end)}'
              ' (${_CreateTripScreenState._calendarDays(dateRange!)} days)'),
        _row('Party', '$partyLabel ($partySize)'),
        _row('Interests',
            interestLabels.isEmpty ? 'Balanced' : interestLabels.join(', ')),
      ],
    );
  }

  String _fmtDate(DateTime d) => '${d.year}-${d.month.toString().padLeft(2, '0')}-${d.day.toString().padLeft(2, '0')}';

  Widget _row(String label, String value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppSpacing.md),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(label,
                style: const TextStyle(
                    fontWeight: FontWeight.w600, color: AppColors.muted)),
          ),
          Expanded(child: Text(value)),
        ],
      ),
    );
  }
}
