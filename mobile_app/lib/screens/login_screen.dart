import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import '../core/theme.dart';
import '../providers/app_state.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  final TextEditingController _codeController = TextEditingController();
  String _errorMessage = '';

  @override
  void dispose() {
    _codeController.dispose();
    super.dispose();
  }

  Future<void> _submitCode() async {
    final appState = Provider.of<AppState>(context, listen: false);
    final code = _codeController.text.trim();

    if (code.length != 6) {
      setState(() {
        _errorMessage = 'Введите 6-значный код из Telegram бота';
      });
      return;
    }

    final success = await appState.verifyLoginCode(code);
    if (!success) {
      setState(() {
        _errorMessage = 'Неверный код. Проверьте правильность ввода.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isLoading = Provider.of<AppState>(context).isLoading;

    return Scaffold(
      body: Container(
        decoration: const BoxDecoration(
          color: AppTheme.background,
        ),
        child: SafeArea(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Spacer(),
                
                // App Logo/Icon
                Center(
                  child: Container(
                    padding: const EdgeInsets.all(20),
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: AppTheme.primaryGradient,
                      boxShadow: [
                        BoxShadow(
                          color: AppTheme.primary.withOpacity(0.4),
                          blurRadius: 20,
                          spreadRadius: 2,
                        ),
                      ],
                    ),
                    child: const Icon(
                      Icons.account_balance_wallet_rounded,
                      size: 48,
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(height: 24),
                
                // Welcome text
                Center(
                  child: Text(
                    'Finance Tracker',
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                          fontWeight: FontWeight.bold,
                          color: AppTheme.textPrimary,
                        ),
                  ),
                ),
                const SizedBox(height: 8),
                const Center(
                  child: Text(
                    'Введите код из Telegram бота для синхронизации',
                    style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
                    textAlign: TextAlign.center,
                  ),
                ),
                
                const Spacer(),

                // OTP Code input field
                Container(
                  decoration: AppTheme.glassCardDecoration(
                    borderOpacity: 0.15,
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: TextField(
                    controller: _codeController,
                    keyboardType: TextInputType.number,
                    maxLength: 6,
                    textAlign: TextAlign.center,
                    style: const TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 8,
                      color: AppTheme.textPrimary,
                    ),
                    decoration: const InputDecoration(
                      hintText: '000000',
                      hintStyle: TextStyle(
                        color: Colors.white24,
                        letterSpacing: 8,
                      ),
                      border: InputBorder.none,
                      counterText: '',
                    ),
                    onSubmitted: (_) => _submitCode(),
                  ),
                ),
                const SizedBox(height: 12),

                // Error message display
                if (_errorMessage.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 12.0),
                    child: Text(
                      _errorMessage,
                      style: const TextStyle(color: AppTheme.expense, fontSize: 13),
                      textAlign: TextAlign.center,
                    ),
                  ),

                // Action buttons
                ElevatedButton(
                  onPressed: isLoading ? null : _submitCode,
                  style: ElevatedButton.styleFrom(
                    padding: const EdgeInsets.symmetric(vertical: 16),
                    backgroundColor: Colors.transparent,
                    shadowColor: Colors.transparent,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ).copyWith(
                    backgroundColor: WidgetStateProperty.resolveWith((states) {
                      if (states.contains(WidgetState.disabled)) {
                        return AppTheme.primary.withOpacity(0.3);
                      }
                      return null; // Uses wrapper gradient decoration
                    }),
                  ),
                  child: Ink(
                    decoration: BoxDecoration(
                      gradient: AppTheme.primaryGradient,
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Container(
                      alignment: Alignment.center,
                      constraints: const BoxConstraints(minHeight: 50),
                      child: isLoading
                          ? const SpinKitThreeBounce(
                              color: Colors.white,
                              size: 24,
                            )
                          : const Text(
                              'Войти в аккаунт',
                              style: TextStyle(
                                fontSize: 16,
                                fontWeight: FontWeight.bold,
                                color: Colors.white,
                              ),
                            ),
                    ),
                  ),
                ),
                
                const Spacer(flex: 2),
                
                // Small note
                const Center(
                  child: Text(
                    'Чтобы получить код, отправьте команду /login в бота',
                    style: TextStyle(color: Colors.white30, fontSize: 12),
                  ),
                ),
                const SizedBox(height: 8),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
