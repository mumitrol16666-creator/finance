import 'package:flutter/material.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';

class Debt {
  final String person;
  final int totalAmount; // minor units
  final int paidAmount;
  final bool isIOwe;
  final DateTime dueDate;

  Debt({
    required this.person,
    required this.totalAmount,
    required this.paidAmount,
    required this.isIOwe,
    required this.dueDate,
  });
}

class DebtsScreen extends StatefulWidget {
  const DebtsScreen({super.key});

  @override
  State<DebtsScreen> createState() => _DebtsScreenState();
}

class _DebtsScreenState extends State<DebtsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  // Mock debts
  final List<Debt> _debts = [
    Debt(
      person: 'Алибек',
      totalAmount: 1500000, // 15,000 KZT
      paidAmount: 500000,
      isIOwe: false, // he owes me
      dueDate: DateTime.now().add(const Duration(days: 5)),
    ),
    Debt(
      person: 'Марат',
      totalAmount: 5000000, // 50,000 KZT
      paidAmount: 0,
      isIOwe: true, // I owe him
      dueDate: DateTime.now().add(const Duration(days: 12)),
    ),
  ];

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

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
        title: const Text('Долги и Займы', style: TextStyle(fontWeight: FontWeight.bold)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: AppTheme.textPrimary, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: AppTheme.primary,
          labelColor: Colors.white,
          unselectedLabelColor: AppTheme.textSecondary,
          indicatorSize: TabBarIndicatorSize.tab,
          tabs: const [
            Tab(text: 'Мне должны'),
            Tab(text: 'Я должен'),
          ],
        ),
      ),
      body: SafeArea(
        child: TabBarView(
          controller: _tabController,
          children: [
            _buildDebtList(isIOwe: false),
            _buildDebtList(isIOwe: true),
          ],
        ),
      ),
    );
  }

  Widget _buildDebtList({required bool isIOwe}) {
    final filtered = _debts.where((d) => d.isIOwe == isIOwe).toList();

    if (filtered.isEmpty) {
      return const Center(
        child: Text(
          'У вас нет активных долгов в этой категории',
          style: TextStyle(color: AppTheme.textSecondary),
        ),
      );
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(),
      padding: const EdgeInsets.all(20),
      itemCount: filtered.length,
      itemBuilder: (context, index) {
        final debt = filtered[index];
        final remaining = debt.totalAmount - debt.paidAmount;
        final progress = debt.totalAmount > 0 ? debt.paidAmount / debt.totalAmount : 0.0;

        return Container(
          margin: const EdgeInsets.only(bottom: 16),
          decoration: AppTheme.glassCardDecoration(radius: 16),
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    debt.person,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: AppTheme.textPrimary),
                  ),
                  Text(
                    _formatKzt(remaining),
                    style: TextStyle(
                      color: isIOwe ? AppTheme.expense : AppTheme.income,
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'Всего: ${_formatKzt(debt.totalAmount)}',
                    style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                  ),
                  Text(
                    'Вернуть до: ${DateFormat('dd.MM.yyyy').format(debt.dueDate)}',
                    style: const TextStyle(color: Colors.white24, fontSize: 11),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              // Progress indicator
              ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: progress,
                  backgroundColor: Colors.white.withOpacity(0.05),
                  valueColor: AlwaysStoppedAnimation<Color>(
                    isIOwe ? AppTheme.expense : AppTheme.income,
                  ),
                  minHeight: 5,
                ),
              ),
              const SizedBox(height: 16),

              // Action Buttons row
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton.icon(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Внесение частичной оплаты будет добавлено в следующем релизе!')),
                      );
                    },
                    icon: const Icon(Icons.payment_rounded, size: 16, color: AppTheme.primary),
                    label: const Text('Оплатить', style: TextStyle(color: AppTheme.primary, fontSize: 13)),
                  ),
                  const SizedBox(width: 8),
                  TextButton.icon(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('🔔 Напоминание отправлено пользователю ${debt.person} в бот!'),
                          backgroundColor: AppTheme.income,
                        ),
                      );
                    },
                    icon: const Icon(Icons.notifications_active_rounded, size: 16, color: AppTheme.textSecondary),
                    label: const Text('Напомнить', style: TextStyle(color: AppTheme.textSecondary, fontSize: 13)),
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }
}
