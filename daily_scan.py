"""
Daily pattern list - runs once a day after market close (about 4:05 PM IST).

Finds every NSE F&O stock with this 3-candle DAILY pattern (no trigger - it just sends the list):
  1. a GREEN daily candle
  2. the next candle is RED and closes below the green candle's low
  3. TODAY's candle closes above the green candle's high
     (the green/red pair can be up to LOOKBACK sessions back; today need not follow the red candle)
Output:
  - one GitHub issue (email / GitHub app) listing the stocks
  - Telegram message if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are set
  - saved to signals/daily_list_<date>.csv and shown on the web page
"""

import datetime as dt
import os
import sys

import pandas as pd

import page
from monitor import retry, github_issue, telegram
from strategy import download, get_fo_symbols, daily_reversal_for

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PAGE_URL = os.getenv("PAGE_URL", "")
LOOKBACK = int(os.getenv("LOOKBACK", "10"))


def main():
    now = dt.datetime.now(IST)
    symbols = get_fo_symbols()
    daily = retry(download, symbols, "1d", "3mo")
    last = max(df.index[-1].date() for df in daily.values())
    if last != now.date() or now.time() < dt.time(15, 30):
        if "--force" not in sys.argv:
            print(f"[info] Today's daily candle isn't complete (latest {last}) - nothing to do.")
            return
    lst = daily_reversal_for(daily, last, LOOKBACK)
    lst = lst.sort_values("change_%", ascending=False) if not lst.empty else lst

    os.makedirs("signals", exist_ok=True)
    lst.to_csv(f"signals/daily_list_{last}.csv", index=False)
    print(f"[info] {len(lst)} stocks on {last}.")

    if lst.empty:
        title = f"[Daily] No stock with the pattern · {last:%d %b}"
        body = "No F&O stock completed the 3-candle daily pattern today."
    else:
        title = f"[Daily] {len(lst)} stocks: today closed above the green candle's high · {last:%d %b}"
        rows = "\n".join(f"| {r['symbol']} | {r['today_close']} ({r['change_%']:+}%) | {r['green_candle']} | {r['red_candle']} |"
                         for _, r in lst.iterrows())
        owner = os.getenv("GITHUB_REPOSITORY_OWNER", "")
        body = (f"{'@' + owner if owner else ''}\n\n"
                f"3-candle daily pattern: **green** candle → next candle **red, closing below its low** → "
                f"**today closed above the green candle's high**:\n\n"
                f"| Stock | Today's close | Green candle (high / low) | Red candle |\n|---|---|---|---|\n{rows}\n\n{PAGE_URL}")
    github_issue(title, body, "daily-list")
    telegram(f"[Daily] {last:%d %b}: {len(lst)} stocks — red candle broke previous green low\n"
             + ", ".join(lst["symbol"]) + (f"\n{PAGE_URL}" if PAGE_URL else ""))
    page.build()


if __name__ == "__main__":
    main()
