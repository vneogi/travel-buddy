import 'package:flutter/material.dart';

import '../../theme/spacing.dart';

class AskEntryBar extends StatefulWidget {
  final ValueChanged<String> onSubmit;
  final bool enabled;
  final String hintText;

  const AskEntryBar({
    super.key,
    required this.onSubmit,
    this.enabled = true,
    this.hintText = 'Ask anything about this trip',
  });

  @override
  State<AskEntryBar> createState() => _AskEntryBarState();
}

class _AskEntryBarState extends State<AskEntryBar> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final value = _controller.text.trim();
    if (!widget.enabled || value.isEmpty) return;
    _controller.clear();
    widget.onSubmit(value);
  }

  @override
  Widget build(BuildContext context) => SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(
            AppSpacing.base,
            AppSpacing.xs,
            AppSpacing.base,
            AppSpacing.sm,
          ),
          child: TextField(
            controller: _controller,
            enabled: widget.enabled,
            textInputAction: TextInputAction.send,
            onSubmitted: (_) => _submit(),
            decoration: InputDecoration(
              hintText: widget.hintText,
              prefixIcon: const Icon(Icons.auto_awesome_outlined),
              suffixIcon: IconButton(
                tooltip: 'Send',
                onPressed: widget.enabled ? _submit : null,
                icon: const Icon(Icons.send_outlined),
              ),
              border: const OutlineInputBorder(),
            ),
          ),
        ),
      );
}
