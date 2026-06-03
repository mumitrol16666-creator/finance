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

class _LoginScreenState extends State<LoginScreen> with TickerProviderStateMixin {
  final TextEditingController _codeController = TextEditingController();
  String _errorMessage = '';

  late final AnimationController _backgroundController;
  late final Animation<double> _blob1AnimationX;
  late final Animation<double> _blob1AnimationY;
  late final Animation<double> _blob2AnimationX;
  late final Animation<double> _blob2AnimationY;

  late final AnimationController _logoController;
  late final Animation<double> _logoScale;
  late final Animation<double> _logoGlow;

  late final AnimationController _entranceController;
  late final Animation<double> _entranceFade;
  late final Animation<Offset> _entranceSlide;

  @override
  void initState() {
    super.initState();

    _backgroundController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 15),
    )..repeat(reverse: true);

    _blob1AnimationX = Tween<double>(begin: -140, end: -60).animate(
      CurvedAnimation(parent: _backgroundController, curve: Curves.easeInOut),
    );
    _blob1AnimationY = Tween<double>(begin: -140, end: -60).animate(
      CurvedAnimation(parent: _backgroundController, curve: Curves.easeInOut),
    );

    _blob2AnimationX = Tween<double>(begin: -120, end: -40).animate(
      CurvedAnimation(parent: _backgroundController, curve: Curves.easeInOut),
    );
    _blob2AnimationY = Tween<double>(begin: -170, end: -70).animate(
      CurvedAnimation(parent: _backgroundController, curve: Curves.easeInOut),
    );

    _logoController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat(reverse: true);

    _logoScale = Tween<double>(begin: 0.94, end: 1.06).animate(
      CurvedAnimation(parent: _logoController, curve: Curves.easeInOut),
    );

    _logoGlow = Tween<double>(begin: 18, end: 38).animate(
      CurvedAnimation(parent: _logoController, curve: Curves.easeInOut),
    );

    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    );

    _entranceFade = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _entranceController, curve: const Interval(0.0, 0.8, curve: Curves.easeOut)),
    );

    _entranceSlide = Tween<Offset>(
      begin: const Offset(0.0, 0.12),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _entranceController, curve: const Interval(0.0, 0.8, curve: Curves.easeOutCubic)),
    );

    _entranceController.forward();
  }

  @override
  void dispose() {
    _codeController.dispose();
    _backgroundController.dispose();
    _logoController.dispose();
    _entranceController.dispose();
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
    final appState = Provider.of<AppState>(context);
    final isLoading = appState.isLoading;
    return Scaffold(
      body: Stack(
        children: [
          // Animated Background Glowing Blobs
          AnimatedBuilder(
            animation: _backgroundController,
            builder: (context, child) {
              return Stack(
                children: [
                  Positioned(
                    top: _blob1AnimationY.value,
                    left: _blob1AnimationX.value,
                    child: const BackgroundGlowBlob(size: 320, color: AppTheme.primary, opacity: 0.15),
                  ),
                  Positioned(
                    bottom: _blob2AnimationY.value,
                    right: _blob2AnimationX.value,
                    child: const BackgroundGlowBlob(size: 370, color: AppTheme.secondary, opacity: 0.15),
                  ),
                ],
              );
            },
          ),
          
          SafeArea(
            child: FadeTransition(
              opacity: _entranceFade,
              child: SlideTransition(
                position: _entranceSlide,
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 24.0, vertical: 16.0),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      const Spacer(),
                      
                      // App Logo/Icon with pulsing scale and glow
                      Center(
                        child: AnimatedBuilder(
                          animation: _logoController,
                          builder: (context, child) {
                            return Transform.scale(
                              scale: _logoScale.value,
                              child: Container(
                                padding: const EdgeInsets.all(22),
                                decoration: BoxDecoration(
                                  shape: BoxShape.circle,
                                  gradient: AppTheme.primaryGradient,
                                  boxShadow: [
                                    BoxShadow(
                                      color: AppTheme.primary.withOpacity(0.35),
                                      blurRadius: _logoGlow.value,
                                      spreadRadius: 2,
                                    ),
                                  ],
                                ),
                                child: const Icon(
                                  Icons.account_balance_wallet_rounded,
                                  size: 44,
                                  color: Colors.white,
                                ),
                              ),
                            );
                          },
                        ),
                      ),
                      const SizedBox(height: 28),
                      
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
                      const SizedBox(height: 10),
                      const Center(
                        child: Text(
                          'Введите код из Telegram бота для синхронизации',
                          style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
                          textAlign: TextAlign.center,
                        ),
                      ),
                      
                      const Spacer(),

                      // OTP Code input field - wrapped in GlassCard
                      GlassCard(
                        borderOpacity: 0.15,
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: TextField(
                          controller: _codeController,
                          keyboardType: TextInputType.number,
                          maxLength: 6,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 26,
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
                      const SizedBox(height: 16),

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
                        ),
                        child: Ink(
                          decoration: BoxDecoration(
                            gradient: AppTheme.primaryGradient,
                            borderRadius: BorderRadius.circular(12),
                          ),
                          child: Container(
                            alignment: Alignment.center,
                            constraints: const BoxConstraints(minHeight: 52),
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
          ),
        ],
      ),
    );
  }
}
