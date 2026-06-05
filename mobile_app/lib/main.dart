import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
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
        _pageController.animateToPage(
          index,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeInOut,
        );
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
              onPressed: () {
                showModalBottomSheet(
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
              },
              backgroundColor: Colors.transparent,
              elevation: 0,
              child: Container(
                width: 56,
                height: 56,
                decoration: const BoxDecoration(
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
