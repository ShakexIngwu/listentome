import 'dart:convert';
import 'package:http/http.dart' as http;

class TopPick {
  final String ticker;
  final String company;
  final double score;
  final String recommendation;
  final double marginOfSafety;

  TopPick({
    required this.ticker,
    required this.company,
    required this.score,
    required this.recommendation,
    required this.marginOfSafety,
  });

  factory TopPick.fromJson(Map<String, dynamic> json) {
    return TopPick(
      ticker: json['ticker'] ?? '',
      company: json['company'] ?? '',
      score: (json['score'] ?? 0).toDouble(),
      recommendation: json['recommendation'] ?? '',
      marginOfSafety: (json['margin_of_safety'] ?? 0).toDouble(),
    );
  }
}

class TickerDetail {
  final Map<String, dynamic> company;
  final Map<String, dynamic>? latestScore;
  final List<dynamic> history;
  final List<dynamic> epsHistory;

  TickerDetail({
    required this.company,
    this.latestScore,
    required this.history,
    required this.epsHistory,
  });

  factory TickerDetail.fromJson(Map<String, dynamic> json) {
    return TickerDetail(
      company: json['company'] ?? {},
      latestScore: json['latest_score'],
      history: json['history'] ?? [],
      epsHistory: json['eps_history'] ?? [],
    );
  }
}

class WeeklyRunSummary {
  final String analysisDate;
  final int tickersScored;
  final int strongBuys;
  final int buys;
  final int holds;
  final int passes;
  final double avgScore;
  final double maxScore;

  WeeklyRunSummary({
    required this.analysisDate,
    required this.tickersScored,
    required this.strongBuys,
    required this.buys,
    required this.holds,
    required this.passes,
    required this.avgScore,
    required this.maxScore,
  });

  factory WeeklyRunSummary.fromJson(Map<String, dynamic> json) {
    return WeeklyRunSummary(
      analysisDate: json['analysis_date'] ?? '',
      tickersScored: json['tickers_scored'] ?? 0,
      strongBuys: json['strong_buys'] ?? 0,
      buys: json['buys'] ?? 0,
      holds: json['holds'] ?? 0,
      passes: json['passes'] ?? 0,
      avgScore: (json['avg_score'] ?? 0).toDouble(),
      maxScore: (json['max_score'] ?? 0).toDouble(),
    );
  }
}

class EarningsData {
  final Map<String, dynamic> summary;
  final List<dynamic> calendar;
  final List<dynamic> events;

  EarningsData({
    required this.summary,
    required this.calendar,
    required this.events,
  });

  factory EarningsData.fromJson(Map<String, dynamic> json) {
    return EarningsData(
      summary: json['summary'] ?? {},
      calendar: json['calendar'] ?? [],
      events: json['events'] ?? [],
    );
  }
}

class ApiService {
  // Use 10.0.2.2 for Android emulator, localhost for iOS/Web
  static const String baseUrl = 'http://127.0.0.1:8000/api';

  Future<List<TopPick>> getTopPicks() async {
    final response = await http.get(Uri.parse('$baseUrl/top-picks'));
    if (response.statusCode == 200) {
      List jsonResponse = json.decode(response.body);
      return jsonResponse.map((data) => TopPick.fromJson(data)).toList();
    } else {
      throw Exception('Failed to load top picks');
    }
  }

  Future<List<String>> getTickers() async {
    final response = await http.get(Uri.parse('$baseUrl/tickers'));
    if (response.statusCode == 200) {
      List jsonResponse = json.decode(response.body);
      return jsonResponse.cast<String>();
    } else {
      throw Exception('Failed to load tickers');
    }
  }

  Future<TickerDetail> getTickerDeepDive(String ticker) async {
    final response = await http.get(Uri.parse('$baseUrl/ticker/$ticker'));
    if (response.statusCode == 200) {
      return TickerDetail.fromJson(json.decode(response.body));
    } else {
      throw Exception('Failed to load deep dive for $ticker');
    }
  }

  Future<List<WeeklyRunSummary>> getWeeklyRuns() async {
    final response = await http.get(Uri.parse('$baseUrl/weekly-runs'));
    if (response.statusCode == 200) {
      List jsonResponse = json.decode(response.body);
      return jsonResponse.map((data) => WeeklyRunSummary.fromJson(data)).toList();
    } else {
      throw Exception('Failed to load weekly runs');
    }
  }

  Future<List<TopPick>> getWeeklyRunDetails(String date) async {
    final response = await http.get(Uri.parse('$baseUrl/weekly-runs/$date'));
    if (response.statusCode == 200) {
      List jsonResponse = json.decode(response.body);
      return jsonResponse.map((data) => TopPick.fromJson(data)).toList();
    } else {
      throw Exception('Failed to load weekly run details');
    }
  }

  Future<EarningsData> getEarnings() async {
    final response = await http.get(Uri.parse('$baseUrl/earnings'));
    if (response.statusCode == 200) {
      return EarningsData.fromJson(json.decode(response.body));
    } else {
      throw Exception('Failed to load earnings data');
    }
  }
}
