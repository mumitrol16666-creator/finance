import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';
import '../utils/currency_utils.dart' as cu;
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

  @override
  void initState() {
    super.initState();
  }

  void _quickAdd(BuildContext context, AppState appState, QuickAddTemplate template) async {
    if (appState.accounts.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('❌ Пожалуйста, создайте сначала хотя бы один счёт!'),
          backgroundColor: AppTheme.expense,
        ),
      );
      return;
    }
    final activeAccounts = appState.accounts.where((a) => !a.isSaving && a.accType != 'deposit').toList();
    final targetAccount = activeAccounts.isNotEmpty ? activeAccounts.first : appState.accounts.first;

    // Find category for default account
    Account? initialAccount;
    try {
      final cat = appState.categories.firstWhere((c) => c.name == template.categoryName);
      if (cat.defaultAccountId != null && cat.defaultAccountId! > 0) {
        initialAccount = appState.accounts.firstWhere((a) => a.id == cat.defaultAccountId);
      }
    } catch (_) {}
    initialAccount ??= targetAccount;

    final amountController = TextEditingController(text: template.amount.toString());
    final noteController = TextEditingController(text: template.title);
    Account? selectedAccount = initialAccount;

    showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              backgroundColor: AppTheme.surfaceCard,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: const BorderSide(color: AppTheme.border),
              ),
              title: Row(
                children: [
                  Text(template.categoryEmoji, style: const TextStyle(fontSize: 24)),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Быстрый ввод: ${template.title}',
                      style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 16),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: amountController,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold),
                      decoration: InputDecoration(
                        labelText: 'Сумма',
                        labelStyle: const TextStyle(color: AppTheme.textSecondary),
                        suffixText: cu.currencySymbol(selectedAccount?.currency ?? appState.baseCurrency),
                        suffixStyle: const TextStyle(color: Colors.white70),
                        enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: noteController,
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        labelText: 'Комментарий (Заметка)',
                        labelStyle: TextStyle(color: AppTheme.textSecondary),
                        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                    ),
                    const SizedBox(height: 20),
                    const Text(
                      'Списать со счёта:',
                      style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<Account>(
                      dropdownColor: AppTheme.surfaceCard,
                      value: selectedAccount,
                      style: const TextStyle(color: Colors.white, fontSize: 14),
                      decoration: InputDecoration(
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        filled: true,
                        fillColor: Colors.white.withOpacity(0.02),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.border),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.border),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.primary),
                        ),
                      ),
                      items: appState.accounts.map((acc) {
                        return DropdownMenuItem<Account>(
                          value: acc,
                          child: Text('${acc.name} (${acc.balance} ${acc.currency})'),
                        );
                      }).toList(),
                      onChanged: (val) {
                        setDialogState(() {
                          selectedAccount = val;
                        });
                      },
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                ),
                ElevatedButton(
                  onPressed: () async {
                    final enteredAmount = int.tryParse(amountController.text.trim()) ?? 0;
                    if (enteredAmount <= 0) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('❌ Введите корректную сумму!'),
                          backgroundColor: AppTheme.expense,
                        ),
                      );
                      return;
                    }
                    if (selectedAccount == null) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('❌ Выберите счёт для списания!'),
                          backgroundColor: AppTheme.expense,
                        ),
                      );
                      return;
                    }

                    Navigator.pop(context);

                    try {
                      await appState.addTransaction(
                        amount: enteredAmount,
                        kind: 'expense',
                        categoryName: template.categoryName,
                        categoryEmoji: template.categoryEmoji,
                        accountName: selectedAccount!.name,
                        note: noteController.text.trim().isNotEmpty ? noteController.text.trim() : template.title,
                      );
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('✅ Добавлен расход: ${template.title} — $enteredAmount ${selectedAccount!.currency}'),
                          backgroundColor: AppTheme.income,
                        ),
                      );
                    } catch (e) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('❌ Ошибка добавления: $e'),
                          backgroundColor: AppTheme.expense,
                        ),
                      );
                    }
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.primary,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                  child: const Text('Добавить', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ),
              ],
            );
          },
        );
      },
    );
  }

  void _showConfigureQuickAddBottomSheet(BuildContext context, AppState appState) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setSheetState) {
            final templates = appState.quickAddTemplates;
            return Container(
              padding: EdgeInsets.only(
                left: 24,
                right: 24,
                top: 24,
                bottom: 24 + MediaQuery.of(context).viewInsets.bottom,
              ),
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
                    'Настройка быстрого расхода',
                    style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 16),
                  ListView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: templates.length,
                    itemBuilder: (context, index) {
                      final template = templates[index];
                      return Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        decoration: AppTheme.glassCardDecoration(radius: 12),
                        child: ListTile(
                          leading: Text(template.categoryEmoji, style: const TextStyle(fontSize: 24)),
                          title: Text(template.title, style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                          subtitle: Text('${_formatBase(template.amount)} • ${template.categoryName}', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
                          trailing: const Icon(Icons.edit_outlined, color: AppTheme.primary, size: 20),
                          onTap: () async {
                            final changed = await _showEditQuickAddTemplateDialog(context, appState, template);
                            if (changed == true) {
                              setSheetState(() {});
                            }
                          },
                        ),
                      );
                    },
                  ),
                  const SizedBox(height: 16),
                  TextButton(
                    onPressed: () => Navigator.pop(context),
                    child: const Text('Готово', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Future<bool?> _showEditQuickAddTemplateDialog(BuildContext context, AppState appState, QuickAddTemplate template) {
    final titleController = TextEditingController(text: template.title);
    final amountController = TextEditingController(text: template.amount.toString());
    
    // Filter categories to only expense ones
    final expenseCategories = appState.categories.where((c) => c.kind == 'expense').toList();
    
    Category? selectedCategory;
    try {
      selectedCategory = expenseCategories.firstWhere((c) => c.name == template.categoryName);
    } catch (_) {
      if (expenseCategories.isNotEmpty) {
        selectedCategory = expenseCategories.first;
      }
    }

    return showDialog<bool>(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setDialogState) {
            return AlertDialog(
              backgroundColor: AppTheme.surfaceCard,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: const BorderSide(color: AppTheme.border),
              ),
              title: const Text('Редактировать шаблон', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: titleController,
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        labelText: 'Название кнопки',
                        labelStyle: TextStyle(color: AppTheme.textSecondary),
                        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                    ),
                    const SizedBox(height: 16),
                    TextField(
                      controller: amountController,
                      keyboardType: TextInputType.number,
                      style: const TextStyle(color: Colors.white),
                      decoration: InputDecoration(
                        labelText: 'Сумма по умолчанию',
                        labelStyle: const TextStyle(color: AppTheme.textSecondary),
                        suffixText: cu.currencySymbol(appState.baseCurrency),
                        suffixStyle: const TextStyle(color: Colors.white70),
                        enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                    ),
                    const SizedBox(height: 20),
                    const Text(
                      'Категория расхода:',
                      style: TextStyle(color: AppTheme.textSecondary, fontSize: 12),
                    ),
                    const SizedBox(height: 8),
                    DropdownButtonFormField<Category>(
                      dropdownColor: AppTheme.surfaceCard,
                      value: selectedCategory,
                      style: const TextStyle(color: Colors.white, fontSize: 14),
                      decoration: InputDecoration(
                        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        filled: true,
                        fillColor: Colors.white.withOpacity(0.02),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.border),
                        ),
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.border),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: const BorderSide(color: AppTheme.primary),
                        ),
                      ),
                      items: expenseCategories.map((cat) {
                        return DropdownMenuItem<Category>(
                          value: cat,
                          child: Text('${cat.emoji} ${cat.name}'),
                        );
                      }).toList(),
                      onChanged: (val) {
                        setDialogState(() {
                          selectedCategory = val;
                        });
                      },
                    ),
                  ],
                ),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                ),
                ElevatedButton(
                  onPressed: () async {
                    final title = titleController.text.trim();
                    final amount = int.tryParse(amountController.text.trim()) ?? 0;
                    if (title.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Введите название шаблона')),
                      );
                      return;
                    }
                    if (amount <= 0) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Введите корректную сумму')),
                      );
                      return;
                    }
                    if (selectedCategory == null) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Выберите категорию')),
                      );
                      return;
                    }

                    await appState.updateQuickAddTemplate(
                      template.id,
                      title: title,
                      amount: amount,
                      categoryName: selectedCategory!.name,
                      categoryEmoji: selectedCategory!.emoji,
                    );

                    Navigator.pop(context, true);
                  },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppTheme.primary,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                  ),
                  child: const Text('Сохранить', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ),
              ],
            );
          },
        );
      },
    );
  }

  String _formatKzt(int amountMinor) {
    return _formatBase(amountMinor);
  }

  String _formatCurrency(int amount, String currency) {
    return cu.formatCurrency(amount, currency);
  }

  /// Format amount in user's base currency
  String _formatBase(int amount) {
    final appState = Provider.of<AppState>(context, listen: false);
    return cu.formatCurrency(amount, appState.baseCurrency);
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
            if (!isPremium)
              ElevatedButton.icon(
                onPressed: () async {
                  await AppTheme.openPremiumInTelegram(context);
                  if (context.mounted) Navigator.pop(context);
                },
                icon: const Icon(Icons.telegram_rounded),
                label: const Text('Открыть Telegram-бота'),
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
                                          '${isExpense ? '-' : '+'}${_formatCurrency(tx.amount, tx.currency)}',
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
                decoration: InputDecoration(
                  labelText: 'Сумма',
                  labelStyle: const TextStyle(color: AppTheme.textSecondary),
                  suffixText: cu.currencySymbol(tx.currency),
                  enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                  focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
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

    final quickAddTemplates = appState.quickAddTemplates;

    // Calculate 30-day forecast (Planned & Recurring)
    final now = DateTime.now();
    final thirtyDaysLater = now.add(const Duration(days: 30));
    int forecastChange = 0;

    for (final p in appState.plannedEvents) {
      if (p.status.toLowerCase() == 'done' || p.status.toLowerCase() == 'completed') {
        continue;
      }
      try {
        final pDate = DateTime.parse(p.date);
        if (pDate.isAfter(now) && pDate.isBefore(thirtyDaysLater)) {
          if (p.kind == 'expense') {
            forecastChange -= p.amount;
          } else {
            forecastChange += p.amount;
          }
        }
      } catch (_) {}
    }

    for (final r in appState.recurringTemplates) {
      DateTime? nextRun;
      if (r.nextRunDate != null && r.nextRunDate!.isNotEmpty) {
        nextRun = DateTime.tryParse(r.nextRunDate!);
      }
      if (nextRun == null) {
        nextRun = DateTime(now.year, now.month, r.intervalValue);
        if (nextRun.isBefore(now)) {
          nextRun = DateTime(now.year, now.month + 1, r.intervalValue);
        }
      }
      var currentRun = nextRun;
      while (currentRun.isBefore(thirtyDaysLater)) {
        if (currentRun.isAfter(now) || currentRun.isAtSameMomentAs(now)) {
          if (r.kind == 'expense') {
            forecastChange -= r.amount;
          } else {
            forecastChange += r.amount;
          }
        }
        if (r.intervalType == 'daily') {
          currentRun = currentRun.add(const Duration(days: 1));
        } else if (r.intervalType == 'weekly') {
          currentRun = currentRun.add(const Duration(days: 7));
        } else {
          currentRun = DateTime(currentRun.year, currentRun.month + 1, currentRun.day);
        }
      }
    }

    final forecastedBalance = totalBal + forecastChange;
    final hasCashGap = forecastedBalance < 0;

    return Stack(
      children: [
        RefreshIndicator(
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

              // Personal/Business sliding toggle chip row
              Row(
                children: [
                  Expanded(
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: AppTheme.border),
                      ),
                      child: Row(
                        children: [
                          Expanded(
                            child: GestureDetector(
                              onTap: () {
                                appState.toggleBusinessMode(false);
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 8),
                                decoration: BoxDecoration(
                                  color: !appState.isBusinessMode ? AppTheme.primary : Colors.transparent,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                alignment: Alignment.center,
                                child: Text(
                                  'Личный кабинет',
                                  style: TextStyle(
                                    color: !appState.isBusinessMode ? Colors.white : AppTheme.textSecondary,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                            ),
                          ),
                          Expanded(
                            child: GestureDetector(
                              onTap: () {
                                appState.toggleBusinessMode(true);
                              },
                              child: Container(
                                padding: const EdgeInsets.symmetric(vertical: 8),
                                decoration: BoxDecoration(
                                  color: appState.isBusinessMode ? AppTheme.primary : Colors.transparent,
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                alignment: Alignment.center,
                                child: Text(
                                  'Бизнес-кабинет',
                                  style: TextStyle(
                                    color: appState.isBusinessMode ? Colors.white : AppTheme.textSecondary,
                                    fontWeight: FontWeight.bold,
                                    fontSize: 13,
                                  ),
                                ),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ).animate().fade(duration: 400.ms),
              const SizedBox(height: 16),

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
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        // Total balance section
                        Expanded(
                          child: GestureDetector(
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
                                  Text(
                                    'ОБЩИЙ БАЛАНС',
                                    style: TextStyle(
                                      color: AppTheme.textSecondary,
                                      fontSize: 10,
                                      fontWeight: FontWeight.w600,
                                      letterSpacing: 1.1,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    _formatBase(totalBal),
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 20,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                  // Multi-currency breakdown (only if multiple currencies exist)
                                  if (appState.hasMultipleCurrencies) ...[
                                    const SizedBox(height: 4),
                                    Builder(builder: (_) {
                                      final byCurrency = appState.balancesByCurrency;
                                      final parts = <Widget>[];
                                      for (final entry in byCurrency.entries) {
                                        if (entry.value == 0) continue;
                                        parts.add(
                                          Text(
                                            '${cu.currencySymbol(entry.key)}${cu.formatAmount(entry.value)}',
                                            style: TextStyle(
                                              color: entry.key == appState.baseCurrency
                                                  ? AppTheme.textSecondary
                                                  : AppTheme.accentBlue.withOpacity(0.8),
                                              fontSize: 11,
                                              fontWeight: FontWeight.w500,
                                            ),
                                          ),
                                        );
                                      }
                                      return Wrap(
                                        spacing: 8,
                                        children: parts,
                                      );
                                    }),
                                    const SizedBox(height: 2),
                                    GestureDetector(
                                      onTap: () => _showExchangeRatesBottomSheet(context, appState),
                                      child: Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          Icon(Icons.currency_exchange_rounded, size: 10, color: AppTheme.textSecondary.withOpacity(0.6)),
                                          const SizedBox(width: 3),
                                          Text(
                                            '≈ ${_formatBase(totalBal)} по курсу',
                                            style: TextStyle(
                                              color: AppTheme.textSecondary.withOpacity(0.6),
                                              fontSize: 9,
                                              fontStyle: FontStyle.italic,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ),
                        ),
                        // Savings column
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.center,
                          children: [
                            Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                const Text(
                                  'КОПИЛКА',
                                  style: TextStyle(
                                    color: AppTheme.textSecondary,
                                    fontSize: 10,
                                    fontWeight: FontWeight.w600,
                                    letterSpacing: 1.1,
                                  ),
                                ),
                                const SizedBox(width: 4),
                                GestureDetector(
                                  onTap: () => setState(() => _showSavings = !_showSavings),
                                  child: Icon(
                                    _showSavings ? Icons.visibility_rounded : Icons.visibility_off_rounded,
                                    color: AppTheme.textSecondary,
                                    size: 13,
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text(
                              _showSavings ? _formatBase(appState.savingsBalance) : '•••• ${cu.currencySymbol(appState.baseCurrency)}',
                              style: const TextStyle(
                                color: AppTheme.secondary,
                                fontSize: 15,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(width: 12),
                        // Deposits column
                        Column(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            const Text(
                              'ДЕПОЗИТЫ',
                              style: TextStyle(
                                color: AppTheme.textSecondary,
                                fontSize: 10,
                                fontWeight: FontWeight.w600,
                                letterSpacing: 1.1,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              _formatBase(appState.depositBalance),
                              style: const TextStyle(
                                color: AppTheme.income,
                                fontSize: 15,
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
                              value: _formatBase(monthlyExp),
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

              // Horizontal scroll row for quick-add widgets
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Быстрый расход',
                        style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                      ),
                      IconButton(
                        icon: const Icon(Icons.settings_outlined, size: 20, color: AppTheme.textSecondary),
                        padding: EdgeInsets.zero,
                        constraints: const BoxConstraints(),
                        onPressed: () {
                          _showConfigureQuickAddBottomSheet(context, appState);
                        },
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    height: 70,
                    child: ListView.builder(
                      scrollDirection: Axis.horizontal,
                      physics: const BouncingScrollPhysics(),
                      itemCount: quickAddTemplates.length,
                      itemBuilder: (context, index) {
                        final template = quickAddTemplates[index];
                        return GestureDetector(
                          onTap: () => _quickAdd(context, appState, template),
                          child: Container(
                            margin: const EdgeInsets.only(right: 12),
                            child: GlassCard(
                              radius: 14,
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                              child: Row(
                                children: [
                                  Text(template.categoryEmoji, style: const TextStyle(fontSize: 20)),
                                  const SizedBox(width: 8),
                                  Column(
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text(
                                        template.title,
                                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.white),
                                      ),
                                      const SizedBox(height: 2),
                                      Text(
                                        _formatBase(template.amount),
                                        style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                ],
              ).animate().fade(delay: 150.ms).slideY(begin: 0.2),
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

              // Cash Gap Forecast Card
              _buildCashGapCard(forecastedBalance, forecastChange, hasCashGap),
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
                                  '${isExpense ? '-' : '+'}${_formatCurrency(tx.amount, tx.currency)}',
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
    ),
    ],
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

  Widget _buildCashGapCard(int forecastedBal, int forecastChange, bool hasGap) {
    return GlassCard(
      color: hasGap ? AppTheme.expense.withOpacity(0.15) : AppTheme.surfaceCard.withOpacity(0.4),
      radius: 20,
      padding: const EdgeInsets.all(20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                hasGap ? Icons.warning_amber_rounded : Icons.trending_up_rounded,
                color: hasGap ? AppTheme.expense : AppTheme.income,
                size: 24,
              ),
              const SizedBox(width: 8),
              Text(
                hasGap ? '⚠️ ОБНАРУЖЕН КАССОВЫЙ РАЗРЫВ!' : '📈 Прогноз баланса (30 дней)',
                style: TextStyle(
                  color: hasGap ? AppTheme.expense : Colors.white,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            hasGap
                ? 'Через 30 дней ваш баланс может опуститься ниже нуля и составить ${_formatKzt(forecastedBal)}. Рекомендуем сократить расходы или запланировать дополнительные доходы.'
                : 'Ваш прогнозируемый баланс через 30 дней составит ${_formatKzt(forecastedBal)} (изменение: ${forecastChange >= 0 ? '+' : ''}${_formatKzt(forecastChange)}).',
            style: const TextStyle(
              color: AppTheme.textPrimary,
              fontSize: 13,
              height: 1.4,
            ),
          ),
          if (hasGap) ...[
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              decoration: BoxDecoration(
                color: AppTheme.expense.withOpacity(0.2),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.expense.withOpacity(0.3)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.info_outline, color: AppTheme.expense, size: 16),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Внимание: Будьте осторожны с крупными тратами!',
                      style: TextStyle(color: AppTheme.expense, fontSize: 11, fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ],
      ),
    );
  }

  void _showExchangeRatesBottomSheet(BuildContext context, AppState appState) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.surface,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      builder: (context) {
        return Padding(
          padding: EdgeInsets.only(
            bottom: MediaQuery.of(context).viewInsets.bottom,
          ),
          child: StatefulBuilder(
            builder: (context, setModalState) {
              final baseCurrency = appState.baseCurrency;
              final list = ['KZT', 'USD', 'EUR', 'RUB'];

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
                    Text(
                      'Курсы валют',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 20,
                        fontWeight: FontWeight.bold,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Относительно вашей базовой валюты: ${cu.currencyFlag(baseCurrency)} $baseCurrency',
                      style: const TextStyle(
                        color: AppTheme.textSecondary,
                        fontSize: 12,
                      ),
                      textAlign: TextAlign.center,
                    ),
                    if (appState.ratesUpdatedAt != null) ...[
                      const SizedBox(height: 2),
                      Text(
                        'Обновлено: ${DateFormat('dd.MM.yyyy HH:mm').format(DateTime.parse(appState.ratesUpdatedAt!).toLocal())}',
                        style: TextStyle(
                          color: AppTheme.textSecondary.withOpacity(0.5),
                          fontSize: 10,
                        ),
                        textAlign: TextAlign.center,
                      ),
                    ],
                    const SizedBox(height: 24),
                    ...list.map((curr) {
                      if (curr == baseCurrency) return const SizedBox.shrink();

                      final rate = (appState.exchangeRates[baseCurrency] ?? 1.0) /
                          (appState.exchangeRates[curr] ?? 1.0);

                      final isOverridden = curr == 'USD'
                          ? appState.customRatesOverride.containsKey(baseCurrency)
                          : appState.customRatesOverride.containsKey(curr);

                      return Container(
                        margin: const EdgeInsets.only(bottom: 12),
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                        decoration: BoxDecoration(
                          color: AppTheme.surfaceCard,
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(
                            color: isOverridden ? AppTheme.accentBlue.withOpacity(0.5) : Colors.white.withOpacity(0.05),
                          ),
                        ),
                        child: Row(
                          children: [
                            Text(
                              cu.currencyFlag(curr),
                              style: const TextStyle(fontSize: 24),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Text(
                                        curr,
                                        style: const TextStyle(
                                          color: Colors.white,
                                          fontWeight: FontWeight.bold,
                                          fontSize: 15,
                                        ),
                                      ),
                                      const SizedBox(width: 6),
                                      Text(
                                        cu.currencyName(curr),
                                        style: const TextStyle(
                                          color: AppTheme.textSecondary,
                                          fontSize: 11,
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    cu.formatDirectExchangeRate(curr, baseCurrency, rate),
                                    style: const TextStyle(
                                      color: Colors.white70,
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            if (isOverridden) ...[
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                decoration: BoxDecoration(
                                  color: AppTheme.accentBlue.withOpacity(0.15),
                                  borderRadius: BorderRadius.circular(8),
                                ),
                                child: const Text(
                                  'Свой курс',
                                  style: TextStyle(
                                    color: AppTheme.accentBlue,
                                    fontSize: 9,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              IconButton(
                                icon: const Icon(Icons.refresh_rounded, color: AppTheme.textSecondary, size: 18),
                                padding: EdgeInsets.zero,
                                constraints: const BoxConstraints(),
                                onPressed: () async {
                                  await appState.removeCustomRate(curr);
                                  setModalState(() {});
                                },
                              ),
                            ] else ...[
                              IconButton(
                                icon: const Icon(Icons.edit_rounded, color: AppTheme.accentBlue, size: 18),
                                padding: EdgeInsets.zero,
                                constraints: const BoxConstraints(),
                                onPressed: () {
                                  _showEditRateDialog(context, appState, curr, rate, () {
                                    setModalState(() {});
                                  });
                                },
                              ),
                            ],
                          ],
                        ),
                      );
                    }).toList(),
                    if (appState.customRatesOverride.isNotEmpty) ...[
                      const SizedBox(height: 12),
                      TextButton.icon(
                        icon: const Icon(Icons.restart_alt_rounded, size: 18, color: AppTheme.expense),
                        label: const Text(
                          'Сбросить все свои курсы',
                          style: TextStyle(color: AppTheme.expense, fontWeight: FontWeight.bold, fontSize: 13),
                        ),
                        onPressed: () async {
                          await appState.clearCustomRates();
                          setModalState(() {});
                        },
                      ),
                    ],
                    const SizedBox(height: 16),
                  ],
                ),
              );
            },
          ),
        );
      },
    );
  }

  void _showEditRateDialog(BuildContext context, AppState appState, String currency, double currentRate, VoidCallback onUpdated) {
    final invertForDisplay = currentRate < 1;
    final displayFromCurrency = invertForDisplay ? appState.baseCurrency : currency;
    final displayToCurrency = invertForDisplay ? currency : appState.baseCurrency;
    final displayRate = invertForDisplay ? 1 / currentRate : currentRate;
    final displayRateText = displayRate.toStringAsFixed(2).replaceFirst(RegExp(r'\.?0+$'), '');
    final controller = TextEditingController(text: displayRateText);
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: Text(
            'Установить курс для $currency',
            style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Укажите стоимость 1 ${cu.currencySymbol(displayFromCurrency)} в ${cu.currencySymbol(displayToCurrency)}:',
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                style: const TextStyle(color: Colors.white),
                decoration: InputDecoration(
                  suffixText: cu.currencySymbol(displayToCurrency),
                  suffixStyle: const TextStyle(color: AppTheme.textSecondary),
                  enabledBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: BorderSide(color: Colors.white.withOpacity(0.1)),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                    borderSide: const BorderSide(color: AppTheme.accentBlue),
                  ),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.accentBlue,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              ),
              onPressed: () async {
                final double? enteredRate = double.tryParse(controller.text.replaceAll(',', '.'));
                if (enteredRate != null && enteredRate > 0) {
                  final directRateInBase = invertForDisplay ? 1 / enteredRate : enteredRate;
                  await appState.setCustomRate(currency, directRateInBase);
                  onUpdated();
                  Navigator.pop(context);
                }
              },
              child: const Text('Сохранить', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }
}
