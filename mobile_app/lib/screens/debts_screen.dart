import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';

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

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _showPayDebtDialog(BuildContext context, AppState appState, Debt debt) {
    final amountController = TextEditingController(
      text: debt.paymentAmount > 0 ? debt.paymentAmount.toString() : debt.remainingAmount.toString(),
    );
    final dateController = TextEditingController(text: debt.nextPaymentDate ?? '');

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppTheme.border),
          ),
          title: Text('Оплата долга: ${debt.title}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
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
              TextField(
                controller: dateController,
                style: const TextStyle(color: AppTheme.textPrimary),
                decoration: const InputDecoration(
                  labelText: 'Следующий платёж (ГГГГ-ММ-ДД)',
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
                    initialDate: DateTime.now(),
                    firstDate: DateTime.now().subtract(const Duration(days: 365)),
                    lastDate: DateTime.now().add(const Duration(days: 3650)),
                  );
                  if (date != null) {
                    dateController.text = DateFormat('yyyy-MM-dd').format(date);
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
              onPressed: () async {
                final amt = int.tryParse(amountController.text) ?? 0;
                if (amt <= 0) return;
                Navigator.pop(context);
                await appState.payDebt(
                  debt.id,
                  amount: amt,
                  nextPaymentDate: dateController.text.trim().isEmpty ? null : dateController.text.trim(),
                );
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: const Text('✅ Платеж успешно внесен!'),
                    backgroundColor: AppTheme.income,
                  ),
                );
              },
              child: const Text('Оплатить', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }

  void _showAddDebtDialog(BuildContext context, AppState appState) {
    final titleController = TextEditingController();
    final amountController = TextEditingController();
    final paymentController = TextEditingController();
    final dateController = TextEditingController();
    String direction = 'out'; // I owe
    String dtype = 'private'; // Private person

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
                      controller: dateController,
                      style: const TextStyle(color: AppTheme.textPrimary),
                      decoration: const InputDecoration(
                        labelText: 'Дата платежа (ГГГГ-ММ-ДД)',
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
                          dateController.text = DateFormat('yyyy-MM-dd').format(date);
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
                  onPressed: () async {
                    final title = titleController.text.trim();
                    final amount = int.tryParse(amountController.text) ?? 0;
                    if (title.isEmpty || amount <= 0) return;
                    Navigator.pop(context);
                    await appState.addDebt(
                      title: title,
                      remainingAmount: amount,
                      direction: direction,
                      dtype: dtype,
                      paymentAmount: int.tryParse(paymentController.text),
                      nextPaymentDate: dateController.text.trim().isEmpty ? null : dateController.text.trim(),
                    );
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('✅ Долг/заём "$title" успешно добавлен!'),
                        backgroundColor: AppTheme.income,
                      ),
                    );
                  },
                  child: const Text('Добавить', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
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
        final dueDateStr = dueDate != null ? DateFormat('dd.MM.yyyy').format(dueDate) : 'Не задана';

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
        );
      },
    );
  }
}
