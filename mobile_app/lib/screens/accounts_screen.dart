import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';

class AccountsScreen extends StatelessWidget {
  const AccountsScreen({super.key});

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _showAddAccountDialog(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (context) => _AddAccountDialog(appState: appState),
    );
  }

  void _showEditAccountDialog(BuildContext context, AppState appState, Account acc) {
    final nameController = TextEditingController(text: acc.name);
    final balanceController = TextEditingController(text: acc.balance.toString());
    bool isSaving = acc.isSaving;

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
              title: const Text('Редактировать счёт', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: nameController,
                    style: const TextStyle(color: AppTheme.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Название счёта',
                      labelStyle: TextStyle(color: AppTheme.textSecondary),
                      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                    ),
                  ),
                  const SizedBox(height: 16),
                  TextField(
                    controller: balanceController,
                    keyboardType: TextInputType.number,
                    style: const TextStyle(color: AppTheme.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Текущий баланс',
                      labelStyle: TextStyle(color: AppTheme.textSecondary),
                      suffixText: '₸',
                      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                    ),
                  ),
                  const SizedBox(height: 16),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Накопительный счёт', style: TextStyle(color: AppTheme.textPrimary)),
                      Switch(
                        value: isSaving,
                        activeColor: AppTheme.primary,
                        onChanged: (val) {
                          setState(() {
                            isSaving = val;
                          });
                        },
                      ),
                    ],
                  ),
                ],
              ),
              actions: [
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    TextButton(
                      onPressed: () {
                        Navigator.pop(context);
                        _showArchiveConfirmDialog(context, appState, acc);
                      },
                      child: const Text('В архив', style: TextStyle(color: AppTheme.expense)),
                    ),
                    Row(
                      children: [
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                        ),
                        TextButton(
                          onPressed: () async {
                            final name = nameController.text.trim();
                            final balance = int.tryParse(balanceController.text) ?? acc.balance;
                            if (name.isEmpty) return;

                            try {
                              Navigator.pop(context);
                              await appState.updateAccount(
                                acc.id,
                                name: name != acc.name ? name : null,
                                balance: balance != acc.balance ? balance : null,
                                isSaving: isSaving != acc.isSaving ? (isSaving ? 1 : 0) : null,
                              );
                              ScaffoldMessenger.of(context).showSnackBar(
                                const SnackBar(
                                  content: Text('✅ Счёт успешно обновлен!'),
                                  backgroundColor: AppTheme.income,
                                ),
                              );
                            } catch (e) {
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(
                                  content: Text('❌ Ошибка: ${e.toString().replaceAll("Exception: ", "")}'),
                                  backgroundColor: AppTheme.expense,
                                ),
                              );
                            }
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
      },
    );
  }

  void _showArchiveConfirmDialog(BuildContext context, AppState appState, Account acc) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppTheme.border),
          ),
          title: const Text('Архивировать счёт?', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
          content: Text(
            'Вы уверены, что хотите перенести счёт "${acc.name}" в архив?\n\nОн перестанет отображаться в списке активных кошельков.',
            style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            TextButton(
              onPressed: () async {
                try {
                  Navigator.pop(context);
                  await appState.deleteAccount(acc.id);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('📥 Счёт "${acc.name}" перенесен в архив'),
                      backgroundColor: AppTheme.primary,
                    ),
                  );
                } catch (e) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('❌ Ошибка: ${e.toString().replaceAll("Exception: ", "")}'),
                      backgroundColor: AppTheme.expense,
                    ),
                  );
                }
              },
              child: const Text('В архив', style: TextStyle(color: AppTheme.expense, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final accounts = appState.accounts;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Мои Счета', style: TextStyle(fontWeight: FontWeight.bold)),
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
                'Управление кошельками',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 16),

              Expanded(
                child: ListView.builder(
                  physics: const BouncingScrollPhysics(),
                  itemCount: accounts.length,
                  itemBuilder: (context, index) {
                    final acc = accounts[index];
                    return GestureDetector(
                      onTap: () => _showEditAccountDialog(context, appState, acc),
                      child: Container(
                        margin: const EdgeInsets.only(bottom: 14),
                        decoration: AppTheme.glassCardDecoration(radius: 16),
                        padding: const EdgeInsets.all(20),
                        child: Row(
                          children: [
                            Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: (acc.accType == 'deposit' ? AppTheme.income : (acc.isSaving ? AppTheme.primary : AppTheme.accentBlue)).withOpacity(0.1),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                acc.accType == 'deposit' ? Icons.trending_up_rounded : (acc.isSaving ? Icons.savings_rounded : Icons.account_balance_wallet_rounded),
                                color: acc.accType == 'deposit' ? AppTheme.income : (acc.isSaving ? AppTheme.primary : AppTheme.accentBlue),
                                size: 24,
                              ),
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    acc.name,
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppTheme.textPrimary),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    acc.accType == 'deposit'
                                        ? 'Депозит (${acc.interestRate}%, ${acc.accrualPeriod == 'month' ? 'мес.' : 'год'})'
                                        : (acc.isSaving ? 'Копилка / Накопления' : 'Обычный счёт'),
                                    style: TextStyle(
                                      color: acc.accType == 'deposit' ? AppTheme.income : (acc.isSaving ? AppTheme.accentBlue : AppTheme.income),
                                      fontSize: 11,
                                      fontWeight: FontWeight.w600,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                            Text(
                              _formatKzt(acc.balance),
                              style: const TextStyle(
                                color: Colors.white,
                                fontSize: 18,
                                fontWeight: FontWeight.bold,
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),

              ElevatedButton(
                onPressed: () => _showAddAccountDialog(context, appState),
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
                  'Добавить новый счёт',
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

class _AddAccountDialog extends StatefulWidget {
  final AppState appState;
  const _AddAccountDialog({required this.appState});

  @override
  State<_AddAccountDialog> createState() => _AddAccountDialogState();
}

class _AddAccountDialogState extends State<_AddAccountDialog> {
  late final TextEditingController nameController;
  late final TextEditingController balanceController;
  late final TextEditingController interestRateController;

  String accType = 'regular'; // 'regular', 'saving', 'deposit'
  String accrualPeriod = 'month'; // 'month', 'year'
  bool isBusiness = false;
  String currency = 'KZT'; // Multi-currency

  @override
  void initState() {
    super.initState();
    nameController = TextEditingController();
    balanceController = TextEditingController(text: '0');
    interestRateController = TextEditingController(text: '12');

    nameController.addListener(_updateState);
    balanceController.addListener(_updateState);
    interestRateController.addListener(_updateState);
  }

  void _updateState() {
    setState(() {});
  }

  @override
  void dispose() {
    nameController.dispose();
    balanceController.dispose();
    interestRateController.dispose();
    super.dispose();
  }

  void _showPremiumPaywall(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppTheme.border),
          ),
          title: const Text('👑 Доступно в Premium версии', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
          content: const Text(
            'Мультивалютные счета и автоматическая конверсия переводов доступны только пользователям с Premium подпиской. Перейдите на Premium, чтобы разблокировать все возможности!',
            style: TextStyle(color: AppTheme.textSecondary),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Позже', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                widget.appState.upgradeToPremium();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('👑 Спасибо за покупку Premium подписки!'),
                    backgroundColor: AppTheme.primary,
                  ),
                );
              },
              child: const Text('Купить Premium', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final name = nameController.text.trim();
    final balance = int.tryParse(balanceController.text) ?? 0;
    final interestRate = double.tryParse(interestRateController.text) ?? 0.0;
    final isButtonEnabled = name.isNotEmpty && (accType != 'deposit' || interestRate > 0);

    return AlertDialog(
      backgroundColor: AppTheme.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
        side: const BorderSide(color: AppTheme.border),
      ),
      title: const Text('Новый счёт', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
      content: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: nameController,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Название счёта',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
                enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
              ),
            ),
            const SizedBox(height: 12),
            TextField(
              controller: balanceController,
              keyboardType: TextInputType.number,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Стартовый баланс',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
                suffixText: '₸',
                enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
              ),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: currency,
              dropdownColor: AppTheme.surface,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Валюта счета',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
              ),
              items: const [
                DropdownMenuItem(value: 'KZT', child: Text('Казахстанский тенге (₸)')),
                DropdownMenuItem(value: 'USD', child: Text('Доллар США (\$)')),
                DropdownMenuItem(value: 'RUB', child: Text('Российский рубль (₽)')),
                DropdownMenuItem(value: 'EUR', child: Text('Евро (€)')),
              ],
              onChanged: (val) {
                if (val != null) {
                  setState(() => currency = val);
                }
              },
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: accType,
              dropdownColor: AppTheme.surface,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: const InputDecoration(
                labelText: 'Тип счёта',
                labelStyle: TextStyle(color: AppTheme.textSecondary),
              ),
              items: const [
                DropdownMenuItem(value: 'regular', child: Text('Обычный счёт')),
                DropdownMenuItem(value: 'saving', child: Text('Накопительный счёт')),
                DropdownMenuItem(value: 'deposit', child: Text('Депозит')),
              ],
              onChanged: (val) {
                if (val != null) {
                  setState(() => accType = val);
                }
              },
            ),
            if (accType == 'deposit') ...[
              const SizedBox(height: 12),
              TextField(
                controller: interestRateController,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                style: const TextStyle(color: AppTheme.textPrimary),
                decoration: const InputDecoration(
                  labelText: 'Процентная ставка (%)',
                  labelStyle: TextStyle(color: AppTheme.textSecondary),
                  suffixText: '%',
                  enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                  focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                ),
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: accrualPeriod,
                dropdownColor: AppTheme.surface,
                style: const TextStyle(color: AppTheme.textPrimary),
                decoration: const InputDecoration(
                  labelText: 'Периодичность начисления',
                  labelStyle: TextStyle(color: AppTheme.textSecondary),
                ),
                items: const [
                  DropdownMenuItem(value: 'month', child: Text('Раз в месяц')),
                  DropdownMenuItem(value: 'year', child: Text('Раз в год')),
                ],
                onChanged: (val) {
                  if (val != null) {
                    setState(() => accrualPeriod = val);
                  }
                },
              ),
            ],
            const SizedBox(height: 12),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Бизнес-счёт', style: TextStyle(color: AppTheme.textPrimary)),
                Switch(
                  value: isBusiness,
                  activeColor: AppTheme.primary,
                  onChanged: (val) {
                    setState(() {
                      isBusiness = val;
                    });
                  },
                ),
              ],
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
                  final isPremium = widget.appState.isPremium;
                  if (currency != 'KZT' && !isPremium) {
                    Navigator.pop(context);
                    _showPremiumPaywall(context);
                    return;
                  }

                  try {
                    Navigator.pop(context);
                    await widget.appState.addAccount(
                      name: name,
                      balance: balance,
                      isSaving: accType == 'saving' ? 1 : 0,
                      accType: accType,
                      interestRate: accType == 'deposit' ? interestRate : 0.0,
                      accrualPeriod: accType == 'deposit' ? accrualPeriod : 'month',
                      isBusiness: isBusiness ? 1 : 0,
                      currency: currency,
                    );
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('✅ Счёт "$name" успешно создан!'),
                        backgroundColor: AppTheme.income,
                      ),
                    );
                  } catch (e) {
                    ScaffoldMessenger.of(context).showSnackBar(
                      SnackBar(
                        content: Text('❌ Ошибка: ${e.toString().replaceAll("Exception: ", "")}'),
                        backgroundColor: AppTheme.expense,
                      ),
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
