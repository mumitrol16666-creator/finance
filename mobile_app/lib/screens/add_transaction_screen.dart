import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';

class AddTransactionScreen extends StatefulWidget {
  const AddTransactionScreen({super.key});

  @override
  State<AddTransactionScreen> createState() => _AddTransactionScreenState();
}

class _AddTransactionScreenState extends State<AddTransactionScreen> {
  String _amountStr = '0';
  String _kind = 'expense'; // 'expense' or 'income'
  String? _selectedCategory;
  String? _selectedAccount;
  final TextEditingController _noteController = TextEditingController();

  // Auto-save logic fields
  bool _autoSave = false;
  String? _selectedSavingAccount;
  int _autoSavePercent = 10; // Default 10%

  @override
  void initState() {
    super.initState();
    _noteController.addListener(_onNoteChanged);
  }

  void _onNoteChanged() {
    setState(() {});
  }

  @override
  void dispose() {
    _noteController.removeListener(_onNoteChanged);
    _noteController.dispose();
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

  Future<void> _saveTransaction() async {
    final amountInt = int.tryParse(_amountStr) ?? 0;
    if (amountInt <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Введите сумму операции')),
      );
      return;
    }

    if (_selectedCategory == null) {
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
    final category = appState.categories.firstWhere((c) => c.name == _selectedCategory);

    // Save transaction in app state
    await appState.addTransaction(
      amount: amountInt, // raw whole units
      kind: _kind,
      categoryName: category.name,
      categoryEmoji: category.emoji,
      accountName: _selectedAccount!,
      note: _noteController.text.trim().isNotEmpty ? _noteController.text.trim() : null,
    );

    // Auto-save part to savings if checked
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

    // Reset state & show success
    setState(() {
      _amountStr = '0';
      _noteController.clear();
      _autoSave = false;
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

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final accounts = appState.accounts;
    final categories = appState.categories;
    final bool isKeyboardVisible = MediaQuery.of(context).viewInsets.bottom > 0;

    // Filter to exclude savings accounts from regular dropdown/selector
    final regularAccounts = accounts.where((a) => !a.isSaving).toList();
    final savingsAccounts = accounts.where((a) => a.isSaving).toList();

    // Set defaults if not selected yet
    if (_selectedAccount == null || !regularAccounts.any((a) => a.name == _selectedAccount)) {
      _selectedAccount = regularAccounts.isNotEmpty ? regularAccounts[0].name : null;
    }
    _selectedCategory ??= categories.isNotEmpty ? categories[0].name : null;

    final isExpense = _kind == 'expense';

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Scrollable fields to prevent keyboard overlap/overflow
          Expanded(
            child: SingleChildScrollView(
              physics: const BouncingScrollPhysics(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // Segmented Tab Control (Expense / Income)
                  Row(
                    children: [
                      Expanded(
                        child: _buildTypeButton(
                          title: 'РАСХОД',
                          active: isExpense,
                          activeColor: AppTheme.expense,
                          onTap: () => setState(() => _kind = 'expense'),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: _buildTypeButton(
                          title: 'ДОХОД',
                          active: !isExpense,
                          activeColor: AppTheme.income,
                          onTap: () => setState(() => _kind = 'income'),
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
                        Text(
                          '$_amountStr ₸',
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.bold,
                            color: isExpense ? AppTheme.expense : AppTheme.income,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 16),

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
                          final name = regularAccounts[index].name;
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
                                name,
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
                  const Text(
                    'Категория',
                    style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: AppTheme.textSecondary),
                  ),
                  const SizedBox(height: 6),
                  SizedBox(
                    height: 40,
                    child: ListView.builder(
                      scrollDirection: Axis.horizontal,
                      physics: const BouncingScrollPhysics(),
                      itemCount: categories.length,
                      itemBuilder: (context, index) {
                        final cat = categories[index];
                        final isSelected = _selectedCategory == cat.name;
                        return GestureDetector(
                          onTap: () => setState(() => _selectedCategory = cat.name),
                          child: Container(
                            margin: const EdgeInsets.only(right: 8),
                            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                            decoration: BoxDecoration(
                              color: isSelected ? AppTheme.primary : AppTheme.surfaceCard,
                              borderRadius: BorderRadius.circular(20),
                              border: Border.all(
                                color: isSelected ? Colors.white24 : Colors.transparent,
                              ),
                            ),
                            child: Row(
                              children: [
                                Text(cat.emoji),
                                const SizedBox(width: 6),
                                Text(
                                  cat.name,
                                  style: TextStyle(
                                    color: isSelected ? Colors.white : AppTheme.textSecondary,
                                    fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                  ),
                                ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
                  const SizedBox(height: 16),

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
                      style: const TextStyle(color: AppTheme.textPrimary),
                      decoration: InputDecoration(
                        hintText: 'Опишите операцию (например: продукты в Магните, подарок маме)',
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

                  // Auto-save settings shown only for income operations if savings accounts exist
                  if (!isExpense && savingsAccounts.isNotEmpty) ...[
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
                                      child: Text('${a.name} (${a.balance} ₸)'),
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
                                            '$calcAmount ₸',
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
        child: Center(
          child: Text(
            title,
            style: TextStyle(
              color: active ? activeColor : AppTheme.textSecondary,
              fontWeight: FontWeight.bold,
              letterSpacing: 1.0,
            ),
          ),
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
}
