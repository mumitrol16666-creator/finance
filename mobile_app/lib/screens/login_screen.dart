import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:flutter_spinkit/flutter_spinkit.dart';
import 'package:url_launcher/url_launcher.dart';
import 'dart:math' as math;
import '../core/theme.dart';
import '../providers/app_state.dart';

class LoginScreen extends StatefulWidget {
  const LoginScreen({super.key});

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class Particle {
  double x;
  double y;
  double speedY;
  double speedX;
  double radius;
  double alpha;

  Particle({
    required this.x,
    required this.y,
    required this.speedY,
    required this.speedX,
    required this.radius,
    required this.alpha,
  });
}

class ParticlePainter extends CustomPainter {
  final List<Particle> particles;
  ParticlePainter(this.particles);

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint();
    for (var p in particles) {
      paint.color = AppTheme.primary.withOpacity(p.alpha);
      canvas.drawCircle(Offset(p.x * size.width, p.y * size.height), p.radius, paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => true;
}

class _LoginScreenState extends State<LoginScreen> with TickerProviderStateMixin {
  final _formKey = GlobalKey<FormState>();
  
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _confirmPasswordController = TextEditingController();
  
  String _errorMessage = '';
  bool _saveLogin = true;
  bool _isLoginMode = true;
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  late final AnimationController _backgroundController;
  final List<Particle> _particles = [];
  final math.Random _random = math.Random();

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
      duration: const Duration(seconds: 10),
    )..repeat();

    for (int i = 0; i < 25; i++) {
      _particles.add(Particle(
        x: _random.nextDouble(),
        y: _random.nextDouble(),
        speedY: 0.0004 + _random.nextDouble() * 0.0008,
        speedX: -0.0003 + _random.nextDouble() * 0.0006,
        radius: 1.5 + _random.nextDouble() * 2.5,
        alpha: 0.05 + _random.nextDouble() * 0.15,
      ));
    }

    _backgroundController.addListener(() {
      setState(() {
        for (var p in _particles) {
          p.y -= p.speedY;
          p.x += p.speedX;
          if (p.y < 0) {
            p.y = 1.0;
            p.x = _random.nextDouble();
          }
          if (p.x < 0 || p.x > 1.0) {
            p.speedX = -p.speedX;
          }
        }
      });
    });

    _logoController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat(reverse: true);

    _logoScale = Tween<double>(begin: 0.95, end: 1.05).animate(
      CurvedAnimation(parent: _logoController, curve: Curves.easeInOut),
    );

    _logoGlow = Tween<double>(begin: 16, end: 32).animate(
      CurvedAnimation(parent: _logoController, curve: Curves.easeInOut),
    );

    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 800),
    );

