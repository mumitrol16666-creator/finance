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

  @override
  void dispose() {
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

    // Reset state & show success
    setState(() {
      _amountStr = '0';
      _noteController.clear();
    });

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('✅ Операция успешно сохранена!'),
        backgroundColor: AppTheme.income,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final accounts = appState.accounts;
    final categories = appState.categories;

    // Set defaults if not selected yet
    _selectedAccount ??= accounts.isNotEmpty ? accounts[0].name : null;
    _selectedCategory ??= categories.isNotEmpty ? categories[0].name : null;

    final isExpense = _kind == 'expense';

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 12.0),
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

          // Horizontal scroll of accounts
          const Text(
            'Счёт списания / зачисления',
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
                final name = accounts[index].name;
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
          TextField(
            controller: _noteController,
            style: const TextStyle(color: AppTheme.textPrimary),
            decoration: InputDecoration(
              hintText: 'Комментарий к операции (например, Обед)',
              hintStyle: const TextStyle(color: Colors.white24, fontSize: 13),
              filled: true,
              fillColor: AppTheme.surfaceCard,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12),
                borderSide: BorderSide.none,
              ),
              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
            ),
          ),
          const SizedBox(height: 16),

          // Custom Numeric Keypad & Save Button in remaining space
          Expanded(
            child: Column(
              children: [
                _buildKeyboardRow(['1', '2', '3']),
                _buildKeyboardRow(['4', '5', '6']),
                _buildKeyboardRow(['7', '8', '9']),
                _buildKeyboardRow(['C', '0', '⌫']),
                const SizedBox(height: 12),
                
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
