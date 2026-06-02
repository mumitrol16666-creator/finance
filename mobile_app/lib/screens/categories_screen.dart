import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';

class CategoriesScreen extends StatelessWidget {
  const CategoriesScreen({super.key});

  void _showAddCategoryDialog(BuildContext context, AppState appState) {
    final nameController = TextEditingController();
    final emojiController = TextEditingController();
    String kind = 'expense';

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
              title: const Text('Новая категория', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  DropdownButtonFormField<String>(
                    value: kind,
                    dropdownColor: AppTheme.surface,
                    style: const TextStyle(color: AppTheme.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Тип категории',
                      labelStyle: TextStyle(color: AppTheme.textSecondary),
                    ),
                    items: const [
                      DropdownMenuItem(value: 'expense', child: Text('Расход')),
                      DropdownMenuItem(value: 'income', child: Text('Доход')),
                    ],
                    onChanged: (val) {
                      if (val != null) setState(() => kind = val);
                    },
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: emojiController,
                    maxLength: 2,
                    style: const TextStyle(color: AppTheme.textPrimary, fontSize: 24),
                    decoration: const InputDecoration(
                      labelText: 'Эмодзи',
                      hintText: '📦',
                      counterText: '',
                      labelStyle: TextStyle(color: AppTheme.textSecondary),
                      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                    ),
                  ),
                  const SizedBox(height: 12),
                  TextField(
                    controller: nameController,
                    style: const TextStyle(color: AppTheme.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Название',
                      labelStyle: TextStyle(color: AppTheme.textSecondary),
                      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                    ),
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
                    final emoji = emojiController.text.trim().isEmpty ? '📦' : emojiController.text.trim();
                    if (name.isEmpty) return;

                    try {
                      Navigator.pop(context);
                      await appState.addCategory(name: name, emoji: emoji, kind: kind);
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text('✅ Категория "$name" успешно создана!'),
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
    final categories = appState.categories;

    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Управление категориями', style: TextStyle(fontWeight: FontWeight.bold)),
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
                'Ваши персональные категории для транзакций',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
              const SizedBox(height: 16),
              Expanded(
                child: ListView.builder(
                  physics: const BouncingScrollPhysics(),
                  itemCount: categories.length,
                  itemBuilder: (context, index) {
                    final cat = categories[index];
                    return Container(
                      margin: const EdgeInsets.only(bottom: 14),
                      decoration: AppTheme.glassCardDecoration(radius: 16),
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: Row(
                        children: [
                          Text(cat.emoji, style: const TextStyle(fontSize: 24)),
                          const SizedBox(width: 16),
                          Expanded(
                            child: Text(
                              cat.name,
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppTheme.textPrimary),
                            ),
                          ),
                          IconButton(
                            icon: const Icon(Icons.delete_outline, color: AppTheme.expense),
                            onPressed: () async {
                              final confirm = await showDialog<bool>(
                                context: context,
                                builder: (context) => AlertDialog(
                                  backgroundColor: AppTheme.surface,
                                  title: const Text('Удаление', style: TextStyle(color: Colors.white)),
                                  content: Text('Удалить категорию "${cat.name}"?', style: const TextStyle(color: AppTheme.textPrimary)),
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
                                await appState.deleteCategory(cat.id);
                              }
                            },
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
              ElevatedButton(
                onPressed: () => _showAddCategoryDialog(context, appState),
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
                  'Создать категорию',
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
