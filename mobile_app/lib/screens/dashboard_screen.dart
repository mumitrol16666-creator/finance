import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';
import 'categories_screen.dart';
import 'all_transactions_screen.dart';

class DashboardScreen extends StatelessWidget {
  const DashboardScreen({super.key});

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _showEditTransactionDialog(BuildContext context, AppState appState, Transaction tx) {
    final amountController = TextEditingController(text: tx.amount.toString());
    final noteController = TextEditingController(text: tx.note ?? '');

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppTheme.border),
          ),
          title: Text(
            tx.kind == 'expense' ? 'Редактировать расход' : 'Редактировать доход',
            style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Text(tx.categoryEmoji, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 8),
                  Text(
                    tx.categoryName,
                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  const Spacer(),
                  Text(
                    tx.accountName,
                    style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              TextField(
                controller: amountController,
                keyboardType: TextInputType.number,
                style: const TextStyle(color: AppTheme.textPrimary),
                decoration: const InputDecoration(
                  labelText: 'Сумма',
                  labelStyle: TextStyle(color: AppTheme.textSecondary),
                  suffixText: '₸',
                  enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                  focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: noteController,
                style: const TextStyle(color: AppTheme.textPrimary),
                decoration: const InputDecoration(
                  labelText: 'Комментарий',
                  labelStyle: TextStyle(color: AppTheme.textSecondary),
                  enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                  focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                ),
              ),
            ],
          ),
          actions: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton.icon(
                  onPressed: () async {
                    final confirm = await showDialog<bool>(
                      context: context,
                      builder: (context) => AlertDialog(
                        backgroundColor: AppTheme.surface,
                        title: const Text('Удаление', style: TextStyle(color: Colors.white)),
                        content: const Text('Удалить эту операцию?', style: TextStyle(color: AppTheme.textPrimary)),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(context, false),
                            child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(context, true),
                            child: const Text('Удалить', style: TextStyle(color: AppTheme.expense)),
                          ),
                        ],
                      ),
                    );
                    if (confirm == true) {
                      Navigator.pop(context);
                      await appState.deleteTransaction(tx.id);
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('✅ Операция успешно удалена!'),
                          backgroundColor: AppTheme.income,
                        ),
                      );
                    }
                  },
                  icon: const Icon(Icons.delete_outline, color: AppTheme.expense),
                  label: const Text('Удалить', style: TextStyle(color: AppTheme.expense)),
                ),
                Row(
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                    ),
                    TextButton(
                      onPressed: () async {
                        final amt = int.tryParse(amountController.text) ?? 0;
                        if (amt <= 0) return;
                        Navigator.pop(context);
                        await appState.updateTransaction(
                          tx_id: tx.id,
                          amount: amt,
                          note: noteController.text.trim().isNotEmpty ? noteController.text.trim() : '',
                        );
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('✅ Изменения сохранены!'),
                            backgroundColor: AppTheme.income,
                          ),
                        );
                      },
                      child: const Text('Сохранить', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
                    ),
                  ],
                ),
              ],
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final totalBal = appState.totalBalance;
    final monthlyExp = appState.monthlyExpenses;
    final transactions = appState.transactions;
    final categories = appState.categories;
    final streak = appState.weeklyStreak;

    return RefreshIndicator(
      onRefresh: () async {
        await appState.refreshAllData();
      },
      color: AppTheme.primary,
      backgroundColor: AppTheme.surfaceCard,
      child: SingleChildScrollView(
        physics: const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'Привет 👋',
                        style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
                      ),
                      Text(
                        'Мой Бюджет',
                        style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                              fontWeight: FontWeight.bold,
                              color: AppTheme.textPrimary,
                            ),
                      ),
                    ],
                  ),
                  IconButton(
                    onPressed: () {
                      appState.logout();
                    },
                    icon: const Icon(Icons.logout_rounded, color: AppTheme.textSecondary),
                  )
                ],
              ).animate().fade(duration: 400.ms).slideY(begin: -0.2),
              const SizedBox(height: 24),

              // Glassmorphic Balance Card
              GlassCard(
                color: AppTheme.surfaceCard.withOpacity(0.4),
                radius: 24,
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'ОБЩИЙ БАЛАНС',
                      style: TextStyle(
                        color: AppTheme.textSecondary,
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 1.2,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      _formatKzt(totalBal),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 32,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                    const SizedBox(height: 20),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        _buildMiniMetric(
                          label: 'РАСХОДЫ В МАЕ',
                          value: _formatKzt(monthlyExp),
                          color: AppTheme.expense,
                        ),
                        _buildMiniMetric(
                          label: 'СЧЕТОВ АКТИВНО',
                          value: appState.accounts.length.toString(),
                          color: AppTheme.accentBlue,
                        ),
                      ],
                    ),
                  ],
                ),
              ).animate().fade(delay: 100.ms).slideY(begin: 0.2),
              const SizedBox(height: 20),

              // Streak tracker visual bar
              GlassCard(
                radius: 16,
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                child: Row(
                  children: [
                    const Text(
                      'Серия:',
                      style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                    ),
                    const SizedBox(width: 8),
                    // Progress flames
                    Expanded(
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                        children: List.generate(7, (index) {
                          final isFilled = index < streak.length && streak[index];
                          return Icon(
                            Icons.local_fire_department_rounded,
                            color: isFilled ? AppTheme.secondary : Colors.grey.withOpacity(0.2),
                            size: 24,
                          ).animate(target: isFilled ? 1 : 0).scale(duration: 300.ms, delay: Duration(milliseconds: 200 + (index * 50)));
                        }),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${streak.where((s) => s).length} из 7',
                      style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                    ),
                  ],
                ),
              ).animate().fade(delay: 200.ms).slideY(begin: 0.2),
              const SizedBox(height: 24),

              // Horizontal Category Budgets / Limits List
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Лимиты категорий',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                  ),
                  TextButton(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => const CategoriesScreen()),
                      );
                    },
                    child: const Text('Все', style: TextStyle(color: AppTheme.primary)),
                  ),
                ],
              ).animate().fade(delay: 300.ms),
              const SizedBox(height: 8),
              SizedBox(
                height: 110,
                child: ListView.builder(
                  scrollDirection: Axis.horizontal,
                  physics: const BouncingScrollPhysics(),
                  itemCount: categories.length,
                  itemBuilder: (context, index) {
                    final cat = categories[index];
                    final limit = cat.limitAmount ?? 0;
                    final progress = limit > 0 ? (cat.spentAmount / limit).clamp(0.0, 1.0) : 0.0;
                    
                    return Container(
                      width: 160,
                      margin: const EdgeInsets.only(right: 12),
                      child: GlassCard(
                        radius: 14,
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                          children: [
                          Row(
                            children: [
                              Text(cat.emoji, style: const TextStyle(fontSize: 18)),
                              const SizedBox(width: 6),
                              Expanded(
                                child: Text(
                                  cat.name,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                  overflow: TextOverflow.ellipsis,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '${_formatKzt(cat.spentAmount)} / ${_formatKzt(limit)}',
                            style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                          ),
                          const SizedBox(height: 6),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: LinearProgressIndicator(
                              value: progress,
                              backgroundColor: Colors.white.withOpacity(0.05),
                              valueColor: AlwaysStoppedAnimation<Color>(
                                progress >= 0.9 ? AppTheme.expense : AppTheme.primary,
                              ),
                              minHeight: 4,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ).animate().fade(delay: Duration(milliseconds: 300 + (index * 100))).slideX(begin: 0.1);
                  },
                ),
              ),
              const SizedBox(height: 24),

              // Recent Transactions header
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'Последние операции',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                  ),
                  TextButton(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => const AllTransactionsScreen()),
                      );
                    },
                    child: const Text('Все', style: TextStyle(color: AppTheme.primary)),
                  ),
                ],
              ).animate().fade(delay: 400.ms),
              const SizedBox(height: 8),

              // Transactions list
              ListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                itemCount: transactions.length,
                itemBuilder: (context, index) {
                  final tx = transactions[index];
                  final isExpense = tx.kind == 'expense';
                  
                  return Container(
                    margin: const EdgeInsets.only(bottom: 12),
                    child: GestureDetector(
                      onTap: () => _showEditTransactionDialog(context, appState, tx),
                      child: GlassCard(
                        radius: 14,
                        padding: const EdgeInsets.all(14),
                        child: Row(
                          children: [
                          Container(
                            padding: const EdgeInsets.all(10),
                            decoration: BoxDecoration(
                              color: Colors.white.withOpacity(0.03),
                              borderRadius: BorderRadius.circular(10),
                            ),
                            child: Text(tx.categoryEmoji, style: const TextStyle(fontSize: 20)),
                          ),
                          const SizedBox(width: 14),
                          
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(
                                  tx.note ?? tx.categoryName,
                                  style: const TextStyle(fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                                  maxLines: 1,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  tx.accountName,
                                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                                ),
                              ],
                            ),
                          ),
                          
                          Column(
                            crossAxisAlignment: CrossAxisAlignment.end,
                            children: [
                              Text(
                                '${isExpense ? '-' : '+'}${_formatKzt(tx.amount)}',
                                style: TextStyle(
                                  color: isExpense ? AppTheme.expense : AppTheme.income,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 15,
                                ),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                DateFormat('dd.MM, HH:mm').format(tx.timestamp),
                                style: const TextStyle(color: Colors.white24, fontSize: 10),
                              ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ),
                ).animate().fade(delay: Duration(milliseconds: 400 + (index * 50))).slideY(begin: 0.1);
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildMiniMetric({required String label, required String value, required Color color}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10, letterSpacing: 0.8),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            color: color,
            fontSize: 16,
            fontWeight: FontWeight.bold,
          ),
        ),
      ],
    );
  }
}
