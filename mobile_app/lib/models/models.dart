class Account {
  final int id;
  final String name;
  final int balance; // minor units (e.g. cents/tiyin)

  Account({
    required this.id,
    required this.name,
    required this.balance,
  });

  factory Account.fromJson(Map<String, dynamic> json) {
    return Account(
      id: json['id'] as int,
      name: json['name'] as String,
      balance: json['balance'] as int,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'balance': balance,
  };
}

class Category {
  final int id;
  final String name;
  final String emoji;
  final int? limitAmount;
  final int spentAmount;

  Category({
    required this.id,
    required this.name,
    required this.emoji,
    this.limitAmount,
    required this.spentAmount,
  });

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(
      id: json['id'] as int,
      name: json['name'] as String,
      emoji: json['emoji'] as String? ?? '📂',
      limitAmount: json['limit_amount'] as int?,
      spentAmount: json['spent_amount'] as int? ?? 0,
    );
  }

  Map<String, dynamic> toJson() => {
    'id': id,
    'name': name,
    'emoji': emoji,
    'limit_amount': limitAmount,
    'spent_amount': spentAmount,
  };
}

class Transaction {
  final int id;
  final int amount;
  final String kind; // 'expense' or 'income'
  final String categoryName;
  final String categoryEmoji;
  final String accountName;
  final String? note;
  final DateTime timestamp;

  Transaction({
    required this.id,
    required this.amount,
    required this.kind,
    required this.categoryName,
    required this.categoryEmoji,
    required this.accountName,
    this.note,
    required this.timestamp,
  });

  factory Transaction.fromJson(Map<String, dynamic> json) {
    return Transaction(
      id: json['id'] as int,
      amount: json['amount'] as int,
      kind: json['kind'] as String,
      categoryName: json['category_name'] as String? ?? 'Other',
      categoryEmoji: json['category_emoji'] as String? ?? '💸',
      accountName: json['account_name'] as String? ?? 'Default',
      note: json['note'] as String?,
      timestamp: DateTime.parse(json['timestamp'] as String),
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
  };
}
