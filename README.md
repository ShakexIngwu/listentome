# 📈 ListenToMe — Warren Buffett Stock Screener

A state-of-the-art automated stock analysis platform and ingestion pipeline. It leverages quantitative financial metrics, discounted cash flow (DCF) models, and Google Gemini LLM analysis via the Google Antigravity (AGY) SDK to rank and generate deep pitch decks for potential Warren Buffett style investments.

---

## 🕰️ Scheduled Pipeline Jobs

All scheduled jobs are executed by the APScheduler daemon running in the `buffett_backend` service. To prevent time-drift issues and align with US market hours, all jobs are configured to run explicitly in local **Pacific Time (`America/Los_Angeles`)**.

### Summary of Scheduled Jobs

| Job Name | Identifier | Schedule Trigger (PT) | Frequency | Core Goal / Objective |
| :--- | :--- | :--- | :--- | :--- |
| **Daily Buffett Analysis** | `daily_analysis` | `04:00 AM` | Daily | Refresh basic company info (e.g. price, cap, PE) and run full Buffett valuation + score pipeline. |
| **Daily Earnings Tracker (AM)** | `daily_earnings_am` | `07:00 AM` | Mon–Fri | Scan EDGAR RSS 8-K feed (pre-market) for earnings filings. Run re-analysis if material. |
| **Daily Earnings Tracker (PM)** | `daily_earnings_pm` | `18:00 PM` (6 PM) | Mon–Fri | Scan EDGAR RSS 8-K feed (after-hours) for earnings filings. Run re-analysis if material. |
| **Morning Upcoming Earnings Alert** | `notify_coming_earnings` | `08:30 AM` | Daily | Query and notify user of upcoming corporate earnings in the next 7 days. |
| **Afternoon Recent Earnings Summary** | `summarize_recent_earnings` | `17:00 PM` (5 PM) | Daily | Aggregate and alert user of earnings beats/misses/summaries from the last 24 hours. |
| **NASDAQ Weekly Ingestion** | `weekly_ingestion` | `02:00 AM` | Sunday | Fetch NASDAQ company listings, pull full yfinance historical data, and run baseline analysis. |
| **PostgreSQL Daily Backup** | `daily_backup` | `03:00 AM` | Daily | Export Postgres databases to compressed SQL archives (30-day rotation retention). |

---

## 🔍 Detailed Job Breakdowns

### 1. Daily Buffett Analysis (`daily_analysis`)
* **Time**: Daily at 4:00 AM PT.
* **Goal**: Refreshes basic security indicators (e.g., market capitalization, current pricing, PE ratios, and forward EPS) via a streamlined `yfinance` crawl. This skips heavy historical pulls to respect API limits. It feeds updated candidates to the core DCF and Gemini Analysis models, exporting fresh ratings to the DuckDB analytics read-replica for the dashboard.
* **Manual Override**: `make run-daily-analysis`

### 2. Daily Earnings Tracker AM & PM (`daily_earnings_am` / `daily_earnings_pm`)
* **Time**: Monday through Friday at 7:00 AM PT (pre-market scan) and 6:00 PM PT (after-hours scan).
* **Goal**: First, updates the SEC CIK-to-ticker mapping database. It then polls the SEC EDGAR RSS feed for newly filed 8-K reports (earnings announcements) filed in the previous 25 hours. When a report is found:
  1. Resolves the filing CIK back to the ticker.
  2. Extracts reported EPS and compares it to estimates.
  3. Evaluates if the surprise triggers "material changes" (>5% deviation).
  4. Triggers immediate re-scoring & analysis for affected tickers.
* **Manual Override**: `make run-earnings-update`

### 3. Morning Upcoming Earnings Alert (`notify_coming_earnings`)
* **Time**: Daily at 8:30 AM PT.
* **Goal**: Scrapes/queries the internal calendar of earnings for active tickers scheduled to report over the next 7 days, building lists of tickers, dates, and forecast EPS. Fires a summary desktop alert to prepare you for the day's market action.
* **Manual Override**: `make run-notify-coming`

### 4. Afternoon Recent Earnings Summary (`summarize_recent_earnings`)
* **Time**: Daily at 5:00 PM PT.
* **Goal**: Gathers all earnings events recorded in the database over the last 24 hours, summarizes the aggregate counts of Beats, Misses, and In-line results, and delivers a consolidated desktop notification list.
* **Manual Override**: `make run-summarize-recent`

### 5. NASDAQ Weekly Ingestion (`weekly_ingestion`)
* **Time**: Every Sunday at 2:00 AM PT.
* **Goal**: Performs the heavy-duty data refresh needed to maintain absolute accuracy:
  * Pulls complete listing changes from the NASDAQ screener api (delisted vs new listings).
  * Executes a rate-throttled historical yfinance crawl for full EPS histories and statements.
  * Runs the complete quantitative screening and multi-stage Gemini scoring models.
  * Rebuilds all Parquet analytics files and initializes/rebuilds DuckDB replicas from scratch.
* **Manual Override**: `make run-stock-pull`

### 6. PostgreSQL Daily Backup (`daily_backup`)
* **Time**: Daily at 3:00 AM PT.
* **Goal**: Automatically invokes `pg_dump` to create compressed backups (`.sql.gz`) in the backups directory, enforcing a automatic 30-day retention pruning cycle.
* **Manual Override**: `make backup`
