import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
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
  bool _telegramNotifications = true;
  bool _dailyReportEnabled = false;
  TimeOfDay _dailyReportTime = const TimeOfDay(hour: 21, minute: 0);
  TimeOfDay _quietHoursStart = const TimeOfDay(hour: 22, minute: 0);
  TimeOfDay _quietHoursEnd = const TimeOfDay(hour: 8, minute: 0);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final appState = Provider.of<AppState>(context, listen: false);
      setState(() {
        _currency = _mapCodeToDisplay(appState.baseCurrency);
        _notifications = appState.pushNotificationsEnabled;
        _telegramNotifications = appState.telegramNotificationsEnabled;
        _quietHours = appState.quietHoursEnabled;
        _dailyReportEnabled = appState.dailyReportEnabled;
        _language = _mapLanguageCodeToDisplay(appState.language);
        _dailyReportTime = _parseTime(appState.dailyReportTime, const TimeOfDay(hour: 21, minute: 0));
        _quietHoursStart = _parseTime(appState.quietHoursStart, const TimeOfDay(hour: 22, minute: 0));
        _quietHoursEnd = _parseTime(appState.quietHoursEnd, const TimeOfDay(hour: 8, minute: 0));
      });
    });
  }

  String _mapCodeToDisplay(String code) {
    switch (code.toUpperCase()) {
      case 'KZT': return 'KZT (₸)';
      case 'RUB': return 'RUB (₽)';
      case 'USD': return 'USD (\$)';
      case 'EUR': return 'EUR (€)';
      default: return 'KZT (₸)';
    }
  }

  String _mapDisplayToCode(String display) {
    if (display.startsWith('KZT')) return 'KZT';
    if (display.startsWith('RUB')) return 'RUB';
    if (display.startsWith('USD')) return 'USD';
    if (display.startsWith('EUR')) return 'EUR';
    return 'KZT';
  }

  String _mapLanguageCodeToDisplay(String code) {
    if (code == 'en') return 'English';
    if (code == 'kk') return 'Қазақша';
    return 'Русский';
  }

  String _mapLanguageDisplayToCode(String display) {
    if (display == 'English') return 'en';
    if (display == 'Қазақша') return 'kk';
    return 'ru';
  }

  String _formatTimeOfDay(TimeOfDay time) {
    final hour = time.hour.toString().padLeft(2, '0');
    final minute = time.minute.toString().padLeft(2, '0');
    return '$hour:$minute';
  }

  TimeOfDay _parseTime(String value, TimeOfDay fallback) {
    final parts = value.split(':');
    if (parts.length != 2) return fallback;
    final hour = int.tryParse(parts[0]);
    final minute = int.tryParse(parts[1]);
    if (hour == null || minute == null || hour < 0 || hour > 23 || minute < 0 || minute > 59) {
      return fallback;
    }
    return TimeOfDay(hour: hour, minute: minute);
  }

  Future<void> _selectTime(BuildContext context, TimeOfDay initialTime, ValueChanged<TimeOfDay> onSelected) async {
    final picked = await showTimePicker(
      context: context,
      initialTime: initialTime,
      builder: (context, child) {
        return MediaQuery(
          data: MediaQuery.of(context).copyWith(alwaysUse24HourFormat: true),
          child: Theme(
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
          ),
        );
      },
    );
    if (picked != null) {
      onSelected(picked);
    }
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
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
                        onChanged: (val) async {
                          if (val != null) {
                            await appState.updateSettings(language: _mapLanguageDisplayToCode(val));
                            if (mounted) setState(() => _language = val);
                          }
                        },
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                       _buildDropdownTile(
                        icon: Icons.monetization_on_rounded,
                        title: 'Основная валюта',
                        value: _currency,
                        items: ['KZT (₸)', 'RUB (₽)', 'USD (\$)', 'EUR (€)'],
                        onChanged: (val) async {
                          if (val != null) {
                            final code = _mapDisplayToCode(val);
                            try {
                              await appState.updateSettings(currency: code);
                              if (mounted) setState(() => _currency = val);
                            } catch (e) {
                              if (!mounted) return;
                              ScaffoldMessenger.of(context).showSnackBar(
                                SnackBar(content: Text(e.toString().replaceFirst('Exception: ', '')), backgroundColor: AppTheme.expense),
                              );
                            }
                          }
                        },
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                      // Budget cycle start day
                      _buildDropdownTile(
                        icon: Icons.calendar_month_rounded,
                        title: 'День начала периода',
                        value: appState.budgetCycleStartDay.toString(),
                        items: List.generate(28, (i) => (i + 1).toString()),
                        onChanged: (val) async {
                          if (val != null) {
                            final day = int.tryParse(val);
                            if (day != null) {
                              try {
                                await appState.updateSettings(budgetCycleStartDay: day);
                              } catch (e) {
                                if (!mounted) return;
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text(e.toString().replaceFirst('Exception: ', '')), backgroundColor: AppTheme.expense),
                                );
                              }
                            }
                          }
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
                        onChanged: (val) async {
                          await appState.updateSettings(pushNotificationsEnabled: val);
                          if (mounted) setState(() => _notifications = val);
                        },
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                      _buildSwitchTile(
                        icon: Icons.telegram_rounded,
                        title: 'Telegram-уведомления',
                        value: _telegramNotifications,
                        onChanged: (val) async {
                          await appState.updateSettings(telegramNotificationsEnabled: val);
                          if (mounted) setState(() => _telegramNotifications = val);
                        },
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                      _buildSwitchTile(
                        icon: Icons.summarize_rounded,
                        title: 'Ежедневный отчет',
                        value: _dailyReportEnabled,
                        onChanged: (val) async {
                          await appState.updateSettings(dailyReportEnabled: val);
                          if (mounted) setState(() => _dailyReportEnabled = val);
                        },
                      ),
                      if (_dailyReportEnabled) ...[
                        const Divider(color: AppTheme.border, height: 1),
                        _buildTimeTile(
                          icon: Icons.access_time_rounded,
                          title: 'Время ежедневного отчета',
                          time: _dailyReportTime,
                          onTap: () => _selectTime(
                            context,
                            _dailyReportTime,
                            (time) async {
                              await appState.updateSettings(
                                dailyReportEnabled: true,
                                dailyReportTime: _formatTimeOfDay(time),
                              );
                              if (mounted) {
                                setState(() {
                                  _dailyReportEnabled = true;
                                  _dailyReportTime = time;
                                });
                              }
                            },
                          ),
                        ),
                      ],
                      const Divider(color: AppTheme.border, height: 1),
                      // Quiet Hours
                      _buildSwitchTile(
                        icon: Icons.do_not_disturb_on_rounded,
                        title: 'Режим тишины (${_formatTimeOfDay(_quietHoursStart)} - ${_formatTimeOfDay(_quietHoursEnd)})',
                        value: _quietHours,
                        onChanged: (val) async {
                          await appState.updateSettings(quietHoursEnabled: val);
                          if (mounted) setState(() => _quietHours = val);
                        },
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
                            (time) async {
                              await appState.updateSettings(quietHoursStart: _formatTimeOfDay(time));
                              if (mounted) setState(() => _quietHoursStart = time);
                            },
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
                            (time) async {
                              await appState.updateSettings(quietHoursEnd: _formatTimeOfDay(time));
                              if (mounted) setState(() => _quietHoursEnd = time);
                            },
                          ),
                        ),
                      ],
                    ],
                  ),
                ),
                const SizedBox(height: 24),

                const SizedBox(height: 20),

                const SizedBox(height: 24),
                _buildSectionHeader('ОПАСНАЯ ЗОНА'),
                const SizedBox(height: 10),
                Container(
                  decoration: AppTheme.glassCardDecoration(radius: 16),
                  padding: const EdgeInsets.all(8),
                  child: Column(
                    children: [
                      // Reset data tile
                      ListTile(
                        leading: const Icon(Icons.delete_sweep_rounded, color: Colors.orangeAccent, size: 24),
                        title: const Text('Сбросить данные', style: TextStyle(fontSize: 14, color: AppTheme.textPrimary, fontWeight: FontWeight.bold)),
                        subtitle: const Text('Стереть всю финансовую историю', style: TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
                        trailing: const Icon(Icons.chevron_right_rounded, color: AppTheme.textSecondary),
                        onTap: () => _showResetWarningDialog(context),
                      ),
                      const Divider(color: AppTheme.border, height: 1),
                      // Delete account tile
                      ListTile(
                        leading: const Icon(Icons.delete_forever_rounded, color: AppTheme.expense, size: 24),
                        title: const Text('Удалить аккаунт', style: TextStyle(fontSize: 14, color: AppTheme.expense, fontWeight: FontWeight.bold)),
                        subtitle: const Text('Полностью удалить профиль и Premium', style: TextStyle(fontSize: 11, color: AppTheme.textSecondary)),
                        trailing: const Icon(Icons.chevron_right_rounded, color: AppTheme.textSecondary),
                        onTap: () => _showDeleteAccountWarningDialog(context),
                      ),
                    ],
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

  void _showResetWarningDialog(BuildContext context) {
    final appState = Provider.of<AppState>(context, listen: false);
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: Colors.orangeAccent, size: 28),
              SizedBox(width: 10),
              Text('Сбросить данные?', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary)),
            ],
          ),
          content: const Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Это действие полностью удалит все ваши операции, лимиты, счета и долги.',
                style: TextStyle(color: AppTheme.textPrimary),
              ),
              SizedBox(height: 12),
              Text(
                '🌟 Ваша Premium-подписка останется активной!',
                style: TextStyle(color: AppTheme.income, fontWeight: FontWeight.bold, fontSize: 13),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(context);
                await appState.wipeUserData();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Все финансовые данные сброшены.'),
                    backgroundColor: Colors.orangeAccent,
                  ),
                );
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.orangeAccent,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text('Сбросить', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }

  void _showDeleteAccountWarningDialog(BuildContext context) {
    final appState = Provider.of<AppState>(context, listen: false);
    showDialog(
      context: context,
      builder: (context) {
        return AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Row(
            children: [
              Icon(Icons.gpp_bad_rounded, color: AppTheme.expense, size: 28),
              SizedBox(width: 10),
              Text('Удалить аккаунт?', style: TextStyle(fontWeight: FontWeight.bold, color: AppTheme.textPrimary)),
            ],
          ),
          content: const Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Вы собираетесь безвозвратно удалить свой профиль и все данные из FinTrack.',
                style: TextStyle(color: AppTheme.textPrimary),
              ),
              SizedBox(height: 12),
              Text(
                '⚠️ Внимание: Ваша Premium-подписка будет аннулирована навсегда без возможности восстановления или возврата!',
                style: TextStyle(color: AppTheme.expense, fontWeight: FontWeight.bold, fontSize: 13),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Отмена', style: TextStyle(color: AppTheme.textSecondary)),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(context);
                await appState.deleteUserAccount();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Аккаунт и все данные успешно удалены.'),
                    backgroundColor: AppTheme.expense,
                  ),
                );
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTheme.expense,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
              child: const Text('Удалить', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );
  }
}
