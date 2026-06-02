import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';

class PlannedTx {
  final String title;
  final int amount; // minor units
  final String categoryEmoji;
  final String kind; // 'income' or 'expense'
  final DateTime expectedDate;

  PlannedTx({
    required this.title,
    required this.amount,
    required this.categoryEmoji,
    required this.kind,
    required this.expectedDate,
  });
}

class PlannedScreen extends StatefulWidget {
  const PlannedScreen({super.key});

  @override
  State<PlannedScreen> createState() => _PlannedScreenState();
}

class _PlannedScreenState extends State<PlannedScreen> {
  // Mock expected events
  final List<PlannedTx> _plannedEvents = [
    PlannedTx(
      title: 'Зарплата',
      amount: 45000000, // 450,000 KZT
      categoryEmoji: '💰',
      kind: 'income',
      expectedDate: DateTime.now().add(const Duration(days: 8)),
    ),
    PlannedTx(
      title: 'Плата за обучение',
      amount: 8000000, // 80,000 KZT
      categoryEmoji: '🎓',
      kind: 'expense',
      expectedDate: DateTime.now().add(const Duration(days: 15)),
    ),
  ];

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor / 100);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Запланировано', style: TextStyle(fontWeight: FontWeight.bold)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: AppTheme.textPrimary, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Ожидаемые финансовые события и поступления',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 16),

              Expanded(
                child: ListView.builder(
                  physics: const BouncingScrollPhysics(),
                  itemCount: _plannedEvents.length,
                  itemBuilder: (context, index) {
                    final item = _plannedEvents[index];
                    final isExpense = item.kind == 'expense';

                    return Container(
                      margin: const EdgeInsets.only(bottom: 14),
                      decoration: AppTheme.glassCardDecoration(radius: 16),
                      padding: const EdgeInsets.all(18),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: Colors.white.withOpacity(0.03),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(item.categoryEmoji, style: const TextStyle(fontSize: 20)),
                          ),
                          const SizedBox(width: 14),

                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  item.title,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: AppTheme.textPrimary),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  'Ожидается: ${DateFormat('dd.MM.yyyy').format(item.expectedDate)}',
                                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                                ),
                              ],
                            ),
                          ),

                          Text(
                            '${isExpense ? '-' : '+'}${_formatKzt(item.amount)}',
                            style: TextStyle(
                              color: isExpense ? AppTheme.expense : AppTheme.income,
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),

              ElevatedButton(
                onPressed: () {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text('Планирование будущих трат будет добавлено в следующем релизе!')),
                  );
                },
                style: ElevatedButton.styleFrom(
                  padding: const EdgeInsets.symmetric(vertical: 16),
                  backgroundColor: AppTheme.surfaceCard,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                    side: const BorderSide(color: AppTheme.border, width: 1),
                  ),
                  elevation: 0,
                ),
                child: const Text(
                  'Добавить планируемое событие',
                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
