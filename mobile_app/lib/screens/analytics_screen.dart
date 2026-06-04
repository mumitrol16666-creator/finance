import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:fl_chart/fl_chart.dart';
import 'package:flutter_animate/flutter_animate.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';
import '../utils/file_saver.dart';

class AnalyticsScreen extends StatefulWidget {
  const AnalyticsScreen({super.key});

  @override
  State<AnalyticsScreen> createState() => _AnalyticsScreenState();
}

class _AnalyticsScreenState extends State<AnalyticsScreen> {
  int _activeTab = 0; // 0: Expenses, 1: Incomes, 2: Savings
  int _activeTimeframe = 1; // 0: Week, 1: Month, 2: Year
  bool _isExporting = false;
  int touchedIndex = -1;

  // AI Audit states
  String? _aiAuditText;
  bool _isAuditing = false;

  // Visual layout mode: Pie vs Line Chart
  bool _showTrendLine = false;

  // Period navigation state
  DateTime _currentRefDate = DateTime.now();

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _previousPeriod() {
    setState(() {
      _currentRefDate = DateTime(_currentRefDate.year, _currentRefDate.month - 1, _currentRefDate.day);
    });
    _reloadPeriodData();
  }

  void _nextPeriod() {
    setState(() {
      _currentRefDate = DateTime(_currentRefDate.year, _currentRefDate.month + 1, _currentRefDate.day);
    });
    _reloadPeriodData();
  }

  void _resetPeriod() {
    setState(() {
      _currentRefDate = DateTime.now();
    });
    _reloadPeriodData();
  }

  void _reloadPeriodData() {
    final appState = Provider.of<AppState>(context, listen: false);
    final dateStr = DateFormat('yyyy-MM-dd').format(_currentRefDate);
    appState.loadDashboardData(refDate: dateStr);
    setState(() {
      _aiAuditText = null;
    });
  }

  Future<void> _runAiAudit() async {
    setState(() {
      _isAuditing = true;
      _aiAuditText = null;
    });
    final appState = Provider.of<AppState>(context, listen: false);
    final dateStr = DateFormat('yyyy-MM-dd').format(_currentRefDate);
    final result = await appState.fetchAIBudgetAudit(refDate: dateStr);
    if (mounted) {
      setState(() {
        _aiAuditText = result;
        _isAuditing = false;
      });
    }
  }

