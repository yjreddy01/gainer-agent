"""
Strategy core
=============

QUALIFIER (previous day, 1-hour chart):
    A RED 1h candle that breaks the low of the GREEN 1h candle right before it
    (the red candle CLOSES below the previous green candle's low).

TRIGGER (current day, 5-minute chart), checked on every completed 5-min candle up to the cutoff:
    1. The stock qualified yesterday, AND
    2. It is in the TOP 10 F&O gainers at that candle (close vs previous day's close), AND
    3. That 5-min candle CLOSES ABOVE the HIGH of today's FIRST 5-min candle (9:15-9:20).
    -> BUY alert (stock future). Each stock alerts at most once per day.
"""

import datetime as dt

import pandas as pd
import yfinance as yf

from gainer_agent import get_fo_symbols, yf_ticker, find_green_low_break

IST = "Asia/Kolkata"
FIRST_CANDLE = dt.time(9, 15)


def to_ist(df):
    df.index = df.index.tz_convert(IST) if df.index.tz else df.index.tz_localize(IST)
    return df


def download(symbols, interval, period):
    """Batch download -> {symbol: OHLC DataFrame in IST}."""
    tickers = [yf_ticker(s) for s in symbols]
    data = yf.download(tickers, period=period, interval=interval, group_by="ticker",
                       auto_adjust=False, progress=False, threads=True)
    out = {}
    for s, t in zip(symbols, tickers):
        try:
            df = data[t].dropna(subset=["Close"])
        except (KeyError, TypeError):
            continue
        if not df.empty:
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]
            out[s] = to_ist(df[cols].copy())
    return out


def qualifiers_for(hourly_by_sym, prev_date, break_mode="close", adjacent=True):
    """Stocks whose prev-day 1h chart has a red candle breaking the low of the previous green candle."""
    rows = []
    for s, df in hourly_by_sym.items():
        day = df[df.index.date == prev_date]
        if day.empty:
            continue
        hits = find_green_low_break(day, break_mode, adjacent)
        if hits:
            h = hits[-1]
            rows.append({"symbol": s, "qual_date": prev_date,
                         "green_candle": f"{h['green_time']} low {h['green_low']}",
                         "red_candle": f"{h['red_time']} close {h['red_close']}"})
    return pd.DataFrame(rows, columns=["symbol", "qual_date", "green_candle", "red_candle"])


def day_triggers(m5_by_sym, day, prev_day, qual_set, top_n=10, cutoff=dt.time(14, 0),
                 now=None, qualified_only=True):
    """
    Replay the 5-min candles of `day` and return the first trigger per stock.
    now: only use candles completed by this IST datetime (live mode). None = full day.
    qualified_only=False -> same trigger for ALL stocks (used as a baseline in the backtest).
    """
    closes, highs, prev_close = {}, {}, {}
    for s, df in m5_by_sym.items():
        p = df[df.index.date == prev_day]
        d = df[df.index.date == day]
        if p.empty or d.empty:
            continue
        if now is not None:
            d = d[d.index + pd.Timedelta(minutes=5) <= now]
        if d.empty or d.index[0].time() != FIRST_CANDLE:
            continue
        prev_close[s] = p["Close"].iloc[-1]
        closes[s] = d["Close"]
        highs[s] = d["High"]
    if not closes:
        return pd.DataFrame(), {}

    C = pd.DataFrame(closes).sort_index().ffill()
    gain = (C / pd.Series(prev_close) - 1) * 100
    first_high = pd.DataFrame(highs).sort_index().iloc[0]   # high of 9:15-9:20 candle

    triggers, done = [], set()
    for ts in C.index[1:]:                                    # from the 9:20 candle onward
        if ts.time() >= cutoff:
            break
        row = gain.loc[ts].dropna()
        top = row.sort_values(ascending=False).head(top_n)
        for rank, (s, g) in enumerate(top.items(), start=1):
            if s in done:
                continue
            if qualified_only and s not in qual_set:
                continue
            c = C.at[ts, s]
            if pd.notna(c) and pd.notna(first_high.get(s)) and c > first_high[s]:
                done.add(s)
                triggers.append({"date": day, "time": ts.strftime("%H:%M"), "symbol": s,
                                 "rank": rank, "gain_%": round(float(g), 2),
                                 "entry": round(float(c), 2),
                                 "first5_high": round(float(first_high[s]), 2),
                                 "qualified": s in qual_set})
    # snapshot of the latest top-N (for the page)
    last = gain.iloc[-1].dropna().sort_values(ascending=False).head(top_n)
    snapshot = {"time": C.index[-1].strftime("%H:%M"),
                "top": [(s, round(float(g), 2), s in qual_set) for s, g in last.items()]}
    return pd.DataFrame(triggers), snapshot


def daily_qualifiers_for(daily_by_sym, prev_date, break_mode="close"):
    """Stocks whose DAILY candle on prev_date is RED and breaks the low of the GREEN daily candle before it."""
    rows = []
    for s, df in daily_by_sym.items():
        d = df[df.index.date <= prev_date]
        if len(d) < 2 or d.index[-1].date() != prev_date:
            continue
        g, r = d.iloc[-2], d.iloc[-1]
        if not (g["Close"] > g["Open"] and r["Close"] < r["Open"]):
            continue
        level = r["Close"] if break_mode == "close" else r["Low"]
        if level < g["Low"]:
            rows.append({"symbol": s, "qual_date": prev_date,
                         "green_candle": f"{d.index[-2].date():%d %b} low {round(float(g['Low']), 2)}",
                         "red_candle": f"{d.index[-1].date():%d %b} close {round(float(r['Close']), 2)}"})
    return pd.DataFrame(rows, columns=["symbol", "qual_date", "green_candle", "red_candle"])



