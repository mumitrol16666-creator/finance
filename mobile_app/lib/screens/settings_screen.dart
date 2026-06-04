import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import 'categories_screen.dart';
import '../providers/app_state.dart';

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
  TimeOfDay _dailyReportTime = const TimeOfDay(hour: 21, minute: 0);
  TimeOfDay _quietHoursStart = const TimeOfDay(hour: 22, minute: 0);
  TimeOfDay _quietHoursEnd = const TimeOfDay(hour: 8, minute: 0);

  String _formatTimeOfDay(TimeOfDay time) {
    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  Future<void> _selectTime(BuildContext context, TimeOfDay initialTime, ValueChanged<TimeOfDay> onSelected) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: initialTime,
      builder: (context, child) {
        return Theme(
          data: Theme.of(context).copyWith(
            colorScheme: const ColorScheme.dark(
              primary: AppTheme.primary,
              onPrimary: Colors.white,
              surface: AppTheme.surface,
              onSurface: Colors.white,
            ),
            timePickerTheme: TimePickerThemeData(
              backgroundColor: AppTheme.surface,
              dialBackgroundColor: AppTheme.surfaceCard,
              dialHandColor: AppTheme.primary,
              entryModeIconColor: AppTheme.primary,
            ),
          ),
          child: child!,
        );
      },
    );
    if (picked != null) {
      onSelected(picked);
    }
  }

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
                      if (_notifications) ...[
                        const Divider(color: AppTheme.border, height: 1),
                        _buildTimeTile(
                          icon: Icons.access_time_rounded,
                          title: 'Время ежедневного отчета',
                          time: _dailyReportTime,
                          onTap: () => _selectTime(
                            context,
                            _dailyReportTime,
                            (time) => setState(() => _dailyReportTime = time),
                          ),
                        ),
                      ],
                      const Divider(color: AppTheme.border, height: 1),
                      // Quiet Hours
                      _buildSwitchTile(
                        icon: Icons.do_not_disturb_on_rounded,
                        title: 'Режим тишины (${_formatTimeOfDay(_quietHoursStart)} - ${_formatTimeOfDay(_quietHoursEnd)})',
                        value: _quietHours,
                        onChanged: (val) => setState(() => _quietHours = val),
                      ),
                      if (_quietHours) ...[
                        const Divider(color: AppTheme.border, height: 1),
                        _buildTimeTile(
                          icon: Icons.play_arrow_rounded,
                          title: 'Начало режима тишины',
                          time: _quietHoursStart,
                          onTap: () => _selectTime(
                            context,
                            _quietHoursStart,
                            (time) => setState(() => _quietHoursStart = time),
                          ),
                        ),
                        const Divider(color: AppTheme.border, height: 1),
                        _buildTimeTile(
                          icon: Icons.stop_rounded,
                          title: 'Конец режима тишины',
                          time: _quietHoursEnd,
                          onTap: () => _selectTime(
                            context,
                            _quietHoursEnd,
                            (time) => setState(() => _quietHoursEnd = time),
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                // 3. Category Directories
                _buildSectionHeader('КАТЕГОРИИ'),
                const SizedBox(height: 10),

                GestureDetector(
                  onTap: () {
                    Navigator.push(
                      context,
                      MaterialPageRoute(builder: (context) => const CategoriesScreen()),
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

  Widget _buildTimeTile({
    required IconData icon,
    required String title,
    required TimeOfDay time,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(12),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
        child: Row(
          children: [
            Icon(icon, color: AppTheme.accentBlue, size: 22),
            const SizedBox(width: 14),
            Expanded(
              child: Text(title, style: const TextStyle(fontSize: 14, color: AppTheme.textPrimary)),
            ),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: AppTheme.primary.withOpacity(0.1),
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: AppTheme.primary.withOpacity(0.3)),
              ),
              child: Text(
                _formatTimeOfDay(time),
                style: const TextStyle(
                  color: AppTheme.primary,
                  fontWeight: FontWeight.bold,
                  fontSize: 14,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _showDeleteWarningDialog(BuildContext context) {
    final appState = Provider.of<AppState>(context, listen: false);
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
              onPressed: () async {
                Navigator.pop(context);
                await appState.wipeUserData();
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
