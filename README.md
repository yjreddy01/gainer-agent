# Top-Gainer Hourly Break Agent: automatic daily results

Once it's set up, GitHub's free cloud runs the agent every weekday at about 9:32 AM IST. Your computer doesn't need to be on. Each run:
- scans today's top 10 F&O gainers for the previous-day 1-hour green-low-break pattern
- recalculates the win rate over the last 5 sessions, top 5 gainers per day
- **publishes** the results to a web page and sends a **Telegram message** to your phone

The setup below is one-time and takes about 10 minutes.

---

## 1. Create the repository
1. Sign up or log in at github.com.
2. Click **+ → New repository**.
3. Name it `gainer-agent` and tick **Add a README file**.
   - **Public**: you get a free results web page, but anyone with the link can see it.
   - **Private**: results come only by Telegram, because a web page needs a paid plan.
4. Click **Create repository**.

## 2. Upload the files
1. Click **Add file → Upload files**.
2. Drag in `gainer_agent.py`, `backtest.py`, `publish.py` and `requirements.txt`, then click **Commit changes**.
3. Click **Add file → Create new file**.
4. In the name box, type exactly `.github/workflows/daily.yml`. The slashes create the folders.
5. Paste in the contents of `daily.yml` from this package and click **Commit changes**.

## 3. Telegram alerts (recommended)
1. In Telegram, open **@BotFather** and send `/newbot`. Follow the prompts, then copy the **token** it gives you.
2. Open your new bot and send it any message, for example "hi".
3. In a browser, open `https://api.telegram.org/bot<TOKEN>/getUpdates`, putting your token in place of `<TOKEN>`. Find `"chat":{"id":123456789` and copy that number. This is your **chat ID**.
4. In your GitHub repository, go to **Settings → Secrets and variables → Actions → New repository secret**. Add two secrets:
   - `TELEGRAM_BOT_TOKEN`: your token
   - `TELEGRAM_CHAT_ID`: your chat ID

## 4. Web page (public repositories only)
Go to **Settings → Pages**. Under Source, choose **Deploy from a branch**, then branch **main**, folder **/docs**, and click **Save**.
Your page will be at https://yjreddy01.github.io/gainer-agent/.

## 5. Test it
1. Open the **Actions** tab and enable workflows if GitHub asks.
2. Click **Daily top-gainer scan → Run workflow**.
3. After about 2 minutes, you should see a green tick and get a Telegram message.

**Note:** a manual run only publishes on a trading day. On weekends and market holidays it does nothing.

---

## Good to know
- **Timing:** GitHub sometimes starts scheduled runs 5–20 minutes late at busy times. The scan still uses the 9:15–9:30 candle, so the signals stay the same, but the alert may arrive a bit late.
- **Settings:** to change any of these, add them as `env:` lines in `daily.yml`.
  - `TOP_SCAN`: how many gainers to scan (default 10)
  - `BT_DAYS`, `BT_TOP`: the backtest window, in days and gainers per day (defaults 5 and 5)
  - `BREAK_MODE`: `close` (default) or `low`
- **Saved results:** every day's results are stored in the `signals/` folder. `history.csv` keeps every signal the agent has given.
- **Data:** prices are Yahoo Finance cash-market prices, which the stock futures track.
- This is a scanner only. It places no orders.

**Running it on your PC instead:** `run_agent.bat` runs the scan, and `python backtest.py --days 5 --top 5` runs the backtest.
