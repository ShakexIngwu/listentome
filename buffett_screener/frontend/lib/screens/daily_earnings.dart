import 'package:flutter/material.dart';
import '../api_service.dart';
import '../portfolio_service.dart';
import '../theme.dart';

class DailyEarningsScreen extends StatefulWidget {
  final Function(String) onTickerTap;

  const DailyEarningsScreen({super.key, required this.onTickerTap});

  @override
  State<DailyEarningsScreen> createState() => _DailyEarningsScreenState();
}

class _DailyEarningsScreenState extends State<DailyEarningsScreen> with SingleTickerProviderStateMixin {
  final ApiService apiService = ApiService();
  late Future<EarningsData> futureEarnings;
  late TabController _tabController;
  PortfolioService? _portfolioService;
  List<PortfolioItem> _portfolio = [];
  bool _filterToPortfolio = false;

  @override
  void initState() {
    super.initState();
    futureEarnings = apiService.getEarnings();
    _tabController = TabController(length: 3, vsync: this);
    _initPortfolio();
  }

  @override
  void dispose() {
    _tabController.dispose();
    super.dispose();
  }

  Future<void> _initPortfolio() async {
    _portfolioService = await PortfolioService.init();
    setState(() {
      _portfolio = _portfolioService!.getPortfolio();
    });
  }

  Color _getRecColor(String? rec) {
    if (rec == null) return Colors.grey.shade300;
    switch (rec) {
      case 'STRONG_BUY': return const Color(0xFF00C853);
      case 'BUY': return const Color(0xFF62FF96);
      case 'HOLD': return const Color(0xFFFFF291);
      default: return const Color(0xFFFF8A80);
    }
  }

  Color _getRecTextColor(String? rec) {
    if (rec == null) return Colors.black87;
    return (rec == 'STRONG_BUY' || rec == 'PASS' || rec == 'BUY') 
        ? Colors.white 
        : Colors.black87;
  }

