import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';
import 'accounts_screen.dart';
import 'debts_screen.dart';
import 'recurring_screen.dart';
import 'budgets_screen.dart';
import 'planned_screen.dart';
import 'categories_screen.dart';

class HubScreen extends StatelessWidget {
  const HubScreen({super.key});

  String _formatExpiryDate(String? dateStr) {
    if (dateStr == null) return 'Подписка активна';
    DateTime? dt = DateTime.tryParse(dateStr);
    if (dt == null) {
      final parts = dateStr.split(' ')[0].split('-');
      if (parts.length == 3) {
        final y = int.tryParse(parts[0]);
        final m = int.tryParse(parts[1]);
        final d = int.tryParse(parts[2]);
        if (y != null && m != null && d != null) {
          dt = DateTime(y, m, d);
        }
      }
    }
    if (dt == null) return 'Подписка активна до $dateStr';
    final months = [
      'января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
      'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря'
    ];
    return 'Подписка активна до ${dt.day} ${months[dt.month - 1]} ${dt.year}г.';
  }

  Widget _buildCard(Map<String, dynamic> item, AppState appState, BuildContext context, {bool isWide = false}) {
    final isLocked = item['feature'] != null && !appState.hasFeature(item['feature'] as String);
    final double screenWidth = MediaQuery.of(context).size.width;
    final double layoutWidth = screenWidth > 1100.0 ? 1100.0 : screenWidth;
    final double cardHeight = layoutWidth > 600.0 ? 115.0 : 105.0;

    return SizedBox(
      height: cardHeight,
      child: GestureDetector(
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
          child: isWide
              ? Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: (isLocked ? AppTheme.textSecondary : item['color'] as Color).withOpacity(0.1),
                        shape: BoxShape.circle,
                      ),
                      child: Icon(
                        item['icon'] as IconData,
                        color: isLocked ? AppTheme.textSecondary : item['color'] as Color,
                        size: 26,
                      ),
                    ),
                    const SizedBox(width: 14),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
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
                    Icon(
                      isLocked ? Icons.lock_outline_rounded : Icons.chevron_right_rounded,
                      color: isLocked ? AppTheme.secondary : AppTheme.textSecondary.withOpacity(0.5),
                      size: 18,
                    ),
                  ],
                )
              : Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Icon(
                          item['icon'] as IconData,
                          color: isLocked ? AppTheme.textSecondary : item['color'] as Color,
                          size: 24,
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
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: AppTheme.textPrimary),
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
      ),
    );
  }

  List<Widget> _buildGridRows(
    BuildContext context,
    AppState appState,
    List<Map<String, dynamic>> tools,
    int crossAxisCount,
  ) {
    List<Widget> rows = [];
    const spacing = 12.0;

    if (crossAxisCount == 2) {
      // Mobile Layout:
      // Row 1: Smetas (Wide)
      rows.add(_buildCard(tools[0], appState, context, isWide: true));
      rows.add(const SizedBox(height: spacing));

      // Row 2: Item 1 & 2
      rows.add(
        Row(
          children: [
            Expanded(child: _buildCard(tools[1], appState, context)),
            const SizedBox(width: spacing),
            Expanded(child: _buildCard(tools[2], appState, context)),
          ],
        ),
      );
      rows.add(const SizedBox(height: spacing));

      // Row 3: Item 3 & 4
      rows.add(
        Row(
          children: [
            Expanded(child: _buildCard(tools[3], appState, context)),
            const SizedBox(width: spacing),
            Expanded(child: _buildCard(tools[4], appState, context)),
          ],
        ),
      );
    } else {
      // Tablet/Desktop Layout (crossAxisCount == 3):
      // Row 1: Smetas (Wide, takes 2/3 width) and Item 1 (takes 1/3 width)
      rows.add(
        LayoutBuilder(
          builder: (context, constraints) {
            final totalWidth = constraints.maxWidth;
            final itemWidth = (totalWidth - spacing * 2) / 3;
            final wideWidth = itemWidth * 2 + spacing;
            return Row(
              children: [
                SizedBox(
                  width: wideWidth,
                  child: _buildCard(tools[0], appState, context, isWide: true),
                ),
                const SizedBox(width: spacing),
                SizedBox(
                  width: itemWidth,
                  child: _buildCard(tools[1], appState, context),
                ),
              ],
            );
          },
        ),
      );
      rows.add(const SizedBox(height: spacing));

      // Row 2: Item 2, Item 3, Item 4 (each takes 1/3 width)
      rows.add(
        Row(
          children: [
            Expanded(child: _buildCard(tools[2], appState, context)),
            const SizedBox(width: spacing),
            Expanded(child: _buildCard(tools[3], appState, context)),
            const SizedBox(width: spacing),
            Expanded(child: _buildCard(tools[4], appState, context)),
          ],
        ),
      );
    }

    return rows;
  }

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
        'title': 'Автоплатежи',
        'subtitle': 'Шаблоны автоплатежей',
        'icon': Icons.loop_rounded,
        'color': AppTheme.primary,
        'target': const RecurringScreen(),
        'feature': 'recurring',
      },
      {
        'title': 'Категории',
        'subtitle': 'Настройка трат, доходов и лимитов',
        'icon': Icons.category_rounded,
        'color': Colors.tealAccent,
        'target': const CategoriesScreen(),
      },
      {
        'title': 'Планы трат',
        'subtitle': 'Ожидаемые транзакции',
        'icon': Icons.schedule_rounded,
        'color': Colors.orangeAccent,
        'target': const PlannedScreen(),
        'feature': 'planned',
      },
    ];

    final double screenWidth = MediaQuery.of(context).size.width;
    final double layoutWidth = screenWidth > 1100.0 ? 1100.0 : screenWidth;
    final int crossAxisCount = layoutWidth > 600.0 ? 3 : 2;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1100.0),
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
                                    ? _formatExpiryDate(appState.premiumExpirationDate)
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

                  // Custom responsive layout of tools
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.stretch,
                        children: _buildGridRows(context, appState, tools, crossAxisCount),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
