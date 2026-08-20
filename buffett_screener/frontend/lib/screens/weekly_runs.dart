import 'package:flutter/material.dart';
import '../api_service.dart';
import '../portfolio_service.dart';
import '../theme.dart';

class WeeklyRunsScreen extends StatefulWidget {
  final Function(String) onTickerTap;

  const WeeklyRunsScreen({super.key, required this.onTickerTap});

  @override
  State<WeeklyRunsScreen> createState() => _WeeklyRunsScreenState();
}

class _WeeklyRunsScreenState extends State<WeeklyRunsScreen> {
  final ApiService apiService = ApiService();
  late Future<List<WeeklyRunSummary>> futureRuns;
  List<TopPick>? selectedRunDetails;
  String? selectedDate;
  bool isLoadingDetails = false;
  PortfolioService? _portfolioService;

  @override
  void initState() {
    super.initState();
    futureRuns = apiService.getWeeklyRuns();
    _initPortfolio();
  }

  Future<void> _initPortfolio() async {
    _portfolioService = await PortfolioService.init();
    setState(() {});
  }

  Future<void> _loadRunDetails(String date) async {
    setState(() {
      isLoadingDetails = true;
      selectedDate = date;
    });
    try {
      final details = await apiService.getWeeklyRunDetails(date);
      setState(() {
        selectedRunDetails = details;
      });
    } catch (e) {
      setState(() {
        selectedRunDetails = [];
      });
    } finally {
      setState(() {
        isLoadingDetails = false;
      });
    }
  }

  void _addToPortfolio(TopPick pick) async {
    if (_portfolioService == null) return;
    
    // Attempt to get the latest price, fallback to 0.0 for now, but usually we'd have the current price in the summary or we can fetch it.
    // Deep dive fetch takes time, but for MVP let's assume price 0.0 or fetch it fast.
    double price = 0.0;
    try {
      final detail = await apiService.getTickerDeepDive(pick.ticker);
      price = (detail.latestScore?['price'] ?? 0).toDouble();
    } catch (_) {}

    await _portfolioService!.addTicker(pick.ticker, pick.company, price);
    setState(() {}); // Refresh UI
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${pick.ticker} added to your Paper Portfolio.')),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF9F7F1), // Newspaper off-white
      body: FutureBuilder<List<WeeklyRunSummary>>(
        future: futureRuns,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator(color: Colors.black));
          } else if (!snapshot.hasData || snapshot.data!.isEmpty) {
            return const Center(child: Text('No Sunday Reads available.', style: TextStyle(color: Colors.black)));
          }

          final runs = snapshot.data!;
          if (selectedDate == null) {
            // Auto-load latest run
            _loadRunDetails(runs.first.analysisDate);
          }

