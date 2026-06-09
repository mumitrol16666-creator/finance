import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:typed_data';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/models.dart';
import '../utils/currency_utils.dart' as cu;

class UserSession {
  final String token;
  final int userId;
  final String name;

  UserSession({required this.token, required this.userId, required this.name});

  Map<String, dynamic> toJson() => {
    'token': token,
    'userId': userId,
    'name': name,
  };

  factory UserSession.fromJson(Map<String, dynamic> json) {
    return UserSession(
      token: json['token'] as String,
      userId: json['userId'] as int,
      name: json['name'] as String? ?? 'Пользователь ${json['userId']}',
    );
  }
}

class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;

  ChatMessage({required this.text, required this.isUser, required this.timestamp});
}

class AppState extends ChangeNotifier {
  bool _isAuthenticated = false;
  bool get isAuthenticated => _isAuthenticated;

  int? _currentUserId;
  int? get currentUserId => _currentUserId;

  bool _appTutorialCompleted = false;
  bool get appTutorialCompleted => _appTutorialCompleted;

  bool _appTutorialStatusLoaded = false;
  bool get appTutorialStatusLoaded => _appTutorialStatusLoaded;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  bool _isPremium = false;
  bool get isPremium => _isPremium;

  String? _premiumExpirationDate;
  String? get premiumExpirationDate => _premiumExpirationDate;

  List<String> _availableFeatures = [];
  List<String> get availableFeatures => _availableFeatures;

  List<QuickAddTemplate> _quickAddTemplates = [];
  List<QuickAddTemplate> get quickAddTemplates => _quickAddTemplates;

  bool hasFeature(String feature) {
    return _isPremium || _availableFeatures.contains(feature);
  }

  // Personalization & Dynamic cycles properties
  String? _userName;
  String? get userName => _userName;

  int _budgetCycleStartDay = 1;
  int get budgetCycleStartDay => _budgetCycleStartDay;

  int _cycleIncome = 0;
  int get cycleIncome => _cycleIncome;

  int _cycleExpenses = 0;
  int get cycleExpenses => _cycleExpenses;

  int _activeDaysCount = 0;
  int get activeDaysCount => _activeDaysCount;

  int _totalCycleDays = 30;
  int get totalCycleDays => _totalCycleDays;

  String? _cycleStart;
  String? get cycleStart => _cycleStart;

  String? _cycleEnd;
  String? get cycleEnd => _cycleEnd;

  int _currentStreak = 0;
  int get currentStreak => _currentStreak;

  int _maxStreak = 0;
  int get maxStreak => _maxStreak;

  bool _needsOnboardingName = false;
  bool get needsOnboardingName => _needsOnboardingName;

  List<UserSession> _savedSessions = [];
  List<UserSession> get savedSessions => _savedSessions;

  // Temp storage for onboarding
  String? _tempToken;
  int? _tempUserId;
  bool? _tempSaveLogin;

  // Real data — loaded from server after login
  bool _isBusinessMode = false;
  bool get isBusinessMode => _isBusinessMode;

  void toggleBusinessMode(bool val) {
    _isBusinessMode = val;
    notifyListeners();
  }

  List<Account> _accounts = [];
  List<Account> get accounts => _accounts.where((acc) => acc.isBusiness == _isBusinessMode).toList();

  List<Category> _categories = [];
  List<Category> get categories => _categories.where((cat) => cat.isBusiness == _isBusinessMode).toList();

  List<Transaction> _transactions = [];
  List<Transaction> get transactions {
    final activeAccNames = accounts.map((a) => a.name).toSet();
    return _transactions.where((tx) => activeAccNames.contains(tx.accountName)).toList();
  }

  List<bool> _weeklyStreak = [false, false, false, false, false, false, false];
  List<bool> get weeklyStreak => _weeklyStreak;

  List<ChatMessage> _chatHistory = [];
  List<ChatMessage> get chatHistory => _chatHistory;

  // Server-converted balances (already converted to base currency)
  int _serverTotalBalance = 0;
  int _serverSavingsBalance = 0;
  int _serverDepositBalance = 0;

  // Exchange rates from server (currency -> rate_to_usd)
  Map<String, double> _exchangeRates = {};
  Map<String, double> _customRatesOverride = {};

  Map<String, double> get exchangeRates => {..._exchangeRates, ..._customRatesOverride};
  Map<String, double> get customRatesOverride => _customRatesOverride;

  String? _ratesUpdatedAt;
  String? get ratesUpdatedAt => _ratesUpdatedAt;

  // User's preferred base currency
  String _baseCurrency = 'KZT';
  String get baseCurrency => _baseCurrency;

  bool _telegramNotificationsEnabled = true;
  bool get telegramNotificationsEnabled => _telegramNotificationsEnabled;

