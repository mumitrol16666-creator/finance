import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import '../models/models.dart';

class ChatMessage {
  final String text;
  final bool isUser;
  final DateTime timestamp;

  ChatMessage({required this.text, required this.isUser, required this.timestamp});
}

class AppState extends ChangeNotifier {
  bool _isAuthenticated = false;
  bool get isAuthenticated => _isAuthenticated;

  bool _isLoading = false;
  bool get isLoading => _isLoading;

  // Mock data for initial layout testing
  List<Account> _accounts = [
    Account(id: 1, name: 'Наличные', balance: 1880000), // 18,800.00 minor units
    Account(id: 2, name: 'Kaspi Gold', balance: 15450000), // 154,500.00
  ];
  List<Account> get accounts => _accounts;

  List<Category> _categories = [
    Category(id: 1, name: 'Еда', emoji: '🍔', limitAmount: 15000000, spentAmount: 6420000),
    Category(id: 2, name: 'Транспорт', emoji: '🚕', limitAmount: 3000000, spentAmount: 1200000),
    Category(id: 3, name: 'Развлечения', emoji: '🎬', limitAmount: 5000000, spentAmount: 4800000),
    Category(id: 4, name: 'Дом', emoji: '🏠', limitAmount: 20000000, spentAmount: 15000000),
  ];
  List<Category> get categories => _categories;

  List<Transaction> _transactions = [
    Transaction(
      id: 101,
      amount: 120000, // 1,200.00
      kind: 'expense',
      categoryName: 'Еда',
      categoryEmoji: '🍔',
      accountName: 'Наличные',
      note: 'Кофе с другом попили',
      timestamp: DateTime.now().subtract(const Duration(minutes: 5)),
    ),
    Transaction(
      id: 102,
      amount: 450000,
      kind: 'expense',
      categoryName: 'Развлечения',
      categoryEmoji: '🎬',
      accountName: 'Kaspi Gold',
      note: 'Билеты в кино',
      timestamp: DateTime.now().subtract(const Duration(hours: 3)),
    ),
    Transaction(
      id: 103,
      amount: 35000000, // 350,000.00
      kind: 'income',
      categoryName: 'Зарплата',
      categoryEmoji: '💰',
      accountName: 'Kaspi Gold',
      note: 'Аванс за май',
      timestamp: DateTime.now().subtract(const Duration(days: 1)),
    ),
  ];
  List<Transaction> get transactions => _transactions;

  // Streak tracker [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
  List<bool> _weeklyStreak = [true, true, false, false, false, false, false];
  List<bool> get weeklyStreak => _weeklyStreak;

  List<ChatMessage> _chatHistory = [
    ChatMessage(
      text: 'Привет! Я твой финансовый ИИ-консультант. Чем я могу помочь тебе сегодня?',
      isUser: false,
      timestamp: DateTime.now().subtract(const Duration(hours: 1)),
    )
  ];
  List<ChatMessage> get chatHistory => _chatHistory;

  int get totalBalance => _accounts.fold(0, (sum, acc) => sum + acc.balance);
  int get monthlyExpenses => _categories.fold(0, (sum, cat) => sum + cat.spentAmount);

  String? _token;
  final String _baseUrl = 'http://178.105.162.123:8000';

  // Authentication
  Future<bool> verifyLoginCode(String code) async {
    _isLoading = true;
    notifyListeners();

    try {
      final response = await http.post(
        Uri.parse('$_baseUrl/api/auth/verify'),
        headers: {'Content-Type': 'application/json'},
        body: json.encode({'code': code}),
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        _token = data['token'] as String;
        _isAuthenticated = true;
        _isLoading = false;
        notifyListeners();
        await loadDashboardData();
        return true;
      }
    } catch (e) {
      print('Verification error: $e');
    }

    _isLoading = false;
    notifyListeners();
    return false;
  }

  Future<void> loadDashboardData() async {
    if (_token == null) return;
    _isLoading = true;
    notifyListeners();

    try {
      final response = await http.get(
        Uri.parse('$_baseUrl/api/dashboard'),
        headers: {
          'Authorization': 'Bearer $_token',
        },
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        
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
      }
    } catch (e) {
      print('Load dashboard error: $e');
    }

    _isLoading = false;
    notifyListeners();
  }

  void logout() {
    _token = null;
    _isAuthenticated = false;
    _chatHistory = [
      ChatMessage(
        text: 'Привет! Я твой финансовый ИИ-консультант. Чем я могу помочь тебе сегодня?',
        isUser: false,
        timestamp: DateTime.now(),
      )
    ];
    notifyListeners();
  }

  // Operations
  Future<void> addTransaction({
    required int amount,
    required String kind,
    required String categoryName,
    required String categoryEmoji,
    required String accountName,
    String? note,
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

      int? categoryId;
      try {
        final cat = _categories.firstWhere((c) => c.name == categoryName);
        categoryId = cat.id;
      } catch (_) {}

      final response = await http.post(
        Uri.parse('$_baseUrl/api/transactions'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $_token',
        },
        body: json.encode({
          'amount': amount,
          'kind': kind,
          'account_id': accountId,
          'category_id': categoryId,
          'note': note,
        }),
      );

      if (response.statusCode == 200) {
        await loadDashboardData();
      }
    } catch (e) {
      print('Add transaction error: $e');
    }

    _isLoading = false;
    notifyListeners();
  }

  // AI Chat
  Future<void> sendAiMessage(String text) async {
    if (text.trim().isEmpty) return;
    if (_token == null) return;

    _chatHistory.add(ChatMessage(text: text, isUser: true, timestamp: DateTime.now()));
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
      } else {
        _chatHistory.add(ChatMessage(
          text: 'Ошибка связи с сервером. Пожалуйста, попробуйте позже.',
          isUser: false,
          timestamp: DateTime.now(),
        ));
      }
    } catch (e) {
      print('Chat error: $e');
      _chatHistory.add(ChatMessage(
        text: 'Ошибка сети. Проверьте подключение.',
        isUser: false,
        timestamp: DateTime.now(),
      ));
    }

    _isLoading = false;
    notifyListeners();
  }
}
