import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../utils/currency_utils.dart' as cu;

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

  void _showAddPlannedDialog(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (context) => _AddPlannedDialog(appState: appState),
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
                                  '${isExpense ? '-' : '+'}${cu.formatCurrency(item.amount, item.currency)}',
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

class _AddPlannedDialog extends StatefulWidget {
  final AppState appState;
  const _AddPlannedDialog({required this.appState});

  @override
  State<_AddPlannedDialog> createState() => _AddPlannedDialogState();
}

class _AddPlannedDialogState extends State<_AddPlannedDialog> {
  late final TextEditingController titleController;
  late final TextEditingController amountController;
  late final TextEditingController dateController;
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
    dateController = TextEditingController();
    commentController = TextEditingController();

    titleController.addListener(_updateState);
    amountController.addListener(_updateState);
    dateController.addListener(_updateState);
  }

  void _updateState() {
    setState(() {});
  }

  @override
  void dispose() {
    titleController.dispose();
    amountController.dispose();
    dateController.dispose();
    commentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final filteredCategories = widget.appState.categories.where((cat) => cat.kind == kind).toList();
    final title = titleController.text.trim();
    final amount = int.tryParse(amountController.text) ?? 0;
    final plannedDate = dateController.text.trim();
    final isButtonEnabled = title.isNotEmpty &&
        amount > 0 &&
        plannedDate.isNotEmpty &&
        selectedCategoryId != null &&
        selectedAccountId != null;

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
                if (val != null) {
                  setState(() {
                    kind = val;
                    selectedCategoryId = null; // Reset category
                  });
                }
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
                labelText: 'Счёт',
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
              controller: dateController,
              readOnly: true,
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
          onPressed: isButtonEnabled
              ? () async {
                  try {
                    await widget.appState.addPlanned(
                      title: title,
                      amount: amount,
                      categoryId: selectedCategoryId!,
                      accountId: selectedAccountId!,
                      plannedDate: plannedDate,
                      kind: kind,
                      comment: commentController.text.trim().isEmpty ? null : commentController.text.trim(),
                    );
                    if (!mounted) return;
                    Navigator.pop(context);
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('✅ Событие "$title" успешно запланировано!'),
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
            'Запланировать',
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
