class Account {
  final int id;
  final String name;
  final int balance;
  final String currency;
  final bool isSaving;
  final String accType; // 'regular', 'saving', 'deposit'
  final double interestRate;
  final String accrualPeriod; // 'month', 'year'
  final bool isBusiness;

  Account({
    required this.id,
    required this.name,
    required this.balance,
    this.currency = 'KZT',
    this.isSaving = false,
    this.accType = 'regular',
    this.interestRate = 0.0,
    this.accrualPeriod = 'month',
    this.isBusiness = false,
  });

  factory Account.fromJson(Map<String, dynamic> json) {
    return Account(
      id: json['id'] as int,
      name: json['name'] as String,
      balance: json['balance'] as int,
      currency: json['currency'] as String? ?? 'KZT',
      isSaving: json['is_saving'] == true || json['is_saving'] == 1,
      accType: json['acc_type'] as String? ?? 'regular',
      interestRate: (json['interest_rate'] as num? ?? 0.0).toDouble(),
      accrualPeriod: json['accrual_period'] as String? ?? 'month',
      isBusiness: json['is_business'] == true || json['is_business'] == 1,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'balance': balance,
    'currency': currency,
    'is_saving': isSaving,
    'acc_type': accType,
    'interest_rate': interestRate,
    'accrual_period': accrualPeriod,
    'is_business': isBusiness,
  };
}

class Category {
  final int id;
  final String name;
  final String emoji;
  final int? limitAmount;
  final int spentAmount;
  final String kind; // 'expense' or 'income'
  final int? defaultAccountId;
  final bool excludeFromAnalytics;
  final double warnThreshold;
  final bool isBusiness;

  Category({
    required this.id,
    required this.name,
    required this.emoji,
    this.limitAmount,
    required this.spentAmount,
    this.kind = 'expense',
    this.defaultAccountId,
    this.excludeFromAnalytics = false,
    this.warnThreshold = 0.70,
    this.isBusiness = false,
  });

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(
      id: json['id'] as int,
      name: json['name'] as String,
      emoji: json['emoji'] as String? ?? '📂',
      limitAmount: json['limitAmount'] as int? ?? json['limit_amount'] as int?,
      spentAmount: json['spentAmount'] as int? ?? json['spent_amount'] as int? ?? 0,
      kind: json['kind'] as String? ?? 'expense',
      defaultAccountId: json['defaultAccountId'] as int? ?? json['default_account_id'] as int?,
      excludeFromAnalytics: (json['excludeFromAnalytics'] == true || json['exclude_from_analytics'] == true || json['excludeFromAnalytics'] == 1 || json['exclude_from_analytics'] == 1),
      warnThreshold: (json['warnThreshold'] as num? ?? json['warn_threshold'] as num? ?? 0.70).toDouble(),
      isBusiness: json['is_business'] == true || json['is_business'] == 1,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'emoji': emoji,
    'limit_amount': limitAmount,
    'spent_amount': spentAmount,
    'kind': kind,
    'default_account_id': defaultAccountId,
    'exclude_from_analytics': excludeFromAnalytics ? 1 : 0,
    'warn_threshold': warnThreshold,
    'is_business': isBusiness ? 1 : 0,
  };
}

class Transaction {
  final int id;
  final int amount;
  final String kind; // 'expense', 'income', or 'transfer'
  final String categoryName;
  final String categoryEmoji;
  final String accountName;
  final String? note;
  final DateTime timestamp;
  final String currency;

  Transaction({
    required this.id,
    required this.amount,
    required this.kind,
    required this.categoryName,
    required this.categoryEmoji,
    required this.accountName,
    this.note,
    required this.timestamp,
    this.currency = 'KZT',
  });

  factory Transaction.fromJson(Map<String, dynamic> json) {
    return Transaction(
      id: json['id'] as int,
      amount: json['amount'] as int,
      kind: json['kind'] as String? ?? json['type'] as String? ?? 'expense',
      categoryName: json['categoryName'] as String? ?? json['category_name'] as String? ?? 'Прочее',
      categoryEmoji: json['categoryEmoji'] as String? ?? json['category_emoji'] as String? ?? '📦',
      accountName: json['accountName'] as String? ?? json['account_name'] as String? ?? '',
      note: json['note'] as String?,
      timestamp: DateTime.tryParse(json['timestamp'] as String? ?? json['ts'] as String? ?? '') ?? DateTime.now(),
      currency: json['currency'] as String? ?? 'KZT',
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'amount': amount,
    'kind': kind,
    'category_name': categoryName,
    'category_emoji': categoryEmoji,
    'account_name': accountName,
    'note': note,
    'timestamp': timestamp.toIso8601String(),
    'currency': currency,
  };
}

class Debt {
  final int id;
  final String direction; // 'in' or 'out'
  final String dtype; // 'bank' or 'private'
  final String title;
  final int totalAmount;
  final int remainingAmount;
  final int paymentAmount;
  final String? nextPaymentDate;
  final String? note;
  final String status;
  final bool reminderEnabled;
  final int reminderDaysBefore;

  Debt({
    required this.id,
    required this.direction,
    required this.dtype,
    required this.title,
    required this.totalAmount,
    required this.remainingAmount,
    required this.paymentAmount,
    this.nextPaymentDate,
    this.note,
    required this.status,
    this.reminderEnabled = true,
    this.reminderDaysBefore = 3,
  });

