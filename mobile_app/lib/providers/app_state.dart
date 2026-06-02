import 'package:flutter/material.dart';
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

  // Authentication
  Future<bool> verifyLoginCode(String code) async {
    _isLoading = true;
    notifyListeners();

    // Simulate network delay
    await Future.delayed(const Duration(seconds: 1500 ~/ 1000));

    if (code == '123456' || code.length == 6) {
      _isAuthenticated = true;
      _isLoading = false;
      notifyListeners();
      return true;
    }

    _isLoading = false;
    notifyListeners();
    return false;
  }

  void logout() {
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
    _isLoading = true;
    notifyListeners();

    await Future.delayed(const Duration(milliseconds: 500));

    final newTx = Transaction(
      id: DateTime.now().millisecondsSinceEpoch,
      amount: amount,
      kind: kind,
      categoryName: categoryName,
      categoryEmoji: categoryEmoji,
      accountName: accountName,
      note: note,
      timestamp: DateTime.now(),
    );

    _transactions.insert(0, newTx);

    // Update account balances
    final accIndex = _accounts.indexWhere((a) => a.name == accountName);
    if (accIndex != -1) {
      final acc = _accounts[accIndex];
      final delta = kind == 'expense' ? -amount : amount;
      _accounts[accIndex] = Account(id: acc.id, name: acc.name, balance: acc.balance + delta);
    }

    // Update category spent
    if (kind == 'expense') {
      final catIndex = _categories.indexWhere((c) => c.name == categoryName);
      if (catIndex != -1) {
        final cat = _categories[catIndex];
        _categories[catIndex] = Category(
          id: cat.id,
          name: cat.name,
          emoji: cat.emoji,
          limitAmount: cat.limitAmount,
          spentAmount: cat.spentAmount + amount,
        );
      }
    }

    // Fill streak for today (mock Tuesday)
    _weeklyStreak[2] = true;

    _isLoading = false;
    notifyListeners();
  }

  // AI Chat
  Future<void> sendAiMessage(String text) async {
    if (text.trim().isEmpty) return;

    _chatHistory.add(ChatMessage(text: text, isUser: true, timestamp: DateTime.now()));
    notifyListeners();

    _isLoading = true;
    notifyListeners();

    // Simulate AI response stream delay
    await Future.delayed(const Duration(seconds: 1));

    String aiResponse = 'Я проанализировал ваш запрос. ';
    if (text.toLowerCase().contains('баланс') || text.toLowerCase().contains('счет')) {
      aiResponse += 'Ваш текущий баланс по счетам составляет ${(totalBalance / 100).toStringAsFixed(2)} тг. Больше всего средств находится на счёте Kaspi Gold.';
    } else if (text.toLowerCase().contains('расход') || text.toLowerCase().contains('трат')) {
      aiResponse += 'В этом месяце вы потратили ${(monthlyExpenses / 100).toStringAsFixed(2)} тг. Основная статья расходов — Категория "Еда" (${(_categories[0].spentAmount / 100).toStringAsFixed(2)} тг).';
    } else {
      aiResponse += 'Вы отлично справляетесь со своим бюджетом! Ваша текущая серия заполнения составляет 2 дня на этой неделе 🔥. Продолжайте фиксировать расходы для поддержания финансовой дисциплины.';
    }

    _chatHistory.add(ChatMessage(text: aiResponse, isUser: false, timestamp: DateTime.now()));
    _isLoading = false;
    notifyListeners();
  }
}
