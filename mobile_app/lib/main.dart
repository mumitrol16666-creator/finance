import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'core/theme.dart';
import 'providers/app_state.dart';
import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/add_transaction_screen.dart';
import 'screens/ai_consultant_screen.dart';
import 'screens/analytics_screen.dart';
import 'screens/hub_screen.dart';

void main() {
  runApp(
    ChangeNotifierProvider(
      create: (_) => AppState(),
      child: const FinanceApp(),
    ),
  );
}

class FinanceApp extends StatelessWidget {
  const FinanceApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Finance Tracker',
      theme: AppTheme.darkTheme,
      debugShowCheckedModeBanner: false,
      localizationsDelegates: const [
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: const [
        Locale('ru', 'RU'),
        Locale('kk', 'KZ'),
        Locale('en', 'US'),
      ],
      locale: const Locale('ru', 'RU'),
      home: const AuthWrapper(),
    );
  }
}

class AuthWrapper extends StatefulWidget {
  const AuthWrapper({super.key});

  @override
  State<AuthWrapper> createState() => _AuthWrapperState();
}

class _AuthWrapperState extends State<AuthWrapper> {
  bool _initialized = false;

  @override
  void initState() {
    super.initState();
    _init();
  }

  Future<void> _init() async {
    final appState = Provider.of<AppState>(context, listen: false);
    await appState.initSessions();
    if (mounted) {
      setState(() {
        _initialized = true;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    
    if (!_initialized) {
      return const Scaffold(
        body: Center(
          child: CircularProgressIndicator(color: AppTheme.primary),
        ),
      );
    }
    
    if (!appState.isAuthenticated) {
      return const LoginScreen();
    }
    
    return const MainNavigationFrame();
  }
}

class MainNavigationFrame extends StatefulWidget {
  const MainNavigationFrame({super.key});

  @override
  State<MainNavigationFrame> createState() => _MainNavigationFrameState();
}

class _MainNavigationFrameState extends State<MainNavigationFrame> {
  int _currentIndex = 0;
  late PageController _pageController;
  bool _plannedAssistantShown = false;
  int _tutorialStep = 0;

  final List<Widget> _screens = [
    const DashboardScreen(),
    const AnalyticsScreen(),
    const AiConsultantScreen(),
    const HubScreen(),
  ];

  @override
  void initState() {
    super.initState();
    _pageController = PageController(initialPage: _currentIndex);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      await _showPlannedAssistant();
      await _checkInteractiveTutorial();
    });
  }

  Future<void> _checkInteractiveTutorial() async {
    final prefs = await SharedPreferences.getInstance();
    if ((prefs.getBool('onboarding_tutorial_shown') ?? false) || !mounted) return;
    final start = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: const Text('Быстрое обучение'),
        content: const Text('Вместе внесем первую операцию, затем откроем раздел сервисов.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Пропустить')),
          ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text('Начать')),
        ],
      ),
    );
    if (start == true && mounted) {
      setState(() => _tutorialStep = 1);
    } else {
      await prefs.setBool('onboarding_tutorial_shown', true);
    }
  }

  Future<void> _finishTutorial() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('onboarding_tutorial_shown', true);
    if (mounted) setState(() => _tutorialStep = 0);
  }

  Future<void> _openTransactionSheet() async {
    final appState = Provider.of<AppState>(context, listen: false);
    final beforeCount = appState.transactions.length;
    await showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.background,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SizedBox(
        height: MediaQuery.of(context).size.height * 0.85,
        child: const ClipRRect(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
          child: Scaffold(
            backgroundColor: AppTheme.background,
            body: SafeArea(child: AddTransactionScreen()),
          ),
        ),
      ),
    );
    if (_tutorialStep == 1 && mounted) {
      if (appState.transactions.length > beforeCount) {
        setState(() => _tutorialStep = 2);
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Заполните и сохраните операцию, чтобы продолжить обучение.')),
        );
      }
    }
  }

  Future<void> _showPlannedAssistant() async {
    if (_plannedAssistantShown || !mounted) return;
    _plannedAssistantShown = true;
    final appState = Provider.of<AppState>(context, listen: false);
    final today = DateTime.now().toIso8601String().split('T').first;
    final due = appState.plannedEvents.where((item) => item.date == today && item.status == 'pending').toList();
    for (final item in due) {
      if (!mounted) return;
      final execute = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Text('Запланированная операция на сегодня'),
          content: Text('${item.title}\n${item.amount} ${item.currency}'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: const Text('Позже'),
            ),
            ElevatedButton.icon(
              onPressed: () => Navigator.pop(context, true),
              icon: const Icon(Icons.check_rounded),
              label: const Text('Внести'),
            ),
          ],
        ),
      );
      if (execute == true) {
        try {
          await appState.executePlanned(item.id);
        } catch (e) {
          if (!mounted) return;
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(e.toString().replaceFirst('Exception: ', '')),
              backgroundColor: AppTheme.expense,
            ),
          );
        }
      }
    }
  }

  @override
  void dispose() {
    _pageController.dispose();
    super.dispose();
  }

  Widget _buildTabItem(int index, IconData icon, String label) {
    final isSelected = _currentIndex == index;
    final appState = Provider.of<AppState>(context);
    final isLocked = index == 2 && !appState.hasFeature('ai');

    return GestureDetector(
      onTap: () {
        if (isLocked) {
          AppTheme.showPremiumBlockDialog(context);
          return;
        }
        setState(() {
          _currentIndex = index;
        });
        _pageController.jumpToPage(index);
        if (_tutorialStep == 2 && index == 3) {
          _finishTutorial();
        }
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Stack(
            clipBehavior: Clip.none,
            children: [
              Icon(icon, color: isSelected ? AppTheme.primary : AppTheme.textSecondary, size: 22),
              if (isLocked)
                Positioned(
                  right: -4,
                  top: -4,
                  child: Container(
                    padding: const EdgeInsets.all(2),
                    decoration: const BoxDecoration(
                      color: AppTheme.secondary,
                      shape: BoxShape.circle,
                    ),
                    child: const Icon(Icons.lock, color: Colors.white, size: 8),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            label,
            style: TextStyle(
              color: isSelected ? AppTheme.primary : AppTheme.textSecondary,
              fontSize: 10,
              fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final bool isKeyboardVisible = MediaQuery.of(context).viewInsets.bottom > 0;

    return Scaffold(
      body: Stack(
        children: [
          // Background Glowing Blobs for Space Aesthetic
          const Positioned(
            top: -120,
            left: -120,
            child: BackgroundGlowBlob(size: 320, color: AppTheme.primary, opacity: 0.1),
          ),
          const Positioned(
            bottom: -150,
            right: -100,
            child: BackgroundGlowBlob(size: 350, color: AppTheme.secondary, opacity: 0.1),
          ),
          
          SafeArea(
            child: PageView(
              controller: _pageController,
              physics: const NeverScrollableScrollPhysics(),
              onPageChanged: (index) {
                final appState = Provider.of<AppState>(context, listen: false);
                final isLocked = index == 2 && !appState.hasFeature('ai');
                if (isLocked) {
                  AppTheme.showPremiumBlockDialog(context);
                  _pageController.animateToPage(
                    _currentIndex,
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOut,
                  );
                } else {
                  setState(() => _currentIndex = index);
                }
              },
              children: _screens,
            ),
          ),
          if (_tutorialStep > 0)
            Positioned(
              left: 20,
              right: 20,
              bottom: 16,
              child: Material(
                color: AppTheme.surface,
                elevation: 12,
                borderRadius: BorderRadius.circular(8),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                  child: Row(
                    children: [
                      const Icon(Icons.touch_app_rounded, color: AppTheme.primary),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          _tutorialStep == 1
                              ? 'Нажмите выделенную кнопку +, заполните операцию и сохраните ее.'
                              : 'Отлично. Теперь нажмите «Сервисы» внизу экрана.',
                        ),
                      ),
                      IconButton(
                        tooltip: 'Пропустить обучение',
                        onPressed: _finishTutorial,
                        icon: const Icon(Icons.close_rounded),
                      ),
                    ],
                  ),
                ),
              ),
            ),
        ],
      ),
      floatingActionButton: isKeyboardVisible
          ? null
          : FloatingActionButton(
              onPressed: _openTransactionSheet,
              backgroundColor: Colors.transparent,
              elevation: _tutorialStep == 1 ? 12 : 0,
              child: Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: AppTheme.primaryGradient,
                  border: _tutorialStep == 1 ? Border.all(color: Colors.white, width: 3) : null,
                ),
                child: const Icon(Icons.add_rounded, color: Colors.white, size: 28),
              ),
            ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerDocked,
      bottomNavigationBar: isKeyboardVisible
          ? null
          : BottomAppBar(
              color: AppTheme.surface,
              shape: const CircularNotchedRectangle(),
              notchMargin: 8.0,
              child: SizedBox(
                height: 60,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceAround,
                  children: [
                    _buildTabItem(0, Icons.grid_view_rounded, 'Обзор'),
                    _buildTabItem(1, Icons.analytics_rounded, 'Аналитика'),
                    const SizedBox(width: 48), // Placeholder for FAB
                    _buildTabItem(2, Icons.android_rounded, 'ИИ Чат'),
                    _buildTabItem(3, Icons.explore_rounded, 'Сервисы'),
                  ],
                ),
              ),
            ),
    );
  }
}
