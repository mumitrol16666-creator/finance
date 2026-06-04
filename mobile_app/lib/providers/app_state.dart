import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'dart:typed_data';
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

  bool _isPremium = false;
  bool get isPremium => _isPremium;

  String? _premiumExpirationDate;
  String? get premiumExpirationDate => _premiumExpirationDate;

  List<String> _availableFeatures = [];
  List<String> get availableFeatures => _availableFeatures;

  bool hasFeature(String feature) {
    return _isPremium || _availableFeatures.contains(feature);
  }

  // Real data — loaded from server after login
  List<Account> _accounts = [];
  List<Account> get accounts => _accounts;

  List<Category> _categories = [];
  List<Category> get categories => _categories;

  List<Transaction> _transactions = [];
  List<Transaction> get transactions => _transactions;

  List<bool> _weeklyStreak = [false, false, false, false, false, false, false];
  List<bool> get weeklyStreak => _weeklyStreak;

  List<ChatMessage> _chatHistory = [];
  List<ChatMessage> get chatHistory => _chatHistory;

  int get totalBalance => _accounts.where((acc) => !acc.isSaving).fold(0, (sum, acc) => sum + acc.balance);
  int get monthlyExpenses => _categories.fold(0, (sum, cat) => sum + cat.spentAmount);

  List<Debt> _debts = [];
  List<Debt> get debts => _debts;

  List<RecurringTemplate> _recurringTemplates = [];
  List<RecurringTemplate> get recurringTemplates => _recurringTemplates;

  List<PlannedTx> _plannedEvents = [];
  List<PlannedTx> get plannedEvents => _plannedEvents;

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
        
        // Clear mock data before loading real data
        _accounts = [];
        _categories = [];
        _transactions = [];
        _debts = [];
        _recurringTemplates = [];
        _plannedEvents = [];
        
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
        
        // Parse premium details
        _isPremium = data['isPremium'] as bool? ?? false;
        _premiumExpirationDate = data['premiumExpirationDate'] as String?;
        _availableFeatures = List<String>.from(data['availableFeatures'] as List? ?? []);
      }

      await Future.wait([
        _fetchDebtsSilent(),
        _fetchRecurringSilent(),
        _fetchPlannedSilent(),
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

  void logout() {
    _token = null;
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
    _weeklyStreak = [false, false, false, false, false, false, false];
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
    String? toAccountName,
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
          'to_account_id': toAccountId,
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
      }
    } catch (e) {
      print('Add debt error: $e');
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
      }
    } catch (e) {
      print('Pay debt error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
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
      }
    } catch (e) {
      print('Add recurring error: $e');
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
      }
    } catch (e) {
      print('Add planned error: $e');
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
}