  Future<void> _exportExcel() async {
    setState(() => _isExporting = true);
    final appState = Provider.of<AppState>(context, listen: false);
    final period = _activeTimeframe == 0
        ? 'week'
        : (_activeTimeframe == 1 ? 'month' : 'all');
    try {
      final bytes = await appState.exportExcelReport(period);
      if (bytes != null && bytes.isNotEmpty) {
        await FileSaver.saveFile(bytes, "finance_${period}_report.xlsx");
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('✅ Отчёт Excel успешно экспортирован и сохранён в загрузки!'),
              backgroundColor: AppTheme.income,
            ),
          );
        }
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('❌ Не удалось экспортировать отчет. Возможно, нет операций за этот период.'),
              backgroundColor: AppTheme.expense,
            ),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('❌ Ошибка при экспорте отчета: $e'),
            backgroundColor: AppTheme.expense,
          ),
        );
      }
    } finally {
      if (mounted) {
        setState(() => _isExporting = false);
      }
    }
  }

  List<FlSpot> _getDailyTrendSpots(List<Transaction> transactions, int daysCount) {
    final Map<int, double> dailyTotals = {};
    for (int i = 1; i <= daysCount; i++) {
      dailyTotals[i] = 0;
    }

    final targetKind = _activeTab == 0 ? 'expense' : 'income';

    for (var tx in transactions) {
      if (tx.kind != targetKind) continue;
      final day = tx.timestamp.day;
      if (day >= 1 && day <= daysCount) {
        dailyTotals[day] = (dailyTotals[day] ?? 0) + tx.amount.toDouble();
      }
    }

    List<FlSpot> spots = [];
    dailyTotals.forEach((day, total) {
      spots.add(FlSpot(day.toDouble(), total));
    });
    spots.sort((a, b) => a.x.compareTo(b.x));
    return spots;
  }

  Widget _buildTabButton(int index, String label) {
    final isActive = _activeTab == index;
    return Expanded(
      child: GestureDetector(
        onTap: () => setState(() {
          _activeTab = index;
          touchedIndex = -1;
        }),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: isActive ? AppTheme.primary.withOpacity(0.18) : AppTheme.surface.withOpacity(0.2),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: isActive ? AppTheme.primary : AppTheme.border.withOpacity(0.3),
              width: 1.5,
            ),
          ),
          child: Center(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.bold,
                color: isActive ? Colors.white : AppTheme.textSecondary,
                letterSpacing: 0.8,
              ),
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

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final allCategories = appState.categories;
    final transactions = appState.transactions;
    final bool isCurrentPeriod = DateTime.now().year == _currentRefDate.year && DateTime.now().month == _currentRefDate.month;

    // Filter categories based on Expenses vs Incomes
    final expensesCategories = allCategories.where((c) => c.kind == 'expense').toList();
    final incomesCategories = allCategories.where((c) => c.kind == 'income').toList();

    final activeCategoriesList = _activeTab == 0 ? expensesCategories : incomesCategories;
    final int activeSum = _activeTab == 0 ? appState.cycleExpenses : appState.cycleIncome;

    final savingsAccounts = appState.accounts.where((a) => a.isSaving).toList();
    final int totalSavings = savingsAccounts.fold(0, (sum, a) => sum + a.balance);

    final List<Color> segmentColors = [
      AppTheme.primary,
      AppTheme.secondary,
      AppTheme.accentBlue,
      Colors.amber,
      Colors.cyan,
      Colors.greenAccent,
      Colors.orangeAccent,
      Colors.pinkAccent,
    ];

    // Net profit calculations
    final netFlow = appState.cycleIncome - appState.cycleExpenses;

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
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Аналитика',
                      style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                            color: AppTheme.textPrimary,
                          ),
                    ),
                    if (appState.isPremium)
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                        decoration: BoxDecoration(
                          gradient: AppTheme.primaryGradient,
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: const Row(
                          children: [
                            Icon(Icons.star_rounded, color: Colors.white, size: 12),
                            SizedBox(width: 4),
                            Text('PREMIUM', style: TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold)),
                          ],
                        ),
                      ),
                  ],
                ).animate().fade(duration: 400.ms).slideY(begin: -0.2),
                const SizedBox(height: 18),

                // Top Tab Selector Row
                Row(
                  children: [
                    _buildTabButton(0, 'РАСХОДЫ'),
                    const SizedBox(width: 8),
                    _buildTabButton(1, 'ДОХОДЫ'),
                    const SizedBox(width: 8),
                    _buildTabButton(2, 'КОПИЛКИ'),
                  ],
                ).animate().fade(delay: 50.ms).slideY(begin: -0.1),
                const SizedBox(height: 20),

                // Net cash flow summary card
                GlassCard(
                  radius: 16,
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Row(
                            children: [
                              const Text('Период списания:', style: TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
                              if (!isCurrentPeriod) ...[
                                const SizedBox(width: 6),
                                GestureDetector(
                                  onTap: _resetPeriod,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2.5),
                                    decoration: BoxDecoration(
                                      color: AppTheme.primary.withOpacity(0.2),
                                      borderRadius: BorderRadius.circular(4),
                                      border: Border.all(color: AppTheme.primary.withOpacity(0.4), width: 0.5),
                                    ),
                                    child: const Text(
                                      'ТЕКУЩИЙ',
                                      style: TextStyle(color: Colors.white, fontSize: 8, fontWeight: FontWeight.bold, letterSpacing: 0.5),
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          Row(
                            children: [
                              IconButton(
                                icon: const Icon(Icons.chevron_left_rounded, color: Colors.white70, size: 20),
                                constraints: const BoxConstraints(),
                                padding: const EdgeInsets.symmetric(horizontal: 4),
                                onPressed: _previousPeriod,
                              ),
                              Text(
                                appState.cycleStart != null && appState.cycleEnd != null
                                    ? '${DateFormat('dd.MM.yy').format(DateTime.parse(appState.cycleStart!))} — ${DateFormat('dd.MM.yy').format(DateTime.parse(appState.cycleEnd!))}'
                                    : 'Весь период',
                                style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 12),
                              ),
                              IconButton(
                                icon: const Icon(Icons.chevron_right_rounded, color: Colors.white70, size: 20),
                                constraints: const BoxConstraints(),
                                padding: const EdgeInsets.symmetric(horizontal: 4),
                                onPressed: _nextPeriod,
                              ),
                            ],
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      const Divider(color: AppTheme.border, height: 1),
                      const SizedBox(height: 12),
                      Row(
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('Доходы', style: TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
                                const SizedBox(height: 4),
                                Text(_formatKzt(appState.cycleIncome), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.income)),
                              ],
                            ),
                          ),
                          Container(width: 1, height: 32, color: AppTheme.border),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text('Расходы', style: TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
                                const SizedBox(height: 4),
                                Text(_formatKzt(appState.cycleExpenses), style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.expense)),
                              ],
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 12),
                      Container(
                        padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
                        decoration: BoxDecoration(
                          color: netFlow >= 0 ? AppTheme.income.withOpacity(0.06) : AppTheme.expense.withOpacity(0.06),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: netFlow >= 0 ? AppTheme.income.withOpacity(0.15) : AppTheme.expense.withOpacity(0.15),
                          ),
                        ),
                        child: Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              netFlow >= 0 ? 'Чистая экономия:' : 'Дефицит бюджета:',
                              style: const TextStyle(color: Colors.white70, fontSize: 12, fontWeight: FontWeight.bold),
                            ),
                            Text(
                              _formatKzt(netFlow),
                              style: TextStyle(
                                fontWeight: FontWeight.bold,
                                fontSize: 14,
                                color: netFlow >= 0 ? AppTheme.income : AppTheme.expense,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ).animate().fade(delay: 100.ms).slideY(begin: 0.1),
                const SizedBox(height: 20),

                // AI Budget Audit Box
                if (appState.isPremium) ...[
                  Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        colors: [
                          AppTheme.primary.withOpacity(0.15),
                          AppTheme.secondary.withOpacity(0.05),
                        ],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                      borderRadius: BorderRadius.circular(16),
                      border: Border.all(color: AppTheme.primary.withOpacity(0.25), width: 1.5),
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.primary.withOpacity(0.06),
                          blurRadius: 16,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Row(
                              children: [
                                Text('🔮', style: TextStyle(fontSize: 18)),
                                SizedBox(width: 8),
                                Text(
                                  'Умный ИИ-Аудитор Бюджета',
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Colors.white),
                                ),
                              ],
                            ),
                            if (_aiAuditText != null && !_isAuditing)
                              IconButton(
                                icon: const Icon(Icons.refresh_rounded, color: AppTheme.secondary, size: 18),
                                constraints: const BoxConstraints(),
                                padding: EdgeInsets.zero,
                                onPressed: _runAiAudit,
                              ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        if (_isAuditing)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 16.0),
                            child: Center(
                              child: SpinKitThreeBounce(
                                color: AppTheme.secondary,
                                size: 24,
                              ),
                            ),
                          )
                        else if (_aiAuditText != null)
                          Text(
                            _aiAuditText!,
                            style: const TextStyle(color: Colors.white70, fontSize: 13, height: 1.45),
                          )
                        else
                          ElevatedButton(
                            onPressed: _runAiAudit,
                            style: ElevatedButton.styleFrom(
                              backgroundColor: AppTheme.surfaceCard,
                              foregroundColor: Colors.white,
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(10),
                                side: BorderSide(color: AppTheme.secondary.withOpacity(0.3)),
                              ),
                              padding: const EdgeInsets.symmetric(vertical: 10),
                            ),
                            child: const Text('Запустить ИИ-Аудит трат', style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold)),
                          ),
                      ],
                    ),
                  ).animate().fade(delay: 150.ms).slideY(begin: 0.1),
                  const SizedBox(height: 20),
                ],

                if (_activeTab < 2) ...[
                  // Timeframe Selector Row
                  Row(
                    children: [
                      _buildTimeframeTab(0, 'НЕДЕЛЯ'),
                      const SizedBox(width: 8),
                      _buildTimeframeTab(1, 'МЕСЯЦ'),
                      const SizedBox(width: 8),
                      _buildTimeframeTab(2, 'ГОД'),
                    ],
                  ).animate().fade(delay: 200.ms),
                  const SizedBox(height: 20),

                  // Chart Card
                  GlassCard(
                    radius: 16,
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Text(
                              _showTrendLine ? 'Трендовый график' : 'Долевое распределение',
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.white70),
                            ),
                            // Toggle Chart Type
                            Row(
                              children: [
                                IconButton(
                                  icon: Icon(Icons.pie_chart_outline_rounded,
                                      color: !_showTrendLine ? AppTheme.primary : AppTheme.textSecondary, size: 20),
                                  onPressed: () => setState(() => _showTrendLine = false),
                                  constraints: const BoxConstraints(),
                                  padding: const EdgeInsets.all(4),
                                ),
                                IconButton(
                                  icon: Icon(Icons.show_chart_rounded,
                                      color: _showTrendLine ? AppTheme.primary : AppTheme.textSecondary, size: 20),
                                  onPressed: () => setState(() => _showTrendLine = true),
                                  constraints: const BoxConstraints(),
                                  padding: const EdgeInsets.all(4),
                                ),
                              ],
                            ),
                          ],
                        ),
                        const SizedBox(height: 16),
                        if (_showTrendLine)
                          SizedBox(
                            height: 190,
                            child: LineChart(
                              LineChartData(
                                gridData: FlGridData(
                                  show: true,
                                  drawVerticalLine: false,
                                  getDrawingHorizontalLine: (val) => FlLine(
                                    color: Colors.white.withOpacity(0.04),
                                    strokeWidth: 1,
                                  ),
                                ),
                                titlesData: FlTitlesData(
                                  rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                                  topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                                  leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
                                  bottomTitles: AxisTitles(
                                    sideTitles: SideTitles(
                                      showTitles: true,
                                      reservedSize: 22,
                                      interval: 7,
                                      getTitlesWidget: (value, meta) {
                                        return Text(
                                          '${value.toInt()}д',
                                          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10),
                                        );
                                      },
                                    ),
                                  ),
                                ),
                                borderData: FlBorderData(show: false),
                                lineBarsData: [
                                  LineChartBarData(
                                    spots: _getDailyTrendSpots(transactions, appState.totalCycleDays),
                                    isCurved: true,
                                    gradient: LinearGradient(
                                      colors: _activeTab == 0
                                          ? [AppTheme.expense, AppTheme.secondary]
                                          : [AppTheme.income, AppTheme.accentBlue],
                                    ),
                                    barWidth: 3,
                                    isStrokeCapRound: true,
                                    dotData: const FlDotData(show: false),
                                    belowBarData: BarAreaData(
                                      show: true,
                                      gradient: LinearGradient(
                                        colors: _activeTab == 0
                                            ? [AppTheme.expense.withOpacity(0.2), AppTheme.secondary.withOpacity(0.01)]
                                            : [AppTheme.income.withOpacity(0.2), AppTheme.accentBlue.withOpacity(0.01)],
                                        begin: Alignment.topCenter,
                                        end: Alignment.bottomCenter,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          )
                        else
                          SizedBox(
                            height: 190,
                            child: Stack(
                              children: [
                                PieChart(
                                  PieChartData(
                                    pieTouchData: PieTouchData(
                                      touchCallback: (FlTouchEvent event, pieTouchResponse) {
                                        setState(() {
                                          if (!event.isInterestedForInteractions ||
                                              pieTouchResponse == null ||
                                              pieTouchResponse.touchedSection == null) {
                                            touchedIndex = -1;
                                            return;
                                          }
                                          touchedIndex = pieTouchResponse.touchedSection!.touchedSectionIndex;
                                        });
                                      },
                                    ),
                                    borderData: FlBorderData(show: false),
                                    sectionsSpace: 2,
                                    centerSpaceRadius: 55,
                                    sections: showingSections(activeCategoriesList, activeSum, segmentColors),
                                  ),
                                ).animate().scale(duration: 500.ms, curve: Curves.easeOut),
                                Center(
                                  child: Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
                                      Text(
                                        _activeTab == 0 ? 'РАСХОДЫ' : 'ДОХОДЫ',
                                        style: const TextStyle(
                                          color: AppTheme.textSecondary,
                                          fontSize: 9,
                                          letterSpacing: 1.0,
                                        ),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        _formatKzt(activeSum),
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontSize: 16,
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
                  ).animate().fade(delay: 250.ms).slideY(begin: 0.1),
                  const SizedBox(height: 24),

                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        _activeTab == 0 ? 'Детализация трат' : 'Детализация поступлений',
                        style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                      ),
                    ],
                  ).animate().fade(delay: 300.ms),
                  const SizedBox(height: 12),

                  if (activeCategoriesList.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text(
                          'Нет данных для отображения',
                          style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                        ),
                      ),
                    )
                  else
                    ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: activeCategoriesList.length,
                      itemBuilder: (context, index) {
                        final cat = activeCategoriesList[index];
                        final color = segmentColors[index % segmentColors.length];
                        final double percent = activeSum > 0 ? (cat.spentAmount / activeSum) * 100 : 0;

                        // Check limit consumption if expense
                        final hasLimit = _activeTab == 0 && cat.limitAmount != null && cat.limitAmount! > 0;
                        final double limitProgress = hasLimit ? (cat.spentAmount / cat.limitAmount!).clamp(0.0, 1.0) : 0.0;
                        final limitColor = limitProgress >= 1.0
                            ? AppTheme.expense
                            : (limitProgress >= 0.85 ? Colors.orangeAccent : AppTheme.primary);

                        return Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: GlassCard(
                            radius: 14,
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      width: 10,
                                      height: 10,
                                      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                                    ),
                                    const SizedBox(width: 10),
                                    Text(cat.emoji, style: const TextStyle(fontSize: 16)),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        cat.name,
                                        style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary, fontSize: 14),
                                      ),
                                    ),
                                    Column(
                                      crossAxisAlignment: CrossAxisAlignment.end,
                                      children: [
                                        Text(
                                          _formatKzt(cat.spentAmount),
                                          style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary, fontSize: 13.5),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          '${percent.toStringAsFixed(1)}%',
                                          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                                if (hasLimit) ...[
                                  const SizedBox(height: 8),
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        'Бюджет: ${_formatKzt(cat.limitAmount!)}',
                                        style: const TextStyle(fontSize: 9.5, color: AppTheme.textSecondary),
                                      ),
                                      Text(
                                        '${(limitProgress * 100).toStringAsFixed(0)}% израсходовано',
                                        style: TextStyle(fontSize: 9.5, color: limitColor, fontWeight: FontWeight.bold),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  ClipRRect(
                                    borderRadius: BorderRadius.circular(4),
                                    child: LinearProgressIndicator(
                                      value: limitProgress,
                                      minHeight: 5,
                                      backgroundColor: AppTheme.border.withOpacity(0.3),
                                      valueColor: AlwaysStoppedAnimation<Color>(limitColor),
                                    ),
                                  ),
                                ] else ...[
                                  const SizedBox(height: 8),
                                  ClipRRect(
                                    borderRadius: BorderRadius.circular(4),
                                    child: LinearProgressIndicator(
                                      value: percent / 100,
                                      minHeight: 4,
                                      backgroundColor: AppTheme.border.withOpacity(0.3),
                                      valueColor: AlwaysStoppedAnimation<Color>(color.withOpacity(0.6)),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        ).animate().fade(delay: Duration(milliseconds: 300 + (index * 60))).slideX(begin: 0.05);
                      },
                    ),
                ] else ...[
                  // Savings Dashboard
                  GlassCard(
                    radius: 16,
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          'Распределение в копилках',
                          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.white70),
                        ),
                        const SizedBox(height: 16),
                        SizedBox(
                          height: 190,
                          child: Stack(
                            children: [
                              PieChart(
                                PieChartData(
                                  pieTouchData: PieTouchData(
                                    touchCallback: (FlTouchEvent event, pieTouchResponse) {
                                      setState(() {
                                        if (!event.isInterestedForInteractions ||
                                            pieTouchResponse == null ||
                                            pieTouchResponse.touchedSection == null) {
                                          touchedIndex = -1;
                                          return;
                                        }
                                        touchedIndex = pieTouchResponse.touchedSection!.touchedSectionIndex;
                                      });
                                    },
                                  ),
                                  borderData: FlBorderData(show: false),
                                  sectionsSpace: 2,
                                  centerSpaceRadius: 55,
                                  sections: showingSavingsSections(savingsAccounts, totalSavings, segmentColors),
                                ),
                              ).animate().scale(duration: 500.ms, curve: Curves.easeOut),
                              Center(
                                child: Column(
                                  mainAxisAlignment: MainAxisAlignment.center,
                                  children: [
                                    const Text(
                                      'НАКОПЛЕНО',
                                      style: TextStyle(
                                        color: AppTheme.textSecondary,
                                        fontSize: 9,
                                        letterSpacing: 1.0,
                                      ),
                                    ),
                                    const SizedBox(height: 2),
                                    Text(
                                      _formatKzt(totalSavings),
                                      style: const TextStyle(
                                        color: Colors.white,
                                        fontSize: 16,
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
                  ).animate().fade(delay: 200.ms).slideY(begin: 0.1),
                  const SizedBox(height: 24),

                  const Text(
                    'Ваши копилки',
                    style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                  ).animate().fade(delay: 300.ms),
                  const SizedBox(height: 12),

                  if (savingsAccounts.isEmpty)
                    const Padding(
                      padding: EdgeInsets.symmetric(vertical: 24),
                      child: Center(
                        child: Text(
                          'У вас пока нет активных копилок.',
                          style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                        ),
                      ),
                    )
                  else
                    ListView.builder(
                      shrinkWrap: true,
                      physics: const NeverScrollableScrollPhysics(),
                      itemCount: savingsAccounts.length,
                      itemBuilder: (context, index) {
                        final acc = savingsAccounts[index];
                        final color = segmentColors[index % segmentColors.length];
                        final double percent = totalSavings > 0 ? (acc.balance / totalSavings) * 100 : 0;

                        return Container(
                          margin: const EdgeInsets.only(bottom: 12),
                          child: GlassCard(
                            radius: 14,
                            padding: const EdgeInsets.all(12),
                            child: Column(
                              children: [
                                Row(
                                  children: [
                                    Container(
                                      width: 10,
                                      height: 10,
                                      decoration: BoxDecoration(color: color, shape: BoxShape.circle),
                                    ),
                                    const SizedBox(width: 10),
                                    const Text('🐷', style: TextStyle(fontSize: 16)),
                                    const SizedBox(width: 8),
                                    Expanded(
                                      child: Text(
                                        acc.name,
                                        style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary, fontSize: 14),
                                      ),
                                    ),
                                    Column(
                                      crossAxisAlignment: CrossAxisAlignment.end,
                                      children: [
                                        Text(
                                          _formatKzt(acc.balance),
                                          style: const TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary, fontSize: 13.5),
                                        ),
                                        const SizedBox(height: 2),
                                        Text(
                                          '${percent.toStringAsFixed(1)}%',
                                          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10),
                                        ),
                                      ],
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 8),
                                ClipRRect(
                                  borderRadius: BorderRadius.circular(4),
                                  child: LinearProgressIndicator(
                                    value: percent / 100,
                                    minHeight: 4,
                                    backgroundColor: AppTheme.border.withOpacity(0.3),
                                    valueColor: AlwaysStoppedAnimation<Color>(color.withOpacity(0.6)),
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ).animate().fade(delay: Duration(milliseconds: 300 + (index * 60))).slideX(begin: 0.05);
                      },
                    ),
                ],
                const SizedBox(height: 20),

                // Export Excel Action Card
                if (_activeTab < 2) ...[
                  GestureDetector(
                    onTap: _isExporting ? null : _exportExcel,
                    child: GlassCard(
                      color: AppTheme.surfaceCard.withOpacity(0.3),
                      radius: 14,
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: Colors.green.withOpacity(0.1),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(Icons.file_present_rounded, color: Colors.green, size: 24),
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
                                  'Сводная книга Excel (XLSX)',
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
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.green),
                              ),
                            )
                          else
                            const Icon(Icons.chevron_right_rounded, color: AppTheme.textSecondary),
                        ],
                      ),
                    ),
                  ).animate().fade(delay: 400.ms),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<PieChartSectionData> showingSections(List<Category> categories, int totalSpent, List<Color> colors) {
    if (totalSpent <= 0 || categories.isEmpty) {
      return [
        PieChartSectionData(
          color: AppTheme.border,
          value: 100,
          title: '',
          radius: 26,
        )
      ];
    }

    return List.generate(categories.length, (i) {
      final isTouched = i == touchedIndex;
      final fontSize = isTouched ? 15.0 : 0.0;
      final radius = isTouched ? 32.0 : 22.0;
      final cat = categories[i];
      final color = colors[i % colors.length];

      return PieChartSectionData(
        color: color,
        value: cat.spentAmount.toDouble(),
        title: isTouched ? '${((cat.spentAmount / totalSpent) * 100).toStringAsFixed(0)}%' : '',
        radius: radius,
        titleStyle: TextStyle(
          fontSize: fontSize,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          shadows: const [Shadow(color: Colors.black, blurRadius: 2)],
        ),
      );
    });
  }

  List<PieChartSectionData> showingSavingsSections(List<Account> savingsAccounts, int totalSavings, List<Color> colors) {
    if (totalSavings <= 0 || savingsAccounts.isEmpty) {
      return [
        PieChartSectionData(
          color: AppTheme.border,
          value: 100,
          title: '',
          radius: 26,
        )
      ];
    }

    return List.generate(savingsAccounts.length, (i) {
      final isTouched = i == touchedIndex;
      final fontSize = isTouched ? 15.0 : 0.0;
      final radius = isTouched ? 32.0 : 22.0;
      final account = savingsAccounts[i];
      final color = colors[i % colors.length];

      return PieChartSectionData(
        color: color,
        value: account.balance.toDouble(),
        title: isTouched ? '${((account.balance / totalSavings) * 100).toStringAsFixed(0)}%' : '',
        radius: radius,
        titleStyle: TextStyle(
          fontSize: fontSize,
          fontWeight: FontWeight.bold,
          color: Colors.white,
          shadows: const [Shadow(color: Colors.black, blurRadius: 2)],
        ),
      );
    });
  }
}