def sr_levels(df, break_mode="close", n=3, merge_pct=0.5):
    """
    Support / resistance from consecutive daily candles:
      SUPPORT    = low of a GREEN candle when the very next candle is RED and breaks that low
      RESISTANCE = high of a RED candle when the very next candle is GREEN and breaks that high
    break_mode "close" = the next candle must CLOSE beyond the level (same as the 2/3-candle alerts),
               "wick"  = its low / high only has to pierce it.
    Returns (supports, resistances): the n nearest below / above the last close, as (date, price) lists.
    Levels within merge_pct % of each other are one zone (the most recent one is kept).
    """
    d = df.dropna()
    sup, res = [], []
    for i in range(1, len(d)):
        p, c = d.iloc[i - 1], d.iloc[i]
        if p["Close"] > p["Open"] and c["Close"] < c["Open"]:
            if (c["Close"] if break_mode == "close" else c["Low"]) < p["Low"]:
                sup.append((d.index[i - 1].date(), round(float(p["Low"]), 2)))
        if p["Close"] < p["Open"] and c["Close"] > c["Open"]:
            if (c["Close"] if break_mode == "close" else c["High"]) > p["High"]:
                res.append((d.index[i - 1].date(), round(float(p["High"]), 2)))
    last = float(d["Close"].iloc[-1])

    def nearest(levels, below):
        lv = sorted([x for x in levels if (x[1] <= last if below else x[1] >= last)],
                    key=lambda x: -x[1] if below else x[1])
        out = []
        for x in lv:
            j = next((k for k, o in enumerate(out) if abs(o[1] - x[1]) / x[1] * 100 < merge_pct), None)
            if j is None:
                out.append(x)
            elif x[0] > out[j][0]:
                out[j] = x
        return out[:n]

    return nearest(sup, True), nearest(res, False)


def daily_reversal_for(daily_by_sym, today, lookback=5, break_mode="close"):
    """
    3-candle daily pattern:
      1. GREEN daily candle
      2. the very next candle is RED and closes below the green candle's low
      3. TODAY's candle closes above the green candle's HIGH
    The red candle can be any of the last `lookback` sessions before today (today need not follow the
    red candle directly), but today must be the FIRST close above that green high since the red candle.
    """
    rows = []
    for s, df in daily_by_sym.items():
        d = df[df.index.date <= today]
        if len(d) < 3 or d.index[-1].date() != today:
            continue
        last = len(d) - 1
        t = d.iloc[last]
        for i in range(last - 1, max(0, last - lookback - 1), -1):    # i = red candle index (most recent first)
            g, r = d.iloc[i - 1], d.iloc[i]
            if not (g["Close"] > g["Open"] and r["Close"] < r["Open"]):
                continue
            level = r["Close"] if break_mode == "close" else r["Low"]
            if not level < g["Low"]:
                continue
            between = d.iloc[i + 1:last]
            if (between["Close"] > g["High"]).any():
                continue                                  # green high already broken earlier
            if t["Close"] > g["High"]:
                rows.append({"symbol": s, "date": today,
                             "green_candle": f"{d.index[i - 1].date():%d %b} H {round(float(g['High']), 2)} / L {round(float(g['Low']), 2)}",
                             "red_candle": f"{d.index[i].date():%d %b} close {round(float(r['Close']), 2)}",
                             "today_close": round(float(t["Close"]), 2),
                             "change_%": round(float(t["Close"] / d.iloc[last - 1]["Close"] - 1) * 100, 2),
                             "days_since_red": last - i})
            break                                         # only the most recent green/red pair
    return pd.DataFrame(rows, columns=["symbol", "date", "green_candle", "red_candle",
                                       "today_close", "change_%", "days_since_red"])


def daily_short_for(daily_by_sym, today):
    """
    4-candle daily SHORT pattern (four consecutive daily candles, D = today):
      A. GREEN candle
      B. RED candle whose HIGH goes above A's high
      C. GREEN candle
      D. RED candle (today) whose HIGH goes above C's high
    Stop-loss reference = the higher of B's and D's highs.
    """
    rows = []
    for s, df in daily_by_sym.items():
        d = df[df.index.date <= today]
        if len(d) < 5 or d.index[-1].date() != today:
            continue
        a, b, c, t = d.iloc[-4], d.iloc[-3], d.iloc[-2], d.iloc[-1]
        green = lambda k: k["Close"] > k["Open"]
        red = lambda k: k["Close"] < k["Open"]
        if not (green(a) and red(b) and b["High"] > a["High"]
                and green(c) and red(t) and t["High"] > c["High"]):
            continue
        dt_ = lambda n: f"{d.index[n].date():%d %b}"
        r2 = lambda v: round(float(v), 2)
        rows.append({"symbol": s, "date": today,
                     "A_green": f"{dt_(-4)} H {r2(a['High'])}",
                     "B_red": f"{dt_(-3)} H {r2(b['High'])}",
                     "C_green": f"{dt_(-2)} H {r2(c['High'])}",
                     "D_red_today": f"{dt_(-1)} H {r2(t['High'])}",
                     "today_close": r2(t["Close"]),
                     "change_%": round(float(t["Close"] / c["Close"] - 1) * 100, 2),
                     "sl_ref": r2(max(b["High"], t["High"]))})
    return pd.DataFrame(rows, columns=["symbol", "date", "A_green", "B_red", "C_green", "D_red_today",
                                       "today_close", "change_%", "sl_ref"])