          return Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Left Column: Archives
              Container(
                width: 250,
                color: const Color(0xFFEFEBE0),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Padding(
                      padding: EdgeInsets.all(24.0),
                      child: Text(
                        'ARCHIVES',
                        style: TextStyle(
                          fontFamily: 'Georgia',
                          fontSize: 16,
                          fontWeight: FontWeight.bold,
                          letterSpacing: 2,
                          color: Colors.black87,
                        ),
                      ),
                    ),
                    Expanded(
                      child: ListView.builder(
                        itemCount: runs.length,
                        itemBuilder: (context, index) {
                          final run = runs[index];
                          final isSelected = selectedDate == run.analysisDate;
                          return InkWell(
                            onTap: () => _loadRunDetails(run.analysisDate),
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                              decoration: BoxDecoration(
                                color: isSelected ? Colors.black12 : Colors.transparent,
                                border: const Border(bottom: BorderSide(color: Colors.black12)),
                              ),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    run.analysisDate,
                                    style: TextStyle(
                                      fontFamily: 'Georgia',
                                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                                      color: Colors.black87,
                                    ),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    '${run.strongBuys} Strong Buys found.',
                                    style: const TextStyle(
                                      fontSize: 12,
                                      color: Colors.black54,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ],
                ),
              ),

              // Right Column: The Sunday Read
              Expanded(
                child: isLoadingDetails
                    ? const Center(child: CircularProgressIndicator(color: Colors.black))
                    : selectedRunDetails == null || selectedRunDetails!.isEmpty
                        ? const Center(child: Text('No picks found for this edition.', style: TextStyle(color: Colors.black)))
                        : CustomScrollView(
                            slivers: [
                              SliverToBoxAdapter(
                                child: Padding(
                                  padding: const EdgeInsets.all(48.0),
                                  child: Column(
                                    children: [
                                      const Text(
                                        'THE SUNDAY READ',
                                        style: TextStyle(
                                          fontFamily: 'Georgia',
                                          fontSize: 48,
                                          fontWeight: FontWeight.bold,
                                          letterSpacing: 4,
                                          color: Colors.black87,
                                        ),
                                      ),
                                      const SizedBox(height: 16),
                                      Text(
                                        'EDITION: $selectedDate',
                                        style: const TextStyle(
                                          fontFamily: 'Georgia',
                                          fontSize: 14,
                                          letterSpacing: 2,
                                          color: Colors.black54,
                                        ),
                                      ),
                                      const SizedBox(height: 32),
                                      Container(height: 1, color: Colors.black26),
                                      const SizedBox(height: 32),
                                    ],
                                  ),
                                ),
                              ),
                              SliverPadding(
                                padding: const EdgeInsets.symmetric(horizontal: 48.0),
                                sliver: SliverList(
                                  delegate: SliverChildBuilderDelegate(
                                    (context, index) {
                                      final pick = selectedRunDetails![index];
                                      final isInPortfolio = _portfolioService?.isInPortfolio(pick.ticker) ?? false;

                                      return Container(
                                        margin: const EdgeInsets.only(bottom: 48),
                                        child: Row(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            // Score & Verdict
                                            SizedBox(
                                              width: 120,
                                              child: Column(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    '${pick.score.toInt()}',
                                                    style: const TextStyle(
                                                      fontFamily: 'Georgia',
                                                      fontSize: 48,
                                                      fontWeight: FontWeight.bold,
                                                      color: Colors.black87,
                                                    ),
                                                  ),
                                                  Text(
                                                    pick.recommendation.replaceAll('_', ' '),
                                                    style: TextStyle(
                                                      fontSize: 12,
                                                      fontWeight: FontWeight.bold,
                                                      letterSpacing: 1,
                                                      color: pick.recommendation.contains('BUY') ? Colors.green[800] : Colors.red[800],
                                                    ),
                                                  ),
                                                  const SizedBox(height: 16),
                                                  OutlinedButton(
                                                    onPressed: isInPortfolio ? null : () => _addToPortfolio(pick),
                                                    style: OutlinedButton.styleFrom(
                                                      foregroundColor: Colors.black,
                                                      side: BorderSide(color: isInPortfolio ? Colors.transparent : Colors.black54),
                                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(0)),
                                                    ),
                                                    child: Text(
                                                      isInPortfolio ? 'Planted' : 'Plant Seed',
                                                      style: const TextStyle(fontSize: 12),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                            const SizedBox(width: 32),
                                            // Article Content
                                            Expanded(
                                              child: Column(
                                                crossAxisAlignment: CrossAxisAlignment.start,
                                                children: [
                                                  Text(
                                                    '${pick.company} (${pick.ticker})',
                                                    style: const TextStyle(
                                                      fontFamily: 'Georgia',
                                                      fontSize: 28,
                                                      fontWeight: FontWeight.bold,
                                                      color: Colors.black87,
                                                    ),
                                                  ),
                                                  const SizedBox(height: 8),
                                                  Text(
                                                    'Margin of Safety: ${pick.marginOfSafety.toStringAsFixed(1)}%',
                                                    style: const TextStyle(
                                                      fontFamily: 'Georgia',
                                                      fontStyle: FontStyle.italic,
                                                      color: Colors.black54,
                                                    ),
                                                  ),
                                                  const SizedBox(height: 16),
                                                  const Text(
                                                    'A robust opportunity identified by our automated analysis. The fundamentals point towards an undervalued position relative to its intrinsic value. To read the full qualitative thesis, including the moat analysis and risk factors, proceed to the Deep Dive.',
                                                    style: TextStyle(
                                                      fontFamily: 'Georgia',
                                                      fontSize: 16,
                                                      height: 1.6,
                                                      color: Colors.black87,
                                                    ),
                                                  ),
                                                  const SizedBox(height: 16),
                                                  InkWell(
                                                    onTap: () => widget.onTickerTap(pick.ticker),
                                                    child: const Text(
                                                      'Read Full Thesis →',
                                                      style: TextStyle(
                                                        fontFamily: 'Georgia',
                                                        fontWeight: FontWeight.bold,
                                                        color: Colors.blue,
                                                      ),
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ],
                                        ),
                                      );
                                    },
                                    childCount: selectedRunDetails!.length,
                                  ),
                                ),
                              ),
                            ],
                          ),
              ),
            ],
          );
        },
      ),
    );
  }
}
