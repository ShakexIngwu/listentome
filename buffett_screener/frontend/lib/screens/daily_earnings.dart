import 'package:flutter/material.dart';
import '../api_service.dart';
import '../portfolio_service.dart';

class DailyEarningsScreen extends StatefulWidget {
  final Function(String) onTickerTap;

  const DailyEarningsScreen({super.key, required this.onTickerTap});

  @override
  State<DailyEarningsScreen> createState() => _DailyEarningsScreenState();
}

class _DailyEarningsScreenState extends State<DailyEarningsScreen> {
  final ApiService apiService = ApiService();
  late Future<EarningsData> futureEarnings;
  PortfolioService? _portfolioService;
  List<PortfolioItem> _portfolio = [];

  @override
  void initState() {
    super.initState();
    futureEarnings = apiService.getEarnings();
    _initPortfolio();
  }

  Future<void> _initPortfolio() async {
    _portfolioService = await PortfolioService.init();
    setState(() {
      _portfolio = _portfolioService!.getPortfolio();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF9F7F1), // Consistent with Sunday Read
      body: FutureBuilder<EarningsData>(
        future: futureEarnings,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator(color: Colors.black));
          } else if (!snapshot.hasData) {
            return const Center(child: Text('No daily pulse available.', style: TextStyle(color: Colors.black)));
          }

          final data = snapshot.data!;
          final isPortfolioEmpty = _portfolio.isEmpty;
          
          // Filter calendar to portfolio if not empty
          final calendar = data.calendar.where((item) {
            if (isPortfolioEmpty) return true;
            return _portfolio.any((p) => p.ticker == item['ticker']);
          }).toList();

          return CustomScrollView(
            slivers: [
              SliverToBoxAdapter(
                child: Padding(
                  padding: const EdgeInsets.all(48.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text(
                        'THE DAILY PULSE',
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
                        isPortfolioEmpty 
                            ? 'LATEST MARKET EARNINGS'
                            : 'UPDATES FOR YOUR PLANTED SEEDS',
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
              if (calendar.isEmpty)
                const SliverToBoxAdapter(
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 48.0),
                    child: Text(
                      'No significant events for your portfolio today. The weather remains calm.',
                      style: TextStyle(fontFamily: 'Georgia', fontSize: 18, color: Colors.black54),
                    ),
                  ),
                )
              else
                SliverPadding(
                  padding: const EdgeInsets.symmetric(horizontal: 48.0),
                  sliver: SliverList(
                    delegate: SliverChildBuilderDelegate(
                      (context, index) {
                        final item = calendar[index];
                        final isPortfolioItem = !isPortfolioEmpty;
                        
                        return Container(
                          margin: const EdgeInsets.only(bottom: 24),
                          padding: const EdgeInsets.all(24),
                          decoration: BoxDecoration(
                            border: Border.all(color: Colors.black12),
                            color: Colors.white,
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Icon / Status
                              Container(
                                width: 48,
                                height: 48,
                                decoration: BoxDecoration(
                                  color: Colors.black.withOpacity(0.05),
                                  shape: BoxShape.circle,
                                ),
                                child: const Icon(Icons.campaign, color: Colors.black54),
                              ),
                              const SizedBox(width: 24),
                              // Content
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Text(
                                          '${item['company']} (${item['ticker']})',
                                          style: const TextStyle(
                                            fontFamily: 'Georgia',
                                            fontSize: 20,
                                            fontWeight: FontWeight.bold,
                                            color: Colors.black87,
                                          ),
                                        ),
                                        Text(
                                          item['earnings_date'] ?? 'Upcoming',
                                          style: const TextStyle(
                                            fontSize: 12,
                                            color: Colors.black54,
                                            fontWeight: FontWeight.bold,
                                            letterSpacing: 1,
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 8),
                                    Text(
                                      'Estimated EPS: \$${item['eps_estimate'] ?? '-'}',
                                      style: const TextStyle(
                                        fontFamily: 'Georgia',
                                        fontSize: 16,
                                        color: Colors.black87,
                                      ),
                                    ),
                                    const SizedBox(height: 16),
                                    if (isPortfolioItem)
                                      const Text(
                                        'Remember your original conviction. Do not let short-term earnings noise shake a long-term thesis.',
                                        style: TextStyle(
                                          fontFamily: 'Georgia',
                                          fontStyle: FontStyle.italic,
                                          color: Colors.black54,
                                        ),
                                      ),
                                    const SizedBox(height: 16),
                                    InkWell(
                                      onTap: () => widget.onTickerTap(item['ticker']),
                                      child: const Text(
                                        'Review Conviction Thesis →',
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
                      childCount: calendar.length,
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}