    _entranceFade = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _entranceController, curve: const Interval(0.0, 0.8, curve: Curves.easeOut)),
    );

    _entranceSlide = Tween<Offset>(
      begin: const Offset(0.0, 0.08),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _entranceController, curve: const Interval(0.0, 0.8, curve: Curves.easeOutCubic)),
    );

    _entranceController.forward();
  }

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
    _nameController.dispose();
    _confirmPasswordController.dispose();
    _backgroundController.dispose();
    _logoController.dispose();
    _entranceController.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    setState(() {
      _errorMessage = '';
    });

    if (!_formKey.currentState!.validate()) {
      return;
    }

    final appState = Provider.of<AppState>(context, listen: false);
    final username = _usernameController.text.trim();
    final password = _passwordController.text;

    if (_isLoginMode) {
      final success = await appState.login(username, password, saveLogin: _saveLogin);
      if (!success) {
        setState(() {
          _errorMessage = 'Неверный логин или пароль.';
        });
      }
    } else {
      final displayName = _nameController.text.trim();
      final confirmPassword = _confirmPasswordController.text;

      final regError = await appState.register(
        displayName,
        username,
        password,
        confirmPassword,
        saveLogin: _saveLogin,
      );

      if (regError != null) {
        setState(() {
          _errorMessage = regError;
        });
      }
    }
  }

  Widget _buildTextField({
    required TextEditingController controller,
    required String label,
    required IconData icon,
    bool obscureText = false,
    Widget? suffixIcon,
    String? Function(String?)? validator,
    TextInputType keyboardType = TextInputType.text,
  }) {
    return TextFormField(
      controller: controller,
      obscureText: obscureText,
      keyboardType: keyboardType,
      style: const TextStyle(color: AppTheme.textPrimary, fontSize: 15),
      validator: validator,
      decoration: InputDecoration(
        labelText: label,
        labelStyle: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
        prefixIcon: Icon(icon, color: AppTheme.accentBlue, size: 20),
        suffixIcon: suffixIcon,
        filled: true,
        fillColor: Colors.white.withOpacity(0.015),
        contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 18),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: BorderSide(color: Colors.white.withOpacity(0.08)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppTheme.primary, width: 2),
        ),
        errorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppTheme.expense, width: 1),
        ),
        focusedErrorBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(14),
          borderSide: const BorderSide(color: AppTheme.expense, width: 2),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final appState = Provider.of<AppState>(context);
    final isLoading = appState.isLoading;
    final size = MediaQuery.of(context).size;
    final isDesktop = size.width > 850;

    return Scaffold(
      backgroundColor: AppTheme.background,
      body: Stack(
        children: [
          Positioned.fill(
            child: CustomPaint(
              painter: ParticlePainter(_particles),
            ),
          ),
          
          const Positioned(
            top: -120,
            left: -120,
            child: BackgroundGlowBlob(size: 400, color: AppTheme.primary, opacity: 0.1),
          ),
          const Positioned(
            bottom: -150,
            right: -100,
            child: BackgroundGlowBlob(size: 450, color: AppTheme.secondary, opacity: 0.1),
          ),

          SafeArea(
            child: Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: FadeTransition(
                  opacity: _entranceFade,
                  child: SlideTransition(
                    position: _entranceSlide,
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        isDesktop
                            ? _buildSplitLayout(isLoading)
                            : _buildMobileLayout(isLoading),
                        if (_isLoginMode && appState.savedSessions.isNotEmpty) ...[
                          const SizedBox(height: 32),
                          const Text(
                            'Сохраненные сессии',
                            style: TextStyle(color: AppTheme.textSecondary, fontSize: 13, fontWeight: FontWeight.bold, letterSpacing: 0.5),
                          ),
                          const SizedBox(height: 12),
                          Container(
                            constraints: const BoxConstraints(maxWidth: 420),
                            child: ListView.builder(
                              shrinkWrap: true,
                              physics: const NeverScrollableScrollPhysics(),
                              itemCount: appState.savedSessions.length,
                              itemBuilder: (context, index) {
                                final session = appState.savedSessions[index];
                                return Card(
                                  color: AppTheme.surfaceCard,
                                  margin: const EdgeInsets.symmetric(vertical: 6),
                                  shape: RoundedRectangleBorder(
                                    borderRadius: BorderRadius.circular(14),
                                    side: const BorderSide(color: AppTheme.border),
                                  ),
                                  child: ListTile(
                                    leading: CircleAvatar(
                                      backgroundColor: AppTheme.primary.withOpacity(0.2),
                                      child: const Icon(Icons.person_rounded, color: AppTheme.primary),
                                    ),
                                    title: Text(session.name, style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                                    subtitle: Text('ID: ${session.userId}', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
                                    trailing: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        IconButton(
                                          icon: const Icon(Icons.login_rounded, color: AppTheme.income, size: 20),
                                          onPressed: () => appState.switchSession(session),
                                        ),
                                        IconButton(
                                          icon: const Icon(Icons.delete_outline_rounded, color: AppTheme.expense, size: 20),
                                          onPressed: () => appState.removeSession(session),
                                        ),
                                      ],
                                    ),
                                    onTap: () => appState.switchSession(session),
                                  ),
                                );
                              },
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSplitLayout(bool isLoading) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          flex: 12,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const NeonCardShowcase(),
              const SizedBox(height: 48),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 40.0),
                child: Column(
                  children: [
                    _buildFeatureItem(Icons.psychology_rounded, 'ИИ-Финансовый Консультант', 'Умный анализ и советы по расходам'),
                    const SizedBox(height: 16),
                    _buildFeatureItem(Icons.autorenew_rounded, 'Регулярные Платежи', 'Автоматическое отслеживание подписок и аренды'),
                    const SizedBox(height: 16),
                    _buildFeatureItem(Icons.analytics_rounded, 'Глубокая Аналитика', 'Интерактивные графики распределения средств'),
                  ],
                ),
              ),
            ],
          ),
        ),
        Container(
          height: 500,
          width: 1.5,
          color: Colors.white.withOpacity(0.08),
          margin: const EdgeInsets.symmetric(horizontal: 40),
        ),
        Expanded(
          flex: 10,
          child: _buildAuthPanel(isLoading, true),
        ),
      ],
    );
  }

  Widget _buildMobileLayout(bool isLoading) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 420),
      child: _buildAuthPanel(isLoading, false),
    );
  }

  Widget _buildFeatureItem(IconData icon, String title, String desc) {
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: AppTheme.primary.withOpacity(0.08),
            shape: BoxShape.circle,
            border: Border.all(color: AppTheme.primary.withOpacity(0.15)),
          ),
          child: Icon(icon, color: AppTheme.primary, size: 22),
        ),
        const SizedBox(width: 16),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: AppTheme.textPrimary),
              ),
              const SizedBox(height: 2),
              Text(
                desc,
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
              ),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildAuthPanel(bool isLoading, bool isDesktop) {
    final appState = Provider.of<AppState>(context, listen: false);
    return GlassCard(
      borderOpacity: 0.12,
      padding: EdgeInsets.symmetric(horizontal: isDesktop ? 36 : 24, vertical: 40),
      child: Form(
        key: _formKey,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            Center(
              child: AnimatedBuilder(
                animation: _logoController,
                builder: (context, child) {
                  return Transform.scale(
                    scale: _logoScale.value,
                    child: Container(
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        shape: BoxShape.circle,
                        gradient: AppTheme.primaryGradient,
                        boxShadow: [
                          BoxShadow(
                            color: AppTheme.primary.withOpacity(0.4),
                            blurRadius: _logoGlow.value,
                            spreadRadius: 2,
                          ),
                        ],
                      ),
                      child: const Icon(
                        Icons.account_balance_wallet_rounded,
                        size: 38,
                        color: Colors.white,
                      ),
                    ),
                  );
                },
              ),
            ),
            const SizedBox(height: 20),
            Center(
              child: Text(
                _isLoginMode ? 'Вход в аккаунт' : 'Регистрация',
                style: const TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 0.5,
                  color: AppTheme.textPrimary,
                ),
              ),
            ),
            const SizedBox(height: 6),
            Center(
              child: Text(
                _isLoginMode 
                    ? 'Войдите под своими учетными данными' 
                    : 'Заполните поля для создания аккаунта',
                style: const TextStyle(color: AppTheme.textSecondary, fontSize: 13),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 28),

            if (!_isLoginMode) ...[
              _buildTextField(
                controller: _nameController,
                label: 'Ваше имя',
                icon: Icons.face_rounded,
                validator: (val) {
                  if (val == null || val.trim().isEmpty) return 'Введите имя';
                  return null;
                },
              ),
              const SizedBox(height: 16),
            ],

            _buildTextField(
              controller: _usernameController,
              label: 'Логин (латиница)',
              icon: Icons.alternate_email_rounded,
              validator: (val) {
                if (val == null || val.trim().isEmpty) return 'Введите логин';
                if (!RegExp(r'^[a-zA-Z0-9_]+$').hasMatch(val)) {
                  return 'Только латинские буквы, цифры и подчеркивания';
                }
                return null;
              },
            ),
            const SizedBox(height: 16),

            _buildTextField(
              controller: _passwordController,
              label: 'Пароль',
              icon: Icons.lock_outline_rounded,
              obscureText: _obscurePassword,
              suffixIcon: IconButton(
                icon: Icon(
                  _obscurePassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                  color: AppTheme.textSecondary,
                  size: 20,
                ),
                onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
              ),
              validator: (val) {
                if (val == null || val.isEmpty) return 'Введите пароль';
                if (val.length < 6) return 'Минимум 6 символов';
                return null;
              },
            ),
            const SizedBox(height: 16),

            if (!_isLoginMode) ...[
              _buildTextField(
                controller: _confirmPasswordController,
                label: 'Повторите пароль',
                icon: Icons.lock_rounded,
                obscureText: _obscureConfirmPassword,
                suffixIcon: IconButton(
                  icon: Icon(
                    _obscureConfirmPassword ? Icons.visibility_off_outlined : Icons.visibility_outlined,
                    color: AppTheme.textSecondary,
                    size: 20,
                  ),
                  onPressed: () => setState(() => _obscureConfirmPassword = !_obscureConfirmPassword),
                ),
                validator: (val) {
                  if (val == null || val.isEmpty) return 'Повторите пароль';
                  if (val != _passwordController.text) return 'Пароли не совпадают';
                  return null;
                },
              ),
              const SizedBox(height: 16),
            ],

            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                SizedBox(
                  width: 24,
                  height: 24,
                  child: Checkbox(
                    value: _saveLogin,
                    onChanged: (val) {
                      if (val != null) {
                        setState(() => _saveLogin = val);
                      }
                    },
                    activeColor: AppTheme.primary,
                    checkColor: Colors.white,
                  ),
                ),
                const SizedBox(width: 8),
                const Text(
                  'Сохранить вход на устройстве',
                  style: TextStyle(color: AppTheme.textPrimary, fontSize: 13),
                ),
              ],
            ),
            const SizedBox(height: 16),

            if (_errorMessage.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 16.0),
                child: Text(
                  _errorMessage,
                  style: const TextStyle(color: AppTheme.expense, fontSize: 13, fontWeight: FontWeight.w500),
                  textAlign: TextAlign.center,
                ),
              ),

            ElevatedButton(
              onPressed: isLoading ? null : _submit,
              style: ElevatedButton.styleFrom(
                padding: const EdgeInsets.symmetric(vertical: 16),
                backgroundColor: Colors.transparent,
                shadowColor: Colors.transparent,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(14),
                ),
              ),
              child: Ink(
                decoration: BoxDecoration(
                  gradient: AppTheme.primaryGradient,
                  borderRadius: BorderRadius.circular(14),
                ),
                child: Container(
                  alignment: Alignment.center,
                  constraints: const BoxConstraints(minHeight: 52),
                  child: isLoading
                      ? const SpinKitThreeBounce(
                          color: Colors.white,
                          size: 24,
                        )
                      : Text(
                          _isLoginMode ? 'Войти в аккаунт' : 'Создать аккаунт',
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                            letterSpacing: 0.5,
                          ),
                        ),
                ),
              ),
            ),
            const SizedBox(height: 20),
            
            Center(
              child: TextButton(
                onPressed: () {
                  setState(() {
                    _isLoginMode = !_isLoginMode;
                    _errorMessage = '';
                  });
                },
                child: Text(
                  _isLoginMode 
                      ? 'Нет аккаунта? Зарегистрироваться' 
                      : 'Уже есть аккаунт? Войти',
                  style: const TextStyle(
                    color: AppTheme.secondary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
            
            const Divider(color: AppTheme.border, height: 32),
            
            Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.015),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withOpacity(0.04)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  const Text(
                    '🤖 Хотите подключить Telegram?',
                    style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  const Text(
                    'Вы можете создать аккаунт прямо здесь или зарегистрироваться в нашем Telegram-боте.\n'
                    'Если вы уже зарегистрированы в Telegram-боте, введите ваш логин и пароль в форме входа выше для синхронизации.',
                    style: TextStyle(color: Colors.white30, fontSize: 11, height: 1.4),
                  ),
                  const SizedBox(height: 12),
                  ElevatedButton.icon(
                    onPressed: () async {
                      final url = Uri.parse('https://t.me/FinanceBo1_bot');
                      if (await canLaunchUrl(url)) {
                        await launchUrl(url, mode: LaunchMode.externalApplication);
                      }
                    },
                    icon: const Icon(Icons.telegram_rounded, size: 18, color: Colors.white),
                    label: const Text(
                      'Открыть Telegram Бота',
                      style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 12),
                    ),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF24A1DE),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(10),
                      ),
                      padding: const EdgeInsets.symmetric(vertical: 8),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class NeonCardShowcase extends StatefulWidget {
  const NeonCardShowcase({super.key});

  @override
  State<NeonCardShowcase> createState() => _NeonCardShowcaseState();
}

class _NeonCardShowcaseState extends State<NeonCardShowcase> with SingleTickerProviderStateMixin {
  late final AnimationController _cardController;
  late final Animation<double> _rotationY;
  late final Animation<double> _rotationX;
  late final Animation<double> _translateY;

  @override
  void initState() {
    super.initState();
    _cardController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 6),
    )..repeat(reverse: true);

    _rotationY = Tween<double>(begin: -0.15, end: 0.15).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.easeInOut),
    );
    _rotationX = Tween<double>(begin: -0.06, end: 0.06).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.easeInOut),
    );
    _translateY = Tween<double>(begin: -8, end: 8).animate(
      CurvedAnimation(parent: _cardController, curve: Curves.easeInOut),
    );
  }

  @override
  void dispose() {
    _cardController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _cardController,
      builder: (context, child) {
        return Transform(
          transform: Matrix4.identity()
            ..setEntry(3, 2, 0.001)
            ..translate(0.0, _translateY.value, 0.0)
            ..rotateY(_rotationY.value)
            ..rotateX(_rotationX.value),
          alignment: Alignment.center,
          child: Container(
            width: 380,
            height: 230,
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  Colors.white.withOpacity(0.06),
                  Colors.white.withOpacity(0.01),
                ],
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
              ),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(
                color: Colors.white.withOpacity(0.12),
                width: 1.2,
              ),
              boxShadow: [
                BoxShadow(
                  color: AppTheme.primary.withOpacity(0.15),
                  blurRadius: 30,
                  spreadRadius: 2,
                ),
                BoxShadow(
                  color: AppTheme.secondary.withOpacity(0.1),
                  blurRadius: 40,
                  offset: const Offset(10, 10),
                )
              ],
            ),
            child: Stack(
              children: [
                Positioned.fill(
                  child: Container(
                    decoration: BoxDecoration(
                      borderRadius: BorderRadius.circular(24),
                      gradient: LinearGradient(
                        colors: [
                          AppTheme.primary.withOpacity(0.08),
                          Colors.transparent,
                          AppTheme.secondary.withOpacity(0.08),
                        ],
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                      ),
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.all(24.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          const Text(
                            'FinTrack Gold',
                            style: TextStyle(
                              fontSize: 18,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 1.2,
                              color: AppTheme.textPrimary,
                            ),
                          ),
                          Container(
                            width: 42,
                            height: 30,
                            decoration: BoxDecoration(
                              color: Colors.amber.withOpacity(0.15),
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(color: Colors.amber.withOpacity(0.3)),
                            ),
                            child: const Center(
                              child: Icon(Icons.nfc_rounded, color: Colors.amber, size: 18),
                            ),
                          ),
                        ],
                      ),
                      const Spacer(),
                      const Text(
                        'ТЕКУЩИЙ БАЛАНС',
                        style: TextStyle(
                          fontSize: 10,
                          color: AppTheme.textSecondary,
                          letterSpacing: 1.5,
                        ),
                      ),
                      const SizedBox(height: 4),
                      const Text(
                        '28,000.00 KZT',
                        style: TextStyle(
                          fontSize: 26,
                          fontWeight: FontWeight.bold,
                          color: AppTheme.textPrimary,
                        ),
                      ),
                      const Spacer(),
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: const [
                          Text(
                            'PREMIUM MEMBER',
                            style: TextStyle(
                              fontSize: 9.5,
                              color: AppTheme.secondary,
                              fontWeight: FontWeight.bold,
                              letterSpacing: 1.2,
                            ),
                          ),
                          Text(
                            '•••• 2026',
                            style: TextStyle(
                              fontSize: 11,
                              color: AppTheme.textSecondary,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}
