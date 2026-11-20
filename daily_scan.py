"""
Daily pattern list - runs once a day after market close (about 4:05 PM IST).

Finds every NSE F&O stock whose DAILY candle today is RED and closes below the low of the
GREEN daily candle right before it. No trigger - it just sends the list:
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
from strategy import download, get_fo_symbols, daily_qualifiers_for

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PAGE_URL = os.getenv("PAGE_URL", "")


def main():
    now = dt.datetime.now(IST)
    symbols = get_fo_symbols()
    daily = retry(download, symbols, "1d", "1mo")
    last = max(df.index[-1].date() for df in daily.values())
    if last != now.date() or now.time() < dt.time(15, 30):
        if "--force" not in sys.argv:
            print(f"[info] Today's daily candle isn't complete (latest {last}) - nothing to do.")
            return
    lst = daily_qualifiers_for(daily, last)
    for s in lst["symbol"]:                       # add the day's % change for context
        d = daily[s]
        lst.loc[lst["symbol"] == s, "change_%"] = round(float(d["Close"].iloc[-1] / d["Close"].iloc[-2] - 1) * 100, 2)
    lst = lst.sort_values("change_%") if not lst.empty else lst

    os.makedirs("signals", exist_ok=True)
    lst.to_csv(f"signals/daily_list_{last}.csv", index=False)
    print(f"[info] {len(lst)} stocks on {last}.")

    if lst.empty:
        title = f"[Daily] No stock with the pattern · {last:%d %b}"
        body = "No F&O stock had a red daily candle closing below the previous green candle's low today."
    else:
        title = f"[Daily] {len(lst)} stocks: red candle broke previous green low · {last:%d %b}"
        rows = "\n".join(f"| {r['symbol']} | {r['change_%']:+}% | {r['green_candle']} | {r['red_candle']} |"
                         for _, r in lst.iterrows())
        owner = os.getenv("GITHUB_REPOSITORY_OWNER", "")
        body = (f"{'@' + owner if owner else ''}\n\n"
                f"Daily candle today was **red** and closed **below the low of the previous green** daily candle:\n\n"
                f"| Stock | Today | Previous green candle | Today's red candle |\n|---|---|---|---|\n{rows}\n\n{PAGE_URL}")
    github_issue(title, body, "daily-list")
    telegram(f"[Daily] {last:%d %b}: {len(lst)} stocks — red candle broke previous green low\n"
             + ", ".join(lst["symbol"]) + (f"\n{PAGE_URL}" if PAGE_URL else ""))
    page.build()


if __name__ == "__main__":
    main()
