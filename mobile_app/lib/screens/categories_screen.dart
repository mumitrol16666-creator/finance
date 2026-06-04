import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import '../models/models.dart';

class CategoriesScreen extends StatelessWidget {
  const CategoriesScreen({super.key});

  void _showAddCategoryDialog(BuildContext context, AppState appState, {required String initialKind}) {
    final nameController = TextEditingController();
    final emojiController = TextEditingController();
    String kind = initialKind;

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

  void _showEditCategoryDialog(BuildContext context, AppState appState, Category category) {
    final nameController = TextEditingController(text: category.name);
    final emojiController = TextEditingController(text: category.emoji);
    final limitController = TextEditingController(
      text: category.limitAmount != null && category.limitAmount! > 0
          ? category.limitAmount.toString()
          : '',
    );

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
            category.kind == 'expense' ? 'Настройка расхода' : 'Настройка дохода',
            style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: emojiController,
                  maxLength: 2,
                  style: const TextStyle(color: AppTheme.textPrimary, fontSize: 24),
                  decoration: const InputDecoration(
                    labelText: 'Эмодзи',
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
                    labelText: 'Название категории',
                    labelStyle: TextStyle(color: AppTheme.textSecondary),
                    enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                    focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                  ),
                ),
                if (category.kind == 'expense') ...[
                  const SizedBox(height: 12),
                  TextField(
                    controller: limitController,
                    keyboardType: TextInputType.number,
                    style: const TextStyle(color: AppTheme.textPrimary),
                    decoration: const InputDecoration(
                      labelText: 'Лимит на период (₸)',
                      hintText: 'Без лимита',
                      hintStyle: TextStyle(color: Colors.white24),
                      labelStyle: TextStyle(color: AppTheme.textSecondary),
                      enabledBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.border)),
                      focusedBorder: UnderlineInputBorder(borderSide: BorderSide(color: AppTheme.primary)),
                    ),
                  ),
                ],
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
                final name = nameController.text.trim();
                final emoji = emojiController.text.trim().isEmpty ? '📦' : emojiController.text.trim();
                final limit = limitController.text.trim().isEmpty
                    ? 0
                    : (int.tryParse(limitController.text.trim()) ?? 0);
                if (name.isEmpty) return;

                try {
                  Navigator.pop(context);
                  await appState.updateCategory(
                    category.id,
                    name: name,
                    emoji: emoji,
                    limitAmount: category.kind == 'expense' ? limit : null,
                  );
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('✅ Изменения сохранены!'),
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
        );
      },
    );
  }

  Widget _buildCategoryList(
      BuildContext context, AppState appState, List<Category> list) {
    if (list.isEmpty) {
      return const Center(
        child: Text(
          'Нет категорий в этом разделе',
          style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
        ),
      );
    }

    return ListView.builder(
      physics: const BouncingScrollPhysics(),
      itemCount: list.length,
      itemBuilder: (context, index) {
        final cat = list[index];
        final limitTxt = (cat.kind == 'expense' && cat.limitAmount != null && cat.limitAmount! > 0)
            ? 'Лимит: ${cat.limitAmount} ₸ • Потрачено: ${cat.spentAmount} ₸'
            : (cat.kind == 'expense' ? 'Без установленного лимита' : 'Получено: ${cat.spentAmount} ₸');
        
        return GestureDetector(
          onTap: () => _showEditCategoryDialog(context, appState, cat),
          child: Container(
            margin: const EdgeInsets.only(bottom: 14),
            decoration: AppTheme.glassCardDecoration(radius: 16),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: Row(
              children: [
                Text(cat.emoji, style: const TextStyle(fontSize: 24)),
                const SizedBox(width: 16),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        cat.name,
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppTheme.textPrimary),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        limitTxt,
                        style: const TextStyle(fontSize: 11, color: AppTheme.textSecondary),
                      ),
                    ],
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
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final categories = appState.categories;
    final expenses = categories.where((c) => c.kind == 'expense').toList();
    final incomes = categories.where((c) => c.kind == 'income').toList();

    return DefaultTabController(
      length: 2,
      child: Scaffold(
        backgroundColor: AppTheme.background,
        appBar: AppBar(
          backgroundColor: Colors.transparent,
          elevation: 0,
          title: const Text('Управление категориями', style: TextStyle(fontWeight: FontWeight.bold)),
          leading: IconButton(
            icon: const Icon(Icons.arrow_back_ios_new_rounded, color: AppTheme.textPrimary, size: 20),
            onPressed: () => Navigator.pop(context),
          ),
          bottom: const TabBar(
            indicatorColor: AppTheme.primary,
            labelColor: Colors.white,
            unselectedLabelColor: Colors.white38,
            indicatorSize: TabBarIndicatorSize.tab,
            tabs: [
              Tab(text: 'Расходы'),
              Tab(text: 'Доходы'),
            ],
          ),
        ),
        body: SafeArea(
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  'Нажмите на любую категорию для ее настройки и установки лимитов бюджета',
                  style: TextStyle(color: AppTheme.textSecondary, fontSize: 12.5),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 16),
                Expanded(
                  child: TabBarView(
                    children: [
                      _buildCategoryList(context, appState, expenses),
                      _buildCategoryList(context, appState, incomes),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
                Builder(
                  builder: (context) {
                    return ElevatedButton(
                      onPressed: () {
                        final tabIndex = DefaultTabController.of(context).index;
                        final currentKind = tabIndex == 0 ? 'expense' : 'income';
                        _showAddCategoryDialog(context, appState, initialKind: currentKind);
                      },
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
                    );
                  }
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
