import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';
import 'package:flutter_animate/flutter_animate.dart';

class DebtsScreen extends StatefulWidget {
  const DebtsScreen({super.key});

  @override
  State<DebtsScreen> createState() => _DebtsScreenState();
}

class _DebtsScreenState extends State<DebtsScreen> with SingleTickerProviderStateMixin {
  late TabController _tabController;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<AppState>(context, listen: false).loadDebts();
    });
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  String _formatRussianListDate(DateTime date) {
    const months = [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ];
    return '${date.day} ${months[date.month - 1]} ${date.year}';
  }

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _showPayDebtDialog(BuildContext context, AppState appState, Debt debt) {
    showDialog(
      context: context,
      builder: (context) => _PayDebtDialog(appState: appState, debt: debt),
    );
  }

  void _showAddDebtDialog(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (context) => _AddDebtDialog(appState: appState),
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);

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
            _buildDebtList(appState, isIOwe: false),
            _buildDebtList(appState, isIOwe: true),
          ],
        ),
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: () => _showAddDebtDialog(context, appState),
        backgroundColor: AppTheme.primary,
        child: const Icon(Icons.add, color: Colors.white),
      ),
    );
  }

  Widget _buildDebtList(AppState appState, {required bool isIOwe}) {
    final filtered = appState.debts.where((d) => (d.direction == 'out') == isIOwe).toList();

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
        final paid = debt.totalAmount - debt.remainingAmount;
        final progress = debt.totalAmount > 0 ? paid / debt.totalAmount : 0.0;
        final dueDate = debt.nextPaymentDate != null ? DateTime.tryParse(debt.nextPaymentDate!) : null;
        final dueDateStr = dueDate != null ? _formatRussianListDate(dueDate) : 'Не задана';

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
                    debt.title,
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: AppTheme.textPrimary),
                  ),
                  Text(
                    _formatKzt(debt.remainingAmount),
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
                    'Вернуть до: $dueDateStr',
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
                    onPressed: () => _showPayDebtDialog(context, appState, debt),
                    icon: const Icon(Icons.payment_rounded, size: 16, color: AppTheme.primary),
                    label: const Text('Оплатить', style: TextStyle(color: AppTheme.primary, fontSize: 13)),
                  ),
                  const SizedBox(width: 8),
                  TextButton.icon(
                    onPressed: () {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('🔔 Напоминание отправлено пользователю ${debt.title} в бот!'),
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
        ).animate().fade(delay: Duration(milliseconds: 100 + (index * 50))).slideY(begin: 0.1);
      },
    );
  }
}

class _PayDebtDialog extends StatefulWidget {
  final AppState appState;
  final Debt debt;
  const _PayDebtDialog({required this.appState, required this.debt});

  @override
  State<_PayDebtDialog> createState() => _PayDebtDialogState();
}

class _PayDebtDialogState extends State<_PayDebtDialog> {
  late final TextEditingController amountController;
  late final TextEditingController displayDateController;
  DateTime? selectedDate;
  int? selectedAccountId;

  @override
  void initState() {
    super.initState();
    amountController = TextEditingController(
      text: widget.debt.paymentAmount > 0 ? widget.debt.paymentAmount.toString() : widget.debt.remainingAmount.toString(),
    );
    selectedDate = widget.debt.nextPaymentDate != null ? DateTime.tryParse(widget.debt.nextPaymentDate!) : null;
    displayDateController = TextEditingController(
      text: selectedDate != null ? _formatRussianDate(selectedDate!) : '',
    );
    amountController.addListener(_updateState);
  }

  void _updateState() {
    setState(() {});
  }

  @override
  void dispose() {
    amountController.dispose();
    displayDateController.dispose();
    super.dispose();
  }

  String _formatRussianDate(DateTime date) {
    const months = [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ];
    return '${date.day} ${months[date.month - 1]} ${date.year}';
  }

