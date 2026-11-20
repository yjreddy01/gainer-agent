"""
Daily pattern lists - run once a day after market close (about 4:05 PM IST). No trigger.

File (a)  signals/daily_2candle_<date>.csv  - 2-candle formation:
    yesterday GREEN daily candle -> TODAY's candle RED and closing below the green candle's low
File (b)  signals/daily_3candle_<date>.csv  - 3-candle formation:
    GREEN daily candle -> next candle RED, closing below its low -> TODAY closes above the green
    candle's high. The red candle can be any of the last LOOKBACK (default 5) sessions before today;
    today must be the first close above that green high.

Both lists go out in one GitHub issue (email / GitHub app), Telegram if configured, and the web page.
"""

import datetime as dt
import os
import sys

import page
from monitor import retry, github_issue, notify
from strategy import download, get_fo_symbols, daily_qualifiers_for, daily_reversal_for

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PAGE_URL = os.getenv("PAGE_URL", "")
LOOKBACK = int(os.getenv("LOOKBACK", "5"))
REPO = os.getenv("GITHUB_REPOSITORY", "")


def main():
    now = dt.datetime.now(IST)
    symbols = get_fo_symbols()
    daily = retry(download, symbols, "1d", "3mo")
    last = max(df.index[-1].date() for df in daily.values())
    if (last != now.date() or now.time() < dt.time(15, 30)) and "--force" not in sys.argv:
        print(f"[info] Today's daily candle isn't complete (latest {last}) - nothing to do.")
        return

    # (a) 2-candle formation
    two = daily_qualifiers_for(daily, last)
    for s in two["symbol"]:
        d = daily[s][daily[s].index.date <= last]
        two.loc[two["symbol"] == s, "today_close"] = round(float(d["Close"].iloc[-1]), 2)
        two.loc[two["symbol"] == s, "change_%"] = round(float(d["Close"].iloc[-1] / d["Close"].iloc[-2] - 1) * 100, 2)
    two = two.rename(columns={"qual_date": "date"})
    two = two.sort_values("change_%") if not two.empty else two

    # (b) 3-candle formation
    three = daily_reversal_for(daily, last, LOOKBACK)
    three = three.sort_values("change_%", ascending=False) if not three.empty else three

    os.makedirs("signals", exist_ok=True)
    f2, f3 = f"signals/daily_2candle_{last}.csv", f"signals/daily_3candle_{last}.csv"
    two.to_csv(f2, index=False)
    three.to_csv(f3, index=False)
    print(f"[info] {last}: 2-candle {len(two)} stocks, 3-candle {len(three)} stocks.")

    def md_table(df, cols, heads):
        if df.empty:
            return "_None today._"
        rows = "\n".join("| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in df.iterrows())
        return "| " + " | ".join(heads) + " |\n|" + "---|" * len(heads) + "\n" + rows

    link = lambda f: f"[download CSV](https://github.com/{REPO}/blob/main/{f})" if REPO else f
    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "")
    title = f"[Daily] {last:%d %b} · 2-candle: {len(two)} · 3-candle: {len(three)}"
    body = (f"{'@' + owner if owner else ''}\n\n"
            f"### (a) 2-candle formation — {len(two)} stocks\n"
            f"Yesterday green → **today red, closing below the green candle's low**. {link(f2)}\n\n"
            + md_table(two, ["symbol", "today_close", "change_%", "green_candle", "red_candle"],
                       ["Stock", "Today's close", "Today %", "Green candle", "Red candle (today)"]) +
            f"\n\n### (b) 3-candle formation — {len(three)} stocks\n"
            f"Green → next candle red, closing below its low (within last {LOOKBACK} sessions) → "
            f"**today closed above the green candle's high**. {link(f3)}\n\n"
            + md_table(three, ["symbol", "today_close", "change_%", "green_candle", "red_candle", "days_since_red"],
                       ["Stock", "Today's close", "Today %", "Green candle (H / L)", "Red candle", "Days since red"]) +
            f"\n\n{PAGE_URL}")
    github_issue(title, body, "daily-list")
    notify(f"[Daily] {last:%d %b}\n(a) 2-candle ({len(two)}): {', '.join(two['symbol']) or '-'}\n"
           f"(b) 3-candle ({len(three)}): {', '.join(three['symbol']) or '-'}" + (f"\n{PAGE_URL}" if PAGE_URL else ""), "daily")
    page.build()


if __name__ == "__main__":
    main()
