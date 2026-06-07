import 'package:intl/intl.dart';

/// Centralized currency formatting and utilities.
/// Replaces duplicated _formatCurrency() across screens.

const Map<String, String> currencySymbols = {
  'KZT': '₸',
  'USD': '\$',
  'EUR': '€',
  'RUB': '₽',
};

const Map<String, String> currencyLocales = {
  'KZT': 'kk_KZ',
  'USD': 'en_US',
  'EUR': 'de_DE',
  'RUB': 'ru_RU',
};

const Map<String, String> currencyFlags = {
  'KZT': '🇰🇿',
  'USD': '🇺🇸',
  'EUR': '🇪🇺',
  'RUB': '🇷🇺',
};

const Map<String, String> currencyNames = {
  'KZT': 'Тенге',
  'USD': 'Доллар',
  'EUR': 'Евро',
  'RUB': 'Рубль',
};

/// Format an integer amount with currency symbol.
/// E.g. formatCurrency(250000, 'KZT') => '250 000 ₸'
String formatCurrency(int amount, String currency) {
  final symbol = currencySymbols[currency.toUpperCase()] ?? currency;
  final locale = currencyLocales[currency.toUpperCase()] ?? 'kk_KZ';
  final formatter = NumberFormat.currency(locale: locale, symbol: symbol, decimalDigits: 0);
  return formatter.format(amount);
}

/// Format an integer amount with a compact form (no symbol, just number).
/// E.g. formatAmount(250000) => '250 000'
String formatAmount(int amount) {
  final formatter = NumberFormat('#,###', 'ru');
  return formatter.format(amount);
}

/// Get the currency symbol for a currency code.
String currencySymbol(String code) {
  return currencySymbols[code.toUpperCase()] ?? code;
}

/// Get the flag emoji for a currency code.
String currencyFlag(String code) {
  return currencyFlags[code.toUpperCase()] ?? '🏳️';
}

/// Get the human-readable name for a currency code.
String currencyName(String code) {
  return currencyNames[code.toUpperCase()] ?? code;
}

/// Convert amount from one currency to another using exchange rates map.
/// Rates are stored relative to USD (e.g. KZT=450 means 1 USD = 450 KZT).
/// Returns null if conversion is impossible.
int? convertCurrency(int amount, String fromCurrency, String toCurrency, Map<String, double> ratesToUsd) {
  if (fromCurrency == toCurrency) return amount;
  
  final fromRate = ratesToUsd[fromCurrency.toUpperCase()];
  final toRate = ratesToUsd[toCurrency.toUpperCase()];
  
  if (fromRate == null || toRate == null || fromRate == 0) return null;
  
  // amount_in_from -> USD -> to_currency
  // USD = amount / fromRate
  // result = USD * toRate
  return (amount / fromRate * toRate).round();
}

/// Format a compact currency breakdown string.
/// E.g. '$1 200 · €800 · ₽15 000'
String formatCurrencyBreakdown(Map<String, int> balancesByCurrency, {String? excludeCurrency}) {
  final parts = <String>[];
  for (final entry in balancesByCurrency.entries) {
    if (excludeCurrency != null && entry.key == excludeCurrency) continue;
    if (entry.value == 0) continue;
    final symbol = currencySymbols[entry.key] ?? entry.key;
    final formatted = formatAmount(entry.value.abs());
    parts.add('$symbol$formatted');
  }
  return parts.join(' · ');
}

/// Format exchange rate display.
/// E.g. '1 \$ = 450 ₸'
String formatExchangeRate(String fromCurrency, String toCurrency, Map<String, double> ratesToUsd) {
  final fromRate = ratesToUsd[fromCurrency.toUpperCase()];
  final toRate = ratesToUsd[toCurrency.toUpperCase()];
  
  if (fromRate == null || toRate == null || fromRate == 0) return '—';
  
  final rate = toRate / fromRate;
  final fromSymbol = currencySymbols[fromCurrency] ?? fromCurrency;
  final toSymbol = currencySymbols[toCurrency] ?? toCurrency;
  
  if (rate >= 1) {
    return '1 $fromSymbol = ${rate.toStringAsFixed(rate > 100 ? 0 : 2)} $toSymbol';
  } else {
    final inverse = 1.0 / rate;
    return '1 $toSymbol = ${inverse.toStringAsFixed(inverse > 100 ? 0 : 2)} $fromSymbol';
  }
}
