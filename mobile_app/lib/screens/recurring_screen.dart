import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';

class RecurringTemplate {
  final String title;
  final int amount; // minor units
  final String categoryEmoji;
  final int dayOfMonth;
  bool isActive;

  RecurringTemplate({
    required this.title,
    required this.amount,
    required this.categoryEmoji,
    required this.dayOfMonth,
    this.isActive = true,
  });
}

class RecurringScreen extends StatefulWidget {
  const RecurringScreen({super.key});

  @override
  State<RecurringScreen> createState() => _RecurringScreenState();
}

class _RecurringScreenState extends State<RecurringScreen> {
  // Mock recurring expense templates
  final List<RecurringTemplate> _templates = [
    RecurringTemplate(
      title: 'Netflix Premium',
      amount: 4500, // 4,500 KZT
      categoryEmoji: '🎬',
      dayOfMonth: 15,
    ),
    RecurringTemplate(
      title: 'Аренда квартиры',
      amount: 150000, // 150,000 KZT
      categoryEmoji: '🏠',
      dayOfMonth: 1,
    ),
    RecurringTemplate(
      title: 'Абонемент в зал',
      amount: 12000, // 12,000 KZT
      categoryEmoji: '💪',
      dayOfMonth: 28,
    ),
  ];

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Регулярные платежи', style: TextStyle(fontWeight: FontWeight.bold)),
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
                'Автоматические шаблоны расходов',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 16),

              Expanded(
                child: ListView.builder(
                  physics: const BouncingScrollPhysics(),
                  itemCount: _templates.length,
                  itemBuilder: (context, index) {
                    final item = _templates[index];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 14),
                      decoration: AppTheme.glassCardDecoration(radius: 16),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
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
                                  'Каждый месяц, ${item.dayOfMonth}-го числа',
                                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                                ),
                              ],
                            ),
                          ),

                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(
                                _formatKzt(item.amount),
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 16,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                              const SizedBox(height: 4),
                              SizedBox(
                                height: 24,
                                child: Switch(
                                  value: item.isActive,
                                  activeColor: AppTheme.primary,
                                  onChanged: (val) {
                                    setState(() {
                                      item.isActive = val;
                                    });
                                  },
                                ),
                              ),
                            ],
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
                    const SnackBar(content: Text('Создание шаблонов будет добавлено в следующем релизе!')),
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
                  'Добавить регулярный платёж',
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
