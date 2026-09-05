import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/providers.dart';
import '../itinerary/itinerary_notifier.dart';
import '../../data/models.dart';
import '../../theme/spacing.dart';
import '../../theme/typography.dart';
import 'booking_parser.dart';
import '../driver_card/driver_card_helpers.dart';

/// Modal bottom sheet for adding a booking anchor (SPEC-10).
class AddBookingSheet extends ConsumerStatefulWidget {
  final String tripId;
  final String initialBookingType;
  final TripNode? editNode;

  const AddBookingSheet({
    super.key,
    required this.tripId,
    this.initialBookingType = 'flight',
    this.editNode,
  });

  @override
  ConsumerState<AddBookingSheet> createState() => _AddBookingSheetState();
}

class _AddBookingSheetState extends ConsumerState<AddBookingSheet> {
  late String _bookingType;
  final _titleController = TextEditingController();
  final _codeController = TextEditingController();
  final _notesController = TextEditingController();
  final _pasteController = TextEditingController();
  DateTime _scheduledStart = DateTime.now().add(const Duration(hours: 24));
  int _durationMinutes = 180;
  DateTime? _checkoutDate;
  String _importSource = 'manual';
  bool _saving = false;
  String? _saveError;
  String? _parsedGeoRegion;

  bool get _isEditMode => widget.editNode != null;
  bool get _isHotel => _bookingType == 'hotel';

