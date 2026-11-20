"""
Backtest: Top-Gainer Hourly Break Agent
=======================================

For each of the last N trading sessions (default 5):
  1. Rank NSE F&O stocks by gain at the close of the first 15-min candle vs previous close.
  2. Take the top K gainers (default 5).
  3. Check the previous day's 1-hour candles: green candle low broken by a later red candle?
  4. If yes -> simulated BUY at the 9:30 price (close of first 15-min candle),
     exit at the day's closing price.

A trade is a WIN if the exit price is above the entry price.
The report also shows all top gainers *without* the filter, so you can see whether
the pattern actually improves the odds.

Usage:
    python backtest.py                      # last 5 days, top 5
    python backtest.py --days 5 --top 5
    python backtest.py --break-mode low     # count a wick below the low as a break
Needs: pip install yfinance pandas requests   (gainer_agent.py in the same folder)
"""

import argparse
import datetime as dt
import os
import sys

import pandas as pd
import yfinance as yf

from gainer_agent import get_fo_symbols, yf_ticker, find_green_low_break

IST = "Asia/Kolkata"


def to_ist(df):
    df.index = df.index.tz_convert(IST) if df.index.tz else df.index.tz_localize(IST)
    return df


def download(symbols, interval, days):
    tickers = [yf_ticker(s) for s in symbols]
    data = yf.download(tickers, period=f"{min(59, days * 2 + 6)}d", interval=interval, group_by="ticker",
                       auto_adjust=False, progress=False, threads=True)
    out = {}
    for s, t in zip(symbols, tickers):
        try:
            df = data[t].dropna(subset=["Close"])
        except (KeyError, TypeError):
            continue
        if not df.empty:
            out[s] = to_ist(df[["Open", "High", "Low", "Close"]].copy())
    return out


def run_backtest(days=5, top=5, break_mode="close", adjacent=False):
    """Returns (trades DataFrame, list of test dates)."""
    a = argparse.Namespace(days=days, top=top, break_mode=break_mode, adjacent=adjacent)

    symbols = get_fo_symbols()
    print(f"[info] Downloading 15-min and 1-hour data for {len(symbols)} F&O stocks...")
    m15 = download(symbols, "15m", a.days)
    h1 = download(symbols, "60m", a.days)
    if not m15:
        raise RuntimeError("No data downloaded - check internet connection.")

    # Common session calendar
    all_dates = sorted({d for df in m15.values() for d in df.index.date})
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).date()
    now_t = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30))).time()
    if all_dates and all_dates[-1] == today and now_t < dt.time(15, 30):
        all_dates = all_dates[:-1]  # skip today's unfinished session
    test_days = all_dates[-a.days:]

    trades = []
    for D in test_days:
        P = all_dates[all_dates.index(D) - 1]
        ranks = []
        for s, df in m15.items():
            prev = df[df.index.date == P]
            day = df[df.index.date == D]
            first = day[day.index.time == dt.time(9, 15)]
            if prev.empty or first.empty or len(day) < 2:
                continue
            entry = first["Close"].iloc[0]
            pc = prev["Close"].iloc[-1]
            after = day[day.index.time > dt.time(9, 15)]
            ranks.append({"symbol": s, "gain15_%": (entry / pc - 1) * 100, "entry": entry,
                          "exit": day["Close"].iloc[-1],
                          "high_after": after["High"].max(), "low_after": after["Low"].min()})
        top = sorted(ranks, key=lambda r: r["gain15_%"], reverse=True)[:a.top]

        for r in top:
            hd = h1.get(r["symbol"])
            hourly = hd[hd.index.date == P] if hd is not None else pd.DataFrame()
            hits = find_green_low_break(hourly, a.break_mode, a.adjacent) if not hourly.empty else []
            ret = (r["exit"] / r["entry"] - 1) * 100
            trades.append({
                "date": D, "symbol": r["symbol"], "gain15_%": round(r["gain15_%"], 2),
                "setup": "YES" if hits else "no",
                "entry_9:30": round(r["entry"], 2), "exit_close": round(r["exit"], 2),
                "return_%": round(ret, 2), "result": "WIN" if ret > 0 else "LOSS",
                "best_move_%": round((r["high_after"] / r["entry"] - 1) * 100, 2),
                "worst_move_%": round((r["low_after"] / r["entry"] - 1) * 100, 2),
                "pattern": f"green {hits[-1]['green_time']} broken by red {hits[-1]['red_time']}" if hits else "",
            })

    return pd.DataFrame(trades), test_days


def summarize(df):
    if df.empty:
        return {"trades": 0, "wins": 0, "win_rate": None, "avg_return": None, "total_return": None}
    wins = int((df["result"] == "WIN").sum())
    return {"trades": len(df), "wins": wins, "win_rate": round(wins / len(df) * 100, 1),
            "avg_return": round(df["return_%"].mean(), 2), "total_return": round(df["return_%"].sum(), 2)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--break-mode", choices=["close", "low"], default="close")
    ap.add_argument("--adjacent", action="store_true")
    a = ap.parse_args()
    res, test_days = run_backtest(a.days, a.top, a.break_mode, a.adjacent)
    pd.set_option("display.width", 200)
    print(f"\nBacktest: {test_days[0]} to {test_days[-1]} | top {a.top} gainers/day | "
          f"break mode: {a.break_mode}\nEntry = 9:30 price, Exit = day close\n")
    print(res.to_string(index=False))

    def summary(df, label):
        if df.empty:
            print(f"{label:<34} no trades")
            return
        wins = (df["result"] == "WIN").sum()
        print(f"{label:<34} trades {len(df):>3} | wins {wins:>3} | WIN RATE {wins/len(df)*100:5.1f}% | "
              f"avg return {df['return_%'].mean():+.2f}% | total {df['return_%'].sum():+.2f}%")

    print("\n" + "=" * 100)
    summary(res[res["setup"] == "YES"], "WITH pattern (agent's BUY signals)")
    summary(res[res["setup"] == "no"], "WITHOUT pattern (skipped)")
    summary(res, "ALL top gainers (no filter)")
    print("=" * 100)
    n = (res["setup"] == "YES").sum()
    if n < 20:
        print(f"Note: only {n} signal trades - too few to trust the win rate. Run with more days "
              f"(e.g. --days 40; Yahoo keeps ~60 days of 15-min data).")

    os.makedirs("signals", exist_ok=True)
    path = os.path.join("signals", f"backtest_{test_days[0]}_to_{test_days[-1]}.csv")
    res.to_csv(path, index=False)
    print(f"Saved: {path}")


if __name__ == "__main__":
    main()
