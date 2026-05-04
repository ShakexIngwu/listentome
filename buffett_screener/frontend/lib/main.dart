import 'package:flutter/material.dart';
import 'theme.dart';
import 'screens/home_dashboard.dart';
import 'screens/deep_dive.dart';
import 'screens/weekly_runs.dart';
import 'screens/daily_earnings.dart';

void main() {
  runApp(const BuffettScreenerApp());
}

class BuffettScreenerApp extends StatelessWidget {
  const BuffettScreenerApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Seasons of Investing',
      theme: BullishTheme.theme,
      home: const MainNavigationLayout(),
      debugShowCheckedModeBanner: false,
    );
  }
}

class MainNavigationLayout extends StatefulWidget {
  const MainNavigationLayout({super.key});

  @override
  State<MainNavigationLayout> createState() => _MainNavigationLayoutState();
}

class _MainNavigationLayoutState extends State<MainNavigationLayout> {
  int _selectedIndex = 0;
  String? _deepDiveTicker;

  void _onItemTapped(int index) {
    setState(() {
      _selectedIndex = index;
    });
  }

  void _navigateToDeepDive(String ticker) {
    setState(() {
      _deepDiveTicker = ticker;
      _selectedIndex = 3; // Deep Dive is now index 3
    });
  }

  @override
  Widget build(BuildContext context) {
    final List<Widget> screens = <Widget>[
      HomeDashboardScreen(onTickerTap: _navigateToDeepDive),
      WeeklyRunsScreen(onTickerTap: _navigateToDeepDive),
      DailyEarningsScreen(onTickerTap: _navigateToDeepDive),
      DeepDiveScreen(initialTicker: _deepDiveTicker),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Icon(Icons.park, color: BullishTheme.primary, size: 28),
            const SizedBox(width: 12),
            Text('Seasons of Investing', style: Theme.of(context).textTheme.displayLarge?.copyWith(fontSize: 24)),
          ],
        ),
        backgroundColor: BullishTheme.surface,
        scrolledUnderElevation: 0,
        bottom: PreferredSize(
          preferredSize: const Size.fromHeight(1.0),
          child: Container(color: BullishTheme.outline, height: 1.0),
        ),
      ),
      body: screens[_selectedIndex],
      bottomNavigationBar: BottomNavigationBar(
        items: const <BottomNavigationBarItem>[
          BottomNavigationBarItem(
            icon: Icon(Icons.home),
            label: 'My Seasons',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.article),
            label: 'Sunday Read',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.notifications),
            label: 'Daily Pulse',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.analytics),
            label: 'Deep Dive',
          ),
        ],
        currentIndex: _selectedIndex,
        selectedItemColor: BullishTheme.primary,
        unselectedItemColor: BullishTheme.textSecondary,
        backgroundColor: BullishTheme.surface,
        type: BottomNavigationBarType.fixed,
        onTap: _onItemTapped,
      ),
    );
  }
}
