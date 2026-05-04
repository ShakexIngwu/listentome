import 'package:flutter/material.dart';
import 'package:fl_chart/fl_chart.dart';
import '../api_service.dart';
import '../theme.dart';

class DeepDiveScreen extends StatefulWidget {
  final String? initialTicker;

  const DeepDiveScreen({super.key, this.initialTicker});

  @override
  State<DeepDiveScreen> createState() => _DeepDiveScreenState();
}

class _DeepDiveScreenState extends State<DeepDiveScreen> {
  final ApiService apiService = ApiService();
  List<String> tickers = [];
  String? selectedTicker;
  TickerDetail? tickerDetail;
  bool isLoading = false;
  late TextEditingController _textEditingController;

  @override
  void initState() {
    super.initState();
    _loadTickers();
    if (widget.initialTicker != null) {
      _loadTickerDetail(widget.initialTicker!);
    }
  }

  @override
  void didUpdateWidget(DeepDiveScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.initialTicker != oldWidget.initialTicker && widget.initialTicker != null) {
      _loadTickerDetail(widget.initialTicker!);
      if (tickers.isNotEmpty) {
        // Update the autocomplete text field if it's already rendered
        // This is a bit tricky with Autocomplete, so it relies on rebuilding
      }
    }
  }

  Future<void> _loadTickers() async {
    try {
      final loadedTickers = await apiService.getTickers();
      setState(() {
        tickers = loadedTickers;
      });
    } catch (e) {
      // Handle error
    }
  }

  Future<void> _loadTickerDetail(String ticker) async {
    setState(() {
      isLoading = true;
      selectedTicker = ticker;
    });
    try {
      final detail = await apiService.getTickerDeepDive(ticker);
      setState(() {
        tickerDetail = detail;
      });
    } catch (e) {
      setState(() {
        tickerDetail = null;
      });
    } finally {
      setState(() {
        isLoading = false;
      });
    }
  }

  Color _getRecColor(String rec) {
    switch (rec) {
      case 'STRONG_BUY': return BullishTheme.primary;
      case 'BUY': return const Color(0xFF62FF96);
      case 'HOLD': return const Color(0xFFFFF291);
      default: return const Color(0xFFBA1A1A);
    }
  }

  Color _getRecTextColor(String rec) {
    return (rec == 'STRONG_BUY' || rec == 'PASS' || rec == 'BUY') 
        ? Colors.white 
        : BullishTheme.textPrimary;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Autocomplete<String>(
              optionsBuilder: (TextEditingValue textEditingValue) {
                if (textEditingValue.text == '') {
                  return const Iterable<String>.empty();
                }
                return tickers.where((String option) {
                  return option.contains(textEditingValue.text.toUpperCase());
                });
              },
              onSelected: (String selection) {
                _loadTickerDetail(selection);
              },
              fieldViewBuilder: (context, textEditingController, focusNode, onFieldSubmitted) {
                return TextField(
                  controller: textEditingController,
                  focusNode: focusNode,
                  decoration: const InputDecoration(
                    labelText: 'Search for a ticker...',
                    border: OutlineInputBorder(),
                    focusedBorder: OutlineInputBorder(borderSide: BorderSide(color: BullishTheme.primary)),
                  ),
                );
              },
            ),
            const SizedBox(height: 16),
            Expanded(
              child: isLoading
                  ? const Center(child: CircularProgressIndicator(color: BullishTheme.primary))
                  : tickerDetail == null
                      ? const Center(child: Text('Select a ticker or no data found.'))
                      : _buildDetailContent(),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDetailContent() {
    final comp = tickerDetail!.company;
    final latest = tickerDetail!.latestScore;

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('${comp['name'] ?? selectedTicker} ($selectedTicker)', style: Theme.of(context).textTheme.displayLarge),
          Text('${comp['sector'] ?? ''} · ${comp['industry'] ?? ''} · ${comp['market_cap_category'] ?? ''}', style: Theme.of(context).textTheme.bodyMedium),
          const SizedBox(height: 24),
          if (latest != null) ...[
            _buildMetricCards(latest),
            const SizedBox(height: 24),
            Text('Score Breakdown', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            SizedBox(
              height: 200,
              child: _buildRadarChart(latest),
            ),
            const SizedBox(height: 24),
            if (latest['investment_thesis'] != null && latest['investment_thesis'] != 'None') ...[
              Text('📝 Investment Thesis', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(latest['investment_thesis'].toString(), style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 24),
            ],
            if (latest['moat_summary'] != null && latest['moat_summary'] != 'None') ...[
              Text('🏰 Moat Summary', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              Text(latest['moat_summary'].toString(), style: Theme.of(context).textTheme.bodyLarge),
              const SizedBox(height: 24),
            ],
            if (latest['risk_factors'] != null && latest['risk_factors'] != 'None' && latest['risk_factors'] != '[]') ...[
              Container(
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: const Color(0xFFFFF291),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Row(
                      children: [
                        Icon(Icons.warning_amber_rounded, color: Color(0xFF685F0B)),
                        SizedBox(width: 8),
                        Text('Risk Factors', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Color(0xFF685F0B))),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(latest['risk_factors'].toString(), style: const TextStyle(color: Color(0xFF5D5400))),
                  ],
                ),
              ),
              const SizedBox(height: 24),
            ],
          ],
          if (tickerDetail!.history.isNotEmpty) ...[
            Text('📈 Score History', style: Theme.of(context).textTheme.titleLarge),
            const SizedBox(height: 16),
            SizedBox(
              height: 250,
              child: _buildHistoryChart(tickerDetail!.history),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildMetricCards(Map<String, dynamic> latest) {
    final isStrongBuy = latest['recommendation'] == 'STRONG_BUY';
    
    return Row(
      children: [
        Expanded(
          child: Card(
            child: Container(
              decoration: isStrongBuy ? BoxDecoration(
                borderRadius: BorderRadius.circular(16),
                gradient: RadialGradient(
                  colors: [BullishTheme.primary.withOpacity(0.15), Colors.transparent],
                  radius: 2,
                ),
              ) : null,
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Text('Buffett Score', style: Theme.of(context).textTheme.bodyMedium),
                  Text('${latest['total_score']}/100', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: BullishTheme.primary)),
                ],
              ),
            ),
          ),
        ),
        Expanded(
          child: Card(
            child: Container(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Text('Recommendation', style: Theme.of(context).textTheme.bodyMedium),
                  const SizedBox(height: 4),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                    decoration: BoxDecoration(
                      color: _getRecColor(latest['recommendation']),
                      borderRadius: BorderRadius.circular(16),
                    ),
                    child: Text(
                      (latest['recommendation'] ?? '').toString().replaceAll('_', ' '),
                      style: TextStyle(color: _getRecTextColor(latest['recommendation']), fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
        Expanded(
          child: Card(
            child: Container(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Text('Price', style: Theme.of(context).textTheme.bodyMedium),
                  Text('\$${latest['price']}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ),
        ),
        Expanded(
          child: Card(
            child: Container(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Text('Intrinsic Value', style: Theme.of(context).textTheme.bodyMedium),
                  Text('\$${latest['intrinsic_value']}', style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildRadarChart(Map<String, dynamic> latest) {
    return BarChart(
      BarChartData(
        alignment: BarChartAlignment.spaceAround,
        barTouchData: BarTouchData(enabled: false),
        titlesData: FlTitlesData(
          show: true,
          bottomTitles: AxisTitles(
            sideTitles: SideTitles(
              showTitles: true,
              getTitlesWidget: (value, meta) {
                final titles = ['EPS', 'ROE', 'MoS', 'Lev', 'FCF', 'Moat', 'LLM'];
                if (value.toInt() >= 0 && value.toInt() < titles.length) {
                  return Padding(
                    padding: const EdgeInsets.only(top: 8.0),
                    child: Text(titles[value.toInt()], style: const TextStyle(fontSize: 10)),
                  );
                }
                return const SizedBox();
              },
            ),
          ),
          leftTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: const AxisTitles(sideTitles: SideTitles(showTitles: false)),
        ),
        gridData: const FlGridData(show: false),
        borderData: FlBorderData(show: false),
        barGroups: [
          BarChartGroupData(x: 0, barRods: [BarChartRodData(toY: (latest['eps_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
          BarChartGroupData(x: 1, barRods: [BarChartRodData(toY: (latest['roe_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
          BarChartGroupData(x: 2, barRods: [BarChartRodData(toY: (latest['mos_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
          BarChartGroupData(x: 3, barRods: [BarChartRodData(toY: (latest['leverage_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
          BarChartGroupData(x: 4, barRods: [BarChartRodData(toY: (latest['fcf_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
          BarChartGroupData(x: 5, barRods: [BarChartRodData(toY: (latest['moat_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
          BarChartGroupData(x: 6, barRods: [BarChartRodData(toY: (latest['llm_score'] ?? 0).toDouble(), color: const Color(0xFF2979FF), width: 16, borderRadius: BorderRadius.circular(4))]),
        ],
      ),
    );
  }

  Widget _buildHistoryChart(List<dynamic> history) {
    List<FlSpot> spots = [];
    for (int i = 0; i < history.length; i++) {
      spots.add(FlSpot(i.toDouble(), (history[i]['score'] ?? 0).toDouble()));
    }

    return LineChart(
      LineChartData(
        gridData: const FlGridData(show: false),
        titlesData: const FlTitlesData(
          bottomTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
          leftTitles: AxisTitles(
            sideTitles: SideTitles(showTitles: true, reservedSize: 40),
          ),
        ),
        borderData: FlBorderData(show: false),
        lineBarsData: [
          LineChartBarData(
            spots: spots,
            isCurved: true,
            color: const Color(0xFF2979FF),
            barWidth: 3,
            isStrokeCapRound: true,
            dotData: const FlDotData(show: false),
            belowBarData: BarAreaData(
              show: true,
              gradient: LinearGradient(
                colors: [
                  const Color(0xFF2979FF).withOpacity(0.3),
                  const Color(0xFF2979FF).withOpacity(0.0),
                ],
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