  bool _pushNotificationsEnabled = true;
  bool get pushNotificationsEnabled => _pushNotificationsEnabled;

  bool _dailyReportEnabled = false;
  bool get dailyReportEnabled => _dailyReportEnabled;

  String _dailyReportTime = '21:00';
  String get dailyReportTime => _dailyReportTime;

  bool _quietHoursEnabled = true;
  bool get quietHoursEnabled => _quietHoursEnabled;

  String _quietHoursStart = '22:00';
  String get quietHoursStart => _quietHoursStart;

  String _quietHoursEnd = '08:00';
  String get quietHoursEnd => _quietHoursEnd;

  String _language = 'ru';
  String get language => _language;

  // Recalculate locally so personal/business mode and custom rates are respected.
  int get totalBalance {
    if (_accounts.isEmpty) return _serverTotalBalance;
    return _recalculateBalance((acc) => !acc.isSaving && acc.accType != 'deposit');
  }

  int get savingsBalance {
    if (_accounts.isEmpty) return _serverSavingsBalance;
    return _recalculateBalance((acc) => acc.isSaving && acc.accType != 'deposit');
  }

  int get depositBalance {
    if (_accounts.isEmpty) return _serverDepositBalance;
    return _recalculateBalance((acc) => acc.accType == 'deposit');
  }

  int _recalculateBalance(bool Function(Account) filter) {
    int total = 0;
    for (final acc in _accounts.where((a) => a.isBusiness == _isBusinessMode && filter(a))) {
      total += convertAmount(acc.balance, acc.currency, _baseCurrency) ?? acc.balance;
    }
    return total;
  }

  int get monthlyExpenses => categories.where((c) => c.kind == 'expense').fold(0, (sum, cat) => sum + cat.spentAmount);
  int get monthlyIncome => categories.where((c) => c.kind == 'income').fold(0, (sum, cat) => sum + cat.spentAmount);

  /// Raw balances grouped by currency (e.g. {'KZT': 250000, 'USD': 1200})
  Map<String, int> get balancesByCurrency {
    final map = <String, int>{};
    for (final acc in _accounts.where((a) => a.isBusiness == _isBusinessMode && !a.isSaving && a.accType != 'deposit')) {
      map[acc.currency] = (map[acc.currency] ?? 0) + acc.balance;
    }
    return map;
  }

  /// Whether user has accounts in multiple currencies
  bool get hasMultipleCurrencies => balancesByCurrency.keys.length > 1;

  /// Convert amount from one currency to another
  int? convertAmount(int amount, String from, String to) {
    return cu.convertCurrency(amount, from, to, exchangeRates);
  }

  String get _customRatesStorageKey => 'custom_rates_override_${_token ?? "anonymous"}';

  Future<void> _loadCustomRates() async {
    final prefs = await SharedPreferences.getInstance();
    final customRatesStr = prefs.getString(_customRatesStorageKey);
    if (customRatesStr == null || customRatesStr.isEmpty) {
      _customRatesOverride = {};
      return;
    }
    try {
      final map = json.decode(customRatesStr) as Map<String, dynamic>;
      _customRatesOverride = map.map((k, v) => MapEntry(k, (v as num).toDouble()));
    } catch (_) {
      _customRatesOverride = {};
    }
  }

  Future<void> _saveCustomRates() async {
    final prefs = await SharedPreferences.getInstance();
    if (_customRatesOverride.isEmpty) {
      await prefs.remove(_customRatesStorageKey);
    } else {
      await prefs.setString(_customRatesStorageKey, json.encode(_customRatesOverride));
    }
  }

  Future<void> setCustomRate(String currency, double rateInBase) async {
    if (currency == _baseCurrency) return;
    final baseRate = _exchangeRates[_baseCurrency] ?? 1.0;
    if (rateInBase > 0) {
      if (currency == 'USD') {
        _customRatesOverride[_baseCurrency] = rateInBase;
        _customRatesOverride['USD'] = 1.0;
      } else {
        _customRatesOverride[currency] = baseRate / rateInBase;
      }
    }
    await _saveCustomRates();
    notifyListeners();
  }

  Future<void> removeCustomRate(String currency) async {
    if (currency == 'USD') {
      _customRatesOverride.remove(_baseCurrency);
      _customRatesOverride.remove('USD');
    } else {
      _customRatesOverride.remove(currency);
    }
    await _saveCustomRates();
    notifyListeners();
  }

  Future<void> clearCustomRates() async {
    _customRatesOverride.clear();
    await _saveCustomRates();
    notifyListeners();
  }

  List<Debt> _debts = [];
  List<Debt> get debts => _debts;

  List<RecurringTemplate> _recurringTemplates = [];
  List<RecurringTemplate> get recurringTemplates => _recurringTemplates;

  List<PlannedTx> _plannedEvents = [];
  List<PlannedTx> get plannedEvents => _plannedEvents;

