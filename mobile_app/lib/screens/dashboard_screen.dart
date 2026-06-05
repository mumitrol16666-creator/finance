import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';
import 'package:url_launcher/url_launcher.dart';
import 'categories_screen.dart';
import 'all_transactions_screen.dart';
import 'accounts_screen.dart';
import 'settings_screen.dart';

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  bool _showSavings = false;

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  String _getRussianPlural(int number, String one, String two, String many) {
    int n = number % 100;
    int n1 = n % 10;
    if (n > 10 && n < 20) return many;
    if (n1 > 1 && n1 < 5) return two;
    if (n1 == 1) return one;
    return many;
  }

  void _showPremiumStatusDialog(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (context) {
        final isPremium = appState.isPremium;
        DateTime? expDate = appState.premiumExpirationDate != null
            ? DateTime.tryParse(appState.premiumExpirationDate!)
            : null;
        if (expDate == null && appState.premiumExpirationDate != null) {
          final parts = appState.premiumExpirationDate!.split(' ')[0].split('-');
          if (parts.length == 3) {
            final y = int.tryParse(parts[0]);
            final m = int.tryParse(parts[1]);
            final d = int.tryParse(parts[2]);
            if (y != null && m != null && d != null) {
              expDate = DateTime(y, m, d);
            }
          }
        }
        
        String expiryText = '';
        if (expDate != null) {
          final months = [
            'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
            'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
          ];
          final formattedDate = '${expDate.day} ${months[expDate.month - 1]} ${expDate.year}г.';
          final daysLeft = expDate.difference(DateTime.now()).inDays;
          if (daysLeft > 0) {
            expiryText = '\n\nПодписка активна до: $formattedDate\nОсталось дней: $daysLeft';
          } else {
            expiryText = '\n\nПодписка активна до: $formattedDate';
          }
        } else if (appState.premiumExpirationDate != null) {
          expiryText = '\n\nПодписка активна до: ${appState.premiumExpirationDate}';
        }

        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppTheme.border),
          ),
          title: Row(
            children: [
              Icon(
                isPremium ? Icons.verified_rounded : Icons.star_rounded,
                color: isPremium ? AppTheme.income : AppTheme.secondary,
                size: 28,
              ),
              const SizedBox(width: 8),
              Text(
                isPremium ? 'Премиум подписка' : 'FinTrack Premium',
                style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 18),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (isPremium) ...[
                Text(
                  'У вас активен Premium статус! 🎉$expiryText',
                  style: const TextStyle(color: Colors.white, height: 1.4),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Вам доступны все продвинутые функции:\n'
                  '• Умный финансовый ИИ-ассистент\n'
                  '• Голосовой ввод транзакций\n'
                  '• Лимиты категорий и планирование\n'
                  '• Переводы между счетами',
                  style: TextStyle(color: AppTheme.textSecondary, height: 1.4, fontSize: 13),
                ),
              ] else ...[
                const Text(
                  'Активируйте Premium статус, чтобы разблокировать все функции приложения:',
                  style: TextStyle(color: Colors.white, height: 1.4),
                ),
                const SizedBox(height: 12),
                const Text(
                  '• 🤖 ИИ-Аналитик: персональный разбор бюджета\n'
                  '• 🎙️ Голосовой ввод: запись расходов голосом\n'
                  '• 💳 Переводы: свободное перемещение между счетами\n'
                  '• 📈 Лимиты и планирование бюджетов без ограничений',
                  style: TextStyle(color: AppTheme.textSecondary, height: 1.4, fontSize: 13),
                ),
                const SizedBox(height: 16),
                const Text(
                  'Для активации перейдите в наш Telegram бот и выберите команду /upgrade.',
                  style: TextStyle(color: Colors.white70, fontStyle: FontStyle.italic, fontSize: 13),
                ),
              ],
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Хорошо', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }

  void _showCategoryDetailsBottomSheet(BuildContext context, AppState appState, Category category) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        final limit = category.limitAmount ?? 0;
        final spent = category.spentAmount;
        final diff = limit - spent;
        final isOverlimit = diff < 0;
        
        final categoryTxs = appState.transactions
            .where((tx) => tx.categoryName == category.name)
            .toList();
        categoryTxs.sort((a, b) => b.timestamp.compareTo(a.timestamp));
        final recentTxs = categoryTxs.take(5).toList();

        return DraggableScrollableSheet(
          initialChildSize: 0.6,
          minChildSize: 0.4,
          maxChildSize: 0.85,
          expand: false,
          builder: (context, scrollController) {
            return Container(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Center(
                    child: Container(
                      width: 40,
                      height: 4,
                      decoration: BoxDecoration(
                        color: Colors.white24,
                        borderRadius: BorderRadius.circular(2),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Text(category.emoji, style: const TextStyle(fontSize: 28)),
                      const SizedBox(width: 8),
                      Text(
                        category.name,
                        style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, color: Colors.white),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),
                  
                  GlassCard(
                    radius: 16,
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text('Потрачено:', style: TextStyle(color: AppTheme.textSecondary)),
                            Text(
                              _formatKzt(spent),
                              style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 16),
                            ),
                          ],
                        ),
                        if (limit > 0) ...[
                          const SizedBox(height: 10),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text('Лимит:', style: TextStyle(color: AppTheme.textSecondary)),
                              Text(
                                _formatKzt(limit),
                                style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 16),
                              ),
                            ],
                          ),
                          const SizedBox(height: 10),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                isOverlimit ? 'Превышение:' : 'Осталось лимита:',
                                style: TextStyle(color: isOverlimit ? AppTheme.expense : AppTheme.income),
                              ),
                              Text(
                                _formatKzt(diff.abs()),
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  color: isOverlimit ? AppTheme.expense : AppTheme.income,
                                  fontSize: 16,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(4),
                            child: LinearProgressIndicator(
                              value: (spent / limit).clamp(0.0, 1.0),
                              backgroundColor: Colors.white.withOpacity(0.05),
                              valueColor: AlwaysStoppedAnimation<Color>(
                                (spent / limit) >= 0.9
                                    ? AppTheme.expense
                                    : ((spent / limit) >= category.warnThreshold ? Colors.amber : AppTheme.income),
                              ),
                              minHeight: 6,
                            ),
                          ),
                        ] else ...[
                          const SizedBox(height: 10),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: const [
                              Text('Лимит:', style: TextStyle(color: AppTheme.textSecondary)),
                              Text(
                                'Без лимита',
                                style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white70, fontSize: 16),
                              ),
                            ],
                          ),
                        ],
                      ],
                    ),
                  ),
                  
                  const SizedBox(height: 24),
                  const Text(
                    'Последние операции категории',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  const SizedBox(height: 12),
                  
                  Expanded(
                    child: recentTxs.isEmpty
                      ? const Center(
                          child: Text(
                            'Нет операций в этой категории за период',
                            style: TextStyle(color: AppTheme.textSecondary),
                          ),
                        )
                      : ListView.builder(
                          controller: scrollController,
                          itemCount: recentTxs.length,
                          itemBuilder: (context, index) {
                            final tx = recentTxs[index];
                            final isExpense = tx.kind == 'expense';
                            
                            return Container(
                              margin: const EdgeInsets.only(bottom: 12),
                              child: GlassCard(
                                radius: 12,
                                padding: const EdgeInsets.all(12),
                                child: Row(
                                  children: [
                                    Expanded(
                                      child: Column(
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            tx.note ?? tx.categoryName,
                                            style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
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
                                            fontSize: 14,
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
                            );
                          },
                        ),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  void _showAccountSwitcherBottomSheet(BuildContext context, AppState appState) {
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return Container(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              const Text(
                'Переключить аккаунт',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 16),
              if (appState.savedSessions.isEmpty)
                const Text(
                  'Нет других сохраненных аккаунтов. Вы можете войти в новый аккаунт, выйдя из текущего.',
                  style: TextStyle(color: AppTheme.textSecondary),
                  textAlign: TextAlign.center,
                )
              else
                ListView.builder(
                  shrinkWrap: true,
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: appState.savedSessions.length,
                  itemBuilder: (context, index) {
                    final session = appState.savedSessions[index];
                    final isCurrent = session.name == appState.userName;
                    return ListTile(
                      leading: CircleAvatar(
                        backgroundColor: isCurrent ? AppTheme.primary : AppTheme.border,
                        child: const Icon(Icons.person_rounded, color: Colors.white),
                      ),
                      title: Text(session.name, style: TextStyle(fontWeight: isCurrent ? FontWeight.bold : FontWeight.normal, color: Colors.white)),
                      subtitle: Text('ID: ${session.userId}', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
                      trailing: isCurrent ? const Icon(Icons.check_circle_outline_rounded, color: AppTheme.income) : null,
                      onTap: () {
                        Navigator.pop(context);
                        if (!isCurrent) {
                          appState.switchSession(session);
                        }
                      },
                    );
                  },
                ),
              const SizedBox(height: 16),
              TextButton(
                onPressed: () {
                  Navigator.pop(context);
                  appState.logout();
                },
                child: const Text('Выйти из аккаунта', style: TextStyle(color: AppTheme.expense)),
              )
            ],
          ),
        );
      },
    );
  }

  void _showStatsBottomSheet(BuildContext context, AppState appState) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        final netSavings = appState.cycleIncome - appState.cycleExpenses;
        final startFormat = appState.cycleStart != null && appState.cycleStart!.isNotEmpty
            ? DateFormat('dd.MM.yyyy').format(DateTime.parse(appState.cycleStart!))
            : '';
        final endFormat = appState.cycleEnd != null && appState.cycleEnd!.isNotEmpty
            ? DateFormat('dd.MM.yyyy').format(DateTime.parse(appState.cycleEnd!))
            : '';
        
        return Container(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Center(
                child: Container(
                  width: 40,
                  height: 4,
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              ),
              const SizedBox(height: 24),
              const Text(
                'Аналитика за текущий период',
                style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.white),
                textAlign: TextAlign.center,
              ),
              if (startFormat.isNotEmpty && endFormat.isNotEmpty) ...[
                const SizedBox(height: 6),
                Text(
                  '$startFormat — $endFormat',
                  style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                  textAlign: TextAlign.center,
                ),
              ],
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Expanded(
                    child: _buildMetricCard(
                      title: 'ДОХОДЫ',
                      value: _formatKzt(appState.cycleIncome),
                      color: AppTheme.income,
                      icon: Icons.trending_up_rounded,
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: _buildMetricCard(
                      title: 'РАСХОДЫ',
                      value: _formatKzt(appState.cycleExpenses),
                      color: AppTheme.expense,
                      icon: Icons.trending_down_rounded,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              GlassCard(
                radius: 16,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text(
                      'Чистая экономия:',
                      style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                    ),
                    Text(
                      _formatKzt(netSavings),
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: netSavings >= 0 ? AppTheme.income : AppTheme.expense,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 20),
              GlassCard(
                radius: 16,
                padding: const EdgeInsets.all(16),
                child: Column(
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Активных дней:',
                          style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                        ),
                        Text(
                          '${appState.activeDaysCount} из ${appState.totalCycleDays}',
                          style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(4),
                      child: LinearProgressIndicator(
                        value: appState.totalCycleDays > 0 
                            ? appState.activeDaysCount / appState.totalCycleDays 
                            : 0,
                        backgroundColor: Colors.white.withOpacity(0.05),
                        valueColor: const AlwaysStoppedAnimation<Color>(AppTheme.primary),
                        minHeight: 6,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
          ),
        );
      },
    );
  }

  Widget _buildMetricCard({required String title, required String value, required Color color, required IconData icon}) {
    return GlassCard(
      radius: 16,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color, size: 16),
              const SizedBox(width: 6),
              Text(
                title,
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.bold),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 16,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
    );
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

    // Filter to only show expense categories on limits overview
    final expenseCategories = categories.where((c) => c.kind == 'expense').toList();

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
                  GestureDetector(
                    onTap: () {
                      _showAccountSwitcherBottomSheet(context, appState);
                    },
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            const Text(
                              'Привет 👋',
                              style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                            ),
                            const SizedBox(width: 6),
                             GestureDetector(
                              onTap: () => _showPremiumStatusDialog(context, appState),
                              child: Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
                                decoration: BoxDecoration(
                                  gradient: appState.isPremium ? AppTheme.primaryGradient : null,
                                  color: appState.isPremium ? null : AppTheme.border,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: Text(
                                  appState.isPremium ? 'PREMIUM' : 'БАЗОВЫЙ',
                                  style: const TextStyle(
                                    fontSize: 7.5,
                                    fontWeight: FontWeight.bold,
                                    color: Colors.white,
                                  ),
                                ),
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 2),
                        Row(
                          children: [
                            Text(
                              appState.userName ?? 'Пользователь',
                              style: Theme.of(context).textTheme.titleLarge?.copyWith(
                                    fontWeight: FontWeight.bold,
                                    color: AppTheme.textPrimary,
                                  ),
                            ),
                            const SizedBox(width: 4),
                            const Icon(Icons.arrow_drop_down_rounded, color: AppTheme.textSecondary),
                          ],
                        ),
                      ],
                    ),
                  ),
                   IconButton(
                    onPressed: () async {
                      final url = Uri.parse('https://t.me/FinanceBo1_bot');
                      if (await canLaunchUrl(url)) {
                        await launchUrl(url, mode: LaunchMode.externalApplication);
                      }
                    },
                    icon: const Icon(Icons.telegram_rounded, color: Color(0xFF229ED9), size: 26),
                  ),
                   IconButton(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (context) => const SettingsScreen()),
                      );
                    },
                    icon: const Icon(Icons.settings_rounded, color: AppTheme.textSecondary),
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
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        GestureDetector(
                          onTap: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(builder: (context) => const AccountsScreen()),
                            );
                          },
                          child: Container(
                            color: Colors.transparent,
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                const Text(
                                  'ОБЩИЙ БАЛАНС',
                                  style: TextStyle(
                                    color: AppTheme.textSecondary,
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1.2,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  _formatKzt(totalBal),
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontSize: 26,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        ),
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Row(
                              children: [
                                const Text(
                                  'КОПИЛКА',
                                  style: TextStyle(
                                    color: AppTheme.textSecondary,
                                    fontSize: 11,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1.2,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                GestureDetector(
                                  onTap: () => setState(() => _showSavings = !_showSavings),
                                  child: Icon(
                                    _showSavings ? Icons.visibility_rounded : Icons.visibility_off_rounded,
                                    color: AppTheme.textSecondary,
                                    size: 14,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              _showSavings ? _formatKzt(appState.savingsBalance) : '•••• ₸',
                              style: const TextStyle(
                                color: AppTheme.secondary,
                                fontSize: 22,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 24),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        GestureDetector(
                          onTap: () {
                            _showStatsBottomSheet(context, appState);
                          },
                          child: Container(
                            color: Colors.transparent,
                            child: _buildMiniMetric(
                              label: 'Расходы за период',
                              value: _formatKzt(monthlyExp),
                              color: AppTheme.expense,
                            ),
                          ),
                        ),
                        _buildMiniMetric(
                          label: 'Активные счета',
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
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Row(
                      children: [
                        const Text(
                          'Серия активности:',
                          style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                            children: List.generate(7, (index) {
                              final isFilled = index < streak.length && streak[index];
                              final labels = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];
                              return Column(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Icon(
                                    Icons.local_fire_department_rounded,
                                    color: isFilled ? AppTheme.secondary : Colors.grey.withOpacity(0.2),
                                    size: 22,
                                  ).animate(target: isFilled ? 1 : 0).scale(duration: 300.ms, delay: Duration(milliseconds: 200 + (index * 50))),
                                  const SizedBox(height: 4),
                                  Text(
                                    labels[index],
                                    style: TextStyle(
                                      fontSize: 9,
                                      color: isFilled ? AppTheme.secondary : AppTheme.textSecondary,
                                      fontWeight: isFilled ? FontWeight.bold : FontWeight.normal,
                                    ),
                                  ),
                                ],
                              );
                            }),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 12),
                    const Divider(color: AppTheme.border, height: 1),
                    const SizedBox(height: 8),
                    Center(
                      child: Text(
                        appState.currentStreak == 0
                            ? 'Начните заполнять трекер сегодня! Ваш рекорд — ${appState.maxStreak} ${_getRussianPlural(appState.maxStreak, 'день', 'дня', 'дней')}.'
                            : 'Вы заполняете трекер ${appState.currentStreak} ${_getRussianPlural(appState.currentStreak, 'день', 'дня', 'дней')} подряд. Ваш рекорд — ${appState.maxStreak} ${_getRussianPlural(appState.maxStreak, 'день', 'дня', 'дней')}!',
                        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11.5),
                        textAlign: TextAlign.center,
                      ),
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
              if (expenseCategories.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 16.0),
                  child: Center(
                    child: Text('Нет настроенных категорий', style: TextStyle(color: AppTheme.textSecondary)),
                  ),
                )
              else
                 SizedBox(
                  height: 110,
                  child: Stack(
                    children: [
                      ListView.builder(
                        scrollDirection: Axis.horizontal,
                        physics: const BouncingScrollPhysics(),
                        itemCount: expenseCategories.length,
                        itemBuilder: (context, index) {
                          final cat = expenseCategories[index];
                          final limit = cat.limitAmount ?? 0;
                          final progress = limit > 0 ? (cat.spentAmount / limit).clamp(0.0, 1.0) : 0.0;
                          
                          return GestureDetector(
                            onTap: () => _showCategoryDetailsBottomSheet(context, appState, cat),
                            child: Container(
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
                                          progress >= 0.9
                                              ? AppTheme.expense
                                              : (progress >= cat.warnThreshold ? Colors.amber : AppTheme.income),
                                        ),
                                        minHeight: 4,
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ).animate().fade(delay: Duration(milliseconds: 300 + (index * 100))).slideX(begin: 0.1);
                        },
                      ),
                      if (expenseCategories.length > 2)
                        Positioned(
                          right: 0,
                          top: 0,
                          bottom: 0,
                          child: IgnorePointer(
                            child: Container(
                              width: 40,
                              decoration: BoxDecoration(
                                gradient: LinearGradient(
                                  colors: [
                                    Colors.transparent,
                                    AppTheme.background.withOpacity(0.85),
                                  ],
                                  begin: Alignment.centerLeft,
                                  end: Alignment.centerRight,
                                ),
                              ),
                              alignment: Alignment.centerRight,
                              child: const Padding(
                                padding: EdgeInsets.only(right: 4.0),
                                child: Icon(
                                  Icons.chevron_right_rounded,
                                  color: AppTheme.primary,
                                  size: 28,
                                ),
                              )
                                  .animate(onPlay: (controller) => controller.repeat(reverse: true))
                                  .fade(duration: 800.ms, begin: 0.3, end: 1.0)
                                  .slideX(duration: 800.ms, begin: -0.2, end: 0.0),
                            ),
                          ),
                        ),
                    ],
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