  // Segmented Toggle for All vs Portfolio
  Widget _buildFilterToggle() {
    return Container(
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.05),
        borderRadius: BorderRadius.circular(12),
      ),
      padding: const EdgeInsets.all(4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildFilterButton('All Market', false),
          _buildFilterButton('My Portfolio (${_portfolio.length})', true),
        ],
      ),
    );
  }

  Widget _buildFilterButton(String text, bool isPortfolio) {
    final isSelected = _filterToPortfolio == isPortfolio;
    return GestureDetector(
      onTap: () {
        setState(() {
          _filterToPortfolio = isPortfolio;
        });
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
        decoration: BoxDecoration(
          color: isSelected ? Colors.white : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
          boxShadow: isSelected ? [
            BoxShadow(
              color: Colors.black.withOpacity(0.05),
              blurRadius: 4,
              offset: const Offset(0, 2),
            )
          ] : null,
        ),
        child: Text(
          text,
          style: TextStyle(
            fontWeight: FontWeight.bold,
            fontSize: 13,
            color: isSelected ? Colors.black87 : Colors.black54,
          ),
        ),
      ),
    );
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
          } else if (snapshot.hasError) {
            return Center(child: Text('Error loading daily pulse: ${snapshot.error}', style: const TextStyle(color: Colors.black87)));
          } else if (!snapshot.hasData) {
            return const Center(child: Text('No daily pulse available.', style: TextStyle(color: Colors.black87)));
          }

          final data = snapshot.data!;
          
          // Apply Portfolio Filter dynamically
          final calendar = data.calendar.where((item) {
            if (!_filterToPortfolio) return true;
            return _portfolio.any((p) => p.ticker == item['ticker']);
          }).toList();

          final events = data.events.where((item) {
            if (!_filterToPortfolio) return true;
            return _portfolio.any((p) => p.ticker == item['ticker']);
          }).toList();

          // Summary stats
          final summary = data.summary;

          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.only(left: 48.0, right: 48.0, top: 48.0, bottom: 16.0),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    const Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'DAILY PULSE',
                          style: TextStyle(
                            fontFamily: 'Georgia',
                            fontSize: 48,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 4,
                            color: Colors.black87,
                          ),
                        ),
                        SizedBox(height: 8),
                        Text(
                          'EARNINGS CALENDAR & MARKET RELEASES',
                          style: TextStyle(
                            fontFamily: 'Georgia',
                            fontSize: 12,
                            letterSpacing: 2,
                            color: Colors.black54,
                          ),
                        ),
                      ],
                    ),
                    _buildFilterToggle(),
                  ],
                ),
              ),

              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 48.0),
                child: Container(height: 1, color: Colors.black12),
              ),

              // TabBar navigation
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 48.0, vertical: 12.0),
                child: TabBar(
                  controller: _tabController,
                  indicatorColor: Colors.black87,
                  labelColor: Colors.black87,
                  unselectedLabelColor: Colors.black54,
                  labelStyle: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                  tabs: const [
                    Tab(text: 'Overview & Stats'),
                    Tab(text: 'Upcoming Calendar'),
                    Tab(text: 'Recent Outcomes'),
                  ],
                ),
              ),

              // TabBarView Content
              Expanded(
                child: TabBarView(
                  controller: _tabController,
                  children: [
                    _buildOverviewTab(summary, calendar, events),
                    _buildUpcomingTab(calendar),
                    _buildRecentOutcomesTab(events),
                  ],
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  // 1. Overview Tab
  Widget _buildOverviewTab(Map<String, dynamic> summary, List<dynamic> calendar, List<dynamic> events) {
    final strongBuysToday = calendar.where((c) => c['recommendation'] == 'STRONG_BUY').toList();
    
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 48.0, vertical: 16.0),
      children: [
        // KPI Statistics Grid
        GridView.count(
          shrinkWrap: true,
          physics: const NeverScrollableScrollPhysics(),
          crossAxisCount: 4,
          crossAxisSpacing: 16,
          mainAxisSpacing: 16,
          childAspectRatio: 1.8,
          children: [
            _buildKpiCard('Total Reporting Today', '${summary["total_reporting_today"] ?? 0}', Icons.business, Colors.grey.shade800),
            _buildKpiCard('Pre-Market Releases', '${summary["pre_market"] ?? 0}', Icons.wb_sunny_outlined, Colors.orange.shade700),
            _buildKpiCard('After-Hours Releases', '${summary["after_hours"] ?? 0}', Icons.dark_mode_outlined, Colors.indigo.shade700),
            _buildKpiCard('High Conviction Buys', '${summary["high_conviction"] ?? 0}', Icons.workspace_premium, Colors.green.shade700),
          ],
        ),
        const SizedBox(height: 36),

        // High Conviction buys Carousel
        const Text(
          'TODAY\'S HIGH CONVICTION REPORTERS',
          style: TextStyle(
            fontFamily: 'Georgia',
            fontSize: 18,
            fontWeight: FontWeight.bold,
            letterSpacing: 1,
            color: Colors.black87,
          ),
        ),
        const SizedBox(height: 16),
        if (strongBuysToday.isEmpty)
          Container(
            padding: const EdgeInsets.all(24),
            decoration: BoxDecoration(
              border: Border.all(color: Colors.black12),
              color: Colors.white,
            ),
            child: const Text(
              'No STRONG BUY conviction stocks are scheduled to report today. The skies remain clear.',
              style: TextStyle(fontFamily: 'Georgia', fontSize: 16, color: Colors.black54),
            ),
          )
        else
          SizedBox(
            height: 170,
            child: ListView.builder(
              scrollDirection: Axis.horizontal,
              itemCount: strongBuysToday.length,
              itemBuilder: (context, index) {
                final item = strongBuysToday[index];
                return _buildBuffettCarouselCard(item);
              },
            ),
          ),
      ],
    );
  }

  Widget _buildKpiCard(String label, String value, IconData icon, Color color) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: Colors.black12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.02),
            blurRadius: 6,
            offset: const Offset(0, 3),
          )
        ]
      ),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(label, style: const TextStyle(fontSize: 12, color: Colors.black54, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text(value, style: const TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: Colors.black87)),
            ],
          ),
          Icon(icon, size: 36, color: color.withOpacity(0.8)),
        ],
      ),
    );
  }

  Widget _buildBuffettCarouselCard(dynamic item) {
    final score = item['score'] ?? 0;
    return GestureDetector(
      onTap: () => widget.onTickerTap(item['ticker']),
      child: Container(
        width: 280,
        margin: const EdgeInsets.only(right: 16, bottom: 8),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: const Color(0xFF00E676).withOpacity(0.3), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: const Color(0xFF00E676).withOpacity(0.05),
              blurRadius: 8,
              offset: const Offset(0, 4),
            )
          ]
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(item['ticker'], style: const TextStyle(fontFamily: 'Georgia', fontSize: 22, fontWeight: FontWeight.bold, color: Colors.black87)),
                    const SizedBox(height: 2),
                    SizedBox(
                      width: 140,
                      child: Text(item['company'] ?? '', maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(fontSize: 12, color: Colors.black54)),
                    ),
                  ],
                ),
                Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 38,
                      height: 38,
                      child: CircularProgressIndicator(
                        value: score / 100,
                        backgroundColor: Colors.grey.shade100,
                        color: const Color(0xFF00E676),
                        strokeWidth: 3.5,
                      ),
                    ),
                    Text('${score.toInt()}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
                  ],
                ),
              ],
            ),
            const Spacer(),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF00C853),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: const Text('STRONG BUY', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 10)),
                ),
                const Text('Deep Dive →', style: TextStyle(fontSize: 11, color: Colors.blue, fontWeight: FontWeight.bold)),
              ],
            ),
          ],
        ),
      ),
    );
  }

  // 2. Upcoming Tab
  Widget _buildUpcomingTab(List<dynamic> calendar) {
    if (calendar.isEmpty) {
      return const Center(
        child: Text(
          'No upcoming earnings found. The fields are quiet.',
          style: TextStyle(fontFamily: 'Georgia', fontSize: 18, color: Colors.black54),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 48.0, vertical: 16.0),
      itemCount: calendar.length,
      itemBuilder: (context, index) {
        final item = calendar[index];
        final timeOfDay = item['time_of_day'] ?? '';
        
        return Container(
          margin: const EdgeInsets.only(bottom: 16),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: Colors.black12),
          ),
          child: Row(
            children: [
              // Time of Day Badges
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                decoration: BoxDecoration(
                  color: timeOfDay == 'pre_market' ? Colors.orange.shade50 : Colors.indigo.shade50,
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Icon(
                  timeOfDay == 'pre_market' ? Icons.wb_sunny_outlined : Icons.dark_mode_outlined,
                  size: 20,
                  color: timeOfDay == 'pre_market' ? Colors.orange.shade800 : Colors.indigo.shade800,
                ),
              ),
              const SizedBox(width: 20),

              // Ticker & Info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${item['company']} (${item['ticker']})',
                      style: const TextStyle(fontFamily: 'Georgia', fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      'Expected Date: ${item["earnings_date"] ?? "N/A"}  ·  Estimated EPS: \$${item["eps_estimate"] != null ? item["eps_estimate"].toStringAsFixed(2) : "-"}',
                      style: const TextStyle(fontSize: 13, color: Colors.black54),
                    ),
                  ],
                ),
              ),

              // Conviction rating indicator
              if (item['recommendation'] != null)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: _getRecColor(item['recommendation']),
                    borderRadius: BorderRadius.circular(100),
                  ),
                  child: Text(
                    item['recommendation'].replaceAll('_', ' '),
                    style: TextStyle(
                      color: _getRecTextColor(item['recommendation']),
                      fontWeight: FontWeight.bold,
                      fontSize: 11,
                    ),
                  ),
                ),
              const SizedBox(width: 16),
              IconButton(
                icon: const Icon(Icons.chevron_right, color: Colors.black54),
                onPressed: () => widget.onTickerTap(item['ticker']),
              )
            ],
          ),
        );
      },
    );
  }

  // 3. Recent Outcomes Tab
  Widget _buildRecentOutcomesTab(List<dynamic> events) {
    if (events.isEmpty) {
      return const Center(
        child: Text(
          'No recent earnings releases found today.',
          style: TextStyle(fontFamily: 'Georgia', fontSize: 18, color: Colors.black54),
        ),
      );
    }

    return ListView.builder(
      padding: const EdgeInsets.symmetric(horizontal: 48.0, vertical: 16.0),
      itemCount: events.length,
      itemBuilder: (context, index) {
        final item = events[index];
        final surprise = item['surprise_pct'];
        final actual = item['eps_actual'];
        final est = item['eps_estimate'];
        
        bool isBeat = surprise != null && surprise > 0;
        bool isMiss = surprise != null && surprise < 0;

        Color badgeBg = const Color(0xFFF1F5F9);
        Color badgeText = const Color(0xFF475569);
        String prefix = "";
        String label = "Inline";

        if (isBeat) {
          badgeBg = const Color(0xFFE8F5E9);
          badgeText = const Color(0xFF2E7D32);
          prefix = "+";
          label = "BEAT ✅";
        } else if (isMiss) {
          badgeBg = const Color(0xFFFFEBEE);
          badgeText = const Color(0xFFC62828);
          label = "MISS ❌";
        }

        return Container(
          margin: const EdgeInsets.only(bottom: 16),
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: Colors.white,
            border: Border.all(color: Colors.black12),
          ),
          child: Row(
            children: [
              // Surprise Soft Badge
              Container(
                width: 100,
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: badgeBg,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      label,
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: badgeText),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      surprise != null ? '$prefix${surprise.toStringAsFixed(1)}%' : '-',
                      style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: badgeText),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 24),

              // Company Info
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '${item['company']} (${item['ticker']})',
                      style: const TextStyle(fontFamily: 'Georgia', fontSize: 18, fontWeight: FontWeight.bold, color: Colors.black87),
                    ),
                    const SizedBox(height: 6),
                    Row(
                      children: [
                        _buildMetricCol('Actual', actual != null ? '\$${actual.toStringAsFixed(2)}' : '-'),
                        const SizedBox(width: 32),
                        _buildMetricCol('Estimate', est != null ? '\$${est.toStringAsFixed(2)}' : '-'),
                        const SizedBox(width: 32),
                        _buildMetricCol('Report Date', item['report_date'] ?? 'N/A'),
                      ],
                    ),
                  ],
                ),
              ),

              // Mini Buffett Score gauge
              if (item['score'] != null) ...[
                Stack(
                  alignment: Alignment.center,
                  children: [
                    SizedBox(
                      width: 40,
                      height: 40,
                      child: CircularProgressIndicator(
                        value: item['score'] / 100,
                        backgroundColor: Colors.grey.shade100,
                        color: _getRecColor(item['recommendation']),
                        strokeWidth: 4,
                      ),
                    ),
                    Text('${item['score'].toInt()}', style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                  ],
                ),
                const SizedBox(width: 16),
              ],

              IconButton(
                icon: const Icon(Icons.chevron_right, color: Colors.black54),
                onPressed: () => widget.onTickerTap(item['ticker']),
              )
            ],
          ),
        );
      },
    );
  }

  Widget _buildMetricCol(String label, String val) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: const TextStyle(fontSize: 10, color: Colors.black54, fontWeight: FontWeight.bold)),
        const SizedBox(height: 2),
        Text(val, style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Colors.black87)),
      ],
    );
  }
}
