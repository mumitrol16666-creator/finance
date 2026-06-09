import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'core/theme.dart';
import 'core/tutorial_controller.dart';
import 'providers/app_state.dart';
import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/add_transaction_screen.dart';
import 'screens/ai_consultant_screen.dart';
import 'screens/analytics_screen.dart';
import 'screens/hub_screen.dart';
import 'screens/accounts_screen.dart';
import 'widgets/guided_tour_overlay.dart';

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
  int _tutorialStep = -1;
  int? _tutorialUserId;
  int? _tutorialCheckedFor;
  int? _tutorialCheckInProgressFor;
  final GlobalKey _overviewKey = GlobalKey();
  final GlobalKey _analyticsKey = GlobalKey();
  final GlobalKey _aiKey = GlobalKey();
  final GlobalKey _servicesKey = GlobalKey();
  final GlobalKey _addKey = GlobalKey();

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
    TutorialController.requests.addListener(_restartTutorial);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final appState = Provider.of<AppState>(context);
    final userId = appState.currentUserId;
    if (userId != null && userId != _tutorialUserId) {
      _tutorialUserId = userId;
      _tutorialCheckedFor = null;
      _plannedAssistantShown = false;
      _tutorialStep = -1;
    }
    if (userId != null && appState.appTutorialStatusLoaded && _tutorialCheckedFor != userId) {
      _tutorialCheckedFor = userId;
      WidgetsBinding.instance.addPostFrameCallback((_) async {
        await _checkInteractiveTutorial();
        await _showPlannedAssistant();
      });
    }
  }

  Future<void> _checkInteractiveTutorial() async {
    final appState = Provider.of<AppState>(context, listen: false);
    final userId = appState.currentUserId;
    if (userId == null ||
        !appState.appTutorialStatusLoaded ||
        appState.appTutorialCompleted ||
        _tutorialCheckInProgressFor == userId) {
      return;
    }
    _tutorialCheckInProgressFor = userId;
    if (!mounted) {
      _tutorialCheckInProgressFor = null;
      return;
    }
    final start = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: const Text('Познакомимся с FinTrack'),
        content: const Text('Покажем основные разделы, откроем форму операции и объясним, где находятся инструменты. Это займет меньше минуты.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Пропустить')),
          ElevatedButton(onPressed: () => Navigator.pop(context, true), child: const Text('Начать')),
        ],
      ),
    );
    if (start == true && mounted) {
      _showTutorialStep(0);
    } else {
      await appState.completeAppTutorial();
    }
    _tutorialCheckInProgressFor = null;
  }

  Future<void> _finishTutorial() async {
    if (mounted) setState(() => _tutorialStep = -1);
    await Provider.of<AppState>(context, listen: false).completeAppTutorial();
    await _showPlannedAssistant();
  }

  void _restartTutorial() {
    if (mounted) _showTutorialStep(0);
  }

  void _showTutorialStep(int step) {
    if (!mounted) return;
    final appState = Provider.of<AppState>(context, listen: false);
    final pageByStep = {0: 0, 2: 1, 3: appState.hasFeature('ai') ? 2 : 1, 4: 3};
    final page = pageByStep[step];
    setState(() {
      _tutorialStep = step;
      if (page != null) _currentIndex = page;
    });
    if (page != null) _pageController.jumpToPage(page);
  }

  Future<void> _advanceFromAddStep() async {
    setState(() => _tutorialStep = -1);
    final appState = Provider.of<AppState>(context, listen: false);
    if (appState.accounts.isEmpty && appState.isBusinessMode) {
      appState.toggleBusinessMode(false);
    }
    if (appState.accounts.isEmpty) {
      final openAccounts = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          backgroundColor: AppTheme.surface,
          title: const Text('Сначала создадим счёт'),
          content: const Text(
            'Счёт нужен, чтобы приложение понимало, откуда списывать и куда зачислять деньги. Создайте первый счёт, затем мы откроем форму операции.',
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Позже')),
            ElevatedButton.icon(
              onPressed: () => Navigator.pop(context, true),
              icon: const Icon(Icons.account_balance_wallet_rounded),
              label: const Text('Создать счёт'),
            ),
          ],
        ),
      );
      if (openAccounts != true || !mounted) {
        if (mounted) _showTutorialStep(1);
        return;
      }
      await Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => const AccountsScreen(
            closeAfterAccountCreated: true,
            openAddDialogOnStart: true,
          ),
        ),
      );
      if (!mounted) return;
      if (appState.accounts.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Создайте счёт, чтобы добавить первую операцию')),
        );
        _showTutorialStep(1);
        return;
      }
    }
    final tutorialCompleted = await _openTransactionSheet(tutorialMode: true);
    if (!mounted) return;
    if (!tutorialCompleted) {
      _showTutorialStep(1);
      return;
    }
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTheme.surface,
        title: const Text('Первая операция проведена'),
        content: const Text(
          'Отлично! Вы прошли главный сценарий FinTrack. Учебная операция удалена и не повлияла на ваши счета или историю.',
        ),
        actions: [
          ElevatedButton(onPressed: () => Navigator.pop(context), child: const Text('Продолжить обучение')),
        ],
      ),
    );
    if (mounted) _showTutorialStep(2);
  }

  Future<bool> _openTransactionSheet({bool tutorialMode = false}) async {
    final appState = Provider.of<AppState>(context, listen: false);
    final beforeCount = appState.transactions.length;
    final tutorialCompleted = await showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: AppTheme.background,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) => SizedBox(
        height: MediaQuery.of(context).size.height * 0.85,
        child: ClipRRect(
          borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
          child: Scaffold(
            backgroundColor: AppTheme.background,
            body: SafeArea(child: AddTransactionScreen(showTutorialHint: tutorialMode)),
          ),
        ),
      ),
    );
    if (appState.transactions.length > beforeCount && mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Операция сохранена. Балансы и аналитика обновлены.')),
      );
    }
    return tutorialCompleted == true;
  }

  Future<void> _showPlannedAssistant() async {
    if (_plannedAssistantShown || !mounted || _tutorialStep >= 0) return;
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
    TutorialController.requests.removeListener(_restartTutorial);
    _pageController.dispose();
    super.dispose();
  }

  Widget _buildTabItem(int index, IconData icon, String label, GlobalKey key) {
    final isSelected = _currentIndex == index;
    final appState = Provider.of<AppState>(context);
    final isLocked = index == 2 && !appState.hasFeature('ai');

    return GestureDetector(
      key: key,
      onTap: () {
        if (isLocked) {
          AppTheme.showPremiumBlockDialog(context);
          return;
        }
        setState(() {
          _currentIndex = index;
        });
        _pageController.jumpToPage(index);
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

    final tutorialTargets = [_overviewKey, _addKey, _analyticsKey, _aiKey, _servicesKey];
    final tutorialTitles = ['Главный экран', 'Добавление операции', 'Аналитика', 'ИИ-консультант', 'Сервисы'];
    final tutorialDescriptions = [
      'Здесь собраны общий баланс, последние операции, быстрые расходы и основные показатели.',
      Provider.of<AppState>(context).accounts.isEmpty
          ? 'Главная рабочая кнопка. Сначала поможем создать счёт, затем откроем форму первой операции.'
          : 'Главная рабочая кнопка. Откроем форму, где можно добавить расход, доход или перевод между счетами.',
      'Раздел уже открыт. Здесь видны динамика денег, категории расходов и финансовые показатели.',
      'ИИ-консультант отвечает по вашим данным и помогает разобрать расходы.${Provider.of<AppState>(context).hasFeature('ai') ? '' : ' Раздел станет доступен после подключения Premium.'}',
      'Раздел уже открыт. Здесь находятся счета, категории, долги, автоплатежи и планы.',
    ];
    final tutorialIcons = [
      Icons.grid_view_rounded,
      Icons.add_rounded,
      Icons.analytics_rounded,
      Icons.android_rounded,
      Icons.explore_rounded,
    ];

    return Stack(
      children: [
        Scaffold(
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
        ],
      ),
      floatingActionButton: isKeyboardVisible
          ? null
          : FloatingActionButton(
              key: _addKey,
              onPressed: _openTransactionSheet,
              backgroundColor: Colors.transparent,
              elevation: 0,
              child: Container(
                width: 56,
                height: 56,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  gradient: AppTheme.primaryGradient,
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
                    _buildTabItem(0, Icons.grid_view_rounded, 'Главная', _overviewKey),
                    _buildTabItem(1, Icons.analytics_rounded, 'Аналитика', _analyticsKey),
                    const SizedBox(width: 48), // Placeholder for FAB
                    _buildTabItem(2, Icons.android_rounded, 'ИИ Чат', _aiKey),
                    _buildTabItem(3, Icons.explore_rounded, 'Сервисы', _servicesKey),
                  ],
                ),
              ),
            ),
        ),
        if (_tutorialStep >= 0)
          GuidedTourOverlay(
            targetKey: tutorialTargets[_tutorialStep],
            title: tutorialTitles[_tutorialStep],
            description: tutorialDescriptions[_tutorialStep],
            primaryLabel: _tutorialStep == 1
                ? 'Открыть'
                : _tutorialStep == tutorialTargets.length - 1
                    ? 'Готово'
                    : 'Далее',
            icon: tutorialIcons[_tutorialStep],
            step: _tutorialStep,
            totalSteps: tutorialTargets.length,
            onSkip: _finishTutorial,
            onBack: _tutorialStep == 0 ? null : () => _showTutorialStep(_tutorialStep - 1),
            onPrimary: () {
              if (_tutorialStep == 1) {
                _advanceFromAddStep();
              } else if (_tutorialStep == tutorialTargets.length - 1) {
                _finishTutorial();
              } else {
                _showTutorialStep(_tutorialStep + 1);
              }
            },
          ),
      ],
    );
  }
}