  @override
  void initState() {
    super.initState();
    final edit = widget.editNode;
    if (edit != null) {
      _bookingType = edit.bookingType ?? 'flight';
      _titleController.text = edit.venueName;
      _codeController.text = edit.confirmationCode ?? '';
      _notesController.text = edit.bookingNotes ?? '';
      _scheduledStart = edit.scheduledStart;
      _durationMinutes = edit.durationMinutes;
      if (edit.bookingType == 'hotel') {
        _checkoutDate = edit.scheduledStart.add(
          Duration(minutes: edit.durationMinutes),
        );
      }
      _importSource = edit.importSource ?? 'manual';
    } else {
      _bookingType = widget.initialBookingType;
      _durationMinutes = _defaultDurations[_bookingType] ?? 180;
      if (_bookingType == 'hotel') {
        _checkoutDate = _scheduledStart.add(
          const Duration(hours: 24),
        );
      }
    }
  }

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
      if (parsed.scheduledStart != null) {
        _scheduledStart = parsed.scheduledStart!;
      }
      if (parsed.checkoutDate != null && _bookingType == 'hotel') {
        _checkoutDate = parsed.checkoutDate;
      }
      _parsedGeoRegion = parsed.geoRegion;
      _importSource = 'email';
    });
  }

  Future<void> _pickDateTime() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _scheduledStart,
      firstDate: _isEditMode
          ? _scheduledStart.isBefore(DateTime.now())
              ? _scheduledStart
              : DateTime.now()
          : DateTime.now(),
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

  Future<void> _pickCheckinDate() async {
    final date = await showDatePicker(
      context: context,
      initialDate: _scheduledStart,
      firstDate: _isEditMode
          ? _scheduledStart.isBefore(DateTime.now())
              ? _scheduledStart
              : DateTime.now()
          : DateTime.now(),
      lastDate: DateTime.now().add(const Duration(days: 365)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: TimeOfDay.fromDateTime(_scheduledStart),
    );
    if (!mounted) return;
    setState(() {
      final hour = time?.hour ?? 15;
      final minute = time?.minute ?? 0;
      _scheduledStart = DateTime(
        date.year, date.month, date.day, hour, minute,
      );
      // Push checkout forward if it is on or before new check-in.
      if (_checkoutDate != null &&
          !_checkoutDate!.isAfter(_scheduledStart)) {
        _checkoutDate = _scheduledStart.add(const Duration(hours: 24));
      }
    });
  }

  Future<void> _pickCheckoutDate() async {
    final initial = _checkoutDate ?? _scheduledStart.add(
      const Duration(hours: 24),
    );
    final date = await showDatePicker(
      context: context,
      initialDate: initial,
      firstDate: _scheduledStart,
      lastDate: _scheduledStart.add(const Duration(days: 365)),
    );
    if (date == null || !mounted) return;
    final time = await showTimePicker(
      context: context,
      initialTime: _checkoutDate != null
          ? TimeOfDay.fromDateTime(_checkoutDate!)
          : const TimeOfDay(hour: 12, minute: 0),
    );
    if (!mounted) return;
    setState(() {
      final hour = time?.hour ?? 12;
      final minute = time?.minute ?? 0;
      _checkoutDate = DateTime(
        date.year, date.month, date.day, hour, minute,
      );
    });
  }

  Future<void> _save() async {
    if (_saving) return;
    // SPEC-33: For hotels, derive duration from check-in / check-out.
    if (_isHotel) {
      if (_checkoutDate == null ||
          !_checkoutDate!.isAfter(_scheduledStart)) {
        setState(() {
          _saveError = 'Check-out must be after check-in.';
        });
        return;
      }
      _durationMinutes =
          _checkoutDate!.difference(_scheduledStart).inMinutes;
    }
    final title = _titleController.text.trim().isEmpty
        ? 'Booking'
        : _titleController.text.trim();
    setState(() {
      _saving = true;
      _saveError = null;
    });
    final result = await ref
        .read(itineraryControllerProvider(widget.tripId).notifier)
        .applyEvent(
      type: _isEditMode ? EventType.editBooking : EventType.addBooking,
      message: _isEditMode ? 'Edit booking' : 'Add booking anchor',
      targetNodeId: widget.editNode?.nodeId,
      preferences: {
        'venue_name': title,
        'scheduled_start': _scheduledStart.toIso8601String(),
        'duration_minutes': _durationMinutes,
        'booking_type': _bookingType,
        if (_parsedGeoRegion != null) 'geo_region': _parsedGeoRegion,
        'confirmation_code': _codeController.text.trim().isEmpty
            ? null
            : _codeController.text.trim(),
        'booking_notes': _notesController.text.trim().isEmpty
            ? null
            : _notesController.text.trim(),
        'import_source': _importSource,
      },
    );
    if (result == null) {
      if (mounted) {
        setState(() {
          _saving = false;
          _saveError =
              'Could not save this booking. Check your connection and try again.';
        });
      }
      return;
    }

    if (!_isEditMode) {
      ref.read(signalServiceProvider).emitBookingAdded(
            bookingType: _bookingType,
            importSource: _importSource,
            tripId: widget.tripId,
          );
    }

    // SPEC-04: Pre-cache place data for offline driver cards
    try {
      final db = ref.read(offlineDatabaseProvider);
      final savedNode = result.updatedNodes
          .where((node) =>
              node.nodeKind == 'booking' &&
              node.bookingType == _bookingType &&
              node.venueName == title)
          .firstOrNull;
      final placeData = savedNode == null
          ? PlaceDriverCardData(placeRef: title, venueName: title)
          : PlaceDriverCardData.fromTripNode(savedNode);
      db.cachePlace(title, placeData.serialize()).catchError((_) {});
    } catch (_) {}

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
            Text(_isEditMode ? 'Edit Booking' : 'Add Booking',
                style: AppTypography.h2),
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
                    if (e.key == 'hotel' && _checkoutDate == null) {
                      _checkoutDate = _scheduledStart.add(
                        const Duration(hours: 24),
                      );
                    } else if (e.key != 'hotel') {
                      _checkoutDate = null;
                    }
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
            if (_isHotel) ...[
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Check-in'),
                subtitle: Text(_formatDate(_scheduledStart)),
                trailing: const Icon(Icons.calendar_today),
                onTap: _pickCheckinDate,
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Check-out'),
                subtitle: Text(
                  _checkoutDate != null
                      ? _formatDate(_checkoutDate!)
                      : 'Select check-out date',
                ),
                trailing: const Icon(Icons.calendar_today),
                onTap: _pickCheckoutDate,
              ),
            ] else
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Date & Time'),
                subtitle: Text(_formatDate(_scheduledStart)),
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
            if (_saveError != null) ...[
              Text(
                _saveError!,
                style: AppTypography.caption.copyWith(
                  color: Theme.of(context).colorScheme.error,
                ),
              ),
              const SizedBox(height: AppSpacing.sm),
            ],
            SizedBox(
              width: double.infinity,
              child: FilledButton.icon(
                onPressed: _saving ? null : _save,
                icon: _saving
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.anchor),
                label: Text(
                  _saving
                      ? 'Saving\u2026'
                      : _isEditMode
                          ? 'Save Changes'
                          : 'Save Anchor',
                ),
              ),
            ),
            const SizedBox(height: AppSpacing.lg),
          ],
        ),
      ),
    );
  }

  String _formatDate(DateTime dt) =>
      '${dt.day}/${dt.month}/${dt.year} '
      '${dt.hour.toString().padLeft(2, "0")}:'
      '${dt.minute.toString().padLeft(2, "0")}';
}
