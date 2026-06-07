import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import 'package:flutter_animate/flutter_animate.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';
import '../utils/currency_utils.dart' as cu;

class AllTransactionsScreen extends StatelessWidget {
  const AllTransactionsScreen({super.key});

  String _formatCurrency(int amount, String currency) => cu.formatCurrency(amount, currency);

  void _showEditTransactionDialog(BuildContext context, AppState appState, Transaction tx) {
    final amountController = TextEditingController(text: tx.amount.toString());
    final noteController = TextEditingController(text: tx.note ?? '');

    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
            side: const BorderSide(color: AppTheme.border),
          ),
          title: Text(
            tx.kind == 'expense' ? 'Редактировать расход' : 'Редактировать доход',
            style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Text(tx.categoryEmoji, style: const TextStyle(fontSize: 20)),
                  const SizedBox(width: 8),
                  Text(
                    tx.categoryName,
                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  const Spacer(),
                  Text(
                    tx.accountName,
                    style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              TextField(
                controller: amountController,
                keyboardType: TextInputType.number,
                style: const TextStyle(color: AppTheme.textPrimary),
                decoration: InputDecoration(
                  labelText: 'Сумма',
                  labelStyle: const TextStyle(color: AppTheme.textSecondary),
                  suffixText: cu.currencySymbol(tx.currency),
                  enabledBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                  focusedBorder: const UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                ),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: noteController,
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
          actions: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                TextButton.icon(
                  onPressed: () async {
                    final confirm = await showDialog<bool>(
                      context: context,
                      builder: (context) => AlertDialog(
                        backgroundColor: AppTheme.surface,
                        title: const Text('Удаление', style: TextStyle(color: Colors.white)),
                        content: const Text('Удалить эту операцию?', style: TextStyle(color: AppTheme.textPrimary)),
                        actions: [
                          TextButton(
                            onPressed: () => Navigator.pop(context, false),
                            child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                          ),
                          TextButton(
                            onPressed: () => Navigator.pop(context, true),
                            child: const Text('Удалить', style: TextStyle(color: AppTheme.expense)),
                          ),
                        ],
                      ),
                    );
                    if (confirm == true) {
                      Navigator.pop(context);
                      await appState.deleteTransaction(tx.id);
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text('✅ Операция успешно удалена!'),
                          backgroundColor: AppTheme.income,
                        ),
                      );
                    }
                  },
                  icon: const Icon(Icons.delete_outline, color: AppTheme.expense),
                  label: const Text('Удалить', style: TextStyle(color: AppTheme.expense)),
                ),
                Row(
                  children: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
                    ),
                    TextButton(
                      onPressed: () async {
                        final amt = int.tryParse(amountController.text) ?? 0;
                        if (amt <= 0) return;
                        Navigator.pop(context);
                        await appState.updateTransaction(
                          tx_id: tx.id,
                          amount: amt,
                          note: noteController.text.trim().isNotEmpty ? noteController.text.trim() : '',
                        );
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text('✅ Изменения сохранены!'),
                            backgroundColor: AppTheme.income,
                          ),
                        );
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
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final transactions = appState.transactions;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Все операции', style: TextStyle(fontWeight: FontWeight.bold)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: AppTheme.textPrimary, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SafeArea(
        child: ListView.builder(
          physics: const BouncingScrollPhysics(),
          padding: const EdgeInsets.all(20),
          itemCount: transactions.length,
          itemBuilder: (context, index) {
            final tx = transactions[index];
            final isExpense = tx.kind == 'expense';

            return GestureDetector(
              onTap: () => _showEditTransactionDialog(context, appState, tx),
              child: Container(
                margin: const EdgeInsets.only(bottom: 12),
                child: GlassCard(
                  radius: 14,
                  padding: const EdgeInsets.all(14),
                  child: Row(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.03),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Text(tx.categoryEmoji, style: const TextStyle(fontSize: 20)),
                      ),
                      const SizedBox(width: 14),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              tx.note ?? tx.categoryName,
                              style: const TextStyle(fontWeight: FontWeight.w600, color: AppTheme.textPrimary),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            const SizedBox(height: 4),
                            Text(
                              tx.accountName,
                              style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11),
                            ),
                          ],
                        ),
                      ),
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.end,
                        children: [
                          Text(
                            '${isExpense ? '-' : '+'}${_formatCurrency(tx.amount, tx.currency)}',
                            style: TextStyle(
                              color: isExpense ? AppTheme.expense : AppTheme.income,
                              fontWeight: FontWeight.bold,
                              fontSize: 15,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Text(
                            DateFormat('dd.MM, HH:mm').format(tx.timestamp),
                            style: const TextStyle(color: Colors.white24, fontSize: 10),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),
            ).animate().fade(delay: Duration(milliseconds: index * 50)).slideY(begin: 0.1);
          },
        ),
      ),
    );
  }
}
