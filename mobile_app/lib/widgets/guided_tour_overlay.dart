import 'package:flutter/material.dart';
import '../core/theme.dart';

class GuidedTourOverlay extends StatelessWidget {
  final GlobalKey targetKey;
  final String title;
  final String description;
  final String primaryLabel;
  final IconData icon;
  final int step;
  final int totalSteps;
  final VoidCallback onPrimary;
  final VoidCallback? onBack;
  final VoidCallback onSkip;

  const GuidedTourOverlay({
    super.key,
    required this.targetKey,
    required this.title,
    required this.description,
    required this.primaryLabel,
    required this.icon,
    required this.step,
    required this.totalSteps,
    required this.onPrimary,
    required this.onSkip,
    this.onBack,
  });

  Rect? _targetRect() {
    final context = targetKey.currentContext;
    final renderObject = context?.findRenderObject();
    if (renderObject is! RenderBox || !renderObject.hasSize) return null;
    final offset = renderObject.localToGlobal(Offset.zero);
    return offset & renderObject.size;
  }

  @override
  Widget build(BuildContext context) {
    final screen = MediaQuery.sizeOf(context);
    final safePadding = MediaQuery.paddingOf(context);
    final rawTarget = _targetRect();
    final target = rawTarget?.inflate(10);
    final cardAbove = target != null && target.center.dy > screen.height * 0.55;

    return Material(
      color: Colors.transparent,
      child: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: _TourScrimPainter(target),
            ),
          ),
          if (target != null)
            Positioned.fromRect(
              rect: target,
              child: IgnorePointer(
                child: Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(18),
                    border: Border.all(color: AppTheme.primary, width: 3),
                    boxShadow: [
                      BoxShadow(
                        color: AppTheme.primary.withOpacity(0.55),
                        blurRadius: 24,
                        spreadRadius: 4,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          Positioned(
            left: 16,
            right: 16,
            top: cardAbove ? safePadding.top + 18 : null,
            bottom: cardAbove ? null : safePadding.bottom + 90,
            child: Container(
              constraints: const BoxConstraints(maxWidth: 520),
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: AppTheme.surface,
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: AppTheme.primary.withOpacity(0.45)),
                boxShadow: const [
                  BoxShadow(color: Colors.black54, blurRadius: 28, offset: Offset(0, 12)),
                ],
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 40,
                        height: 40,
                        decoration: BoxDecoration(
                          color: AppTheme.primary.withOpacity(0.16),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Icon(icon, color: AppTheme.primary),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          title,
                          style: const TextStyle(
                            color: AppTheme.textPrimary,
                            fontSize: 17,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                      Text(
                        '${step + 1}/$totalSteps',
                        style: const TextStyle(color: AppTheme.textSecondary, fontWeight: FontWeight.bold),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Text(
                    description,
                    style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13, height: 1.4),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      TextButton(
                        onPressed: onSkip,
                        child: const Text('Пропустить', style: TextStyle(color: AppTheme.textSecondary)),
                      ),
                      const Spacer(),
                      if (onBack != null)
                        IconButton(
                          tooltip: 'Назад',
                          onPressed: onBack,
                          icon: const Icon(Icons.arrow_back_rounded, color: AppTheme.textPrimary),
                        ),
                      const SizedBox(width: 6),
                      ElevatedButton.icon(
                        onPressed: onPrimary,
                        icon: const Icon(Icons.arrow_forward_rounded, size: 18),
                        label: Text(primaryLabel),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: AppTheme.primary,
                          foregroundColor: Colors.white,
                          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _TourScrimPainter extends CustomPainter {
  final Rect? target;

  const _TourScrimPainter(this.target);

  @override
  void paint(Canvas canvas, Size size) {
    final full = Path()..addRect(Offset.zero & size);
    if (target == null) {
      canvas.drawPath(full, Paint()..color = Colors.black.withOpacity(0.78));
      return;
    }
    final hole = Path()
      ..addRRect(RRect.fromRectAndRadius(target!, const Radius.circular(18)));
    final scrim = Path.combine(PathOperation.difference, full, hole);
    canvas.drawPath(scrim, Paint()..color = Colors.black.withOpacity(0.78));
  }

  @override
  bool shouldRepaint(covariant _TourScrimPainter oldDelegate) => oldDelegate.target != target;
}
