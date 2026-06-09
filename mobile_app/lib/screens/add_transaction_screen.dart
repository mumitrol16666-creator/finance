import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../utils/currency_utils.dart' as cu;

class AddTransactionScreen extends StatefulWidget {
  final bool showTutorialHint;

  const AddTransactionScreen({super.key, this.showTutorialHint = false});

  @override
  State<AddTransactionScreen> createState() => _AddTransactionScreenState();
}

class _AddTransactionScreenState extends State<AddTransactionScreen> {
  String _amountStr = '0';
  String _kind = 'expense'; // 'expense', 'income', or 'transfer'
  String? _selectedCategory;
  String? _selectedAccount;
  String? _selectedToAccount;
  final TextEditingController _noteController = TextEditingController();
  final FocusNode _noteFocusNode = FocusNode();

  int? _selectedPlannedId;
  int? _selectedDebtId;
  String? _linkedItemTitle;

  double? _customTransferRate;
  bool _isCustomRateActive = false;

  // Auto-save logic fields
  bool _autoSave = false;
  String? _selectedSavingAccount;
  int _autoSavePercent = 10; // Default 10%

  String _formatKzt(num amount) {
    final appState = Provider.of<AppState>(context, listen: false);
    return cu.formatCurrency(amount.round(), appState.baseCurrency);
  }

  int _convertAmountToBase(AppState appState, int amount) {
    if (_selectedAccount == null) return amount;
    try {
      final acc = appState.accounts.firstWhere((a) => a.name == _selectedAccount);
      return appState.convertAmount(amount, acc.currency, appState.baseCurrency) ?? amount;
    } catch (_) {
      return amount;
    }
  }

  String _selectedAccountCurrency(AppState appState) {
    if (_selectedAccount == null) return appState.baseCurrency;
    try {
      return appState.accounts.firstWhere((a) => a.name == _selectedAccount).currency;
    } catch (_) {
      return appState.baseCurrency;
    }
  }

  @override
  void initState() {
    super.initState();
    _noteController.addListener(_onNoteChanged);
    _noteFocusNode.addListener(_onFocusChanged);
  }

  void _onNoteChanged() {
    setState(() {});
  }

  void _onFocusChanged() {
    setState(() {});
  }

  @override
  void dispose() {
    _noteController.removeListener(_onNoteChanged);
    _noteFocusNode.removeListener(_onFocusChanged);
    _noteController.dispose();
    _noteFocusNode.dispose();
    super.dispose();
  }

  void _onKeyPress(String val) {
    setState(() {
      if (val == 'C') {
        _amountStr = '0';
      } else if (val == '⌫') {
        if (_amountStr.length > 1) {
          _amountStr = _amountStr.substring(0, _amountStr.length - 1);
        } else {
          _amountStr = '0';
        }
      } else {
        if (_amountStr == '0') {
          _amountStr = val;
        } else {
          if (_amountStr.length < 9) {
            _amountStr += val;
          }
        }
      }
    });
  }

