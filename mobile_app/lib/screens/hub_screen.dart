import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'accounts_screen.dart';
import 'debts_screen.dart';
import 'recurring_screen.dart';

class HubScreen extends StatelessWidget {
  const HubScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);

    // List of tools with their icons, colors, labels, and targets
    final List<Map<String, dynamic>> tools = [
      {
        'title': 'Счета',
        'subtitle': '${appState.accounts.length} активных счетов',
        'icon': Icons.credit_card_rounded,
        'color': AppTheme.accentBlue,
        'target': const AccountsScreen(),
      },
      {
        'title': 'Долги и займы',
        'subtitle': 'Отслеживание долгов',
        'icon': Icons.handshake_rounded,
        'color': AppTheme.secondary,
        'target': const DebtsScreen(),
      },
      {
        'title': 'Регулярные',
        'subtitle': 'Шаблоны автоплатежей',
        'icon': Icons.loop_rounded,
        'color': AppTheme.primary,
        'target': const RecurringScreen(),
      },
      {
        'title': 'Бюджеты',
        'subtitle': 'Лимиты категорий',
        'icon': Icons.pie_chart_rounded,
        'color': AppTheme.income,
        'target': null, // Managed inline
      },
      {
        'title': 'Экспорт',
        'subtitle': 'Скачать отчет Excel',
        'icon': Icons.file_download_rounded,
        'color': Colors.orangeAccent,
        'target': null,
      },
      {
        'title': 'Настройки',
        'subtitle': 'Язык, валюта, тишина',
        'icon': Icons.settings_rounded,
        'color': AppTheme.textSecondary,
        'target': null,
      },
    ];

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20.0, vertical: 16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Premium Profile Badge
              Container(
                decoration: AppTheme.glassCardDecoration(
                  color: AppTheme.surfaceCard.withOpacity(0.7),
                  radius: 16,
                ),
                padding: const EdgeInsets.all(18),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: const BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: AppTheme.primaryGradient,
                      ),
                      child: const Icon(Icons.star_rounded, color: Colors.white, size: 24),
                    ),
                    const SizedBox(width: 14),
                    const Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'FinTrack Premium',
                            style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppTheme.textPrimary),
                          ),
                          SizedBox(height: 2),
                          Text(
                            'Подписка активна до 30 июня',
                            style: TextStyle(color: AppTheme.income, fontSize: 11, fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 24),

              const Text(
                'Инструменты и отчёты',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.textPrimary),
              ),
              const SizedBox(height: 14),

              // Grid layout of tools
              Expanded(
                child: GridView.builder(
                  physics: const BouncingScrollPhysics(),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                    childAspectRatio: 1.35,
                  ),
                  itemCount: tools.length,
                  itemBuilder: (context, index) {
                    final item = tools[index];
                    return GestureDetector(
                      onTap: () {
                        if (item['target'] != null) {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (context) => item['target'] as Widget),
                          );
                        } else {
                          ScaffoldMessenger.of(context).showSnackBar(
                            SnackBar(
                              content: Text('Раздел "${item['title']}" будет подключен в следующем релизе!'),
                              duration: const Duration(seconds: 1),
                            ),
                          );
                        }
                      },
                      child: Container(
                        decoration: AppTheme.glassCardDecoration(radius: 14, borderOpacity: 0.05),
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Icon(
                                  item['icon'] as IconData,
                                  color: item['color'] as Color,
                                  size: 26,
                                ),
                                Icon(
                                  Icons.chevron_right_rounded,
                                  color: AppTheme.textSecondary.withOpacity(0.5),
                                  size: 16,
                                ),
                              ],
                            ),
                            const Spacer(),
                            Text(
                              item['title'] as String,
                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: AppTheme.textPrimary),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              item['subtitle'] as String,
                              style: const TextStyle(color: AppTheme.textSecondary, fontSize: 10),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
