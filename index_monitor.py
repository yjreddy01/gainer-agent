"""
Index 15-minute pattern monitor - NIFTY 50, SENSEX, BANKNIFTY and CRUDE.
Runs every 15 minutes from 9:15 AM to 11:45 PM IST (just after each 15-min candle closes).
Indices: 9:15 AM - 3:30 PM. CRUDE: WTI crude futures (Yahoo CL=F, in USD) as a proxy for MCX crude,
restricted to MCX hours 9:00 AM - 11:30 PM IST; formations reported only from 5:00 PM.

Same logic as the daily lists, on 15-minute candles:
  (a) 2-candle: GREEN candle -> next candle RED and closes below the green candle's low
  (b) 3-candle: GREEN candle -> next candle RED, closing below its low -> a later candle (within the
      next LOOKBACK candles, default 5) closes above the green candle's HIGH (first such close only)

Each run replays all completed 15-min candles, so a late run never misses a formation.
During market hours every new formation is a GitHub issue (+ Telegram if configured).
A run after market close sends one summary instead.
Files: signals/index_2candle_<date>.csv and signals/index_3candle_<date>.csv
"""

import datetime as dt
import os

import pandas as pd
import yfinance as yf

import page
from monitor import retry, github_issue, notify, telegram_file

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
INDICES = {"NIFTY": "^NSEI", "SENSEX": "^BSESN", "BANKNIFTY": "^NSEBANK", "CRUDE": "CL=F"}
# trading hours (IST) used for each instrument: candles outside are ignored; alerts sent live until session end
SESSION = {"CRUDE": (dt.time(9, 0), dt.time(23, 30))}
DEFAULT_SESSION = (dt.time(9, 15), dt.time(15, 30))
# only report formations completing at/after this time (earlier candles still count as pattern context)
REPORT_FROM = {"CRUDE": dt.time(17, 0)}
LOOKBACK = int(os.getenv("INDEX_LOOKBACK", "5"))
PAGE_URL = os.getenv("PAGE_URL", "")
COLS2 = ["date", "index", "time", "green_candle", "red_candle", "red_close"]
COLS3 = ["date", "index", "time", "green_candle", "red_candle", "close", "candles_since_red"]


def download_indices(now):
    out = {}
    for name, tk in INDICES.items():
        df = yf.download(tk, period="5d", interval="15m", auto_adjust=False, progress=False)
        if df.empty:
            continue
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.index = df.index.tz_convert("Asia/Kolkata") if df.index.tz else df.index.tz_localize("Asia/Kolkata")
        df = df[["Open", "High", "Low", "Close"]].dropna()
        start, end = SESSION.get(name, DEFAULT_SESSION)
        t = df.index.time
        df = df[(t >= start) & (t < end) & (df.index.weekday < 5)]
        out[name] = df[df.index + pd.Timedelta(minutes=15) <= pd.Timestamp(now)]   # completed candles only
    return out


def fmt_t(ts):
    return ts.strftime("%d %b %H:%M")


def two_candle(df, name):
    ev = []
    for i in range(1, len(df)):
        g, r = df.iloc[i - 1], df.iloc[i]
        if g["Close"] > g["Open"] and r["Close"] < r["Open"] and r["Close"] < g["Low"]:
            ev.append({"date": df.index[i].date(), "index": name, "time": df.index[i].strftime("%H:%M"),
                       "green_candle": f"{fmt_t(df.index[i - 1])} L {g['Low']:.2f}",
                       "red_candle": f"{fmt_t(df.index[i])}", "red_close": round(float(r["Close"]), 2)})
    return ev


def three_candle(df, name, lookback=LOOKBACK):
    ev = []
    for i in range(1, len(df)):
        g, r = df.iloc[i - 1], df.iloc[i]
        if not (g["Close"] > g["Open"] and r["Close"] < r["Open"] and r["Close"] < g["Low"]):
            continue
        for j in range(i + 1, min(i + lookback + 1, len(df))):
            if df.iloc[j]["Close"] > g["High"]:
                ev.append({"date": df.index[j].date(), "index": name, "time": df.index[j].strftime("%H:%M"),
                           "green_candle": f"{fmt_t(df.index[i - 1])} H {g['High']:.2f} / L {g['Low']:.2f}",
                           "red_candle": f"{fmt_t(df.index[i])} close {r['Close']:.2f}",
                           "close": round(float(df.iloc[j]["Close"]), 2), "candles_since_red": j - i})
                break                                   # first close above the green high only
    return ev


