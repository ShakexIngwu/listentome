import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';
import '../portfolio_service.dart';
import '../api_service.dart';

class HomeDashboardScreen extends StatefulWidget {
  final Function(String) onTickerTap;
  const HomeDashboardScreen({super.key, required this.onTickerTap});

  @override
  State<HomeDashboardScreen> createState() => _HomeDashboardScreenState();
}

class _HomeDashboardScreenState extends State<HomeDashboardScreen> with TickerProviderStateMixin {
  late PortfolioService _portfolioService;
  final ApiService _apiService = ApiService();
  
  List<PortfolioItem> _portfolio = [];
  Map<String, double> _currentPrices = {};
  bool _isLoading = true;

  late AnimationController _waterAnimController;

  final List<Offset> _slotPositions = [
    const Offset(0.3, 0.35),
    const Offset(0.5, 0.25),
    const Offset(0.7, 0.35),
    const Offset(0.2, 0.5),
    const Offset(0.4, 0.4),
    const Offset(0.6, 0.4),
    const Offset(0.8, 0.5),
    const Offset(0.3, 0.65),
    const Offset(0.5, 0.55),
    const Offset(0.7, 0.65),
  ];

  @override
  void initState() {
    super.initState();
    _waterAnimController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 4),
    )..repeat();
    _initData();
  }

  Future<void> _initData() async {
    _portfolioService = await PortfolioService.init();
    _portfolio = _portfolioService.getPortfolio();
    
    for (var item in _portfolio) {
      try {
        final detail = await _apiService.getTickerDeepDive(item.ticker);
        final price = detail.company['price']?.toDouble() ?? item.addedPrice;
        _currentPrices[item.ticker] = price;
      } catch (e) {
        _currentPrices[item.ticker] = item.addedPrice;
      }
    }

    if (mounted) {
      setState(() {
        _isLoading = false;
      });
    }
  }

  @override
  void dispose() {
    _waterAnimController.dispose();
    super.dispose();
  }

  void _showTreeDetails(PortfolioItem item, double currentPrice, double gainPct) {
    showDialog(
      context: context,
      builder: (context) {
        final isGain = gainPct >= 0;
        final color = isGain ? const Color(0xFF10B981) : const Color(0xFFF59E0B);
        return BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: Dialog(
            backgroundColor: Colors.transparent,
            elevation: 0,
            child: Container(
              padding: const EdgeInsets.all(24),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.6),
                borderRadius: BorderRadius.circular(24),
                border: Border.all(color: Colors.white, width: 1.5),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    item.ticker,
                    style: GoogleFonts.notoSerif(
                      fontSize: 32,
                      fontWeight: FontWeight.bold,
                      color: const Color(0xFF1A1C1A),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    item.companyName,
                    style: GoogleFonts.manrope(
                      fontSize: 16,
                      color: const Color(0xFF4D4635),
                    ),
                  ),
                  const SizedBox(height: 24),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      _buildDetailMetric('Added Price', '\$${item.addedPrice.toStringAsFixed(2)}'),
                      _buildDetailMetric('Current Value', '\$${currentPrice.toStringAsFixed(2)}'),
                    ],
                  ),
                  const SizedBox(height: 24),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: color.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(999),
                    ),
                    child: Text(
                      '${isGain ? '+' : ''}${(gainPct * 100).toStringAsFixed(2)}%',
                      style: GoogleFonts.manrope(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: color,
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
                  ElevatedButton(
                    onPressed: () {
                      Navigator.pop(context);
                      widget.onTickerTap(item.ticker);
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFFD4AF37),
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      minimumSize: const Size(double.infinity, 48),
                    ),
                    child: Text('View Details', style: GoogleFonts.manrope(fontWeight: FontWeight.w600)),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildDetailMetric(String label, String value) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: GoogleFonts.manrope(
            fontSize: 12,
            fontWeight: FontWeight.bold,
            color: const Color(0xFF7F7663),
          ),
        ),
        const SizedBox(height: 4),
        Text(
          value,
          style: GoogleFonts.manrope(
            fontSize: 20,
            fontWeight: FontWeight.w600,
            color: const Color(0xFF1A1C1A),
          ),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return const Center(child: CircularProgressIndicator(color: Color(0xFFD4AF37)));
    }

    double totalAdded = 0;
    double totalCurrent = 0;
    for (var item in _portfolio) {
      totalAdded += item.addedPrice;
      totalCurrent += _currentPrices[item.ticker] ?? item.addedPrice;
    }
    double overallGain = totalAdded > 0 ? (totalCurrent - totalAdded) / totalAdded : 0;
    bool isOverallGain = overallGain >= 0;

    return Scaffold(
      backgroundColor: const Color(0xFFFAF9F6), // Warm paper neutral
      body: Stack(
        children: [
          // Background Garden Image
          Positioned.fill(
            child: Image.asset(
              'assets/images/portfolio_garden_bg.jpg',
              fit: BoxFit.cover,
            ),
          ),

          // Water & Bubble Animations Overlay
          Positioned.fill(
            child: AnimatedBuilder(
              animation: _waterAnimController,
              builder: (context, child) {
                return CustomPaint(
                  painter: WaterEffectsPainter(animationValue: _waterAnimController.value),
                );
              },
            ),
          ),

          // Trees Overlay
          Positioned.fill(
            child: LayoutBuilder(
              builder: (context, constraints) {
                return Stack(
                  fit: StackFit.expand,
                  clipBehavior: Clip.none,
                  children: List.generate(10, (index) {
                    if (index >= _portfolio.length) {
                      return const SizedBox.shrink(); // Empty slot
                    }
                    
                    final item = _portfolio[index];
                    final currentPrice = _currentPrices[item.ticker] ?? item.addedPrice;
                    final gainPct = item.addedPrice > 0 ? (currentPrice - item.addedPrice) / item.addedPrice : 0.0;
                    
                    final pos = _slotPositions[index];
                    final x = pos.dx * constraints.maxWidth;
                    final y = pos.dy * constraints.maxHeight;

                    return Positioned(
                      left: x - 40,
                      top: y - 80,
                      child: GestureDetector(
                        onTap: () => _showTreeDetails(item, currentPrice, gainPct),
                        child: TreeWidget(gainPct: gainPct),
                      ),
                    );
                  }),
                );
              }
            ),
          ),

          // Top Glassmorphic Summary Card
          Positioned(
            top: 64,
            left: 32,
            right: 32,
            child: ClipRRect(
              borderRadius: BorderRadius.circular(24),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
                child: Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.6),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: Colors.white, width: 1.0),
                  ),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'Portfolio Harvest',
                            style: GoogleFonts.notoSerif(
                              fontSize: 24,
                              fontWeight: FontWeight.w500,
                              color: const Color(0xFF1A1C1A),
                            ),
                          ),
                          const SizedBox(height: 8),
                          Text(
                            '\$${totalCurrent.toStringAsFixed(2)}',
                            style: GoogleFonts.manrope(
                              fontSize: 32,
                              fontWeight: FontWeight.w600,
                              color: const Color(0xFF735C00), // Primary
                            ),
                          ),
                        ],
                      ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        decoration: BoxDecoration(
                          color: (isOverallGain ? const Color(0xFF10B981) : const Color(0xFFF59E0B)).withOpacity(0.15),
                          borderRadius: BorderRadius.circular(999),
                        ),
                        child: Text(
                          '${isOverallGain ? '+' : ''}${(overallGain * 100).toStringAsFixed(2)}%',
                          style: GoogleFonts.manrope(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                            color: isOverallGain ? const Color(0xFF10B981) : const Color(0xFFF59E0B),
                          ),
                        ),
                      )
                    ],
                  ),
                ),
              ),
            ),
          ),

          // Empty State Message
          if (_portfolio.isEmpty)
            Center(
              child: ClipRRect(
                borderRadius: BorderRadius.circular(24),
                child: BackdropFilter(
                  filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 32, vertical: 24),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.6),
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: Colors.white, width: 1.0),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.spa, size: 48, color: Color(0xFF735C00)),
                        const SizedBox(height: 16),
                        Text(
                          'Your garden is empty',
                          style: GoogleFonts.notoSerif(
                            fontSize: 24,
                            fontWeight: FontWeight.bold,
                            color: const Color(0xFF1A1C1A),
                          ),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'Add stocks to your portfolio to plant trees.',
                          style: GoogleFonts.manrope(
                            fontSize: 16,
                            color: const Color(0xFF4D4635),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class WaterEffectsPainter extends CustomPainter {
  final double animationValue;

  WaterEffectsPainter({required this.animationValue});

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withOpacity(0.4)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 2.0;
      
    final bubblePaint = Paint()
      ..color = Colors.white.withOpacity(0.6)
      ..style = PaintingStyle.fill;

    int numRipples = 8;
    for (int i = 0; i < numRipples; i++) {
      double progress = (animationValue + (i / numRipples)) % 1.0;
      double yOffset = size.height * 0.6 + (progress * size.height * 0.3);
      double xOffset = size.width * 0.2 + (sin(progress * pi * 2) * size.width * 0.3) + (i * 20);
      
      double rippleWidth = 40.0 * sin(progress * pi); // fades in/out
      paint.color = Colors.white.withOpacity(0.3 * sin(progress * pi));
      canvas.drawLine(Offset(xOffset, yOffset), Offset(xOffset + rippleWidth, yOffset + (rippleWidth * 0.2)), paint);
    }

    final rand = Random(42); // stable seed for bubble positions
    for (int i = 0; i < 20; i++) {
      double baseX = size.width * 0.5 + (rand.nextDouble() - 0.5) * size.width * 0.8;
      double baseY = size.height * 0.7 + rand.nextDouble() * size.height * 0.25;
      
      double bubbleProgress = (animationValue + rand.nextDouble()) % 1.0;
      double currentY = baseY - (bubbleProgress * 100); // Rises by 100 pixels
      double currentX = baseX + sin(bubbleProgress * pi * 4 + i) * 10; // Wiggles
      
      double radius = 2.0 + rand.nextDouble() * 3.0;
      double opacity = sin(bubbleProgress * pi) * 0.6; // Fade in and out
      
      bubblePaint.color = Colors.white.withOpacity(opacity);
      canvas.drawCircle(Offset(currentX, currentY), radius, bubblePaint);
    }
  }

  @override
  bool shouldRepaint(covariant WaterEffectsPainter oldDelegate) {
    return oldDelegate.animationValue != animationValue;
  }
}

class TreeWidget extends StatefulWidget {
  final double gainPct;

  const TreeWidget({super.key, required this.gainPct});

  @override
  State<TreeWidget> createState() => _TreeWidgetState();
}

class _TreeWidgetState extends State<TreeWidget> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _growAnimation;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    );
    _growAnimation = CurvedAnimation(parent: _controller, curve: Curves.easeOutBack);
    _controller.forward();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _growAnimation,
      builder: (context, child) {
        double scale = 1.0 + (widget.gainPct * 2).clamp(-0.2, 0.5);
        scale *= _growAnimation.value;
        return Transform.scale(
          scale: scale,
          child: Image.asset(
            'assets/images/glass_tree_transparent.png',
            width: 80,
            height: 100,
            fit: BoxFit.contain,
          ),
        );
      },
    );
  }
}
