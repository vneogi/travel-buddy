import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import '../../core/api_exception.dart';
import '../../core/providers.dart';
import '../../data/models.dart';
import '../../theme/colors.dart';
import '../../theme/spacing.dart';

/// SPEC-40: Five-step guided trip creation wizard.
///
/// Steps: destination, dates, party, interests, review.
/// Back preserves entered values. Success opens the fetched itinerary.
class CreateTripScreen extends ConsumerStatefulWidget {
  final CreateTripOptions? options;
  final List<String> supportedRegions;

  const CreateTripScreen({
    super.key,
    this.options,
    this.supportedRegions = const [],
  });

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

  int get _maxDays {
    if (_selectedRegion == null || widget.options == null) return 5;
    return widget.options!.maxDaysByRegion[_selectedRegion!] ?? 5;
  }

  List<PartyOption> get _partyOptions =>
      widget.options?.partyTypes ?? const [];

  List<InterestOption> get _interestOptions =>
      widget.options?.interests ?? const [];

  static const _stepTitles = [
    'Where are you going?',
    'When?',
    'Who is travelling?',
    'Trip interests',
    'Review & create',
  ];

  bool get _canProceed {
    switch (_step) {
      case 0:
        return _selectedRegion != null;
      case 1:
        return _dateRange != null;
      case 2:
        return true; // party always has a default
      case 3:
        return true; // zero interests is allowed
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

  Future<void> _submit() async {
    if (_submitting) return; // guard against double tap
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
      if (mounted) context.go('/trip/${trip.tripId}');
    } on ApiException catch (e) {
      setState(() {
        _errorMessage = e.message;
        _submitting = false;
      });
    } catch (_) {
      setState(() {
        _errorMessage = 'Something went wrong. Please try again.';
        _submitting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
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
                child: _buildStep(),
              ),
            ),
            if (_errorMessage != null)
              Padding(
                padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.base),
                child: Text(
                  _errorMessage!,
                  style: TextStyle(color: AppColors.danger),
                ),
              ),
            Padding(
              padding: const EdgeInsets.all(AppSpacing.base),
              child: SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: _canProceed ? _next : null,
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

  Widget _buildStep() {
    switch (_step) {
      case 0:
        return _buildDestinationStep();
      case 1:
        return _buildDatesStep();
      case 2:
        return _buildPartyStep();
      case 3:
        return _buildInterestsStep();
      case 4:
        return _buildReviewStep();
      default:
        return const SizedBox.shrink();
    }
  }

  // Step 1: Destination
  Widget _buildDestinationStep() {
    final regions = widget.supportedRegions;
    const displayNames = {
      'dubai_uae': 'Dubai',
      'luang_prabang_laos': 'Luang Prabang',
      'vang_vieng_laos': 'Vang Vieng',
      'vientiane_laos': 'Vientiane',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Choose your destination',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        ...regions.map((r) => Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: RadioListTile<String>(
                title: Text(displayNames[r] ?? r),
                value: r,
                groupValue: _selectedRegion,
                onChanged: (v) => setState(() => _selectedRegion = v),
                shape: RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusCard),
                ),
                tileColor: _selectedRegion == r
                    ? AppColors.primaryLight
                    : AppColors.card,
              ),
            )),
      ],
    );
  }

  // Step 2: Dates
  Widget _buildDatesStep() {
    final max = _maxDays;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Pick your dates (up to $max days)',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        SizedBox(
          width: double.infinity,
          child: OutlinedButton.icon(
            icon: const Icon(Icons.calendar_today),
            label: Text(_dateRange == null
                ? 'Select date range'
                : '${_formatDate(_dateRange!.start)} - ${_formatDate(_dateRange!.end)}'),
            onPressed: _pickDateRange,
          ),
        ),
        if (_dateRange != null) ...[
          const SizedBox(height: AppSpacing.sm),
          Text(
            '${_dateRange!.end.difference(_dateRange!.start).inDays + 1} days',
            style: Theme.of(context).textTheme.bodySmall,
          ),
        ],
      ],
    );
  }

  Future<void> _pickDateRange() async {
    final now = DateTime.now();
    final max = _maxDays;
    final picked = await showDateRangePicker(
      context: context,
      firstDate: now,
      lastDate: now.add(const Duration(days: 365)),
      initialDateRange: _dateRange,
    );
    if (picked == null) return;
    final days = picked.end.difference(picked.start).inDays + 1;
    if (days > max) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Maximum $max days for this destination')),
        );
      }
      return;
    }
    setState(() => _dateRange = picked);
  }

  String _formatDate(DateTime d) =>
      '${d.day}/${d.month}/${d.year}';

  // Step 3: Party
  Widget _buildPartyStep() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Who is travelling?',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        ..._partyOptions.map((p) => Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.sm),
              child: RadioListTile<String>(
                title: Text(p.label),
                value: p.id,
                groupValue: _partyType,
                onChanged: (v) {
                  if (v == null) return;
                  setState(() {
                    _partyType = v;
                    _partySize = v == 'solo' ? 1 : v == 'couple' ? 2 : _partySize;
                  });
                },
                shape: RoundedRectangleBorder(
                  borderRadius:
                      BorderRadius.circular(AppSpacing.radiusCard),
                ),
                tileColor: _partyType == p.id
                    ? AppColors.primaryLight
                    : AppColors.card,
              ),
            )),
        if (_partyType != 'solo' && _partyType != 'couple') ...[
          const SizedBox(height: AppSpacing.base),
          Text('Party size',
              style: Theme.of(context).textTheme.titleSmall),
          Slider(
            value: _partySize.toDouble(),
            min: 2,
            max: 12,
            divisions: 10,
            label: '$_partySize',
            onChanged: (v) => setState(() => _partySize = v.round()),
          ),
        ],
      ],
    );
  }

  // Step 4: Interests
  Widget _buildInterestsStep() {
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
          children: _interestOptions.map((interest) {
            final selected = _selectedInterests.contains(interest.id);
            return FilterChip(
              label: Text(interest.label),
              selected: selected,
              onSelected: (on) {
                setState(() {
                  if (on) {
                    if (_selectedInterests.length < 3) {
                      _selectedInterests.add(interest.id);
                    }
                  } else {
                    _selectedInterests.remove(interest.id);
                  }
                });
              },
              selectedColor: AppColors.primaryLight,
              checkmarkColor: AppColors.primary,
            );
          }).toList(),
        ),
      ],
    );
  }

  // Step 5: Review
  Widget _buildReviewStep() {
    const displayNames = {
      'dubai_uae': 'Dubai',
      'luang_prabang_laos': 'Luang Prabang',
      'vang_vieng_laos': 'Vang Vieng',
      'vientiane_laos': 'Vientiane',
    };
    final partyLabel = _partyOptions
        .where((p) => p.id == _partyType)
        .map((p) => p.label)
        .firstOrNull ?? _partyType;
    final interestLabels = _interestOptions
        .where((i) => _selectedInterests.contains(i.id))
        .map((i) => i.label)
        .toList();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Review your trip',
            style: Theme.of(context).textTheme.titleMedium),
        const SizedBox(height: AppSpacing.base),
        _reviewRow('Destination', displayNames[_selectedRegion] ?? _selectedRegion ?? ''),
        if (_dateRange != null)
          _reviewRow('Dates',
              '${_formatDate(_dateRange!.start)} - ${_formatDate(_dateRange!.end)}'
              ' (${_dateRange!.end.difference(_dateRange!.start).inDays + 1} days)'),
        _reviewRow('Party', '$partyLabel ($_partySize)'),
        _reviewRow('Interests',
            interestLabels.isEmpty ? 'Balanced' : interestLabels.join(', ')),
      ],
    );
  }

  Widget _reviewRow(String label, String value) {
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
