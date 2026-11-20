"""
Backtest of the current rule (see strategy.py):
  qualified on previous-day 1h pattern  +  top-10 gainer  +  5-min close above today's first 5-min high
Entry = close of the trigger candle, Exit = day's close. WIN = exit above entry.

Baseline: the same top-10 + first-5-min-high trigger on stocks that did NOT qualify,
so you can see whether the 1h pattern actually improves the odds.

Usage:  python backtest.py --days 20
(Yahoo keeps about 60 days of 5-min data, so --days can go up to ~50.)
"""

import argparse
import datetime as dt
import json
import os

import pandas as pd

from strategy import download, get_fo_symbols, qualifiers_for, day_triggers

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def summarize(df):
    if df is None or df.empty:
        return {"trades": 0}
    wins = int((df["result"] == "WIN").sum())
    return {"trades": int(len(df)), "wins": wins, "win_rate": round(wins / len(df) * 100, 1),
            "avg_return": round(float(df["return_%"].mean()), 2),
            "total_return": round(float(df["return_%"].sum()), 2)}


def run_backtest(days=20, top_n=10, cutoff=dt.time(14, 0)):
    symbols = get_fo_symbols()
    period = f"{min(59, days * 2 + 6)}d"
    print(f"[info] Downloading 5-min and 1-hour data ({period}) for {len(symbols)} stocks...")
    m5 = download(symbols, "5m", period)
    h1 = download(symbols, "60m", period)
    if not m5:
        raise RuntimeError("No data downloaded.")

    dates = sorted({d for df in m5.values() for d in df.index.date})
    now = dt.datetime.now(IST)
    if dates[-1] == now.date() and now.time() < dt.time(15, 30):
        dates = dates[:-1]                      # today's session not finished
    test_days = dates[-days:]
    if dates.index(test_days[0]) == 0:
        test_days = test_days[1:]               # need a previous day for the first one

    rows = []
    for D in test_days:
        P = dates[dates.index(D) - 1]
        quals = qualifiers_for(h1, P)
        qset = set(quals["symbol"]) if not quals.empty else set()
        trig, _ = day_triggers(m5, D, P, qset, top_n, cutoff, qualified_only=False)
        for _, t in trig.iterrows():
            d = m5[t["symbol"]]
            day = d[d.index.date == D]
            after = day[day.index.strftime("%H:%M") > t["time"]]
            exit_ = float(day["Close"].iloc[-1])
            ret = (exit_ / t["entry"] - 1) * 100
            rows.append({**t.to_dict(), "exit_close": round(exit_, 2), "return_%": round(ret, 2),
                         "result": "WIN" if ret > 0 else "LOSS",
                         "best_move_%": round((after["High"].max() / t["entry"] - 1) * 100, 2) if not after.empty else 0,
                         "worst_move_%": round((after["Low"].min() / t["entry"] - 1) * 100, 2) if not after.empty else 0})
        print(f"  {D}: {len(qset)} qualified, {len(trig)} triggers "
              f"({int(trig['qualified'].sum()) if not trig.empty else 0} qualified)")

    res = pd.DataFrame(rows)
    summary = {"days": len(test_days), "from": str(test_days[0]), "to": str(test_days[-1]),
               "qualified": summarize(res[res["qualified"] == True]) if not res.empty else {"trades": 0},
               "not_qualified": summarize(res[res["qualified"] == False]) if not res.empty else {"trades": 0},
               "all": summarize(res)}
    return res, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=int(os.getenv("BT_DAYS", "20")))
    ap.add_argument("--top", type=int, default=10)
    a = ap.parse_args()

    res, s = run_backtest(a.days, a.top)
    os.makedirs("signals", exist_ok=True)
    res.to_csv("signals/backtest_latest.csv", index=False)
    json.dump(s, open("signals/backtest_summary.json", "w"), indent=1)

    pd.set_option("display.width", 220)
    if not res.empty:
        print(res[res["qualified"] == True].to_string(index=False))
    print("\n" + "=" * 90)
    for k, label in [("qualified", "Agent's alerts (qualified)"),
                     ("not_qualified", "Same trigger, NOT qualified"), ("all", "All triggers")]:
        x = s[k]
        if x.get("trades"):
            print(f"{label:<30} trades {x['trades']:>4} | wins {x['wins']:>4} | WIN RATE {x['win_rate']:5.1f}% "
                  f"| avg {x['avg_return']:+.2f}% | total {x['total_return']:+.2f}%")
        else:
            print(f"{label:<30} no trades")
    print("=" * 90)

    try:
        import page
        page.build()
    except Exception as e:
        print(f"[warn] page not rebuilt: {e}")


if __name__ == "__main__":
    main()
