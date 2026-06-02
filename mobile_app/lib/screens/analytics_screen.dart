import 'dart:math';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  int _activeTimeframe = 1; // 0: Week, 1: Month, 2: Year
  bool _isExporting = false;

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor / 100);
  }

  Future<void> _exportExcel() async {
    setState(() => _isExporting = true);
    // Simulate generation of excel report
    await Future.delayed(const Duration(seconds: 2));
    if (mounted) {
      setState(() => _isExporting = false);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('✅ Отчёт Excel успешно экспортирован и сохранён в загрузки!'),
          backgroundColor: AppTheme.income,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final categories = appState.categories;
    final totalSpent = appState.monthlyExpenses;

    // Define colors for chart segments
    final List<Color> segmentColors = [
      AppTheme.expense,
      AppTheme.accentBlue,
      AppTheme.primary,
      Colors.yellowAccent,
    ];

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  'Аналитика расходов',
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: AppTheme.textPrimary,
                      ),
                ),
                const SizedBox(height: 18),

                // Timeframe Selector Row
                Row(
                  children: [
                    _buildTimeframeTab(0, 'НЕДЕЛЯ'),
                    const SizedBox(width: 8),
                    _buildTimeframeTab(1, 'МЕСЯЦ'),
                    const SizedBox(width: 8),
                    _buildTimeframeTab(2, 'ГОД'),
                  ],
                ),
                const SizedBox(height: 24),

                // Donut Chart Card
                GlassCard(
                  radius: 16,
                  padding: const EdgeInsets.all(20),
                  child: Column(
                    children: [
                      // Render Custom Donut Chart
                      SizedBox(
                        height: 180,
                        child: Stack(
                          children: [
                            Center(
                              child: SizedBox(
                                width: 140,
                                height: 140,
                                child: CustomPaint(
                                  painter: DonutChartPainter(
                                    categories: categories,
                                    totalSpent: totalSpent,
                                    colors: segmentColors,
                                  ),
                                ),
                              ),
                            ),
                            Center(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  const Text(
                                    'ВСЕГО',
                                    style: TextStyle(
                                      color: AppTheme.textSecondary,
                                      fontSize: 10,
                                      letterSpacing: 1.0,
                                    ),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    _formatKzt(totalSpent),
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 18,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 20),

                // Export to Excel Button Card
                GestureDetector(
                  onTap: _isExporting ? null : _exportExcel,
                  child: GlassCard(
                    color: AppTheme.surfaceCard.withOpacity(0.4),
                    radius: 14,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                    child: Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.all(10),
                          decoration: BoxDecoration(
                            color: Colors.orangeAccent.withOpacity(0.1),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(Icons.file_present_rounded, color: Colors.orangeAccent, size: 24),
                        ),
                        const SizedBox(width: 14),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: const [
                              Text(
                                'Выгрузить полный отчёт',
                                style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                              ),
                              SizedBox(height: 2),
                              Text(
                                'Сводная книга Excel (XLSX) за месяц',
                                style: TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                              ),
                            ],
                          ),
                        ),
                        if (_isExporting)
                          const SizedBox(
                            width: 18,
                            height: 18,
                            child: CircularProgressIndicator(
                              strokeWidth: 2,
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.orangeAccent),
                            ),
                          )
                        else
                          const Icon(Icons.chevron_right_rounded, color: AppTheme.textSecondary),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 24),

                // Percent Breakdown category list
                const Text(
                  'Детализация трат',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                ),
                const SizedBox(height: 12),

                ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: categories.length,
                  itemBuilder: (context, index) {
                    final cat = categories[index];
                    final color = segmentColors[index % segmentColors.length];
                    final double percent = totalSpent > 0 ? (cat.spentAmount / totalSpent) * 100 : 0;
                    
                    return Container(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: GlassCard(
                        radius: 12,
                        padding: const EdgeInsets.all(12),
                        child: Row(
                        children: [
                          Container(
                            width: 12,
                            height: 12,
                            decoration: BoxDecoration(
                              color: color,
                              shape: BoxShape.circle,
                            ),
                          ),
                          const SizedBox(width: 12),
                          Text(cat.emoji, style: const TextStyle(fontSize: 16)),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              cat.name,
                              style: const TextStyle(fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                            ),
                          ),
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(
                                _formatKzt(cat.spentAmount),
                                style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                              ),
                              const SizedBox(height: 2),
                              Text(
                                '${percent.toStringAsFixed(1)}%',
                                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  );
                  },
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTimeframeTab(int index, String label) {
    final isActive = _activeTimeframe == index;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() => _activeTimeframe = index),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 10),
          decoration: BoxDecoration(
            color: isActive ? AppTheme.surfaceCard : AppTheme.surface.withOpacity(0.5),
            borderRadius: BorderRadius.circular(10),
            border: Border.all(
              color: isActive ? AppTheme.border : Colors.transparent,
            ),
          ),
          child: Center(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: isActive ? Colors.white : AppTheme.textSecondary,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

// Custom Painter to draw Donut Chart segments
class DonutChartPainter extends CustomPainter {
  final List<Category> categories;
  final int totalSpent;
  final List<Color> colors;

  DonutChartPainter({
    required this.categories,
    required this.totalSpent,
    required this.colors,
  });

  @override
  void paint(Canvas canvas, Size size) {
    if (totalSpent <= 0) return;

    final center = Offset(size.width / 2, size.height / 2);
    final radius = min(size.width / 2, size.height / 2);
    final rect = Rect.fromCircle(center: center, radius: radius);

    double startAngle = -pi / 2;

    for (int i = 0; i < categories.length; i++) {
      final cat = categories[i];
      final color = colors[i % colors.length];
      
      final sweepAngle = (cat.spentAmount / totalSpent) * 2 * pi;

      final paint = Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 24
        ..color = color
        ..strokeCap = StrokeCap.butt;

      canvas.drawArc(rect, startAngle, sweepAngle, false, paint);
      startAngle += sweepAngle;
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}
