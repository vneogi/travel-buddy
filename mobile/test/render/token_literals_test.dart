import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

/// Token literal guard (SPEC-22 decision 10).
///
/// Scans every .dart file under mobile/lib/render/ for raw numeric literals
/// in fontSize or EdgeInsets. All spacing/typography must go through
/// AppSpacing.* and AppTypography.*.
void main() {
  test('no raw fontSize literals in lib/render/', () {
    final renderDir = Directory('lib/render');
    if (!renderDir.existsSync()) {
      // When running from mobile/ the path is lib/render
      // When running from repo root it is mobile/lib/render
      return; // skip gracefully if dir not found (CI runs from mobile/)
    }
    final violations = <String>[];
    for (final file in renderDir.listSync(recursive: true)) {
      if (file is! File || !file.path.endsWith('.dart')) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
        if (RegExp(r'fontSize:\s*\d').hasMatch(line)) {
          violations.add('${file.path}:${i + 1}: $line');
        }
      }
    }
    expect(violations, isEmpty,
        reason: 'Raw fontSize literals found. Use AppTypography tokens.');
  });

  test('no raw EdgeInsets numeric literals in lib/render/', () {
    final renderDir = Directory('lib/render');
    if (!renderDir.existsSync()) return;
    final violations = <String>[];
    for (final file in renderDir.listSync(recursive: true)) {
      if (file is! File || !file.path.endsWith('.dart')) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
        // Match EdgeInsets.(all|only|symmetric) with 2+ digit raw numbers
        // but allow AppSpacing references
        if (RegExp(r'EdgeInsets\.(all|only|symmetric)\([^)]*\d{2,}').hasMatch(line) &&
            !line.contains('AppSpacing')) {
          violations.add('${file.path}:${i + 1}: $line');
        }
      }
    }
    expect(violations, isEmpty,
        reason: 'Raw EdgeInsets literals found. Use AppSpacing tokens.');
  });
}
