import 'package:flutter/material.dart';
import '../core/theme.dart';

class SettingsScreen extends StatefulWidget {
  const SettingsScreen({super.key});

  @override
  State<SettingsScreen> createState() => _SettingsScreenState();
}

class _SettingsScreenState extends State<SettingsScreen> {
  String _language = 'Русский';
  String _currency = 'KZT (₸)';
  bool _quietHours = true;
  bool _notifications = true;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppTheme.background,
      appBar: AppBar(
        backgroundColor: Colors.transparent,
        elevation: 0,
        title: const Text('Настройки', style: TextStyle(fontWeight: FontWeight.bold)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new_rounded, color: AppTheme.textPrimary, size: 20),
          onPressed: () => Navigator.pop(context),
        ),
      ),
      body: SafeArea(
        child: SingleChildScrollView(
          physics: const BouncingScrollPhysics(),
          child: Padding(
            padding: const EdgeInsets.all(20.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // 1. Core Profile Header
                _buildSectionHeader('АККАУНТ И ЛОКАЛИЗАЦИЯ'),
                const SizedBox(height: 10),
                
                Container(
                  decoration: AppTheme.glassCardDecoration(radius: 16),
                  padding: const EdgeInsets.all(8),
                  child: Column(
                    children: [
                      // Language
                      _buildDropdownTile(
                        icon: Icons.language_rounded,
                        title: 'Язык интерфейса',
                        value: _language,
                        items: ['Русский', 'English', 'Қазақша'],
                        onChanged: (val) {
                          if (val != null) setState(() => _language = val);
                        },
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                      // Currency
                      _buildDropdownTile(
                        icon: Icons.monetization_on_rounded,
                        title: 'Основная валюта',
                        value: _currency,
                        items: ['KZT (₸)', 'RUB (₽)', 'USD (\$)', 'EUR (€)'],
                        onChanged: (val) {
                          if (val != null) setState(() => _currency = val);
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // 2. Alert & Reports Preferences
                _buildSectionHeader('ОТЧЁТЫ И УВЕДОМЛЕНИЯ'),
                const SizedBox(height: 10),

                Container(
                  decoration: AppTheme.glassCardDecoration(radius: 16),
                  padding: const EdgeInsets.all(8),
                  child: Column(
                    children: [
                      // Notification toggling
                      _buildSwitchTile(
                        icon: Icons.notifications_rounded,
                        title: 'Пуш-уведомления',
                        value: _notifications,
                        onChanged: (val) => setState(() => _notifications = val),
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                      // Quiet Hours
                      _buildSwitchTile(
                        icon: Icons.do_not_disturb_on_rounded,
                        title: 'Режим тишины (22:00 - 08:00)',
                        value: _quietHours,
                        onChanged: (val) => setState(() => _quietHours = val),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // 3. Category Directories
                _buildSectionHeader('КАТЕГОРИИ'),
                const SizedBox(height: 10),

                GestureDetector(
                  onTap: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Управление списком категорий будет доступно в следующем релизе!')),
                    );
                  },
                  child: Container(
                    decoration: AppTheme.glassCardDecoration(radius: 16),
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
                    child: Row(
                      children: const [
                        Icon(Icons.category_rounded, color: AppTheme.primary),
                        SizedBox(width: 14),
                        Expanded(
                          child: Text(
                            'Настроить категории трат',
                            style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
                          ),
                        ),
                        Icon(Icons.chevron_right_rounded, color: AppTheme.textSecondary),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 36),

                // 4. Wipe account data
                ElevatedButton.icon(
                  onPressed: () {
                    _showDeleteWarningDialog(context);
                  },
                  icon: const Icon(Icons.delete_forever_rounded, color: Colors.white),
                  label: const Text('Сбросить все данные', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    backgroundColor: AppTheme.expense,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                    elevation: 0,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSectionHeader(String title) {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0),
      child: Text(
        title,
        style: const TextStyle(
          color: AppTheme.textSecondary,
          fontSize: 11,
          fontWeight: FontWeight.w600,
          letterSpacing: 1.0,
        ),
      ),
    );
  }

  Widget _buildDropdownTile({
    required IconData icon,
    required String title,
    required String value,
    required List<String> items,
    required ValueChanged<String?> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.accentBlue, size: 22),
          const SizedBox(width: 14),
          Expanded(
            child: Text(title, style: const TextStyle(fontSize: 14, color: AppTheme.textPrimary)),
          ),
          DropdownButton<String>(
            value: value,
            underline: const SizedBox(),
            dropdownColor: AppTheme.surfaceCard,
            style: const TextStyle(color: AppTheme.textPrimary, fontWeight: FontWeight.bold),
            items: items.map((item) {
              return DropdownMenuItem<String>(
                value: item,
                child: Text(item),
              );
            }).toList(),
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }

  Widget _buildSwitchTile({
    required IconData icon,
    required String title,
    required bool value,
    required ValueChanged<bool> onChanged,
  }) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      child: Row(
        children: [
          Icon(icon, color: AppTheme.primary, size: 22),
          const SizedBox(width: 14),
          Expanded(
            child: Text(title, style: const TextStyle(fontSize: 14, color: AppTheme.textPrimary)),
          ),
          SizedBox(
            height: 24,
            child: Switch(
              value: value,
              activeColor: AppTheme.primary,
              onChanged: onChanged,
            ),
          ),
        ],
      ),
    );
  }

  void _showDeleteWarningDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Text('Сбросить данные?', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.expense)),
          content: const Text(
            'Это действие полностью удалит все ваши операции, лимиты и счета как в приложении, так и на сервере. Восстановить данные будет невозможно.',
            style: TextStyle(color: AppTheme.textPrimary),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Данные очищены. Вы вышли из аккаунта.'),
                    backgroundColor: AppTheme.expense,
                  ),
                );
              },
              child: const Text('Сбросить', style: TextStyle(color: AppTheme.expense, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }
}
