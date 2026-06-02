import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'accounts_screen.dart';
import 'debts_screen.dart';
import 'recurring_screen.dart';
import 'budgets_screen.dart';
import 'settings_screen.dart';
import 'planned_screen.dart';

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
        'feature': 'debts',
      },
      {
        'title': 'Регулярные',
        'subtitle': 'Шаблоны автоплатежей',
        'icon': Icons.loop_rounded,
        'color': AppTheme.primary,
        'target': const RecurringScreen(),
        'feature': 'recurring',
      },
      {
        'title': 'Бюджеты',
        'subtitle': 'Лимиты категорий',
        'icon': Icons.pie_chart_rounded,
        'color': AppTheme.income,
        'target': const BudgetsScreen(),
      },
      {
        'title': 'Запланировано',
        'subtitle': 'Ожидаемые транзакции',
        'icon': Icons.schedule_rounded,
        'color': Colors.orangeAccent,
        'target': const PlannedScreen(),
        'feature': 'planned',
      },
      {
        'title': 'Настройки',
        'subtitle': 'Язык, валюта, тишина',
        'icon': Icons.settings_rounded,
        'color': AppTheme.textSecondary,
        'target': const SettingsScreen(),
      },
    ];

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: RefreshIndicator(
        onRefresh: () async {
          await appState.refreshAllData();
        },
        color: AppTheme.primary,
        backgroundColor: AppTheme.surfaceCard,
        child: SafeArea(
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
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: appState.isPremium ? AppTheme.primaryGradient : null,
                        color: appState.isPremium ? null : AppTheme.surfaceCard,
                      ),
                      child: Icon(
                        appState.isPremium ? Icons.star_rounded : Icons.star_border_rounded,
                        color: appState.isPremium ? Colors.white : AppTheme.textSecondary,
                        size: 24,
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            appState.isPremium ? 'FinTrack Premium' : 'FinTrack Free',
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: AppTheme.textPrimary),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            appState.isPremium
                                ? (appState.premiumExpirationDate != null
                                    ? 'Подписка активна до ${appState.premiumExpirationDate}'
                                    : 'Подписка активна')
                                : 'Активируйте Premium в боте (/upgrade)',
                            style: TextStyle(
                              color: appState.isPremium ? AppTheme.income : AppTheme.textSecondary,
                              fontSize: 11,
                              fontWeight: FontWeight.w600,
                            ),
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
                    final isLocked = item['feature'] != null && !appState.hasFeature(item['feature'] as String);

                    return GestureDetector(
                      onTap: () {
                        if (isLocked) {
                          AppTheme.showPremiumBlockDialog(context);
                          return;
                        }
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
                                  color: isLocked ? AppTheme.textSecondary : item['color'] as Color,
                                  size: 26,
                                ),
                                Icon(
                                  isLocked ? Icons.lock_outline_rounded : Icons.chevron_right_rounded,
                                  color: isLocked ? AppTheme.secondary : AppTheme.textSecondary.withOpacity(0.5),
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