  @override
  Widget build(BuildContext context) {
    final amt = int.tryParse(amountController.text) ?? 0;
    final isButtonEnabled = amt > 0 && selectedAccountId != null;

    return AlertDialog(
      backgroundColor: AppTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppTheme.border),
      ),
      title: Text('Оплата долга: ${widget.debt.title}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: amountController,
            keyboardType: TextInputType.number,
            style: const TextStyle(color: AppTheme.textPrimary),
            decoration: const InputDecoration(
              labelText: 'Сумма платежа',
              labelStyle: TextStyle(color: AppTheme.textSecondary),
              suffixText: '₸',
              enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
              focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
            ),
          ),
          const SizedBox(height: 16),
          DropdownButtonFormField<int>(
            value: selectedAccountId,
            dropdownColor: AppTheme.surface,
            style: const TextStyle(color: AppTheme.textPrimary),
            decoration: const InputDecoration(
              labelText: 'Счет для списания/зачисления',
              labelStyle: TextStyle(color: AppTheme.textSecondary),
            ),
            hint: const Text('Выберите счёт', style: TextStyle(color: AppTheme.textSecondary)),
            items: widget.appState.accounts.map((acc) {
              return DropdownMenuItem<int>(
                value: acc.id,
                child: Text('${acc.name} (${acc.balance} ₸)'),
              );
            }).toList(),
            onChanged: (val) {
              setState(() => selectedAccountId = val);
            },
          ),
          const SizedBox(height: 16),
          TextField(
            controller: displayDateController,
            readOnly: true,
            style: const TextStyle(color: AppTheme.textPrimary),
            decoration: const InputDecoration(
              labelText: 'Следующий платёж',
              labelStyle: TextStyle(color: AppTheme.textSecondary),
              hintText: 'Необязательно',
              hintStyle: TextStyle(color: Colors.white24),
              enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
              focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
            ),
            onTap: () async {
              FocusScope.of(context).requestFocus(FocusNode());
              final date = await showDatePicker(
                context: context,
                initialDate: selectedDate ?? DateTime.now(),
                firstDate: DateTime.now().subtract(const Duration(days: 365)),
                lastDate: DateTime.now().add(const Duration(days: 3650)),
              );
              if (date != null) {
                setState(() {
                  selectedDate = date;
                  displayDateController.text = _formatRussianDate(date);
                });
              }
            },
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
        ),
        TextButton(
          onPressed: isButtonEnabled
              ? () async {
                  Navigator.pop(context);
                  await widget.appState.payDebt(
                    widget.debt.id,
                    amount: amt,
                    accountId: selectedAccountId!,
                    nextPaymentDate: selectedDate != null ? DateFormat('yyyy-MM-dd').format(selectedDate!) : null,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('✅ Платеж успешно внесен!'),
                      backgroundColor: AppTheme.income,
                    ),
                  );
                }
              : null,
          child: Text(
            'Оплатить',
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

class _AddDebtDialog extends StatefulWidget {
  final AppState appState;
  const _AddDebtDialog({required this.appState});

  @override
  State<_AddDebtDialog> createState() => _AddDebtDialogState();
}

class _AddDebtDialogState extends State<_AddDebtDialog> {
  late final TextEditingController titleController;
  late final TextEditingController amountController;
  late final TextEditingController paymentController;
  late final TextEditingController displayDateController;
  DateTime? selectedDate;
  String direction = 'out'; // I owe
  String dtype = 'private'; // Private person

  @override
  void initState() {
    super.initState();
    titleController = TextEditingController();
    amountController = TextEditingController();
    paymentController = TextEditingController();
    displayDateController = TextEditingController();

    titleController.addListener(_updateState);
    amountController.addListener(_updateState);
  }

  void _updateState() {
    setState(() {});
  }

  @override
  void dispose() {
    titleController.dispose();
    amountController.dispose();
    paymentController.dispose();
    displayDateController.dispose();
    super.dispose();
  }

  String _formatRussianDate(DateTime date) {
    const months = [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ];
    return '${date.day} ${months[date.month - 1]} ${date.year}';
  }

  @override
  Widget build(BuildContext context) {
    final title = titleController.text.trim();
    final amount = int.tryParse(amountController.text) ?? 0;
    final isButtonEnabled = title.isNotEmpty && amount > 0;

    return AlertDialog(
      backgroundColor: AppTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppTheme.border),
      ),
      title: const Text('Новый долг / заём', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            DropdownButtonFormField<String>(
              value: direction,
              dropdownColor: AppTheme.surface,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Тип обязательства',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
              ),
              items: const [
                DropdownMenuItem(value: 'out', child: Text('Я должен (Долг)')),
                DropdownMenuItem(value: 'in', child: Text('Мне должны (Заём)')),
              ],
              onChanged: (val) {
                if (val != null) setState(() => direction = val);
              },
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: dtype,
              dropdownColor: AppTheme.surface,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Кредитор / Дебитор',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
              ),
              items: const [
                DropdownMenuItem(value: 'private', child: Text('Физ. лицо')),
                DropdownMenuItem(value: 'bank', child: Text('Банк / Организация')),
              ],
              onChanged: (val) {
                if (val != null) setState(() => dtype = val);
              },
            ),
            const SizedBox(height: 12),
            TextField(
              controller: titleController,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Имя / Название',
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
                labelText: 'Общая сумма',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
                suffixText: '₸',
                enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: paymentController,
              keyboardType: TextInputType.number,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Сумма платежа',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
                hintText: 'Необязательно',
                suffixText: '₸',
                enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: displayDateController,
              readOnly: true,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Дата платежа',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
                hintText: 'Необязательно',
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
                  setState(() {
                    selectedDate = date;
                    displayDateController.text = _formatRussianDate(date);
                  });
                }
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
        TextButton(
          onPressed: isButtonEnabled
              ? () async {
                  final title = titleController.text.trim();
                  final amount = int.tryParse(amountController.text) ?? 0;
                  Navigator.pop(context);
                  await widget.appState.addDebt(
                    title: title,
                    remainingAmount: amount,
                    direction: direction,
                    dtype: dtype,
                    paymentAmount: int.tryParse(paymentController.text),
                    nextPaymentDate: selectedDate != null ? DateFormat('yyyy-MM-dd').format(selectedDate!) : null,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('✅ Долг/заём "$title" успешно добавлен!'),
                      backgroundColor: AppTheme.income,
                    ),
                  );
                }
              : null,
          child: Text(
            'Добавить',
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
