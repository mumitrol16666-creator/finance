import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../utils/currency_utils.dart' as cu;

class RecurringScreen extends StatefulWidget {
  const RecurringScreen({super.key});

  @override
  State<RecurringScreen> createState() => _RecurringScreenState();
}

class _RecurringScreenState extends State<RecurringScreen> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<AppState>(context, listen: false).loadRecurring();
    });
  }

  void _showAddTemplateDialog(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (context) => _AddTemplateDialog(appState: appState),
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final templates = appState.recurringTemplates;

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
                child: templates.isEmpty
                    ? const Center(
                        child: Text(
                          'У вас нет сохраненных регулярных платежей',
                          style: TextStyle(color: AppTheme.textSecondary),
                        ),
                      )
                    : ListView.builder(
                        physics: const BouncingScrollPhysics(),
                        itemCount: templates.length,
                        itemBuilder: (context, index) {
                          final item = templates[index];
                          final isExpense = item.kind == 'expense';
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
                                        'Каждый месяц, ${item.intervalValue}-го числа',
                                        style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                                      ),
                                    ],
                                  ),
                                ),

                                Column(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Text(
                                      '${isExpense ? '-' : '+'}${cu.formatCurrency(item.amount, item.currency)}',
                                      style: TextStyle(
                                        color: isExpense ? AppTheme.expense : AppTheme.income,
                                        fontSize: 16,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    const Text(
                                      'Активен',
                                      style: TextStyle(color: AppTheme.income, fontSize: 10, fontWeight: FontWeight.bold),
                                    ),
                                  ],
                                ),
                              ],
                            ),
                          ).animate().fade(delay: Duration(milliseconds: 100 + (index * 50))).slideX(begin: 0.1);
                        },
                      ),
              ),

              ElevatedButton(
                onPressed: () => _showAddTemplateDialog(context, appState),
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

class _AddTemplateDialog extends StatefulWidget {
  final AppState appState;
  const _AddTemplateDialog({required this.appState});

  @override
  State<_AddTemplateDialog> createState() => _AddTemplateDialogState();
}

class _AddTemplateDialogState extends State<_AddTemplateDialog> {
  late final TextEditingController titleController;
  late final TextEditingController amountController;
  late final TextEditingController dayController;
  late final TextEditingController commentController;
  String kind = 'expense';
  int? selectedCategoryId;
  int? selectedAccountId;

  String _selectedCurrency() {
    final accounts = widget.appState.accounts.where((a) => a.id == selectedAccountId);
    return accounts.isNotEmpty ? accounts.first.currency : widget.appState.baseCurrency;
  }

  @override
  void initState() {
    super.initState();
    titleController = TextEditingController();
    amountController = TextEditingController();
    dayController = TextEditingController(text: '1');
    commentController = TextEditingController();

    titleController.addListener(_updateState);
    amountController.addListener(_updateState);
    dayController.addListener(_updateState);
  }

  void _updateState() {
    setState(() {});
  }

  @override
  void dispose() {
    titleController.dispose();
    amountController.dispose();
    dayController.dispose();
    commentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final filteredCategories = widget.appState.categories.where((cat) => cat.kind == kind).toList();
    final title = titleController.text.trim();
    final amount = int.tryParse(amountController.text) ?? 0;
    final day = int.tryParse(dayController.text) ?? 1;
    final isButtonEnabled = title.isNotEmpty &&
        amount > 0 &&
        selectedCategoryId != null &&
        selectedAccountId != null &&
        day >= 1 &&
        day <= 31;

    return AlertDialog(
      backgroundColor: AppTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppTheme.border),
      ),
      title: const Text('Новый регулярный платёж', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
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
                if (val != null) {
                  setState(() {
                    kind = val;
                    selectedCategoryId = null; // Reset category selection
                  });
                }
              },
            ),
            const SizedBox(height: 12),
            TextField(
              controller: titleController,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Название шаблона',
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
              decoration: InputDecoration(
                labelText: 'Сумма',
                labelStyle: const TextStyle(color: AppTheme.textSecondary),
                suffixText: cu.currencySymbol(_selectedCurrency()),
                enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              value: selectedCategoryId,
              dropdownColor: AppTheme.surface,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Категория',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
              ),
              hint: const Text('Выберите категорию', style: TextStyle(color: AppTheme.textSecondary)),
              items: filteredCategories.map((cat) {
                return DropdownMenuItem(value: cat.id, child: Text('${cat.emoji} ${cat.name}'));
              }).toList(),
              onChanged: (val) {
                setState(() => selectedCategoryId = val);
              },
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<int>(
              value: selectedAccountId,
              dropdownColor: AppTheme.surface,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Счёт списания / зачисления',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
              ),
              hint: const Text('Выберите счёт', style: TextStyle(color: AppTheme.textSecondary)),
              items: widget.appState.accounts.map((acc) {
                return DropdownMenuItem(value: acc.id, child: Text('${acc.name} (${cu.formatCurrency(acc.balance, acc.currency)})'));
              }).toList(),
              onChanged: (val) {
                setState(() => selectedAccountId = val);
              },
            ),
            const SizedBox(height: 12),
            TextField(
              controller: dayController,
              keyboardType: TextInputType.number,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'День месяца (1-31)',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
                enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
              ),
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
          onPressed: isButtonEnabled
              ? () async {
                  final title = titleController.text.trim();
                  final amount = int.tryParse(amountController.text) ?? 0;
                  final day = int.tryParse(dayController.text) ?? 1;
                  try {
                    await widget.appState.addRecurring(
                      title: title,
                      amount: amount,
                      categoryId: selectedCategoryId!,
                      accountId: selectedAccountId!,
                      dayOfMonth: day,
                      kind: kind,
                      comment: commentController.text.trim().isEmpty ? null : commentController.text.trim(),
                    );
                    if (!mounted) return;
                    Navigator.pop(context);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('✅ Шаблон "$title" успешно создан!'),
                        backgroundColor: AppTheme.income,
                      ),
                    );
                  } catch (e) {
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(content: Text(e.toString().replaceFirst('Exception: ', '')), backgroundColor: AppTheme.expense),
                    );
                  }
                }
              : null,
          child: Text(
            'Создать',
            style: TextStyle(
              color: isButtonEnabled ? AppTheme.primary : AppTheme.textSecondary.withOpacity(0.5),
              fontWeight: FontWeight.bold,
            ),
          ),
        ),
      ],
    );
  }
}
