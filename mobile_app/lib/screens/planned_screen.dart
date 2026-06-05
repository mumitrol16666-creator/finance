import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'package:flutter_animate/flutter_animate.dart';

class PlannedScreen extends StatefulWidget {
  const PlannedScreen({super.key});

  @override
  State<PlannedScreen> createState() => _PlannedScreenState();
}

class _PlannedScreenState extends State<PlannedScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<AppState>(context, listen: false).loadPlanned();
    });
  }

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _showAddPlannedDialog(BuildContext context, AppState appState) {
    final titleController = TextEditingController();
    final amountController = TextEditingController();
    final dateController = TextEditingController();
    final commentController = TextEditingController();
    String kind = 'expense';
    int? selectedCategoryId = appState.categories.isNotEmpty ? appState.categories.first.id : null;
    int? selectedAccountId = appState.accounts.isNotEmpty ? appState.accounts.first.id : null;

    showDialog(
      context: context,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setState) {
            return AlertDialog(
              backgroundColor: AppTheme.surface,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(16),
                side: const BorderSide(color: AppTheme.border),
              ),
              title: const Text('Новое планируемое событие', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<String>(
                      value: kind,
                      dropdownColor: AppTheme.surface,
                      style: const TextStyle(color: AppTheme.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'Тип операции',
                        labelStyle: TextStyle(color: AppTheme.textSecondary),
                      ),
                      items: const [
                        DropdownMenuItem(value: 'expense', child: Text('Расход')),
                        DropdownMenuItem(value: 'income', child: Text('Доход')),
                      ],
                      onChanged: (val) {
                        if (val != null) setState(() => kind = val);
                      },
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: titleController,
                      style: const TextStyle(color: AppTheme.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'Название события',
                        labelStyle: TextStyle(color: AppTheme.textSecondary),
                        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                    ),
                    const SizedBox(height: 12),
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
                    const SizedBox(height: 12),
                    if (appState.categories.isNotEmpty)
                      DropdownButtonFormField<int>(
                        value: selectedCategoryId,
                        dropdownColor: AppTheme.surface,
                        style: const TextStyle(color: AppTheme.textPrimary),
                        decoration: const InputDecoration(
                          labelText: 'Категория',
                          labelStyle: TextStyle(color: AppTheme.textSecondary),
                        ),
                        items: appState.categories.map((cat) {
                          return DropdownMenuItem(value: cat.id, child: Text('${cat.emoji} ${cat.name}'));
                        }).toList(),
                        onChanged: (val) {
                          if (val != null) setState(() => selectedCategoryId = val);
                        },
                      ),
                    const SizedBox(height: 12),
                    if (appState.accounts.isNotEmpty)
                      DropdownButtonFormField<int>(
                        value: selectedAccountId,
                        dropdownColor: AppTheme.surface,
                        style: const TextStyle(color: AppTheme.textPrimary),
                        decoration: const InputDecoration(
                          labelText: 'Счёт',
                          labelStyle: TextStyle(color: AppTheme.textSecondary),
                        ),
                        items: appState.accounts.map((acc) {
                          return DropdownMenuItem(value: acc.id, child: Text(acc.name));
                        }).toList(),
                        onChanged: (val) {
                          if (val != null) setState(() => selectedAccountId = val);
                        },
                      ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: dateController,
                      style: const TextStyle(color: AppTheme.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'Ожидаемая дата (ГГГГ-ММ-ДД)',
                        labelStyle: TextStyle(color: AppTheme.textSecondary),
                        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                      onTap: () async {
                        FocusScope.of(context).requestFocus(FocusNode());
                        final date = await showDatePicker(
                          context: context,
                          initialDate: DateTime.now(),
                          firstDate: DateTime.now().subtract(const Duration(days: 365)),
                          lastDate: DateTime.now().add(const Duration(days: 3650)),
                        );
                        if (date != null) {
                          dateController.text = DateFormat('yyyy-MM-dd').format(date);
                        }
                      },
                    ),
                    const SizedBox(height: 12),
                    TextField(
                      controller: commentController,
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
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                ),
                TextButton(
                  onPressed: () async {
                    final title = titleController.text.trim();
                    final amount = int.tryParse(amountController.text) ?? 0;
                    final plannedDate = dateController.text.trim();
                    if (title.isEmpty || amount <= 0 || plannedDate.isEmpty || selectedCategoryId == null || selectedAccountId == null) return;
                    Navigator.pop(context);
                    await appState.addPlanned(
                      title: title,
                      amount: amount,
                      categoryId: selectedCategoryId!,
                      accountId: selectedAccountId!,
                      plannedDate: plannedDate,
                      kind: kind,
                      comment: commentController.text.trim().isEmpty ? null : commentController.text.trim(),
                    );
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('✅ Событие "$title" успешно запланировано!'),
                        backgroundColor: AppTheme.income,
                      ),
                    );
                  },
                  child: const Text('Запланировать', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
                ),
              ],
            );
          },
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final events = appState.plannedEvents;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Планы трат', style: TextStyle(fontWeight: FontWeight.bold)),
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
                child: events.isEmpty
                    ? const Center(
                        child: Text(
                          'У вас нет запланированных событий',
                          style: TextStyle(color: AppTheme.textSecondary),
                        ),
                      )
                    : ListView.builder(
                        physics: const BouncingScrollPhysics(),
                        itemCount: events.length,
                        itemBuilder: (context, index) {
                          final item = events[index];
                          final isExpense = item.kind == 'expense';
                          final dateStr = item.date;
                          final dateParsed = DateTime.tryParse(dateStr);
                          final dateFormatted = dateParsed != null ? DateFormat('dd.MM.yyyy').format(dateParsed) : dateStr;

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
                                        'Ожидается: $dateFormatted',
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
                          ).animate().fade(delay: Duration(milliseconds: 100 + (index * 50))).slideX(begin: 0.1);
                        },
                      ),
              ),

              ElevatedButton(
                onPressed: () => _showAddPlannedDialog(context, appState),
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
