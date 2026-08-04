import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import 'colors.dart';

/// Two-family type scale: Fraunces (editorial headings) + Inter (body).
class AppTypography {
  AppTypography._();

  // Headings — Fraunces (serif, editorial feel)
  static TextStyle get display => GoogleFonts.fraunces(
        fontSize: 32,
        height: 1.25,
        fontWeight: FontWeight.w700,
        color: AppColors.ink,
      );

  static TextStyle get h1 => GoogleFonts.fraunces(
        fontSize: 24,
        height: 1.33,
        fontWeight: FontWeight.w700,
        color: AppColors.ink,
      );

  static TextStyle get h2 => GoogleFonts.fraunces(
        fontSize: 20,
        height: 1.4,
        fontWeight: FontWeight.w600,
        color: AppColors.ink,
      );

  // Body — Inter (clean, readable)
  static TextStyle get body => GoogleFonts.inter(
        fontSize: 16,
        height: 1.5,
        fontWeight: FontWeight.w400,
        color: AppColors.ink,
      );

  static TextStyle get bodyMedium => GoogleFonts.inter(
        fontSize: 16,
        height: 1.5,
        fontWeight: FontWeight.w500,
        color: AppColors.ink,
      );

  static TextStyle get caption => GoogleFonts.inter(
        fontSize: 13,
        height: 1.38,
        fontWeight: FontWeight.w400,
        color: AppColors.muted,
      );

  static TextStyle get label => GoogleFonts.inter(
        fontSize: 14,
        height: 1.43,
        fontWeight: FontWeight.w500,
        color: AppColors.ink,
      );

  // Numerals (tabular for counter badge)
  static TextStyle get counter => GoogleFonts.inter(
        fontSize: 14,
        height: 1.0,
        fontWeight: FontWeight.w600,
        color: AppColors.ink,
        fontFeatures: const [FontFeature.tabularFigures()],
      );
}
