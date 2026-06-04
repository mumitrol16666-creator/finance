import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:flutter/cupertino.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  // Ultra-premium space color palette
  static const Color background = Color(0xFF07090E); // Very deep slate/black
  static const Color surface = Color(0xFF0E131E); // Translucent slate
  static const Color surfaceCard = Color(0xFF161C2A); // Carbon card
  static const Color border = Color(0xFF242C3E);

  // High-fidelity Neon Gradients
  static const Color primary = Color(0xFF6366F1); // Indigo
  static const Color secondary = Color(0xFFD946EF); // Fuchsia Neon

  static const Gradient primaryGradient = LinearGradient(
    colors: [Color(0xFF6366F1), Color(0xFF8B5CF6), Color(0xFFD946EF)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const Gradient incomeGradient = LinearGradient(
    colors: [Color(0xFF059669), Color(0xFF10B981), Color(0xFF34D399)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const Gradient expenseGradient = LinearGradient(
    colors: [Color(0xFFE11D48), Color(0xFFF43F5E), Color(0xFFFB7185)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static const Gradient accentBlueGradient = LinearGradient(
    colors: [Color(0xFF2563EB), Color(0xFF3B82F6), Color(0xFF60A5FA)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  // Semantic solid colors for simple chips
  static const Color income = Color(0xFF10B981);
  static const Color expense = Color(0xFFF43F5E);
  static const Color textPrimary = Color(0xFFF9FAFB);
  static const Color textSecondary = Color(0xFF9CA3AF);
  static const Color accentBlue = Color(0xFF3B82F6);

  // Glassmorphic Card decoration helper
  static BoxDecoration glassCardDecoration({double radius = 20, double borderOpacity = 0.08, Color? color}) {
    return BoxDecoration(
      color: color ?? Colors.white.withOpacity(0.035),
      borderRadius: BorderRadius.circular(radius),
      border: Border.all(
        color: Colors.white.withOpacity(borderOpacity),
        width: 1.2,
      ),
    );
  }

  // Theme Builder
  static ThemeData get darkTheme {
    return ThemeData(
      brightness: Brightness.dark,
      scaffoldBackgroundColor: background,
      primaryColor: primary,
      cardColor: surfaceCard,
      dividerColor: border,
      textTheme: GoogleFonts.outfitTextTheme(ThemeData.dark().textTheme).copyWith(
        bodyLarge: const TextStyle(color: textPrimary, fontSize: 16, letterSpacing: 0.2),
        bodyMedium: const TextStyle(color: textSecondary, fontSize: 14, letterSpacing: 0.1),
      ),
      colorScheme: const ColorScheme.dark(
        primary: primary,
        secondary: secondary,
        surface: surface,
        error: expense,
      ),
      pageTransitionsTheme: PageTransitionsTheme(
        builders: {
          TargetPlatform.android: CupertinoPageTransitionsBuilder(),
          TargetPlatform.iOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.windows: CupertinoPageTransitionsBuilder(),
          TargetPlatform.macOS: CupertinoPageTransitionsBuilder(),
          TargetPlatform.linux: CupertinoPageTransitionsBuilder(),
          TargetPlatform.fuchsia: CupertinoPageTransitionsBuilder(),
        },
      ),
      useMaterial3: true,
    );
  }

  static void showPremiumBlockDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: border),
          ),
          title: Row(
            children: const [
              Icon(Icons.star_rounded, color: secondary, size: 28),
              SizedBox(width: 8),
              Text('FinTrack Premium', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
            ],
          ),
          content: const Text(
            'Данная функция доступна только в Premium-версии.\n\nАктивируйте Premium в нашем Telegram боте с помощью команды /upgrade или получите пробный период!',
            style: TextStyle(color: textPrimary, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Хорошо', style: TextStyle(color: primary, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }
}

// Reusable premium Glassmorphic Card widget
class GlassCard extends StatelessWidget {
  final Widget child;
  final double radius;
  final double borderOpacity;
  final double blur;
  final Color? color;
  final Gradient? gradient;
  final EdgeInsetsGeometry? padding;

  const GlassCard({
    super.key,
    required this.child,
    this.radius = 20,
    this.borderOpacity = 0.08,
    this.blur = 18,
    this.color,
    this.gradient,
    this.padding,
  });

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(radius),
      child: BackdropFilter(
        filter: ImageFilter.blur(sigmaX: blur, sigmaY: blur),
        child: Container(
          padding: padding ?? const EdgeInsets.all(18),
          decoration: BoxDecoration(
            gradient: gradient,
            color: color ?? Colors.white.withOpacity(0.035),
            borderRadius: BorderRadius.circular(radius),
            border: Border.all(
              color: Colors.white.withOpacity(borderOpacity),
              width: 1.2,
            ),
          ),
          child: child,
        ),
      ),
    );
  }
}

// Glowing background blur decoration blobs for the "Nebula" look
class BackgroundGlowBlob extends StatelessWidget {
  final double size;
  final Color color;
  final double opacity;

  const BackgroundGlowBlob({
    super.key,
    required this.size,
    required this.color,
    this.opacity = 0.15,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color.withOpacity(opacity),
        boxShadow: [
          BoxShadow(
            color: color.withOpacity(opacity),
            blurRadius: size * 0.7,
            spreadRadius: size * 0.2,
          )
        ],
      ),
    );
  }
}