def main():
    now = dt.datetime.now(IST)
    if now.weekday() >= 5:
        print("[info] Weekend - nothing to do.")
        return
    data = retry(download_indices, now)
    today = max(df.index[-1].date() for df in data.values() if not df.empty) if data else None
    if today != now.date():
        print(f"[info] No session today ({now.date()}) - market holiday.")
        return

    ev2, ev3 = [], []
    for name, df in data.items():
        frm = REPORT_FROM.get(name, dt.time(0, 0)).strftime("%H:%M")
        ev2 += [e for e in two_candle(df, name) if e["date"] == today and e["time"] >= frm]
        ev3 += [e for e in three_candle(df, name) if e["date"] == today and e["time"] >= frm]
    t2 = pd.DataFrame(ev2, columns=COLS2).sort_values(["time", "index"])
    t3 = pd.DataFrame(ev3, columns=COLS3).sort_values(["time", "index"])

    os.makedirs("signals", exist_ok=True)
    f2, f3 = f"signals/index_2candle_{today}.csv", f"signals/index_3candle_{today}.csv"
    key = lambda df: set(zip(df["index"], df["time"]))
    old2 = key(pd.read_csv(f2)) if os.path.exists(f2) else set()
    old3 = key(pd.read_csv(f3)) if os.path.exists(f3) else set()
    new2 = t2[[k not in old2 for k in zip(t2["index"], t2["time"])]]
    new3 = t3[[k not in old3 for k in zip(t3["index"], t3["time"])]]
    t2.to_csv(f2, index=False)
    t3.to_csv(f3, index=False)
    print(f"[info] {today}: 2-candle {len(t2)} ({len(new2)} new), 3-candle {len(t3)} ({len(new3)} new).")

    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "")
    mention = f"@{owner}\n\n" if owner else ""
    backfill = os.getenv("GITHUB_EVENT_NAME") == "push"     # code update run: summarise, don't spam

    def live(name):           # still within (or just after) this instrument's session -> per-event alerts
        end = SESSION.get(name, DEFAULT_SESSION)[1]
        return not backfill and now.time() <= (dt.datetime.combine(today, end) + dt.timedelta(minutes=20)).time()

    late2 = new2[[not live(n) for n in new2["index"]]]
    late3 = new3[[not live(n) for n in new3["index"]]]
    new2 = new2[[live(n) for n in new2["index"]]]
    new3 = new3[[live(n) for n in new3["index"]]]

    if True:  # live alerts, one per formation
        for _, e in new2.iterrows():
            github_issue(f"[{e['index']} 15m] 2-candle: red closed below green low · {e['time']} · {today:%d %b}",
                         f"{mention}**{e['index']}** 15-min: green candle {e['green_candle']} → next candle "
                         f"**red, closed {e['red_close']}**, below the green candle's low.\n\n{PAGE_URL}", "index-15m")
            notify(f"[{e['index']} 15m] 2-candle at {e['time']}: red closed {e['red_close']} below green low "
                   f"({e['green_candle']})", "index")
        for _, e in new3.iterrows():
            github_issue(f"[{e['index']} 15m] 3-candle: closed above green high · {e['time']} · {today:%d %b}",
                         f"{mention}**{e['index']}** 15-min: green candle {e['green_candle']} → red candle "
                         f"{e['red_candle']} broke its low → **{e['time']} candle closed {e['close']}, above the "
                         f"green candle's high** ({e['candles_since_red']} candles after the red).\n\n{PAGE_URL}",
                         "index-15m")
            notify(f"[{e['index']} 15m] 3-candle at {e['time']}: closed {e['close']} above green high "
                   f"({e['green_candle']})", "index")
    if len(late2) or len(late3):
        def lines(df, cols):
            return "\n".join("| " + " | ".join(str(r[c]) for c in cols) + " |" for _, r in df.iterrows())
        body = (f"{mention}Formations on 15-min candles today (summary sent after market close).\n\n"
                f"### (a) 2-candle — {len(t2)}\n| Index | Time | Green candle | Red close |\n|---|---|---|---|\n"
                f"{lines(t2, ['index', 'time', 'green_candle', 'red_close'])}\n\n"
                f"### (b) 3-candle — {len(t3)}\n| Index | Time | Green candle | Red candle | Close | Candles since red |\n"
                f"|---|---|---|---|---|---|\n{lines(t3, ['index', 'time', 'green_candle', 'red_candle', 'close', 'candles_since_red'])}"
                f"\n\n{PAGE_URL}")
        github_issue(f"[Index 15m] {today:%d %b} summary · 2-candle: {len(t2)} · 3-candle: {len(t3)}", body, "index-15m")
    # after crude's session ends, send the day's full files to Telegram once
    flag = f"signals/.index_files_sent_{today}"
    if now.time() >= dt.time(23, 30) and not os.path.exists(flag):
        telegram_file(f2, f"Index + Crude 15-min 2-candle - {today:%d %b} - {len(t2)} formations")
        telegram_file(f3, f"Index + Crude 15-min 3-candle - {today:%d %b} - {len(t3)} formations")
        open(flag, "w").write("sent")
    page.build()


if __name__ == "__main__":
    main()
