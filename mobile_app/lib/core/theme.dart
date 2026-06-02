import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  // Brand colors
  static const Color background = Color(0xFF0D0F12);
  static const Color surface = Color(0xFF161A22);
  static const Color surfaceCard = Color(0xFF1E232E);
  static const Color border = Color(0xFF2E3545);

  // Accents
  static const Color primary = Color(0xFF6366F1); // Indigo
  static const Color secondary = Color(0xFFEC4899); // Rose Pink
  static const Color accentBlue = Color(0xFF3B82F6); // Electric Blue

  // Semantic
  static const Color income = Color(0xFF10B981); // Emerald
  static const Color expense = Color(0xFFF43F5E); // Rose Red
  static const Color textPrimary = Color(0xFFF3F4F6);
  static const Color textSecondary = Color(0xFF9CA3AF);

  // Gradients
  static const Gradient primaryGradient = LinearGradient(
    colors: [primary, Color(0xFF8B5CF6)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const Gradient accentGradient = LinearGradient(
    colors: [accentBlue, primary],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // Custom Glassmorphic decoration helper
  static BoxDecoration glassCardDecoration({
    Color? color,
    double radius = 16,
    double borderOpacity = 0.1,
  }) {
    return BoxDecoration(
      color: color ?? surface.withOpacity(0.85),
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(
        color: Colors.white.withOpacity(borderOpacity),
        width: 1.0,
      ),
      boxShadow: [
        BoxShadow(
          color: Colors.black.withOpacity(0.2),
          blurRadius: 10,
          offset: const Offset(0, 4),
        ),
      ],
    );
  }

  // Theme Data Builder
  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      primaryColor: primary,
      cardColor: surfaceCard,
      dividerColor: border,
      textTheme: GoogleFonts.outfitTextTheme(ThemeData.dark().textTheme).copyWith(
        bodyLarge: TextStyle(color: textPrimary, fontSize: 16),
        bodyMedium: TextStyle(color: textSecondary, fontSize: 14),
      ),
      colorScheme: const ColorScheme.dark(
        primary: primary,
        secondary: secondary,
        surface: surface,
        error: expense,
      ),
      useMaterial3: true,
    );
  }
}
