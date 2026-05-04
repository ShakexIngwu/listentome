import 'package:flutter/material.dart';
import 'dart:math';
import '../portfolio_service.dart';
import '../api_service.dart';

enum WeatherState { sunny, cloudy, stormy }

class HomeDashboardScreen extends StatefulWidget {
  final Function(String) onTickerTap;

  const HomeDashboardScreen({super.key, required this.onTickerTap});

  @override
  State<HomeDashboardScreen> createState() => _HomeDashboardScreenState();
}

class _HomeDashboardScreenState extends State<HomeDashboardScreen> with SingleTickerProviderStateMixin {
  final ApiService _apiService = ApiService();
  PortfolioService? _portfolioService;
  List<PortfolioItem> _portfolio = [];
  bool _isLoading = true;
  double _portfolioChangePct = 0.0;
  double _totalValue = 0.0;

  late AnimationController _weatherAnimController;

  @override
  void initState() {
    super.initState();
    _weatherAnimController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 10),
    )..repeat();

    _loadPortfolio();
  }

  @override
  void dispose() {
    _weatherAnimController.dispose();
    super.dispose();
  }

  Future<void> _loadPortfolio() async {
    final service = await PortfolioService.init();
    final items = service.getPortfolio();

    double totalCost = 0.0;
    double currentValue = 0.0;

    for (var item in items) {
      try {
        final detail = await _apiService.getTickerDeepDive(item.ticker);
        final currentPrice = (detail.latestScore?['price'] ?? item.addedPrice).toDouble();
        totalCost += item.addedPrice;
        currentValue += currentPrice;
      } catch (e) {
        totalCost += item.addedPrice;
        currentValue += item.addedPrice;
      }
    }

    double pctChange = 0.0;
    if (totalCost > 0) {
      pctChange = ((currentValue - totalCost) / totalCost) * 100;
    }

    setState(() {
      _portfolioService = service;
      _portfolio = items;
      _totalValue = currentValue;
      _portfolioChangePct = pctChange;
      _isLoading = false;
    });
  }

  WeatherState get _currentWeather {
    if (_portfolio.isEmpty) return WeatherState.sunny; // Default
    if (_portfolioChangePct >= 1.0) return WeatherState.sunny;
    if (_portfolioChangePct <= -1.0) return WeatherState.stormy;
    return WeatherState.cloudy;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : Stack(
              children: [
                // Background & Weather Scene
                Positioned.fill(
                  child: AnimatedBuilder(
                    animation: _weatherAnimController,
                    builder: (context, child) {
                      return CustomPaint(
                        painter: LandscapePainter(
                          weather: _currentWeather,
                          animationValue: _weatherAnimController.value,
                        ),
                      );
                    },
                  ),
                ),
                // Overlay Content
                SafeArea(
                  child: Padding(
                    padding: const EdgeInsets.all(32.0),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        _buildGreeting(),
                        const Spacer(),
                        _buildPortfolioSummaryCard(),
                      ],
                    ),
                  ),
                ),
              ],
            ),
    );
  }

  Widget _buildGreeting() {
    String greeting = "It's a beautiful day.";
    if (_currentWeather == WeatherState.cloudy) {
      greeting = "The winds of change are blowing.";
    } else if (_currentWeather == WeatherState.stormy) {
      greeting = "Storms pass. Roots grow deeper.";
    }

    if (_portfolio.isEmpty) {
      greeting = "Plant your first seed. Explore the Sunday Read.";
    }

    return Text(
      greeting,
      style: const TextStyle(
        fontSize: 32,
        fontWeight: FontWeight.w300,
        color: Colors.white,
        shadows: [Shadow(blurRadius: 4, color: Colors.black45, offset: Offset(1, 1))],
      ),
    );
  }

  Widget _buildPortfolioSummaryCard() {
    return Container(
      width: 320,
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: Colors.black.withOpacity(0.6),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.1)),
        boxShadow: [
          BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 10, offset: const Offset(0, 5)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            "Paper Portfolio",
            style: TextStyle(color: Colors.white.withOpacity(0.7), fontSize: 14, letterSpacing: 1.2),
          ),
          const SizedBox(height: 8),
          Text(
            _portfolio.isEmpty ? "Empty" : "\$${_totalValue.toStringAsFixed(2)}",
            style: const TextStyle(color: Colors.white, fontSize: 36, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 4),
          if (_portfolio.isNotEmpty)
            Row(
              children: [
                Icon(
                  _portfolioChangePct >= 0 ? Icons.arrow_upward : Icons.arrow_downward,
                  color: _portfolioChangePct >= 0 ? Colors.greenAccent : Colors.redAccent,
                  size: 16,
                ),
                const SizedBox(width: 4),
                Text(
                  "${_portfolioChangePct.abs().toStringAsFixed(2)}% total",
                  style: TextStyle(
                    color: _portfolioChangePct >= 0 ? Colors.greenAccent : Colors.redAccent,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          const SizedBox(height: 24),
          ElevatedButton(
            onPressed: () => widget.onTickerTap(''), // Let main nav handle deep dive or read
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.white.withOpacity(0.1),
              foregroundColor: Colors.white,
              elevation: 0,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              minimumSize: const Size(double.infinity, 48),
            ),
            child: Text(_portfolio.isEmpty ? "Discover Companies" : "View Details"),
          )
        ],
      ),
    );
  }
}

