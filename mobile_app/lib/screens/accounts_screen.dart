import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';

class AccountsScreen extends StatelessWidget {
  const AccountsScreen({super.key});

  String _formatKzt(int amountMinor) {
    return _formatCurrency(amountMinor, 'KZT');
  }

  String _formatCurrency(int amount, String currency) {
    String symbol = '₸';
    String locale = 'kk_KZ';
    if (currency == 'USD') {
      symbol = '\$';
      locale = 'en_US';
    } else if (currency == 'EUR') {
      symbol = '€';
      locale = 'de_DE';
    } else if (currency == 'RUB') {
      symbol = '₽';
      locale = 'ru_RU';
    }
    final formatter = NumberFormat.currency(locale: locale, symbol: symbol, decimalDigits: 0);
    return formatter.format(amount);
  }

  void _showAddAccountDialog(BuildContext context, AppState appState) {
    showDialog(
      context: context,
      builder: (context) => _AddAccountDialog(appState: appState),
    );
  }

  void _showEditAccountDialog(BuildContext context, AppState appState, Account acc) {
    showDialog(
      context: context,
      builder: (context) => _EditAccountDialog(appState: appState, account: acc),
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
                              _formatCurrency(acc.balance, acc.currency),
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
  late final FocusNode balanceFocusNode;

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
    balanceFocusNode = FocusNode();
    balanceFocusNode.addListener(() {
      if (balanceFocusNode.hasFocus && balanceController.text == '0') {
        balanceController.clear();
      } else if (!balanceFocusNode.hasFocus && balanceController.text.trim().isEmpty) {
        balanceController.text = '0';
      }
    });

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
    balanceFocusNode.dispose();
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
              focusNode: balanceFocusNode,
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

class _EditAccountDialog extends StatefulWidget {
  final AppState appState;
  final Account account;
  const _EditAccountDialog({required this.appState, required this.account});

  @override
  State<_EditAccountDialog> createState() => _EditAccountDialogState();
}

class _EditAccountDialogState extends State<_EditAccountDialog> {
  late final TextEditingController nameController;
  late final TextEditingController balanceController;
  late final TextEditingController interestRateController;
  late final FocusNode balanceFocusNode;

  late String accType;
  late String accrualPeriod;
  late bool isBusiness;
  late String currency;

  @override
  void initState() {
    super.initState();
    nameController = TextEditingController(text: widget.account.name);
    balanceController = TextEditingController(text: widget.account.balance.toString());
    interestRateController = TextEditingController(text: widget.account.interestRate.toString());
    accType = widget.account.accType;
    accrualPeriod = widget.account.accrualPeriod;
    isBusiness = widget.account.isBusiness;
    currency = widget.account.currency;

    balanceFocusNode = FocusNode();
    balanceFocusNode.addListener(() {
      if (balanceFocusNode.hasFocus && balanceController.text == '0') {
        balanceController.clear();
      } else if (!balanceFocusNode.hasFocus && balanceController.text.trim().isEmpty) {
        balanceController.text = '0';
      }
    });

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
    balanceFocusNode.dispose();
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
      title: const Text('Редактировать счёт', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
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
              focusNode: balanceFocusNode,
              keyboardType: TextInputType.number,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: InputDecoration(
                labelText: 'Баланс',
                labelStyle: const TextStyle(color: AppTheme.textSecondary),
                suffixText: currency,
                enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
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
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _showArchiveConfirmDialog(context);
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
                            await widget.appState.updateAccount(
                              widget.account.id,
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
                        }
                      : null,
                  child: Text(
                    'Сохранить',
                    style: TextStyle(
                      color: isButtonEnabled ? AppTheme.primary : AppTheme.textSecondary.withOpacity(0.5),
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ],
    );
  }

  void _showArchiveConfirmDialog(BuildContext context) {
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
            'Вы уверены, что хотите перенести счёт "${widget.account.name}" в архив?\n\nОн перестанет отображаться в списке активных кошельков.',
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
                  await widget.appState.deleteAccount(widget.account.id);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('📥 Счёт "${widget.account.name}" перенесен в архив'),
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
}
