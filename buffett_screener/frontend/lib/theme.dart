import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class BullishTheme {
  static const Color background = Color(0xFFF2FCEF);
  static const Color surface = Color(0xFFFFFFFF);
  static const Color primary = Color(0xFF00E676);
  static const Color outline = Color(0xFFE2E8F0);
  
  static const Color textPrimary = Color(0xFF151E16);
  static const Color textSecondary = Color(0xFF3B4A3D);

  static ThemeData get theme {
    return ThemeData(
      useMaterial3: true,
      scaffoldBackgroundColor: background,
      colorScheme: ColorScheme.fromSeed(
        seedColor: primary,
        background: background,
        surface: surface,
        primary: primary,
      ),
      cardTheme: CardThemeData(
        color: surface,
        elevation: 1,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: const BorderSide(color: outline, width: 1),
        ),
      ),
      textTheme: TextTheme(
        displayLarge: GoogleFonts.splineSans(
          color: textPrimary,
          fontSize: 32,
          fontWeight: FontWeight.bold,
        ),
        titleLarge: GoogleFonts.splineSans(
          color: textPrimary,
          fontSize: 20,
          fontWeight: FontWeight.bold,
        ),
        bodyLarge: GoogleFonts.workSans(
          color: textPrimary,
          fontSize: 16,
        ),
        bodyMedium: GoogleFonts.workSans(
          color: textSecondary,
          fontSize: 14,
        ),
      ),
    );
  }
}
