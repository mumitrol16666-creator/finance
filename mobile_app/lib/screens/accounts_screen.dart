import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';

class AccountsScreen extends StatelessWidget {
  const AccountsScreen({super.key});

  String _formatKzt(int amountMinor) {
    final formatter = NumberFormat.currency(locale: 'kk_KZ', symbol: '₸', decimalDigits: 0);
    return formatter.format(amountMinor);
  }

  void _showAddAccountDialog(BuildContext context, AppState appState) {
    final nameController = TextEditingController();
    final balanceController = TextEditingController();
    bool isSaving = false;

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
              title: const Text('Новый счёт', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
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
                      labelText: 'Стартовый баланс',
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
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                ),
                TextButton(
                  onPressed: () async {
                    final name = nameController.text.trim();
                    final balance = int.tryParse(balanceController.text) ?? 0;
                    if (name.isEmpty) return;

                    try {
                      Navigator.pop(context);
                      await appState.addAccount(
                        name: name,
                        balance: balance,
                        isSaving: isSaving ? 1 : 0,
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
                  },
                  child: const Text('Создать', style: TextStyle(color: AppTheme.primary, fontWeight: FontWeight.bold)),
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
                    return Container(
                      margin: const EdgeInsets.only(bottom: 14),
                      decoration: AppTheme.glassCardDecoration(radius: 16),
                      padding: const EdgeInsets.all(20),
                      child: Row(
                        children: [
                          Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppTheme.accentBlue.withOpacity(0.1),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(Icons.account_balance_wallet_rounded, color: AppTheme.accentBlue, size: 24),
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
                                const Text(
                                  'Активный',
                                  style: TextStyle(color: AppTheme.income, fontSize: 11, fontWeight: FontWeight.w600),
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
