import 'dart:io';
import 'package:flutter_test/flutter_test.dart';

/// Token literal guard (SPEC-22 decision 10).
///
/// Scans every .dart file under lib/render/ for raw numeric literals
/// in fontSize or EdgeInsets. All spacing/typography must go through
/// AppSpacing.* and AppTypography.*.

Directory _resolveRenderDir() {
  // flutter test runs from mobile/; CI may run from repo root.
  final candidates = [
    Directory('lib/render'),
    Directory('mobile/lib/render'),
  ];
  for (final d in candidates) {
    if (d.existsSync()) return d;
  }
  fail('Neither lib/render nor mobile/lib/render found. '
       'Run from mobile/ or repo root.');
}

void main() {
  test('no raw fontSize literals in lib/render/', () {
    final renderDir = _resolveRenderDir();
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
    final renderDir = _resolveRenderDir();
    final violations = <String>[];
    for (final file in renderDir.listSync(recursive: true)) {
      if (file is! File || !file.path.endsWith('.dart')) continue;
      final lines = file.readAsLinesSync();
      for (var i = 0; i < lines.length; i++) {
        final line = lines[i];
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