  void _selectTransfer(AppState appState) {
    if (!appState.hasFeature('transfer')) {
      AppTheme.showPremiumBlockDialog(context);
      return;
    }
    if (appState.accounts.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Для перевода нужно создать минимум два счёта'),
          backgroundColor: AppTheme.expense,
        ),
      );
      return;
    }
    setState(() => _kind = 'transfer');
  }

  Future<void> _saveTransaction() async {
    final amountInt = int.tryParse(_amountStr) ?? 0;
    if (amountInt <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Введите сумму операции')),
      );
      return;
    }

    if (_selectedDebtId == null && _kind != 'transfer' && _selectedCategory == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Выберите категорию')),
      );
      return;
    }

    if (_selectedAccount == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Выберите счёт')),
      );
      return;
    }

    final appState = Provider.of<AppState>(context, listen: false);

    try {
      if (_selectedDebtId != null) {
        final account = appState.accounts.firstWhere((a) => a.name == _selectedAccount);
        await appState.payDebt(
          _selectedDebtId!,
          amount: amountInt,
          accountId: account.id,
        );
      } else if (_kind == 'transfer') {
        if (!appState.hasFeature('transfer')) {
          AppTheme.showPremiumBlockDialog(context);
          return;
        }
        if (_selectedToAccount == null) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Выберите счёт зачисления')),
          );
          return;
        }
        if (_selectedAccount == _selectedToAccount) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Счета списания и зачисления должны отличаться')),
          );
          return;
        }

        await appState.addTransaction(
          amount: amountInt,
          kind: 'transfer',
          categoryName: '',
          categoryEmoji: '',
          accountName: _selectedAccount!,
          toAccountName: _selectedToAccount!,
          note: _noteController.text.trim().isNotEmpty ? _noteController.text.trim() : null,
          customRate: _isCustomRateActive ? _customTransferRate : null,
        );
      } else {
        final category = appState.categories.firstWhere((c) => c.name == _selectedCategory);

        await appState.addTransaction(
          amount: amountInt,
          kind: _kind,
          categoryName: category.name,
          categoryEmoji: category.emoji,
          accountName: _selectedAccount!,
          note: _noteController.text.trim().isNotEmpty ? _noteController.text.trim() : null,
        );

        if (_kind == 'income' && _autoSave && _selectedSavingAccount != null) {
          final transferAmount = (amountInt * _autoSavePercent / 100).round();
          if (transferAmount > 0) {
            await appState.addTransaction(
              amount: transferAmount,
              kind: 'transfer',
              categoryName: category.name,
              categoryEmoji: category.emoji,
              accountName: _selectedAccount!,
              toAccountName: _selectedSavingAccount!,
              note: 'Автонакопление ($_autoSavePercent% от дохода)',
            );
          }
        }

        if (_selectedPlannedId != null) {
          await appState.completePlanned(_selectedPlannedId!);
        }
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Не удалось сохранить операцию: ${e.toString().replaceAll("Exception: ", "")}'),
          backgroundColor: AppTheme.expense,
        ),
      );
      return;
    }

    // Reset state & show success
    setState(() {
      _amountStr = '0';
      _noteController.clear();
      _autoSave = false;
      _selectedPlannedId = null;
      _selectedDebtId = null;
      _linkedItemTitle = null;
      _customTransferRate = null;
      _isCustomRateActive = false;
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('✅ Операция успешно сохранена!'),
        backgroundColor: AppTheme.income,
      ),
    );

    if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    }
  }

  void _showAddCategoryDialog(BuildContext context) {
    final nameController = TextEditingController();
    String selectedEmoji = '📦';
    final popularEmojis = ['📦', '💸', '🍔', '🚗', '🛍️', '🍿', '🏠', '📈', '💰', '🎁', '🏥', '✈️'];

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
              title: const Text('Новая категория', style: TextStyle(color: Colors.white, fontSize: 16, fontWeight: FontWeight.bold)),
              content: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    TextField(
                      controller: nameController,
                      style: const TextStyle(color: Colors.white),
                      decoration: const InputDecoration(
                        labelText: 'Название категории',
                        labelStyle: TextStyle(color: AppTheme.textSecondary),
                        enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                        focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                      ),
                    ),
                    const SizedBox(height: 16),
                    const Text('Выберите иконку (Emoji):', style: TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
                    const SizedBox(height: 8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: popularEmojis.map((emoji) {
                        final isSelected = selectedEmoji == emoji;
                        return GestureDetector(
                          onTap: () => setDialogState(() => selectedEmoji = emoji),
                          child: Container(
                            padding: const EdgeInsets.all(8),
                            decoration: BoxDecoration(
                              color: isSelected ? AppTheme.primary.withOpacity(0.2) : Colors.transparent,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: isSelected ? AppTheme.primary : AppTheme.border.withOpacity(0.5)),
                            ),
                            child: Text(emoji, style: const TextStyle(fontSize: 18)),
                          ),
                        );
                      }).toList(),
                    ),
                    const SizedBox(height: 12),
                    Row(
                      children: [
                        const Text('Свой Emoji: ', style: TextStyle(color: AppTheme.textSecondary, fontSize: 12)),
                        const SizedBox(width: 8),
                        SizedBox(
                          width: 40,
                          child: TextField(
                            maxLength: 1,
                            style: const TextStyle(color: Colors.white, fontSize: 18),
                            decoration: const InputDecoration(
                              counterText: '',
                              isDense: true,
                              contentPadding: EdgeInsets.symmetric(vertical: 4),
                            ),
                            onChanged: (val) {
                              if (val.trim().isNotEmpty) {
                                setDialogState(() => selectedEmoji = val.trim());
                              }
                            },
                          ),
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
                ElevatedButton(
                  onPressed: () async {
                    final name = nameController.text.trim();
                    if (name.isEmpty) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text('Введите название категории')),
                      );
                      return;
                    }
                    Navigator.pop(context);

                    try {
                      final appState = Provider.of<AppState>(context, listen: false);
                      await appState.addCategory(
                        name: name,
                        emoji: selectedEmoji,
                        kind: _kind,
                      );
                      setState(() {
                        _selectedCategory = name;
                      });
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Категория "$name" успешно создана!'), backgroundColor: AppTheme.income),
                      );
                    } catch (e) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(content: Text('Ошибка при создании категории: $e'), backgroundColor: AppTheme.expense),
                      );
                    }
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: AppTheme.primary),
                  child: const Text('Создать', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
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
    final accounts = appState.accounts;
    final categories = appState.categories;
    final bool isKeyboardVisible = MediaQuery.of(context).viewInsets.bottom > 0 || _noteFocusNode.hasFocus;

    // Filter to exclude savings accounts from regular dropdown/selector
    final regularAccounts = accounts.where((a) => !a.isSaving).toList();
    final savingsAccounts = accounts.where((a) => a.isSaving).toList();

    // Set defaults if not selected yet
    if (_selectedAccount == null || !accounts.any((a) => a.name == _selectedAccount)) {
      _selectedAccount = accounts.isNotEmpty ? accounts[0].name : null;
    }
    if (_selectedToAccount == null || !accounts.any((a) => a.name == _selectedToAccount) || _selectedToAccount == _selectedAccount) {
      try {
        _selectedToAccount = accounts.firstWhere((a) => a.name != _selectedAccount).name;
      } catch (_) {
        _selectedToAccount = null;
      }
    }
    
    final isExpense = _kind == 'expense';
    final isTransfer = _kind == 'transfer';
    final filteredCategories = categories.where((c) => c.kind == (isExpense ? 'expense' : 'income')).toList();

    if (_selectedCategory == null || !filteredCategories.any((c) => c.name == _selectedCategory)) {
      _selectedCategory = filteredCategories.isNotEmpty ? filteredCategories[0].name : null;
    }

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          if (widget.showTutorialHint) ...[
            Container(
              margin: const EdgeInsets.only(bottom: 10),
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: AppTheme.primary.withOpacity(0.12),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: AppTheme.primary.withOpacity(0.45)),
              ),
              child: const Row(
                children: [
                  Icon(Icons.school_rounded, color: AppTheme.primary, size: 20),
                  SizedBox(width: 10),
                  Expanded(
                    child: Text(
                      'Выберите тип операции, введите сумму, укажите счёт и нажмите «Сохранить операцию».',
                      style: TextStyle(color: AppTheme.textPrimary, fontSize: 11, height: 1.3),
                    ),
                  ),
                ],
              ),
            ),
          ],
          // Scrollable fields to prevent keyboard overlap/overflow
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Segmented Tab Control (Expense / Income / Transfer)
                  Row(
                    children: [
                      Expanded(
                        child: _buildTypeButton(
                          title: 'РАСХОД',
                          active: _kind == 'expense',
                          activeColor: AppTheme.expense,
                          onTap: () => setState(() {
                            _kind = 'expense';
                            final filtered = categories.where((c) => c.kind == 'expense').toList();
                            _selectedCategory = filtered.isNotEmpty ? filtered[0].name : null;
                          }),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _buildTypeButton(
                          title: 'ДОХОД',
                          active: _kind == 'income',
                          activeColor: AppTheme.income,
                          onTap: () => setState(() {
                            _kind = 'income';
                            final filtered = categories.where((c) => c.kind == 'income').toList();
                            _selectedCategory = filtered.isNotEmpty ? filtered[0].name : null;
                          }),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: _buildTypeButton(
                          title: 'ПЕРЕВОД',
                          active: _kind == 'transfer',
                          activeColor: AppTheme.accentBlue,
                          locked: !appState.hasFeature('transfer'),
                          onTap: () => _selectTransfer(appState),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 20),

                  // Display Amount field
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                    decoration: AppTheme.glassCardDecoration(radius: 12),
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Сумма:',
                          style: TextStyle(color: AppTheme.textSecondary, fontWeight: FontWeight.bold),
                        ),
                        Builder(builder: (context) {
                          String sym = cu.currencySymbol(appState.baseCurrency);
                          if (_selectedAccount != null) {
                            try {
                              final acc = appState.accounts.firstWhere((a) => a.name == _selectedAccount);
                              sym = cu.currencySymbol(acc.currency);
                            } catch (_) {}
                          }
                          return Text(
                            '$_amountStr $sym',
                            style: TextStyle(
                              fontSize: 28,
                              fontWeight: FontWeight.bold,
                              color: isTransfer
                                  ? AppTheme.accentBlue
                                  : (isExpense ? AppTheme.expense : AppTheme.income),
                            ),
                          );
                        }),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

                  if (isTransfer) ...[
                    // Счёт списания
                    const Text(
                      'Откуда (Счёт списания)',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      height: 40,
                      child: ListView.builder(
                        scrollDirection: Axis.horizontal,
                        physics: const BouncingScrollPhysics(),
                        itemCount: accounts.length,
                        itemBuilder: (context, index) {
                          final acc = accounts[index];
                          final name = acc.name;
                          final balance = acc.balance;
                          final isSelected = _selectedAccount == name;
                          return GestureDetector(
                            onTap: () => setState(() {
                              _selectedAccount = name;
                              if (_selectedAccount == _selectedToAccount) {
                                try {
                                  _selectedToAccount = accounts.firstWhere((a) => a.name != name).name;
                                } catch (_) {
                                  _selectedToAccount = null;
                                }
                              }
                            }),
                            child: Container(
                              margin: const EdgeInsets.only(right: 8),
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                              decoration: BoxDecoration(
                                color: isSelected ? AppTheme.primary : AppTheme.surfaceCard,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(
                                  color: isSelected ? Colors.white24 : Colors.transparent,
                                ),
                              ),
                              child: Text(
                                '$name (${cu.formatCurrency(balance, acc.currency)})',
                                style: TextStyle(
                                  color: isSelected ? Colors.white : AppTheme.textSecondary,
                                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Счёт зачисления
                    const Text(
                      'Куда (Счёт зачисления)',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      height: 40,
                      child: ListView.builder(
                        scrollDirection: Axis.horizontal,
                        physics: const BouncingScrollPhysics(),
                        itemCount: accounts.length,
                        itemBuilder: (context, index) {
                          final acc = accounts[index];
                          final name = acc.name;
                          final balance = acc.balance;
                          if (name == _selectedAccount) return const SizedBox.shrink();

                          final isSelected = _selectedToAccount == name;
                          return GestureDetector(
                            onTap: () => setState(() => _selectedToAccount = name),
                            child: Container(
                              margin: const EdgeInsets.only(right: 8),
                              padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                              decoration: BoxDecoration(
                                color: isSelected ? AppTheme.accentBlue : AppTheme.surfaceCard,
                                borderRadius: BorderRadius.circular(20),
                                border: Border.all(
                                  color: isSelected ? Colors.white24 : Colors.transparent,
                                ),
                              ),
                              child: Text(
                                '$name (${cu.formatCurrency(balance, acc.currency)})',
                                style: TextStyle(
                                  color: isSelected ? Colors.white : AppTheme.textSecondary,
                                  fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                ),
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Multi-currency transfer details
                    Builder(builder: (context) {
                      try {
                        final fromAcc = accounts.firstWhere((a) => a.name == _selectedAccount);
                        final toAcc = accounts.firstWhere((a) => a.name == _selectedToAccount);

                        if (fromAcc.currency != toAcc.currency) {
                          final fromRate = appState.exchangeRates[fromAcc.currency.toUpperCase()] ?? 1.0;
                          final toRate = appState.exchangeRates[toAcc.currency.toUpperCase()] ?? 1.0;
                          final defaultRate = toRate / fromRate;

                          final rateToUse = _isCustomRateActive && _customTransferRate != null
                              ? _customTransferRate!
                              : defaultRate;

                          final amountVal = int.tryParse(_amountStr) ?? 0;
                          final receivedAmount = (amountVal * rateToUse).round();

                          return Container(
                            margin: const EdgeInsets.only(bottom: 16),
                            padding: const EdgeInsets.all(16),
                            decoration: AppTheme.glassCardDecoration(radius: 16),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    const Text(
                                      'Курс обмена:',
                                      style: TextStyle(
                                        color: AppTheme.textSecondary,
                                        fontSize: 12,
                                        fontWeight: FontWeight.bold,
                                      ),
                                    ),
                                    Row(
                                      children: [
                                        GestureDetector(
                                          onTap: () {
                                            _showEditTransferRateDialog(context, fromAcc.currency, toAcc.currency, rateToUse);
                                          },
                                          child: Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                            decoration: BoxDecoration(
                                              color: _isCustomRateActive
                                                  ? AppTheme.accentBlue.withOpacity(0.15)
                                                  : Colors.white.withOpacity(0.05),
                                              borderRadius: BorderRadius.circular(8),
                                              border: Border.all(
                                                color: _isCustomRateActive
                                                    ? AppTheme.accentBlue.withOpacity(0.3)
                                                    : Colors.white.withOpacity(0.05),
                                              ),
                                            ),
                                            child: Row(
                                              children: [
                                                Text(
                                                  cu.formatDirectExchangeRate(fromAcc.currency, toAcc.currency, rateToUse),
                                                  style: TextStyle(
                                                    color: _isCustomRateActive ? AppTheme.accentBlue : Colors.white70,
                                                    fontSize: 12,
                                                    fontWeight: FontWeight.bold,
                                                  ),
                                                ),
                                                const SizedBox(width: 4),
                                                Icon(
                                                  Icons.edit_rounded,
                                                  size: 12,
                                                  color: _isCustomRateActive ? AppTheme.accentBlue : AppTheme.textSecondary,
                                                ),
                                              ],
                                            ),
                                          ),
                                        ),
                                        if (_isCustomRateActive) ...[
                                          const SizedBox(width: 6),
                                          IconButton(
                                            icon: const Icon(Icons.refresh_rounded, size: 16, color: AppTheme.textSecondary),
                                            padding: EdgeInsets.zero,
                                            constraints: const BoxConstraints(),
                                            onPressed: () {
                                              setState(() {
                                                _isCustomRateActive = false;
                                                _customTransferRate = null;
                                              });
                                            },
                                          ),
                                        ],
                                      ],
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    const Text(
                                      'Получатель получит:',
                                      style: TextStyle(
                                        color: AppTheme.textSecondary,
                                        fontSize: 12,
                                      ),
                                    ),
                                    Text(
                                      '≈ ${cu.formatCurrency(receivedAmount, toAcc.currency)}',
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
                          );
                        }
                      } catch (_) {}
                      return const SizedBox.shrink();
                    }),
                  ] else ...[
                    // Horizontal scroll of accounts (Excluding Savings)
                    const Text(
                      'Счёт списания / зачисления',
                      style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                    ),
                    const SizedBox(height: 6),
                    if (regularAccounts.isEmpty)
                      const Padding(
                        padding: EdgeInsets.symmetric(vertical: 8.0),
                        child: Text('Нет активных счетов', style: TextStyle(color: AppTheme.textSecondary)),
                      )
                    else
                      SizedBox(
                        height: 40,
                        child: ListView.builder(
                          scrollDirection: Axis.horizontal,
                          physics: const BouncingScrollPhysics(),
                          itemCount: regularAccounts.length,
                          itemBuilder: (context, index) {
                            final acc = regularAccounts[index];
                            final name = acc.name;
                            final balance = acc.balance;
                            final isSelected = _selectedAccount == name;
                            return GestureDetector(
                              onTap: () => setState(() => _selectedAccount = name),
                              child: Container(
                                margin: const EdgeInsets.only(right: 8),
                                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                decoration: BoxDecoration(
                                  color: isSelected ? AppTheme.primary : AppTheme.surfaceCard,
                                  borderRadius: BorderRadius.circular(20),
                                  border: Border.all(
                                    color: isSelected ? Colors.white24 : Colors.transparent,
                                  ),
                                ),
                                child: Text(
                                  '$name (${cu.formatCurrency(balance, acc.currency)})',
                                  style: TextStyle(
                                    color: isSelected ? Colors.white : AppTheme.textSecondary,
                                    fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                  ),
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                    const SizedBox(height: 16),

                    // Horizontal scroll of categories
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text(
                          'Категория',
                          style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                        ),
                        TextButton.icon(
                          onPressed: () => _showAddCategoryDialog(context),
                          icon: const Icon(Icons.add_circle_outline_rounded, size: 16, color: AppTheme.primary),
                          label: const Text(
                            'Добавить',
                            style: TextStyle(fontSize: 12, color: AppTheme.primary, fontWeight: FontWeight.bold),
                          ),
                          style: TextButton.styleFrom(
                            padding: EdgeInsets.zero,
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    Stack(
                      alignment: Alignment.centerRight,
                      children: [
                        SizedBox(
                          height: 120, // Taller to fit all details
                          child: ListView.builder(
                            scrollDirection: Axis.horizontal,
                            physics: const BouncingScrollPhysics(),
                            itemCount: filteredCategories.length,
                            itemBuilder: (context, index) {
                              final cat = filteredCategories[index];
                              final isSelected = _selectedCategory == cat.name;
                              
                              // Parse currently typed amount preview
                              final currentTypedAmount = int.tryParse(_amountStr) ?? 0;
                              final currentTypedBaseAmount = _convertAmountToBase(appState, currentTypedAmount);
                              final limit = cat.limitAmount;
                              final spent = cat.spentAmount;
                              
                              // Check if current type is expense (limits only make sense for expenses)
                              final showLimitInfo = limit != null && _kind == 'expense';
                              
                              // Calculate warning text and progress
                              String? warningText;
                              double progressVal = 0.0;
                              
                              if (showLimitInfo && limit > 0) {
                                final totalPredicted = spent + (isSelected ? currentTypedBaseAmount : 0);
                                progressVal = totalPredicted / limit;
                                if (progressVal >= 1.0) {
                                  warningText = '⚠️ Превысит лимит!';
                                } else if (progressVal >= cat.warnThreshold) {
                                  warningText = '⚠️ Близко к лимиту';
                                }
                              }
                              
                              return GestureDetector(
                                onTap: () {
                                  setState(() {
                                    _selectedCategory = cat.name;
                                    if (cat.defaultAccountId != null && cat.defaultAccountId! > 0) {
                                      final matchAcc = appState.accounts.where((a) => a.id == cat.defaultAccountId);
                                      if (matchAcc.isNotEmpty) {
                                        _selectedAccount = matchAcc.first.name;
                                      }
                                    }
                                  });
                                },
                                child: Container(
                                  width: 170,
                                  margin: const EdgeInsets.only(right: 10),
                                  child: GlassCard(
                                    padding: const EdgeInsets.all(10),
                                    radius: 12,
                                    color: isSelected 
                                        ? AppTheme.primary.withOpacity(0.12)
                                        : Colors.white.withOpacity(0.02),
                                    borderOpacity: isSelected ? 0.25 : 0.06,
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        // Emoji + Name
                                        Row(
                                          children: [
                                            Text(cat.emoji, style: const TextStyle(fontSize: 16)),
                                            const SizedBox(width: 6),
                                            Expanded(
                                              child: Text(
                                                cat.name,
                                                style: TextStyle(
                                                  color: isSelected ? Colors.white : AppTheme.textPrimary,
                                                  fontWeight: FontWeight.bold,
                                                  fontSize: 12,
                                                ),
                                                maxLines: 1,
                                                overflow: TextOverflow.ellipsis,
                                              ),
                                            ),
                                          ],
                                        ),
                                        
                                        // Spent / Limit status
                                        Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              limit != null && limit > 0
                                                  ? 'Лимит: ${_formatKzt(limit)}'
                                                  : 'Без лимита',
                                              style: const TextStyle(
                                                color: AppTheme.textSecondary,
                                                fontSize: 10,
                                              ),
                                            ),
                                            const SizedBox(height: 2),
                                            Text(
                                              currentTypedAmount > 0 && isSelected && _kind == 'expense'
                                                  ? '${_formatKzt(spent)} + ${_formatKzt(currentTypedBaseAmount)}'
                                                  : 'Потрачено: ${_formatKzt(spent)}',
                                              style: TextStyle(
                                                color: isSelected ? Colors.white70 : AppTheme.textSecondary,
                                                fontSize: 10,
                                                fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                              ),
                                              maxLines: 1,
                                              overflow: TextOverflow.ellipsis,
                                            ),
                                          ],
                                        ),
                                        
                                        // Progress bar & Warning text
                                        Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            if (showLimitInfo) ...[
                                              const SizedBox(height: 2),
                                              ClipRRect(
                                                borderRadius: BorderRadius.circular(4),
                                                child: LinearProgressIndicator(
                                                  value: progressVal.clamp(0.0, 1.0),
                                                  backgroundColor: Colors.white10,
                                                  valueColor: AlwaysStoppedAnimation<Color>(
                                                    progressVal >= 1.0 
                                                        ? AppTheme.expense 
                                                        : (progressVal >= cat.warnThreshold ? Colors.amber : AppTheme.income)
                                                  ),
                                                  minHeight: 4,
                                                ),
                                              ),
                                            ],
                                            if (warningText != null && isSelected) ...[
                                              const SizedBox(height: 4),
                                              Text(
                                                warningText,
                                                style: TextStyle(
                                                  color: progressVal >= 1.0 ? AppTheme.expense : Colors.orange,
                                                  fontSize: 9,
                                                  fontWeight: FontWeight.bold,
                                                ),
                                                maxLines: 1,
                                                overflow: TextOverflow.ellipsis,
                                              ),
                                            ],
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
                        if (filteredCategories.length > 2)
                          Positioned(
                            right: 4,
                            child: IgnorePointer(
                              child: Container(
                                padding: const EdgeInsets.all(4),
                                decoration: BoxDecoration(
                                  color: Colors.black45,
                                  shape: BoxShape.circle,
                                  border: Border.all(color: Colors.white10),
                                ),
                                child: const Icon(
                                  Icons.chevron_right_rounded,
                                  color: AppTheme.primary,
                                  size: 20,
                                ),
                              )
                              .animate(onPlay: (controller) => controller.repeat(reverse: true))
                              .slideX(begin: 0.0, end: 0.2, duration: 800.ms)
                              .fade(begin: 0.5, end: 1.0),
                            ),
                          ),
                      ],
                    ),
                    const SizedBox(height: 16),
                  ],

                  // Comment note field
                  const Text(
                    '💬 Описание / Комментарий',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                  ),
                  const SizedBox(height: 8),
                  Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(12),
                      boxShadow: _noteController.text.trim().isEmpty
                          ? [
                              BoxShadow(
                                color: AppTheme.secondary.withOpacity(0.12),
                                blurRadius: 10,
                                spreadRadius: 2,
                              )
                            ]
                          : [],
                    ),
                    child: TextField(
                      controller: _noteController,
                      focusNode: _noteFocusNode,
                      style: const TextStyle(color: AppTheme.textPrimary),
                      decoration: InputDecoration(
                        hintText: 'Опишите операцию (например: продукты в Магните, перевод на карту)',
                        hintStyle: const TextStyle(color: Colors.white30, fontSize: 13),
                        filled: true,
                        fillColor: AppTheme.surfaceCard,
                        enabledBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide(
                            color: _noteController.text.trim().isEmpty
                                ? AppTheme.secondary.withOpacity(0.6)
                                : AppTheme.accentBlue.withOpacity(0.4),
                            width: 1.5,
                          ),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(12),
                          borderSide: BorderSide(
                            color: _noteController.text.trim().isEmpty ? AppTheme.secondary : AppTheme.accentBlue,
                            width: 2.0,
                          ),
                        ),
                        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  AnimatedSwitcher(
                    duration: const Duration(milliseconds: 300),
                    child: _noteController.text.trim().isEmpty
                        ? Row(
                            key: const ValueKey('empty_note'),
                            children: const [
                              Icon(Icons.lightbulb_outline_rounded, color: AppTheme.secondary, size: 16),
                              SizedBox(width: 6),
                              Expanded(
                                child: Text(
                                  'ИИ рекомендует: напишите коммент для точного аудита!',
                                  style: TextStyle(
                                    color: AppTheme.secondary,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ],
                          )
                        : Row(
                            key: const ValueKey('filled_note'),
                            children: const [
                              Icon(Icons.check_circle_outline_rounded, color: AppTheme.income, size: 16),
                              SizedBox(width: 6),
                              Expanded(
                                child: Text(
                                  'Умный ИИ-анализ активен для этого платежа 🚀',
                                  style: TextStyle(
                                    color: AppTheme.income,
                                    fontSize: 11,
                                    fontWeight: FontWeight.bold,
                                  ),
                                ),
                              ),
                            ],
                          ),
                  ),
                  const SizedBox(height: 16),

                  // Linked status chip
                  if (_linkedItemTitle != null) ...[
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                      decoration: BoxDecoration(
                        color: AppTheme.primary.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: AppTheme.primary.withOpacity(0.3)),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Row(
                            children: [
                              const Icon(Icons.link_rounded, color: AppTheme.primary, size: 18),
                              const SizedBox(width: 8),
                              Text(
                                _linkedItemTitle!,
                                style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                              ),
                            ],
                          ),
                          GestureDetector(
                            onTap: () {
                              setState(() {
                                _selectedPlannedId = null;
                                _selectedDebtId = null;
                                _linkedItemTitle = null;
                                _noteController.clear();
                              });
                            },
                            child: const Icon(Icons.close_rounded, color: AppTheme.textSecondary, size: 18),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 12),
                  ],

                  if (_kind == 'expense') ...[
                    // Planned payments
                    if (appState.plannedEvents.where((p) => p.kind == 'expense' && p.status != 'done').isNotEmpty) ...[
                      const Text(
                        '📅 Ближайшие планируемые платежи',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                      ),
                      const SizedBox(height: 8),
                      SizedBox(
                        height: 70,
                        child: ListView.builder(
                          scrollDirection: Axis.horizontal,
                          physics: const BouncingScrollPhysics(),
                          itemCount: appState.plannedEvents.where((p) => p.kind == 'expense' && p.status != 'done').length,
                          itemBuilder: (context, index) {
                            final planned = appState.plannedEvents.where((p) => p.kind == 'expense' && p.status != 'done').toList()[index];
                            final isLinked = _selectedPlannedId == planned.id;
                            
                            return GestureDetector(
                              onTap: () {
                                setState(() {
                                  _amountStr = planned.amount.toString();
                                  _selectedPlannedId = planned.id;
                                  _selectedDebtId = null;
                                  _linkedItemTitle = 'План: ${planned.title}';
                                  _noteController.text = planned.title;

                                  if (planned.accountId != null) {
                                    final plannedAccounts = appState.accounts.where((a) => a.id == planned.accountId);
                                    if (plannedAccounts.isNotEmpty) {
                                      _selectedAccount = plannedAccounts.first.name;
                                    }
                                  }
                                  
                                  // Auto match category
                                  final match = appState.categories.where((c) => c.emoji == planned.categoryEmoji);
                                  if (match.isNotEmpty) {
                                    _selectedCategory = match.first.name;
                                    
                                    // Fall back to the category account for older planned items.
                                    final cat = match.first;
                                    if (planned.accountId == null && cat.defaultAccountId != null && cat.defaultAccountId! > 0) {
                                      final matchAcc = appState.accounts.where((a) => a.id == cat.defaultAccountId);
                                      if (matchAcc.isNotEmpty) {
                                        _selectedAccount = matchAcc.first.name;
                                      }
                                    }
                                  }
                                });
                              },
                              child: Container(
                                width: 160,
                                margin: const EdgeInsets.only(right: 8),
                                child: GlassCard(
                                  radius: 10,
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                  color: isLinked ? AppTheme.primary.withOpacity(0.15) : Colors.white.withOpacity(0.02),
                                  borderOpacity: isLinked ? 0.25 : 0.05,
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        planned.title,
                                        style: TextStyle(
                                          color: isLinked ? Colors.white : AppTheme.textPrimary,
                                          fontSize: 11,
                                          fontWeight: FontWeight.bold,
                                        ),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            cu.formatCurrency(planned.amount, planned.currency),
                                            style: const TextStyle(color: AppTheme.expense, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                          Text(
                                            planned.categoryEmoji,
                                            style: const TextStyle(fontSize: 12),
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
                      const SizedBox(height: 16),
                    ],

                    // Active debts
                    if (appState.debts.where((d) => d.direction == 'out' && d.status == 'active').isNotEmpty) ...[
                      const Text(
                        '💳 Активные долги и кредиты (к выплате)',
                        style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                      ),
                      const SizedBox(height: 8),
                      SizedBox(
                        height: 70,
                        child: ListView.builder(
                          scrollDirection: Axis.horizontal,
                          physics: const BouncingScrollPhysics(),
                          itemCount: appState.debts.where((d) => d.direction == 'out' && d.status == 'active').length,
                          itemBuilder: (context, index) {
                            final debt = appState.debts.where((d) => d.direction == 'out' && d.status == 'active').toList()[index];
                            final isLinked = _selectedDebtId == debt.id;
                            final nextPaymentText = debt.nextPaymentDate != null 
                              ? DateFormat('dd.MM').format(DateTime.parse(debt.nextPaymentDate!))
                              : null;
                            
                            return GestureDetector(
                              onTap: () {
                                setState(() {
                                  _amountStr = debt.paymentAmount > 0 ? debt.paymentAmount.toString() : debt.remainingAmount.toString();
                                  _selectedPlannedId = null;
                                  _selectedDebtId = debt.id;
                                  _linkedItemTitle = 'Долг: ${debt.title}';
                                  _noteController.text = debt.title;
                                  
                                  // Find first matching category for debt payment
                                  final match = appState.categories.where((c) => c.name.toLowerCase().contains('долг') || c.name.toLowerCase().contains('кредит') || c.emoji == '💳');
                                  if (match.isNotEmpty) {
                                    _selectedCategory = match.first.name;
                                    final cat = match.first;
                                    if (cat.defaultAccountId != null && cat.defaultAccountId! > 0) {
                                      final matchAcc = appState.accounts.where((a) => a.id == cat.defaultAccountId);
                                      if (matchAcc.isNotEmpty) {
                                        _selectedAccount = matchAcc.first.name;
                                      }
                                    }
                                  }
                                });
                              },
                              child: Container(
                                width: 170,
                                margin: const EdgeInsets.only(right: 8),
                                child: GlassCard(
                                  radius: 10,
                                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                  color: isLinked ? AppTheme.primary.withOpacity(0.15) : Colors.white.withOpacity(0.02),
                                  borderOpacity: isLinked ? 0.25 : 0.05,
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        debt.title,
                                        style: TextStyle(
                                          color: isLinked ? Colors.white : AppTheme.textPrimary,
                                          fontSize: 11,
                                          fontWeight: FontWeight.bold,
                                        ),
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                      ),
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            _formatKzt(debt.paymentAmount > 0 ? debt.paymentAmount : debt.remainingAmount),
                                            style: const TextStyle(color: AppTheme.expense, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                          if (nextPaymentText != null)
                                            Text(
                                              'до $nextPaymentText',
                                              style: const TextStyle(color: AppTheme.textSecondary, fontSize: 9),
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
                      const SizedBox(height: 16),
                    ],
                  ],

                  // Auto-save settings shown only for income operations if savings accounts exist
                  if (_kind == 'income' && savingsAccounts.isNotEmpty && appState.hasFeature('transfer')) ...[
                    GlassCard(
                      radius: 12,
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Text(
                                'Отложить часть в копилку?',
                                style: TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.bold, fontSize: 13),
                              ),
                              Switch(
                                value: _autoSave,
                                activeColor: AppTheme.primary,
                                activeTrackColor: AppTheme.primary.withOpacity(0.3),
                                inactiveThumbColor: AppTheme.textSecondary,
                                inactiveTrackColor: AppTheme.surfaceCard,
                                onChanged: (val) {
                                  setState(() {
                                    _autoSave = val;
                                    if (val && _selectedSavingAccount == null && savingsAccounts.isNotEmpty) {
                                      _selectedSavingAccount = savingsAccounts[0].name;
                                    }
                                  });
                                },
                              ),
                            ],
                          ),
                          if (_autoSave) ...[
                            const SizedBox(height: 10),
                            const Text(
                              'Выберите копилку',
                              style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 4),
                            Container(
                              padding: const EdgeInsets.symmetric(horizontal: 12),
                              decoration: BoxDecoration(
                                color: AppTheme.surfaceCard,
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: DropdownButtonHideUnderline(
                                child: DropdownButton<String>(
                                  value: _selectedSavingAccount,
                                  dropdownColor: AppTheme.background,
                                  style: const TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                                  isExpanded: true,
                                  items: savingsAccounts.map((a) {
                                    return DropdownMenuItem<String>(
                                      value: a.name,
                                      child: Text('${a.name} (${cu.formatCurrency(a.balance, a.currency)})'),
                                    );
                                  }).toList(),
                                  onChanged: (val) {
                                    setState(() {
                                      _selectedSavingAccount = val;
                                    });
                                  },
                                ),
                              ),
                            ),
                            const SizedBox(height: 12),
                            const Text(
                              'Процент сбережений',
                              style: TextStyle(color: AppTheme.textSecondary, fontSize: 11, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 6),
                            Row(
                              children: [10, 20, 30, 50].map((percent) {
                                final isSelected = _autoSavePercent == percent;
                                final amountInt = int.tryParse(_amountStr) ?? 0;
                                final calcAmount = (amountInt * percent / 100).round();
                                return Expanded(
                                  child: GestureDetector(
                                    onTap: () => setState(() => _autoSavePercent = percent),
                                    child: Container(
                                      margin: const EdgeInsets.symmetric(horizontal: 4),
                                      padding: const EdgeInsets.symmetric(vertical: 8),
                                      decoration: BoxDecoration(
                                        color: isSelected ? AppTheme.primary : AppTheme.surfaceCard,
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: isSelected ? Colors.white24 : Colors.transparent,
                                        ),
                                      ),
                                      child: Column(
                                        children: [
                                          Text(
                                            '$percent%',
                                            style: TextStyle(
                                              color: isSelected ? Colors.white : AppTheme.textPrimary,
                                              fontWeight: FontWeight.bold,
                                              fontSize: 12,
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            cu.formatCurrency(calcAmount, _selectedAccountCurrency(appState)),
                                            style: TextStyle(
                                              color: isSelected ? Colors.white70 : AppTheme.textSecondary,
                                              fontSize: 9,
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                );
                              }).toList(),
                            ),
                          ],
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],
                ],
              ),
            ),
          ),
          const SizedBox(height: 8),

          // Custom Numeric Keypad & Save Button in fixed space
          SizedBox(
            height: isKeyboardVisible ? 60 : 260,
            child: Column(
              children: [
                if (!isKeyboardVisible) ...[
                  _buildKeyboardRow(['1', '2', '3']),
                  _buildKeyboardRow(['4', '5', '6']),
                  _buildKeyboardRow(['7', '8', '9']),
                  _buildKeyboardRow(['C', '0', '⌫']),
                  const SizedBox(height: 12),
                ],

                // Save Button
                SizedBox(
                  width: double.infinity,
                  height: 52,
                  child: ElevatedButton(
                    onPressed: _saveTransaction,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.transparent,
                      shadowColor: Colors.transparent,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: Ink(
                      decoration: BoxDecoration(
                        gradient: AppTheme.primaryGradient,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Container(
                        alignment: Alignment.center,
                        child: const Text(
                          'Сохранить операцию',
                          style: TextStyle(color: Colors.white, fontSize: 15, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildTypeButton({
    required String title,
    required bool active,
    required Color activeColor,
    required VoidCallback onTap,
    bool locked = false,
  }) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: active ? activeColor.withOpacity(0.15) : AppTheme.surfaceCard,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: active ? activeColor : Colors.transparent,
            width: 1.5,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (locked) ...[
              const Icon(Icons.lock_rounded, color: AppTheme.textSecondary, size: 13),
              const SizedBox(width: 4),
            ],
            Flexible(
              child: Text(
                title,
                style: TextStyle(
                  color: active ? activeColor : AppTheme.textSecondary,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.0,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildKeyboardRow(List<String> keys) {
    return Expanded(
      child: Row(
        children: keys.map((key) {
          final isAction = key == 'C' || key == '⌫';
          return Expanded(
            child: Container(
              margin: const EdgeInsets.all(4),
              child: ElevatedButton(
                onPressed: () => _onKeyPress(key),
                style: ElevatedButton.styleFrom(
                  backgroundColor: isAction ? Colors.white.withOpacity(0.02) : AppTheme.surfaceCard,
                  foregroundColor: isAction ? AppTheme.secondary : AppTheme.textPrimary,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                  elevation: 0,
                ),
                child: Text(
                  key,
                  style: TextStyle(
                    fontSize: isAction ? 18 : 22,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  void _showEditTransferRateDialog(BuildContext context, String fromCurrency, String toCurrency, double currentRate) {
    final invertForDisplay = currentRate < 1;
    final displayFromCurrency = invertForDisplay ? toCurrency : fromCurrency;
    final displayToCurrency = invertForDisplay ? fromCurrency : toCurrency;
    final displayRate = invertForDisplay ? 1 / currentRate : currentRate;
    final displayRateText = displayRate.toStringAsFixed(2).replaceFirst(RegExp(r'\.?0+$'), '');
    final controller = TextEditingController(text: displayRateText);
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
          title: const Text(
            'Курс обмена',
            style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Укажите сколько $displayToCurrency стоит 1 $displayFromCurrency:',
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: controller,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                style: const TextStyle(color: Colors.white),
                decoration: InputDecoration(
                  suffixText: displayToCurrency,
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
              onPressed: () {
                final double? enteredRate = double.tryParse(controller.text.replaceAll(',', '.'));
                if (enteredRate != null && enteredRate > 0) {
                  setState(() {
                    _customTransferRate = invertForDisplay ? 1 / enteredRate : enteredRate;
                    _isCustomRateActive = true;
                  });
                  Navigator.pop(context);
                }
              },
              child: const Text('Установить', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }
}