  String? _token;
  final String _baseUrl = 'http://178.105.162.123:8000';

  String _apiError(http.Response response, String fallback) {
    try {
      return (json.decode(response.body)['detail'] ?? fallback).toString();
    } catch (_) {
      return fallback;
    }
  }

  // Authentication & Session management
  Future<void> initSessions() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final jsonStr = prefs.getString('saved_sessions');
      if (jsonStr != null) {
        final list = json.decode(jsonStr) as List;
        _savedSessions = list.map((item) => UserSession.fromJson(item as Map<String, dynamic>)).toList();
      }
      
      final activeToken = prefs.getString('active_token');
      if (activeToken != null && _savedSessions.isNotEmpty) {
        final session = _savedSessions.firstWhere((s) => s.token == activeToken, orElse: () => _savedSessions.first);
        _token = session.token;
        _currentUserId = session.userId;
        _appTutorialCompleted = false;
        _appTutorialStatusLoaded = false;
        await _loadCustomRates();
        _isAuthenticated = true;
        notifyListeners();
        await loadDashboardData();
      }
    } catch (e) {
      print('Init sessions error: $e');
    }
  }

  Future<void> switchSession(UserSession session) async {
    _isLoading = true;
    notifyListeners();
    
    _token = session.token;
    _currentUserId = session.userId;
    _appTutorialCompleted = false;
    _appTutorialStatusLoaded = false;
    _isAuthenticated = true;
    await _loadCustomRates();
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('active_token', session.token);
    
    // Clear old state before load
    _accounts = [];
    _categories = [];
    _transactions = [];
    _debts = [];
    _recurringTemplates = [];
    _plannedEvents = [];
    
    await loadDashboardData();
    
    _isLoading = false;
    notifyListeners();
  }

  Future<void> removeSession(UserSession session) async {
    _savedSessions.removeWhere((s) => s.token == session.token);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('saved_sessions', json.encode(_savedSessions.map((s) => s.toJson()).toList()));
    
    if (_token == session.token) {
      logout();
    } else {
      notifyListeners();
    }
  }

  Future<bool> login(String username, String password, {bool saveLogin = true}) async {
    _isLoading = true;
    _needsOnboardingName = false;
    notifyListeners();

    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'username': username,
          'password': password,
        }),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final token = data['token'] as String;
        final userId = data['user_id'] as int;
        final name = data['name'] as String;

        _token = token;
        _currentUserId = userId;
        _appTutorialCompleted = false;
        _appTutorialStatusLoaded = false;
        await _loadCustomRates();
        _isAuthenticated = true;
        _isLoading = false;
        
        _accounts = [];
        _categories = [];
        _transactions = [];
        _debts = [];
        _recurringTemplates = [];
        _plannedEvents = [];
        
        if (saveLogin) {
          final existingIndex = _savedSessions.indexWhere((s) => s.userId == userId);
          final newSession = UserSession(token: token, userId: userId, name: name);
          if (existingIndex >= 0) {
            _savedSessions[existingIndex] = newSession;
          } else {
            _savedSessions.add(newSession);
          }
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('active_token', token);
          await prefs.setString('saved_sessions', json.encode(_savedSessions.map((s) => s.toJson()).toList()));
        }
        
        notifyListeners();
        await loadDashboardData();
        return true;
      }
    } catch (e) {
      print('Login error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
    return false;
  }

  Future<String?> register(String displayName, String username, String password, String confirmPassword, {bool saveLogin = true}) async {
    _isLoading = true;
    _needsOnboardingName = false;
    notifyListeners();

    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/auth/register'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({
          'display_name': displayName,
          'username': username,
          'password': password,
          'confirm_password': confirmPassword,
        }),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final token = data['token'] as String;
        final userId = data['user_id'] as int;
        final name = data['name'] as String;

        _token = token;
        _currentUserId = userId;
        _appTutorialCompleted = false;
        _appTutorialStatusLoaded = false;
        await _loadCustomRates();
        _isAuthenticated = true;
        _isLoading = false;
        
        _accounts = [];
        _categories = [];
        _transactions = [];
        _debts = [];
        _recurringTemplates = [];
        _plannedEvents = [];
        
        if (saveLogin) {
          final existingIndex = _savedSessions.indexWhere((s) => s.userId == userId);
          final newSession = UserSession(token: token, userId: userId, name: name);
          if (existingIndex >= 0) {
            _savedSessions[existingIndex] = newSession;
          } else {
            _savedSessions.add(newSession);
          }
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('active_token', token);
          await prefs.setString('saved_sessions', json.encode(_savedSessions.map((s) => s.toJson()).toList()));
        }
        
        notifyListeners();
        await loadDashboardData();
        return null;
      } else {
        final data = json.decode(response.body);
        return data['detail'] ?? 'Ошибка регистрации';
      }
    } catch (e) {
      print('Register error: $e');
      return 'Сетевая ошибка при регистрации';
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> isUsernameAvailable(String username) async {
    if (username.trim().isEmpty) return false;
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/auth/check-username?username=${Uri.encodeComponent(username.trim())}'),
      );
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return data['available'] as bool;
      }
    } catch (e) {
      print('Check username error: $e');
    }
    return false;
  }

  Future<void> updateSettings({
    int? budgetCycleStartDay,
    String? currency,
    String? language,
    bool? telegramNotificationsEnabled,
    bool? pushNotificationsEnabled,
    bool? dailyReportEnabled,
    String? dailyReportTime,
    bool? quietHoursEnabled,
    String? quietHoursStart,
    String? quietHoursEnd,
    bool? appTutorialCompleted,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();

    try {
      final Map<String, dynamic> bodyMap = {};
      if (budgetCycleStartDay != null) bodyMap['budget_cycle_start_day'] = budgetCycleStartDay;
      if (currency != null) bodyMap['currency'] = currency;
      if (language != null) bodyMap['lang'] = language;
      if (telegramNotificationsEnabled != null) bodyMap['telegram_notifications_enabled'] = telegramNotificationsEnabled;
      if (pushNotificationsEnabled != null) bodyMap['push_notifications_enabled'] = pushNotificationsEnabled;
      if (dailyReportEnabled != null) bodyMap['daily_report_enabled'] = dailyReportEnabled;
      if (dailyReportTime != null) bodyMap['daily_report_time'] = dailyReportTime;
      if (quietHoursEnabled != null) bodyMap['quiet_hours_enabled'] = quietHoursEnabled;
      if (quietHoursStart != null) bodyMap['quiet_hours_start'] = quietHoursStart;
      if (quietHoursEnd != null) bodyMap['quiet_hours_end'] = quietHoursEnd;
      if (appTutorialCompleted != null) bodyMap['app_tutorial_completed'] = appTutorialCompleted;

      final response = await http.post(
        Uri.parse('$_baseUrl/api/user/settings'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode(bodyMap),
      );

      if (response.statusCode == 200) {
        if (appTutorialCompleted != null) {
          _appTutorialCompleted = appTutorialCompleted;
          _appTutorialStatusLoaded = true;
        }
        if (currency != null && currency != _baseCurrency) {
          await clearCustomRates();
          _baseCurrency = currency;
        }
        await loadDashboardData();
      } else {
        throw Exception(_apiError(response, 'Не удалось обновить настройки'));
      }
    } catch (e) {
      print('Update settings error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateCategory(int categoryId, {
    String? name,
    String? emoji,
    int? limitAmount,
    int? defaultAccountId,
    bool? excludeFromAnalytics,
    double? warnThreshold,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final Map<String, dynamic> bodyMap = {};
      if (name != null) bodyMap['name'] = name;
      if (emoji != null) bodyMap['emoji'] = emoji;
      if (limitAmount != null) bodyMap['limit_amount'] = limitAmount;
      if (defaultAccountId != null) {
        bodyMap['default_account_id'] = defaultAccountId;
      }
      if (excludeFromAnalytics != null) {
        bodyMap['exclude_from_analytics'] = excludeFromAnalytics ? 1 : 0;
      }
      if (warnThreshold != null) {
        bodyMap['warn_threshold'] = warnThreshold;
      }

      final response = await http.put(
        Uri.parse('$_baseUrl/api/categories/$categoryId'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode(bodyMap),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(json.decode(response.body)['detail'] ?? 'Failed to update category');
      }
    } catch (e) {
      print('Update category error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<String> fetchAIBudgetAudit({String? refDate, String? startDate, String? endDate}) async {
    if (_token == null) return "Ошибка авторизации";
    try {
      Uri uri;
      if (startDate != null && endDate != null) {
        uri = Uri.parse('$_baseUrl/api/analytics/ai-audit?start_date=$startDate&end_date=$endDate');
      } else if (refDate != null) {
        uri = Uri.parse('$_baseUrl/api/analytics/ai-audit?ref_date=$refDate');
      } else {
        uri = Uri.parse('$_baseUrl/api/analytics/ai-audit');
      }
      final response = await http.post(
        uri,
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        return data['audit'] as String? ?? "Анализ не получен";
      } else {
        final err = json.decode(response.body)['detail'] ?? "Не удалось получить ИИ-анализ";
        return err.toString();
      }
    } catch (e) {
      print('Fetch AI Audit error: $e');
      return "Ошибка соединения с сервером";
    }
  }

  Future<void> loadDashboardData({String? refDate, String? startDate, String? endDate}) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();

    try {
      Uri uri;
      if (startDate != null && endDate != null) {
        uri = Uri.parse('$_baseUrl/api/dashboard?start_date=$startDate&end_date=$endDate');
      } else if (refDate != null) {
        uri = Uri.parse('$_baseUrl/api/dashboard?ref_date=$refDate');
      } else {
        uri = Uri.parse('$_baseUrl/api/dashboard');
      }
      final response = await http.get(
        uri,
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        await loadQuickAddTemplates();
        
        // Parse accounts
        _accounts = (data['accounts'] as List)
            .map((a) => Account.fromJson(a as Map<String, dynamic>))
            .toList();
            
        // Parse categories
        _categories = (data['categories'] as List)
            .map((c) => Category.fromJson(c as Map<String, dynamic>))
            .toList();
            
        // Parse transactions
        _transactions = (data['recentTransactions'] as List)
            .map((t) => Transaction.fromJson(t as Map<String, dynamic>))
            .toList();
            
        // Parse weekly streak
        _weeklyStreak = List<bool>.from(data['weeklyStreak'] as List);
        
        // Parse premium details
        _isPremium = data['isPremium'] as bool? ?? false;
        _premiumExpirationDate = data['premiumExpirationDate'] as String?;
        _availableFeatures = List<String>.from(data['availableFeatures'] as List? ?? []);

        // Parse personalization & cycle stats
        _userName = data['userName'] as String?;
        _budgetCycleStartDay = data['budgetCycleStartDay'] as int? ?? 1;
        _cycleIncome = data['cycleIncome'] as int? ?? 0;
        _cycleExpenses = data['cycleExpenses'] as int? ?? 0;
        _activeDaysCount = data['activeDaysCount'] as int? ?? 0;
        _totalCycleDays = data['totalCycleDays'] as int? ?? 30;
        _cycleStart = data['cycleStart'] as String?;
        _cycleEnd = data['cycleEnd'] as String?;
        _currentStreak = data['currentStreak'] as int? ?? 0;
        _maxStreak = data['maxStreak'] as int? ?? 0;

        // Parse server-converted balances (already converted to base currency)
        _serverTotalBalance = data['totalBalance'] as int? ?? 0;
        _serverSavingsBalance = data['savingsBalance'] as int? ?? 0;
        _serverDepositBalance = data['depositBalance'] as int? ?? 0;

        // Parse base currency
        _baseCurrency = data['baseCurrency'] as String? ?? 'KZT';

        // Parse exchange rates
        final ratesData = data['exchangeRates'] as Map<String, dynamic>?;
        if (ratesData != null) {
          final ratesMap = ratesData['rates'] as Map<String, dynamic>?;
          if (ratesMap != null) {
            _exchangeRates = ratesMap.map((k, v) => MapEntry(k, (v as num?)?.toDouble() ?? 0.0));
          }
          _ratesUpdatedAt = ratesData['updated_at'] as String?;
        }
      }

      await Future.wait([
        _fetchDebtsSilent(),
        _fetchRecurringSilent(),
        _fetchPlannedSilent(),
        _fetchSettingsSilent(),
      ]);
    } catch (e) {
      print('Load dashboard error: $e');
    }

    _isLoading = false;
    notifyListeners();
  }

  Future<void> _fetchDebtsSilent() async {
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/debts'),
        headers: {'Authorization': 'Bearer $_token'},
      );
      if (response.statusCode == 200) {
        final list = json.decode(response.body) as List;
        _debts = list.map((item) => Debt.fromJson(item as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
  }

  Future<void> _fetchSettingsSilent() async {
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/user/settings'),
        headers: {'Authorization': 'Bearer $_token'},
      );
      if (response.statusCode == 200) {
        final data = json.decode(response.body) as Map<String, dynamic>;
        _telegramNotificationsEnabled = (data['telegram_notifications_enabled'] as int? ?? 1) == 1;
        _pushNotificationsEnabled = (data['push_notifications_enabled'] as int? ?? 1) == 1;
        _dailyReportEnabled = (data['daily_report_enabled'] as int? ?? 0) == 1;
        _dailyReportTime = data['daily_report_time'] as String? ?? '21:00';
        _quietHoursEnabled = (data['quiet_hours_enabled'] as int? ?? 1) == 1;
        _quietHoursStart = data['quiet_hours_start'] as String? ?? '22:00';
        _quietHoursEnd = data['quiet_hours_end'] as String? ?? '08:00';
        _language = data['lang'] as String? ?? 'ru';
        _appTutorialCompleted = (data['app_tutorial_completed'] as int? ?? 0) == 1;
        _appTutorialStatusLoaded = true;
      }
    } catch (_) {}
  }

  Future<void> completeAppTutorial() async {
    await updateSettings(appTutorialCompleted: true);
  }

  Future<void> _fetchRecurringSilent() async {
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/recurring'),
        headers: {'Authorization': 'Bearer $_token'},
      );
      if (response.statusCode == 200) {
        final list = json.decode(response.body) as List;
        _recurringTemplates = list.map((item) => RecurringTemplate.fromJson(item as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
  }

  Future<void> refreshAllData() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      await Future.wait([
        loadDashboardData(),
        _fetchRecurringSilent(),
        _fetchDebtsSilent(),
        _fetchPlannedSilent(),
      ]);
    } catch (e) {
      print('Error refreshing data: $e');
    }
    _isLoading = false;
    notifyListeners();
  }

  Future<void> _fetchPlannedSilent() async {
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/planned'),
        headers: {'Authorization': 'Bearer $_token'},
      );
      if (response.statusCode == 200) {
        final list = json.decode(response.body) as List;
        _plannedEvents = list.map((item) => PlannedTx.fromJson(item as Map<String, dynamic>)).toList();
      }
    } catch (_) {}
  }

  Future<void> loadDebts() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    await _fetchDebtsSilent();
    _isLoading = false;
    notifyListeners();
  }

  Future<void> loadRecurring() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    await _fetchRecurringSilent();
    _isLoading = false;
    notifyListeners();
  }

  Future<void> loadPlanned() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    await _fetchPlannedSilent();
    _isLoading = false;
    notifyListeners();
  }

  void logout() async {
    _token = null;
    _currentUserId = null;
    _appTutorialCompleted = false;
    _appTutorialStatusLoaded = false;
    _isAuthenticated = false;
    _isPremium = false;
    _premiumExpirationDate = null;
    _availableFeatures = [];
    _accounts = [];
    _categories = [];
    _transactions = [];
    _debts = [];
    _recurringTemplates = [];
    _plannedEvents = [];
    _customRatesOverride = {};
    _exchangeRates = {};
    _baseCurrency = 'KZT';
    _weeklyStreak = [false, false, false, false, false, false, false];
    _chatHistory = [
      ChatMessage(
        text: 'Привет! Я твой финансовый ИИ-консультант. Чем я могу помочь тебе сегодня?',
        isUser: false,
        timestamp: DateTime.now(),
      )
    ];
    _userName = null;
    _needsOnboardingName = false;
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('active_token');
    
    notifyListeners();
  }

  // Operations
  Future<void> addTransaction({
    required int amount,
    required String kind,
    required String categoryName,
    required String categoryEmoji,
    required String accountName,
    String? toAccountName,
    String? note,
    double? customRate,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();

    try {
      // Find category_id and account_id
      int? accountId;
      try {
        final acc = _accounts.firstWhere((a) => a.name == accountName);
        accountId = acc.id;
      } catch (_) {}

      if (accountId == null) {
        throw Exception("Account not found");
      }

      int? toAccountId;
      if (toAccountName != null) {
        try {
          final acc = _accounts.firstWhere((a) => a.name == toAccountName);
          toAccountId = acc.id;
        } catch (_) {}
      }

      int? categoryId;
      try {
        final cat = _categories.firstWhere((c) => c.name == categoryName);
        categoryId = cat.id;
      } catch (_) {}

      final Map<String, dynamic> bodyMap = {
        'amount': amount,
        'kind': kind,
        'account_id': accountId,
        'to_account_id': toAccountId,
        'category_id': categoryId,
        'note': note,
      };
      if (customRate != null) {
        bodyMap['custom_rate'] = customRate;
      }

      final response = await http.post(
        Uri.parse('$_baseUrl/api/transactions'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode(bodyMap),
      );

      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        String detail = 'Failed to add transaction';
        try {
          detail = (json.decode(response.body)['detail'] ?? detail).toString();
        } catch (_) {}
        throw Exception(detail);
      }
    } catch (e) {
      print('Add transaction error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<Uint8List?> exportExcelReport(String period) async {
    if (_token == null) return null;
    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/reports/export?period=$period'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        return response.bodyBytes;
      } else {
        print('Export excel response code: ${response.statusCode}');
      }
    } catch (e) {
      print('Export excel error: $e');
    }
    return null;
  }

  Future<void> addAccount({
    required String name,
    required int balance,
    String currency = 'KZT',
    int isSaving = 0,
    String accType = 'regular',
    double interestRate = 0.0,
    String accrualPeriod = 'month',
    int isBusiness = 0,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/accounts'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'name': name,
          'balance': balance,
          'currency': currency,
          'is_saving': isSaving,
          'acc_type': accType,
          'interest_rate': interestRate,
          'accrual_period': accrualPeriod,
          'is_business': isBusiness,
        }),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(json.decode(response.body)['detail'] ?? 'Failed to add account');
      }
    } catch (e) {
      print('Add account error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateAccount(int accountId, {
    String? name,
    int? balance,
    int? isSaving,
    int? isArchived,
    String? accType,
    double? interestRate,
    String? accrualPeriod,
    int? isBusiness,
    String? currency,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final Map<String, dynamic> bodyMap = {};
      if (name != null) bodyMap['name'] = name;
      if (balance != null) bodyMap['balance'] = balance;
      if (isSaving != null) bodyMap['is_saving'] = isSaving;
      if (isArchived != null) bodyMap['is_archived'] = isArchived;
      if (accType != null) bodyMap['acc_type'] = accType;
      if (interestRate != null) bodyMap['interest_rate'] = interestRate;
      if (accrualPeriod != null) bodyMap['accrual_period'] = accrualPeriod;
      if (isBusiness != null) bodyMap['is_business'] = isBusiness;
      if (currency != null) bodyMap['currency'] = currency;

      final response = await http.put(
        Uri.parse('$_baseUrl/api/accounts/$accountId'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode(bodyMap),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(json.decode(response.body)['detail'] ?? 'Failed to update account');
      }
    } catch (e) {
      print('Update account error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> deleteAccount(int accountId) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.delete(
        Uri.parse('$_baseUrl/api/accounts/$accountId'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(json.decode(response.body)['detail'] ?? 'Failed to delete account');
      }
    } catch (e) {
      print('Delete account error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> addDebt({
    required String title,
    required int remainingAmount,
    required String direction,
    required String dtype,
    int? paymentAmount,
    String? nextPaymentDate,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/debts'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'title': title,
          'remaining_amount': remainingAmount,
          'direction': direction,
          'dtype': dtype,
          'payment_amount': paymentAmount,
          'next_payment_date': nextPaymentDate,
        }),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(_apiError(response, 'Не удалось добавить долг'));
      }
    } catch (e) {
      print('Add debt error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> payDebt(int debtId, {required int amount, int? accountId, String? nextPaymentDate}) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final Map<String, dynamic> bodyMap = {
        'payment_amount': amount,
        'next_payment_date': nextPaymentDate,
      };
      if (accountId != null) {
        bodyMap['account_id'] = accountId;
      }
      final response = await http.post(
        Uri.parse('$_baseUrl/api/debts/$debtId/pay'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode(bodyMap),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(_apiError(response, 'Не удалось внести платеж'));
      }
    } catch (e) {
      print('Pay debt error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> setDebtReminder(int debtId, {required bool enabled, required int daysBefore}) async {
    if (_token == null) return;
    final response = await http.post(
      Uri.parse('$_baseUrl/api/debts/$debtId/reminder'),
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer $_token',
      },
      body: json.encode({'enabled': enabled, 'days_before': daysBefore}),
    );
    if (response.statusCode != 200) {
      throw Exception(_apiError(response, 'Не удалось сохранить напоминание'));
    }
    await _fetchDebtsSilent();
    notifyListeners();
  }

  Future<void> addRecurring({
    required String title,
    required int amount,
    required int categoryId,
    required int accountId,
    required int dayOfMonth,
    required String kind,
    String? comment,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/recurring'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'title': title,
          'amount': amount,
          'category_id': categoryId,
          'account_id': accountId,
          'day_of_month': dayOfMonth,
          'kind': kind,
          'comment': comment,
        }),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(_apiError(response, 'Не удалось создать регулярный платеж'));
      }
    } catch (e) {
      print('Add recurring error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> addCategory({
    required String name,
    String emoji = '📦',
    String kind = 'expense',
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/categories'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'name': name,
          'emoji': emoji,
          'kind': kind,
        }),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception('Ошибка при добавлении категории: ${response.body}');
      }
    } catch (e) {
      _isLoading = false;
      notifyListeners();
      rethrow;
    }
    _isLoading = false;
    notifyListeners();
  }

  Future<void> deleteCategory(int categoryId) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.delete(
        Uri.parse('$_baseUrl/api/categories/$categoryId'),
        headers: {'Authorization': 'Bearer $_token'},
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception('Ошибка при удалении категории: ${response.body}');
      }
    } catch (e) {
      _isLoading = false;
      notifyListeners();
      rethrow;
    }
    _isLoading = false;
    notifyListeners();
  }

  Future<void> addPlanned({
    required String title,
    required int amount,
    required int categoryId,
    required int accountId,
    required String plannedDate,
    required String kind,
    String? comment,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/planned'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'title': title,
          'amount': amount,
          'category_id': categoryId,
          'account_id': accountId,
          'planned_date': plannedDate,
          'kind': kind,
          'comment': comment,
        }),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception(_apiError(response, 'Не удалось создать плановую операцию'));
      }
    } catch (e) {
      print('Add planned error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> saveBudget({required int categoryId, required int amount}) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/budgets'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'category_id': categoryId,
          'amount': amount,
        }),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      }
    } catch (e) {
      print('Save budget error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> wipeUserData() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/auth/reset'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        logout();
      }
    } catch (e) {
      print('Wipe user data error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> deleteUserAccount() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/auth/delete-account'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        logout();
      }
    } catch (e) {
      print('Delete user account error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  // AI Chat
  Future<void> sendAiMessage(String text) async {
    if (text.trim().isEmpty) return;
    if (_token == null) return;
    if (!hasFeature('ai')) {
      throw Exception('premium_required');
    }

    final userMessage = ChatMessage(text: text, isUser: true, timestamp: DateTime.now());
    _chatHistory.add(userMessage);
    notifyListeners();

    _isLoading = true;
    notifyListeners();

    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/chat'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({'text': text}),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final reply = data['text'] as String;
        _chatHistory.add(ChatMessage(text: reply, isUser: false, timestamp: DateTime.now()));
      } else if (response.statusCode == 403) {
        _chatHistory.remove(userMessage);
        throw Exception('premium_required');
      } else {
        _chatHistory.add(ChatMessage(
          text: 'Ошибка связи с сервером. Пожалуйста, попробуйте позже.',
          isUser: false,
          timestamp: DateTime.now(),
        ));
      }
    } catch (e) {
      print('Chat error: $e');
      if (e.toString().contains('premium_required')) {
        _isLoading = false;
        notifyListeners();
        rethrow;
      }
      _chatHistory.add(ChatMessage(text: 'Ошибка сети. Проверьте подключение.', isUser: false, timestamp: DateTime.now()));
    }

    _isLoading = false;
    notifyListeners();
  }

  Future<void> deleteTransaction(int txId) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.delete(
        Uri.parse('$_baseUrl/api/transactions/$txId'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      }
    } catch (e) {
      print('Delete transaction error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> updateTransaction({
    required int tx_id,
    int? amount,
    String? note,
  }) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final Map<String, dynamic> bodyMap = {};
      if (amount != null) bodyMap['amount'] = amount;
      if (note != null) bodyMap['note'] = note;

      final response = await http.put(
        Uri.parse('$_baseUrl/api/transactions/$tx_id'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode(bodyMap),
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      }
    } catch (e) {
      print('Update transaction error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> completePlanned(int plannedId) async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();
    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/planned/$plannedId/done'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );
      if (response.statusCode == 200) {
        await loadDashboardData();
      } else {
        throw Exception('Failed to complete planned payment');
      }
    } catch (e) {
      print('Complete planned error: $e');
      rethrow;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> executePlanned(int plannedId) async {
    if (_token == null) return;
    final response = await http.post(
      Uri.parse('$_baseUrl/api/planned/$plannedId/execute'),
      headers: {'Authorization': 'Bearer $_token'},
    );
    if (response.statusCode != 200) {
      throw Exception(_apiError(response, 'Не удалось внести запланированную операцию'));
    }
    await loadDashboardData();
  }

  Future<void> loadQuickAddTemplates() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = prefs.getString('quick_add_templates');
    if (jsonStr != null && jsonStr.isNotEmpty) {
      try {
        final List<dynamic> list = json.decode(jsonStr);
        _quickAddTemplates = list.map((x) => QuickAddTemplate.fromJson(x as Map<String, dynamic>)).toList();
        notifyListeners();
        return;
      } catch (e) {
        print('Error loading quick add templates: $e');
      }
    }
    // Default templates
    _quickAddTemplates = [
      QuickAddTemplate(id: 1, title: 'Кофе', amount: 800, categoryName: 'Еда и рестораны', categoryEmoji: '🍔'),
      QuickAddTemplate(id: 2, title: 'Такси', amount: 1500, categoryName: 'Транспорт', categoryEmoji: '🚗'),
      QuickAddTemplate(id: 3, title: 'Обед', amount: 2500, categoryName: 'Еда и рестораны', categoryEmoji: '🍔'),
      QuickAddTemplate(id: 4, title: 'Подписка', amount: 2000, categoryName: 'Услуги', categoryEmoji: '🛠️'),
    ];
    await saveQuickAddTemplates();
  }

  Future<void> saveQuickAddTemplates() async {
    final prefs = await SharedPreferences.getInstance();
    final jsonStr = json.encode(_quickAddTemplates.map((x) => x.toJson()).toList());
    await prefs.setString('quick_add_templates', jsonStr);
    notifyListeners();
  }

  Future<void> updateQuickAddTemplate(int id, {required String title, required int amount, required String categoryName, required String categoryEmoji}) async {
    final idx = _quickAddTemplates.indexWhere((x) => x.id == id);
    if (idx != -1) {
      _quickAddTemplates[idx] = QuickAddTemplate(
        id: id,
        title: title,
        amount: amount,
        categoryName: categoryName,
        categoryEmoji: categoryEmoji,
      );
      await saveQuickAddTemplates();
    }
  }
}
