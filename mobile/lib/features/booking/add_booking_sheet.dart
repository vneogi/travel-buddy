import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../itinerary/itinerary_notifier.dart';
import '../../data/models.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import 'booking_parser.dart';

/// Modal bottom sheet for adding a booking anchor (SPEC-10).
class AddBookingSheet extends ConsumerStatefulWidget {
  final String tripId;

  const AddBookingSheet({super.key, required this.tripId});

  @override
  ConsumerState<AddBookingSheet> createState() => _AddBookingSheetState();
}

class _AddBookingSheetState extends ConsumerState<AddBookingSheet> {
  String _bookingType = 'flight';
  final _titleController = TextEditingController();
  final _codeController = TextEditingController();
  final _notesController = TextEditingController();
  final _pasteController = TextEditingController();
  DateTime _scheduledStart = DateTime.now().add(const Duration(hours: 24));
  int _durationMinutes = 180;

  static const _typeIcons = {
    'flight': Icons.flight_takeoff,
    'hotel': Icons.hotel,
    'train': Icons.train,
    'tour': Icons.explore,
  };

  static const _defaultDurations = {
    'flight': 180,
    'hotel': 480,
    'train': 120,
    'tour': 90,
  };

  @override
  void dispose() {
    _titleController.dispose();
    _codeController.dispose();
    _notesController.dispose();
    _pasteController.dispose();
    super.dispose();
  }

  void _autoFill() {
    final parsed = extractBookingFromText(
      _pasteController.text,
      importSource: 'email',
    );
    setState(() {
      if (parsed.bookingType != null) _bookingType = parsed.bookingType!;
      if (parsed.venueName != null) _titleController.text = parsed.venueName!;
      if (parsed.confirmationCode != null) {
        _codeController.text = parsed.confirmationCode!;
      }
      if (parsed.durationMinutes != null) {
        _durationMinutes = parsed.durationMinutes!;
      }
    });
  }

  Future<void> _pickDateTime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _scheduledStart,
      firstDate: DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_scheduledStart),
    );
    if (time == null || !mounted) return;
    setState(() {
      _scheduledStart = DateTime(
        date.year,
        date.month,
        date.day,
        time.hour,
        time.minute,
      );
    });
  }

  Future<void> _save() async {
    final title = _titleController.text.trim().isEmpty
        ? 'Booking'
        : _titleController.text.trim();

    await ref
        .read(itineraryControllerProvider(widget.tripId).notifier)
        .applyEvent(
      type: EventType.addBooking,
      message: 'Add booking anchor',
      preferences: {
        'venue_name': title,
        'scheduled_start': _scheduledStart.toIso8601String(),
        'duration_minutes': _durationMinutes,
        'booking_type': _bookingType,
        'confirmation_code': _codeController.text.trim().isEmpty
            ? null
            : _codeController.text.trim(),
        'booking_notes': _notesController.text.trim().isEmpty
            ? null
            : _notesController.text.trim(),
        'import_source':
            _pasteController.text.isEmpty ? 'manual' : 'email',
      },
    );

    ref.read(signalServiceProvider).emitBookingAdded(
          bookingType: _bookingType,
          importSource:
              _pasteController.text.isEmpty ? 'manual' : 'email',
          tripId: widget.tripId,
        );

    if (mounted) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
        left: AppSpacing.lg,
        right: AppSpacing.lg,
        top: AppSpacing.lg,
      ),
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Add Booking', style: AppTypography.h2),
            const SizedBox(height: AppSpacing.base),
            // Type picker
            Wrap(
              spacing: AppSpacing.sm,
              children: _typeIcons.entries.map((e) {
                final selected = _bookingType == e.key;
                return ChoiceChip(
                  label: Text(e.key[0].toUpperCase() + e.key.substring(1)),
                  avatar: Icon(e.value, size: 18),
                  selected: selected,
                  onSelected: (_) => setState(() {
                    _bookingType = e.key;
                    _durationMinutes =
                        _defaultDurations[e.key] ?? 90;
                  }),
                );
              }).toList(),
            ),
            const SizedBox(height: AppSpacing.base),
            TextField(
              controller: _titleController,
              decoration: const InputDecoration(labelText: 'Title / Venue'),
            ),
            const SizedBox(height: AppSpacing.sm),
            ListTile(
              contentPadding: EdgeInsets.zero,
              title: const Text('Date & Time'),
              subtitle: Text(
                '${_scheduledStart.day}/${_scheduledStart.month}/${_scheduledStart.year} '
                '${_scheduledStart.hour.toString().padLeft(2, '0')}:'
                '${_scheduledStart.minute.toString().padLeft(2, '0')}',
              ),
              trailing: const Icon(Icons.calendar_today),
              onTap: _pickDateTime,
            ),
            TextField(
              controller: _codeController,
              decoration:
                  const InputDecoration(labelText: 'Confirmation Code'),
            ),
            const SizedBox(height: AppSpacing.sm),
            TextField(
              controller: _notesController,
              decoration: const InputDecoration(labelText: 'Notes'),
              maxLines: 2,
            ),
            const SizedBox(height: AppSpacing.base),
            // Paste import
            ExpansionTile(
              title: const Text('Paste confirmation text'),
              children: [
                TextField(
                  controller: _pasteController,
                  maxLines: 4,
                  decoration: const InputDecoration(
                    hintText: 'Paste email / booking text here',
                  ),
                ),
                const SizedBox(height: AppSpacing.sm),
                TextButton(
                  onPressed: _autoFill,
                  child: const Text('Auto-fill from paste'),
                ),
              ],
            ),
            const SizedBox(height: AppSpacing.lg),
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _save,
                icon: const Icon(Icons.anchor),
                label: const Text('Save Anchor'),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
          ],
        ),
      ),
    );
  }
}
