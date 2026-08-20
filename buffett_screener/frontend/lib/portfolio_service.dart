import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';

class PortfolioItem {
  final String ticker;
  final String companyName;
  final double addedPrice;
  final DateTime dateAdded;

  PortfolioItem({
    required this.ticker,
    required this.companyName,
    required this.addedPrice,
    required this.dateAdded,
  });

  Map<String, dynamic> toJson() => {
        'ticker': ticker,
        'companyName': companyName,
        'addedPrice': addedPrice,
        'dateAdded': dateAdded.toIso8601String(),
      };

  factory PortfolioItem.fromJson(Map<String, dynamic> json) {
    return PortfolioItem(
      ticker: json['ticker'],
      companyName: json['companyName'] ?? '',
      addedPrice: (json['addedPrice'] ?? 0).toDouble(),
      dateAdded: DateTime.parse(json['dateAdded']),
    );
  }
}

class PortfolioService {
  static const String _storageKey = 'paper_portfolio';
  final SharedPreferences _prefs;

  PortfolioService(this._prefs);

  static Future<PortfolioService> init() async {
    final prefs = await SharedPreferences.getInstance();
    return PortfolioService(prefs);
  }

  List<PortfolioItem> getPortfolio() {
    final String? itemsJson = _prefs.getString(_storageKey);
    if (itemsJson == null) return [];

    final List<dynamic> decoded = json.decode(itemsJson);
    return decoded.map((item) => PortfolioItem.fromJson(item)).toList();
  }

  Future<void> addTicker(String ticker, String companyName, double currentPrice) async {
    final items = getPortfolio();
    
    // Don't add if already exists
    if (items.any((item) => item.ticker == ticker)) return;

    items.add(PortfolioItem(
      ticker: ticker,
      companyName: companyName,
      addedPrice: currentPrice,
      dateAdded: DateTime.now(),
    ));

    await _savePortfolio(items);
  }

  Future<void> removeTicker(String ticker) async {
    final items = getPortfolio();
    items.removeWhere((item) => item.ticker == ticker);
    await _savePortfolio(items);
  }

  Future<void> _savePortfolio(List<PortfolioItem> items) async {
    final String encoded = json.encode(items.map((e) => e.toJson()).toList());
    await _prefs.setString(_storageKey, encoded);
  }

  bool isInPortfolio(String ticker) {
    return getPortfolio().any((item) => item.ticker == ticker);
  }
}
