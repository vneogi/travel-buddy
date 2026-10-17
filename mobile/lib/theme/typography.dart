import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'colors.dart';

/// Two-family type scale: Fraunces (editorial headings) + Inter (body).
class AppTypography {
  AppTypography._();

  /// Set to false in tests to avoid GoogleFonts HTTP / plugin calls.
  static bool useGoogleFonts = true;

  // Headings — Fraunces (serif, editorial feel)
  static TextStyle get display => useGoogleFonts
      ? GoogleFonts.fraunces(
          fontSize: 32,
          height: 1.25,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        )
      : const TextStyle(
          fontSize: 32,
          height: 1.25,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        );

  static TextStyle get h1 => useGoogleFonts
      ? GoogleFonts.fraunces(
          fontSize: 24,
          height: 1.33,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        )
      : const TextStyle(
          fontSize: 24,
          height: 1.33,
          fontWeight: FontWeight.w700,
          color: AppColors.ink,
        );

  static TextStyle get h2 => useGoogleFonts
      ? GoogleFonts.fraunces(
          fontSize: 20,
          height: 1.4,
          fontWeight: FontWeight.w600,
          color: AppColors.ink,
        )
      : const TextStyle(
          fontSize: 20,
          height: 1.4,
          fontWeight: FontWeight.w600,
          color: AppColors.ink,
        );

  /// Large native-script treatment for arm's-length driver-card reading.
  /// Uses system fallbacks so rendering does not require a font download.
  /// Bundled Noto assets remain the deterministic full offline fix.
  static TextStyle localScript(String? languageCode) {
    final fallbacks = switch (languageCode) {
      'lo' => const ['Noto Sans Lao', 'Leelawadee UI', 'sans-serif'],
      'ar' => const ['Noto Naskh Arabic', 'Segoe UI', 'sans-serif'],
      _ => const ['Noto Sans', 'Arial Unicode MS', 'sans-serif'],
    };
    return TextStyle(
      fontSize: 36,
      height: 1.45,
      fontWeight: FontWeight.w700,
      color: AppColors.ink,
      fontFamilyFallback: fallbacks,
    );
  }

  // Body — Inter (clean, readable)
  static TextStyle get body => useGoogleFonts
      ? GoogleFonts.inter(
          fontSize: 16,
          height: 1.5,
          fontWeight: FontWeight.w400,
          color: AppColors.ink,
        )
      : const TextStyle(
          fontSize: 16,
          height: 1.5,
          fontWeight: FontWeight.w400,
          color: AppColors.ink,
        );

  static TextStyle get bodyMedium => useGoogleFonts
      ? GoogleFonts.inter(
          fontSize: 16,
          height: 1.5,
          fontWeight: FontWeight.w500,
          color: AppColors.ink,
        )
      : const TextStyle(
          fontSize: 16,
          height: 1.5,
          fontWeight: FontWeight.w500,
          color: AppColors.ink,
        );

  static TextStyle get caption => useGoogleFonts
      ? GoogleFonts.inter(
          fontSize: 13,
          height: 1.38,
          fontWeight: FontWeight.w400,
          color: AppColors.muted,
        )
      : TextStyle(
          fontSize: 13,
          height: 1.38,
          fontWeight: FontWeight.w400,
          color: AppColors.muted,
        );

  static TextStyle get label => useGoogleFonts
      ? GoogleFonts.inter(
          fontSize: 14,
          height: 1.43,
          fontWeight: FontWeight.w500,
          color: AppColors.ink,
        )
      : const TextStyle(
          fontSize: 14,
          height: 1.43,
          fontWeight: FontWeight.w500,
          color: AppColors.ink,
        );

  // Numerals (tabular for counter badge)
  static TextStyle get counter => useGoogleFonts
      ? GoogleFonts.inter(
          fontSize: 14,
          height: 1.0,
          fontWeight: FontWeight.w600,
          color: AppColors.ink,
          fontFeatures: const [FontFeature.tabularFigures()],
        )
      : const TextStyle(
          fontSize: 14,
          height: 1.0,
          fontWeight: FontWeight.w600,
          color: AppColors.ink,
          fontFeatures: [FontFeature.tabularFigures()],
        );
}
