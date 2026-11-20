# Top-Gainer Break Agent

**Results page:** https://yjreddy01.github.io/gainer-agent/

## Rule
1. **Qualifier (previous day, 1-hour chart):** a red candle broke the low of the green candle right before it, meaning the red candle closed below that green candle's low.
2. **Trigger (today, 5-minute chart):** a stock gets a BUY alert for its future when all three of these are true:
   - it qualified yesterday,
   - it is in the **top 10 F&O gainers**,
   - a 5-minute candle **closes above the high of today's first 5-minute candle** (9:15–9:20).

   The agent watches until 2:00 PM, and each stock is alerted at most once a day.

## What runs automatically
| Job | When | What it does |
|---|---|---|
| Live monitor | Every 5 minutes, 9:20 AM–2:00 PM IST, Mon–Fri | Checks for triggers and sends alerts. It updates the page. |
| Backtest | 3:47 PM IST daily, and whenever the strategy code changes | Simulates the last 20 days and updates the win rates on the page. |

## How alerts reach you
- **GitHub (works now):** each BUY alert opens an issue in this repository, and GitHub emails it to you.
  - For phone notifications, install the **GitHub mobile app**.
  - Make sure email notifications for your own repositories are on: GitHub → Settings → Notifications, under **Watching**.
- **Telegram (optional):** add the `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets in Settings → Secrets and variables → Actions.

## Manual runs
To run a job yourself, go to **Actions**, pick the job, and click **Run workflow**. The backtest asks how many days to test; Yahoo keeps about 50 days of 5-minute data.

## Notes
- **Data:** prices are Yahoo Finance cash-market prices, which the stock futures track.
- **Simulated trades:** the backtest buys at the close of the trigger candle and sells at the day's close.
- **Missed runs:** GitHub can delay a scheduled run by a few minutes. Each run re-checks the whole day so far, so a late run still catches any trigger it missed.
- This is a scanner only. It places no orders.
