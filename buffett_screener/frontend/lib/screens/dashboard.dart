import 'package:flutter/material.dart';
import '../api_service.dart';
import '../theme.dart';

class DashboardScreen extends StatefulWidget {
  final Function(String) onTickerTap;

  const DashboardScreen({super.key, required this.onTickerTap});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  final ApiService apiService = ApiService();
  late Future<List<TopPick>> futurePicks;

  @override
  void initState() {
    super.initState();
    futurePicks = apiService.getTopPicks();
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
      body: FutureBuilder<List<TopPick>>(
        future: futurePicks,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(
              child: CircularProgressIndicator(color: BullishTheme.primary),
            );
          } else if (snapshot.hasError) {
            return Center(child: Text('Error: ${snapshot.error}'));
          } else if (!snapshot.hasData || snapshot.data!.isEmpty) {
            return const Center(child: Text('No stocks found.'));
          }

          final picks = snapshot.data!;
          return ListView.builder(
            padding: const EdgeInsets.all(16),
            itemCount: picks.length,
            itemBuilder: (context, index) {
              final pick = picks[index];
              final isStrongBuy = pick.recommendation == 'STRONG_BUY';
              
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Card(
                  clipBehavior: Clip.hardEdge,
                  child: InkWell(
                    onTap: () => widget.onTickerTap(pick.ticker),
                    child: Container(
                      decoration: isStrongBuy ? BoxDecoration(
                        gradient: RadialGradient(
                          colors: [
                            BullishTheme.primary.withOpacity(0.15),
                            Colors.transparent,
                          ],
                          radius: 2,
                        ),
                      ) : null,
                      padding: const EdgeInsets.all(16),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(pick.ticker, style: Theme.of(context).textTheme.titleLarge),
                                Text(pick.company, style: Theme.of(context).textTheme.bodyMedium),
                              ],
                            ),
                          ),
                          Column(
                            children: [
                              Text('Score', style: TextStyle(fontSize: 10, color: BullishTheme.textSecondary)),
                              const SizedBox(height: 4),
                              Stack(
                                alignment: Alignment.center,
                                children: [
                                  SizedBox(
                                    width: 40,
                                    height: 40,
                                    child: CircularProgressIndicator(
                                      value: pick.score / 100,
                                      backgroundColor: BullishTheme.background,
                                      color: BullishTheme.primary,
                                      strokeWidth: 4,
                                    ),
                                  ),
                                  Text('${pick.score.toInt()}', style: const TextStyle(fontWeight: FontWeight.bold)),
                                ],
                              ),
                            ],
                          ),
                          const SizedBox(width: 16),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                            decoration: BoxDecoration(
                              color: _getRecColor(pick.recommendation),
                              borderRadius: BorderRadius.circular(100),
                            ),
                            child: Text(
                              pick.recommendation.replaceAll('_', ' '),
                              style: TextStyle(
                                color: _getRecTextColor(pick.recommendation),
                                fontWeight: FontWeight.bold,
                                fontSize: 12,
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
              );
            },
          );
        },
      ),
    );
  }
}