  factory Debt.fromJson(Map<String, dynamic> json) {
    return Debt(
      id: json['id'] as int,
      direction: json['direction'] as String,
      dtype: json['dtype'] as String,
      title: json['title'] as String,
      totalAmount: json['totalAmount'] as int? ?? json['total_amount'] as int? ?? 0,
      remainingAmount: json['remainingAmount'] as int? ?? json['remaining_amount'] as int? ?? 0,
      paymentAmount: json['paymentAmount'] as int? ?? json['payment_amount'] as int? ?? 0,
      nextPaymentDate: json['nextPaymentDate'] as String? ?? json['next_payment_date'] as String?,
      note: json['note'] as String?,
      status: json['status'] as String? ?? 'active',
      reminderEnabled: json['reminderEnabled'] as bool? ?? true,
      reminderDaysBefore: json['reminderDaysBefore'] as int? ?? 3,
    );
  }
}

class RecurringTemplate {
  final int id;
  final String title;
  final int amount;
  final String kind; // 'expense' or 'income'
  final String intervalType; // 'monthly'
  final int intervalValue; // day_of_month
  final String? nextRunDate;
  final String categoryEmoji;
  final int? accountId;
  final String currency;

  RecurringTemplate({
    required this.id,
    required this.title,
    required this.amount,
    required this.kind,
    required this.intervalType,
    required this.intervalValue,
    this.nextRunDate,
    required this.categoryEmoji,
    this.accountId,
    this.currency = 'KZT',
  });

  factory RecurringTemplate.fromJson(Map<String, dynamic> json) {
    return RecurringTemplate(
      id: json['id'] as int,
      title: json['name'] as String? ?? json['title'] as String? ?? '',
      amount: json['amount'] as int,
      kind: json['kind'] as String? ?? 'expense',
      intervalType: json['intervalType'] as String? ?? 'monthly',
      intervalValue: json['intervalValue'] as int? ?? json['day_of_month'] as int? ?? 1,
      nextRunDate: json['nextRunDate'] as String? ?? json['next_run_date'] as String?,
      categoryEmoji: json['categoryEmoji'] as String? ?? json['category_emoji'] as String? ?? '🔁',
      accountId: json['accountId'] as int? ?? json['account_id'] as int?,
      currency: json['currency'] as String? ?? 'KZT',
    );
  }
}

class PlannedTx {
  final int id;
  final String title;
  final int amount;
  final String date; // YYYY-MM-DD
  final String kind; // 'expense' or 'income'
  final String status;
  final String categoryEmoji;
  final int? accountId;
  final String currency;

  PlannedTx({
    required this.id,
    required this.title,
    required this.amount,
    required this.date,
    required this.kind,
    required this.status,
    required this.categoryEmoji,
    this.accountId,
    this.currency = 'KZT',
  });

  factory PlannedTx.fromJson(Map<String, dynamic> json) {
    return PlannedTx(
      id: json['id'] as int,
      title: json['title'] as String,
      amount: json['amount'] as int,
      date: json['date'] as String? ?? json['planned_date'] as String? ?? '',
      kind: json['kind'] as String? ?? 'expense',
      status: json['status'] as String? ?? 'pending',
      categoryEmoji: json['categoryEmoji'] as String? ?? json['category_emoji'] as String? ?? '📅',
      accountId: json['accountId'] as int? ?? json['account_id'] as int?,
      currency: json['currency'] as String? ?? 'KZT',
    );
  }
}

/// Analytic chart data point from /api/analytics
class AnalyticsCategory {
  final String name;
  final String emoji;
  final int amount;

  AnalyticsCategory({required this.name, required this.emoji, required this.amount});

  factory AnalyticsCategory.fromJson(Map<String, dynamic> json) {
    return AnalyticsCategory(
      name: json['categoryName'] as String? ?? '',
      emoji: json['categoryEmoji'] as String? ?? '📦',
      amount: json['amount'] as int? ?? 0,
    );
  }
}

class QuickAddTemplate {
  final int id;
  final String title;
  final int amount;
  final String kind;
  final String categoryName;
  final String categoryEmoji;
  final int? accountId;

  QuickAddTemplate({
    required this.id,
    required this.title,
    required this.amount,
    this.kind = 'expense',
    required this.categoryName,
    required this.categoryEmoji,
    this.accountId,
  });

  factory QuickAddTemplate.fromJson(Map<String, dynamic> json) {
    return QuickAddTemplate(
      id: json['id'] as int,
      title: json['title'] as String? ?? '',
      amount: json['amount'] as int? ?? 0,
      kind: json['kind'] as String? ?? 'expense',
      categoryName: json['category_name'] as String? ?? json['categoryName'] as String? ?? 'Прочее',
      categoryEmoji: json['category_emoji'] as String? ?? json['categoryEmoji'] as String? ?? '📦',
      accountId: json['account_id'] as int? ?? json['accountId'] as int?,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'title': title,
    'amount': amount,
    'kind': kind,
    'category_name': categoryName,
    'category_emoji': categoryEmoji,
    'account_id': accountId,
  };
}
