import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
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

// Particle model for dynamic background
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
  final TextEditingController _codeController = TextEditingController();
  final TextEditingController _nameController = TextEditingController();
  final FocusNode _focusNode = FocusNode();
  String _errorMessage = '';
  bool _saveLogin = true;

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

    // 1. Particle setup & background loop
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

    // 2. Logo breath animation
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

    // 3. Page slide & fade entrance
    _entranceController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1000),
    );

    _entranceFade = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _entranceController, curve: const Interval(0.0, 0.8, curve: Curves.easeOut)),
    );

    _entranceSlide = Tween<Offset>(
      begin: const Offset(0.0, 0.1),
      end: Offset.zero,
    ).animate(
      CurvedAnimation(parent: _entranceController, curve: const Interval(0.0, 0.8, curve: Curves.easeOutCubic)),
    );

    _entranceController.forward();

    // Auto-focus OTP field
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _focusNode.requestFocus();
    });
  }

  @override
  void dispose() {
    _codeController.dispose();
    _nameController.dispose();
    _focusNode.dispose();
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

    final success = await appState.verifyLoginCode(code, saveLogin: _saveLogin);
    if (!success) {
      setState(() {
        _errorMessage = 'Неверный код. Проверьте правильность ввода.';
      });
    }
  }

  Future<void> _pasteFromClipboard() async {
    try {
      final ClipboardData? data = await Clipboard.getData(Clipboard.kTextPlain);
      if (data != null && data.text != null) {
        final pastedText = data.text!.replaceAll(RegExp(r'\D'), '').trim();
        if (pastedText.isNotEmpty) {
          final digits = pastedText.length > 6 ? pastedText.substring(0, 6) : pastedText;
          setState(() {
            _codeController.text = digits;
            _errorMessage = '';
          });
          if (digits.length == 6) {
            _submitCode();
          }
        }
      }
    } catch (e) {
      debugPrint('Clipboard error: $e');
      setState(() {
        _errorMessage = 'Не удалось получить данные из буфера обмена. Проверьте разрешения браузера или используйте HTTPS.';
      });
    }
  }

  // Modern digital OTP digit grid layout
  Widget _buildOTPInput() {
    return GestureDetector(
      onTap: () {
        _focusNode.requestFocus();
      },
      child: Stack(
        children: [
          // Hidden actual text field
          Opacity(
            opacity: 0,
            child: SizedBox(
              height: 0,
              width: 0,
              child: TextField(
                controller: _codeController,
                focusNode: _focusNode,
                keyboardType: TextInputType.number,
                maxLength: 6,
                enableInteractiveSelection: false,
                onChanged: (val) {
                  setState(() {
                    _errorMessage = '';
                  });
                  if (val.length == 6) {
                    _submitCode();
                  }
                },
              ),
            ),
          ),
          // 6 Glassmorphic interactive digital digit containers
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: List.generate(6, (index) {
              final codeText = _codeController.text;
              String digit = '';
              if (index < codeText.length) {
                digit = codeText[index];
              }
              final isFocused = _focusNode.hasFocus && index == codeText.length;
              final isFilled = index < codeText.length;

              return Expanded(
                child: Container(
                  margin: const EdgeInsets.symmetric(horizontal: 5),
                  height: 62,
                  decoration: BoxDecoration(
                    color: isFocused
                        ? AppTheme.primary.withOpacity(0.08)
                        : Colors.white.withOpacity(0.015),
                    borderRadius: BorderRadius.circular(14),
                    border: Border.all(
                      color: isFocused
                          ? AppTheme.primary
                          : (isFilled ? AppTheme.secondary.withOpacity(0.6) : Colors.white.withOpacity(0.08)),
                      width: isFocused ? 2.2 : 1.2,
                    ),
                    boxShadow: isFocused
                        ? [
                            BoxShadow(
                              color: AppTheme.primary.withOpacity(0.35),
                              blurRadius: 10,
                              spreadRadius: 1,
                            )
                          ]
                        : [],
                  ),
                  alignment: Alignment.center,
                  child: digit.isNotEmpty
                      ? Text(
                          digit,
                          style: const TextStyle(
                            fontSize: 26,
                            fontWeight: FontWeight.bold,
                            color: AppTheme.textPrimary,
                          ),
                        )
                      : Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                            shape: BoxShape.circle,
                            color: isFocused ? AppTheme.primary : Colors.white24,
                          ),
                        ),
                ),
              );
            }),
          ),
        ],
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
      body: Stack(
        children: [
          // Dynamic Floating Particles background
          Positioned.fill(
            child: CustomPaint(
              painter: ParticlePainter(_particles),
            ),
          ),
          
          // Nebula glow blobs
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
                        appState.needsOnboardingName
                            ? _buildNameOnboardingPanel(appState)
                            : (isDesktop
                                ? _buildSplitLayout(isLoading)
                                : _buildMobileLayout(isLoading)),
                        if (!appState.needsOnboardingName && appState.savedSessions.isNotEmpty) ...[
                          const SizedBox(height: 32),
                          const Text(
                            'Сохраненные аккаунты',
                            style: TextStyle(color: AppTheme.textSecondary, fontSize: 14, fontWeight: FontWeight.bold),
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
                                    borderRadius: BorderRadius.circular(12),
                                    side: const BorderSide(color: AppTheme.border),
                                  ),
                                  child: ListTile(
                                    leading: CircleAvatar(
                                      backgroundColor: AppTheme.primary.withOpacity(0.2),
                                      child: const Icon(Icons.person_rounded, color: AppTheme.primary),
                                    ),
                                    title: Text(session.name, style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                                    subtitle: Text('ID: ${session.userId}', style: const TextStyle(color: AppTheme.textSecondary, fontSize: 11)),
                                    trailing: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        IconButton(
                                          icon: const Icon(Icons.login_rounded, color: AppTheme.income),
                                          onPressed: () => appState.switchSession(session),
                                        ),
                                        IconButton(
                                          icon: const Icon(Icons.delete_outline_rounded, color: AppTheme.expense),
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

  // 1. Splitted Premium layout for web/desktop screen width
  Widget _buildSplitLayout(bool isLoading) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Left side: 3D rotating card showcase & brand info
        Expanded(
          flex: 12,
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const NeonCardShowcase(),
              const SizedBox(height: 48),
              
              // Key Features
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
        
        // Vertical spacer
        Container(
          height: 450,
          width: 1.5,
          color: Colors.white.withOpacity(0.08),
          margin: const EdgeInsets.symmetric(horizontal: 40),
        ),

        // Right side: Login Panel
        Expanded(
          flex: 10,
          child: _buildLoginPanel(isLoading, true),
        ),
      ],
    );
  }

  // 2. Focused layout for mobile screen width
  Widget _buildMobileLayout(bool isLoading) {
    return Container(
      constraints: const BoxConstraints(maxWidth: 420),
      child: _buildLoginPanel(isLoading, false),
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

  Widget _buildLoginPanel(bool isLoading, bool isDesktop) {
    return GlassCard(
      borderOpacity: 0.12,
      padding: EdgeInsets.symmetric(horizontal: isDesktop ? 36 : 24, vertical: 40),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Bouncing/glowing logo
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
                      size: 40,
                      color: Colors.white,
                    ),
                  ),
                );
              },
            ),
          ),
          const SizedBox(height: 24),
          
          const Center(
            child: Text(
              'Finance Tracker',
              style: TextStyle(
                fontSize: 26,
                fontWeight: FontWeight.bold,
                letterSpacing: 0.5,
                color: AppTheme.textPrimary,
              ),
            ),
          ),
          const SizedBox(height: 8),
          const Center(
            child: Text(
              'Введите код из Telegram бота для синхронизации',
              style: TextStyle(color: AppTheme.textSecondary, fontSize: 13.5),
              textAlign: TextAlign.center,
            ),
          ),
          
          const SizedBox(height: 36),

          // Digital code grid
          _buildOTPInput(),
          
          const SizedBox(height: 10),

          // Paste from clipboard button
          Center(
            child: TextButton.icon(
              onPressed: isLoading ? null : _pasteFromClipboard,
              icon: const Icon(Icons.paste_rounded, size: 16, color: AppTheme.secondary),
              label: const Text(
                'Вставить скопированное',
                style: TextStyle(
                  color: AppTheme.secondary,
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                ),
              ),
              style: TextButton.styleFrom(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              ),
            ),
          ),

          const SizedBox(height: 8),

          // Save login checkbox
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Checkbox(
                value: _saveLogin,
                onChanged: (val) {
                  if (val != null) {
                    setState(() => _saveLogin = val);
                  }
                },
                activeColor: AppTheme.primary,
                checkColor: Colors.white,
              ),
              const Text(
                'Сохранить вход на устройстве',
                style: TextStyle(color: AppTheme.textPrimary, fontSize: 12.5),
              ),
            ],
          ),

          const SizedBox(height: 16),

          // Error display
          if (_errorMessage.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 16.0),
              child: Text(
                _errorMessage,
                style: const TextStyle(color: AppTheme.expense, fontSize: 13, fontWeight: FontWeight.w500),
                textAlign: TextAlign.center,
              ),
            ),

          // Action button
          ElevatedButton(
            onPressed: isLoading ? null : _submitCode,
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
                    : const Text(
                        'Войти в аккаунт',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                          letterSpacing: 0.5,
                        ),
                      ),
              ),
            ),
          ),
          
          const SizedBox(height: 24),
          
          // Registration guide section
          Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.02),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white.withOpacity(0.05)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const Text(
                  '💡 Как получить код для входа?',
                  style: TextStyle(color: Colors.white70, fontSize: 13, fontWeight: FontWeight.bold),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 8),
                const Text(
                  '1. Откройте нашего Telegram бота @FIntrack24_bot\n'
                  '2. Нажмите Запустить (/start) или напишите /login\n'
                  '3. Скопируйте сгенерированный 6-значный код и вставьте его выше.',
                  style: TextStyle(color: Colors.white30, fontSize: 11.5, height: 1.4),
                ),
                const SizedBox(height: 12),
                ElevatedButton.icon(
                  onPressed: () async {
                    final url = Uri.parse('https://t.me/FIntrack24_bot');
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
                    backgroundColor: const Color(0xFF24A1DE), // Telegram color
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
    );
  }

  Widget _buildNameOnboardingPanel(AppState appState) {
    final isLoading = appState.isLoading;
    return Container(
      constraints: const BoxConstraints(maxWidth: 420),
      child: GlassCard(
        borderOpacity: 0.12,
        padding: const EdgeInsets.all(32),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          mainAxisSize: MainAxisSize.min,
          children: [
            const Center(
              child: Icon(
                Icons.face_rounded,
                size: 64,
                color: AppTheme.secondary,
              ),
            ),
            const SizedBox(height: 24),
            const Center(
              child: Text(
                'Добро пожаловать!',
                style: TextStyle(
                  fontSize: 22,
                  fontWeight: FontWeight.bold,
                  color: Colors.white,
                ),
              ),
            ),
            const SizedBox(height: 8),
            const Center(
              child: Text(
                'Как к вам обращаться в приложении?',
                style: TextStyle(color: AppTheme.textSecondary, fontSize: 14),
                textAlign: TextAlign.center,
              ),
            ),
            const SizedBox(height: 24),
            TextField(
              controller: _nameController,
              style: const TextStyle(color: AppTheme.textPrimary),
              decoration: InputDecoration(
                labelText: 'Ваше имя',
                labelStyle: const TextStyle(color: AppTheme.textSecondary),
                hintText: 'Иван',
                hintStyle: const TextStyle(color: Colors.white24),
                filled: true,
                fillColor: AppTheme.surfaceCard,
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: AppTheme.border),
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12),
                  borderSide: const BorderSide(color: AppTheme.primary, width: 2),
                ),
              ),
            ),
            const SizedBox(height: 24),
            ElevatedButton(
              onPressed: isLoading
                  ? null
                  : () async {
                      final name = _nameController.text.trim();
                      if (name.isEmpty) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Введите имя')),
                        );
                        return;
                      }
                      await appState.submitOnboardingName(name);
                    },
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
                      : const Text(
                          'Продолжить',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                            letterSpacing: 0.5,
                          ),
                        ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// 3D card display widget
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
            ..setEntry(3, 2, 0.001) // perspective
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
                // Glowing background shine inside card
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
                // Card Details
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
