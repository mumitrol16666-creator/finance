import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'core/theme.dart';
import 'providers/app_state.dart';
import 'screens/login_screen.dart';
import 'screens/dashboard_screen.dart';
import 'screens/add_transaction_screen.dart';
import 'screens/ai_consultant_screen.dart';

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
      home: const AuthWrapper(),
    );
  }
}

class AuthWrapper extends StatelessWidget {
  const AuthWrapper({super.key});

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    
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

  final List<Widget> _screens = [
    const DashboardScreen(),
    const AddTransactionScreen(),
    const AiConsultantScreen(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: IndexedStack(
          index: _currentIndex,
          children: _screens,
        ),
      ),
      bottomNavigationBar: Container(
        decoration: const BoxDecoration(
          border: Border(
            top: BorderSide(color: AppTheme.border, width: 0.5),
          ),
        ),
        child: BottomNavigationBar(
          currentIndex: _currentIndex,
          onTap: (index) {
            setState(() {
              _currentIndex = index;
            });
          },
          backgroundColor: AppTheme.surface,
          selectedItemColor: AppTheme.primary,
          unselectedItemColor: AppTheme.textSecondary,
          selectedLabelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11),
          unselectedLabelStyle: const TextStyle(fontSize: 11),
          type: BottomNavigationBarType.fixed,
          elevation: 8,
          items: const [
            BottomNavigationBarItem(
              icon: Icon(Icons.grid_view_rounded),
              activeIcon: Icon(Icons.grid_view_rounded, color: AppTheme.primary),
              label: 'Обзор',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.add_circle_outline_rounded),
              activeIcon: Icon(Icons.add_circle_rounded, color: AppTheme.primary),
              label: 'Операция',
            ),
            BottomNavigationBarItem(
              icon: Icon(Icons.android_outlined),
              activeIcon: Icon(Icons.android_rounded, color: AppTheme.primary),
              label: 'Консультант',
            ),
          ],
        ),
      ),
    );
  }
}
