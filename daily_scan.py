"""
Daily pattern lists - run once a day after market close (about 4:05 PM IST). No trigger.

File (a)  signals/daily_2candle_<date>.csv  - 2-candle formation:
    yesterday GREEN daily candle -> TODAY's candle RED and closing below the green candle's low
File (b)  signals/daily_3candle_<date>.csv  - 3-candle formation:
    GREEN daily candle -> next candle RED, closing below its low -> TODAY closes above the green
    candle's high. The red candle can be any of the last LOOKBACK (default 5) sessions before today;
    today must be the first close above that green high.

Both lists (and the CSV files) go out in one GitHub issue (email / GitHub app), Telegram if configured, and the web page.
"""

import datetime as dt
import os
import sys

import page
from monitor import retry, github_issue, notify, telegram_file, telegram, telegram_photo
from strategy import download, get_fo_symbols, daily_qualifiers_for, daily_reversal_for

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PAGE_URL = os.getenv("PAGE_URL", "")
LOOKBACK = int(os.getenv("LOOKBACK", "5"))
REPO = os.getenv("GITHUB_REPOSITORY", "")


def main():
    now = dt.datetime.now(IST)
    symbols = get_fo_symbols()
    daily = retry(download, symbols, "1d", "6mo")
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
    # attach the files on Telegram: stock lists + today's index 15-min files
    telegram_file(f2, f"(a) Stocks 2-candle - {last:%d %b} - {len(two)} stocks")
    telegram_file(f3, f"(b) Stocks 3-candle - {last:%d %b} - {len(three)} stocks")
    for kind, label in (("2candle", "2-candle"), ("3candle", "3-candle"), ("short", "SHORT signals")):
        p = f"signals/index_{kind}_{last}.csv"
        if os.path.exists(p):
            telegram_file(p, f"Index 15-min {label} - {last:%d %b}")
    send_pattern_charts(daily, last, two, three)
    page.build()


def send_pattern_charts(daily, last, two, three, k=5):
    """1-day chart (swing highs/lows + volume) for every stock in the 2-candle and 3-candle lists -> Telegram."""
    import datetime as _dt
    import shutil
    from swing_charts import chart, swings
    out = "docs/charts/patterns"
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(out, exist_ok=True)

    def d_of(txt):            # "19 Nov low 123" -> date (year from `last`)
        dd = _dt.datetime.strptime(" ".join(txt.split()[:2]) + f" {last.year}", "%d %b %Y").date()
        return dd if dd <= last else dd.replace(year=last.year - 1)

    jobs = []
    for _, r in two.iterrows():
        jobs.append((r["symbol"], "2-candle", [(d_of(r["green_candle"]), "green", "#16a34a"),
                                                (last, "red", "#dc2626")],
                     f"(a) 2-candle: green {r['green_candle']} -> today red close {r['today_close']} ({r['change_%']:+}%)"))
    for _, r in three.iterrows():
        jobs.append((r["symbol"], "3-candle", [(d_of(r["green_candle"]), "green", "#16a34a"),
                                                (d_of(r["red_candle"]), "red", "#dc2626"),
                                                (last, "break", "#2563eb")],
                     f"(b) 3-candle: green {r['green_candle']} -> red {r['red_candle']} -> "
                     f"today close {r['today_close']} above green high ({r['change_%']:+}%)"))
    if not jobs:
        return
    from swing_charts import make_pdf
    pngs, lines = [], []
    for sym, kind, hl, cap in jobs:
        df = daily.get(sym)
        if df is None:
            continue
        df = df[df.index.date <= last].dropna().iloc[-65:]      # last ~3 months, so pattern candles are readable
        hi, lo = swings(df, k)
        path = f"{out}/{kind}_{sym}.png"
        try:
            chart(sym, 0, df, hi, lo, k, path, highlight=hl, title_extra=f" · {kind}")
            pngs.append(path)
            lines.append(f"{sym:<12} {cap}"[:150])
        except Exception as e:
            print(f"[warn] chart {sym}: {e}")
    pdf = f"{out}/daily_patterns_{last}.pdf"
    make_pdf(pngs, pdf, f"Daily pattern charts - {last:%d %b %Y}  ({len(two)} x 2-candle, {len(three)} x 3-candle)",
             ["Shaded candles = the pattern (green / red / blue = today's break). Swing highs v, lows ^, volume below.", ""]
             + lines)
    telegram_file(pdf, f"Daily pattern charts - {last:%d %b} - {len(pngs)} stocks (1-day, swing highs/lows, volume)")