class LandscapePainter extends CustomPainter {
  final WeatherState weather;
  final double animationValue;

  LandscapePainter({required this.weather, required this.animationValue});

  @override
  void paint(Canvas canvas, Size size) {
    // 1. Sky Gradient
    Color skyTop;
    Color skyBottom;
    if (weather == WeatherState.sunny) {
      skyTop = const Color(0xFF4A90E2);
      skyBottom = const Color(0xFF87CEFA);
    } else if (weather == WeatherState.cloudy) {
      skyTop = const Color(0xFF78909C);
      skyBottom = const Color(0xFFB0BEC5);
    } else {
      skyTop = const Color(0xFF263238);
      skyBottom = const Color(0xFF455A64);
    }

    final skyRect = Rect.fromLTWH(0, 0, size.width, size.height);
    final skyPaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: [skyTop, skyBottom],
      ).createShader(skyRect);
    canvas.drawRect(skyRect, skyPaint);

    // 2. Weather Effects (Clouds/Stars/Rain)
    if (weather == WeatherState.sunny) {
      _drawSun(canvas, size);
    } else if (weather == WeatherState.stormy) {
      _drawRain(canvas, size);
    }

    // 3. Ground/Hills
    Color hillColor = weather == WeatherState.stormy ? const Color(0xFF3E2723) : const Color(0xFF558B2F);
    if (weather == WeatherState.cloudy) hillColor = const Color(0xFF8D6E63);

    final hillPaint = Paint()..color = hillColor;
    final path = Path();
    path.moveTo(0, size.height * 0.7);
    path.quadraticBezierTo(size.width * 0.25, size.height * 0.65, size.width * 0.5, size.height * 0.75);
    path.quadraticBezierTo(size.width * 0.75, size.height * 0.85, size.width, size.height * 0.7);
    path.lineTo(size.width, size.height);
    path.lineTo(0, size.height);
    path.close();
    canvas.drawPath(path, hillPaint);

    // 4. The Tree
    _drawTree(canvas, size);
  }

  void _drawSun(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.yellow.withOpacity(0.8)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 20);
    canvas.drawCircle(Offset(size.width * 0.8, size.height * 0.2), 60, paint);
    canvas.drawCircle(Offset(size.width * 0.8, size.height * 0.2), 40, Paint()..color = Colors.yellow);
  }

  void _drawRain(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withOpacity(0.4)
      ..strokeWidth = 2;
    final rand = Random(42); // Deterministic random for stationary lines, but animated offset
    for (int i = 0; i < 100; i++) {
      double x = rand.nextDouble() * size.width;
      double y = (rand.nextDouble() * size.height + animationValue * size.height) % size.height;
      canvas.drawLine(Offset(x, y), Offset(x - 5, y + 20), paint);
    }
  }

  void _drawTree(Canvas canvas, Size size) {
    // Trunk
    final trunkPaint = Paint()..color = const Color(0xFF4E342E)..strokeWidth = 12..strokeCap = StrokeCap.round;
    final trunkBottom = Offset(size.width * 0.3, size.height * 0.8);
    final trunkTop = Offset(size.width * 0.3, size.height * 0.55);
    canvas.drawLine(trunkBottom, trunkTop, trunkPaint);

    // Leaves
    if (weather != WeatherState.stormy) {
      Color leafColor = weather == WeatherState.sunny ? const Color(0xFF2E7D32) : const Color(0xFFD84315); // Green or Autumn orange
      final leafPaint = Paint()..color = leafColor.withOpacity(0.9);
      
      canvas.drawCircle(Offset(size.width * 0.3, size.height * 0.55), 60, leafPaint);
      canvas.drawCircle(Offset(size.width * 0.25, size.height * 0.6), 50, leafPaint);
      canvas.drawCircle(Offset(size.width * 0.35, size.height * 0.6), 50, leafPaint);
      canvas.drawCircle(Offset(size.width * 0.3, size.height * 0.48), 45, leafPaint);
    }
  }

  @override
  bool shouldRepaint(covariant LandscapePainter oldDelegate) {
    return oldDelegate.weather != weather || oldDelegate.animationValue != animationValue;
  }
}
