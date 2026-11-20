"""
Strategy core
=============

QUALIFIER (previous day, 1-hour chart):
    A GREEN 1h candle whose low was later broken by a RED 1h candle
    (red candle CLOSES below the green candle's low).

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
            out[s] = to_ist(df[["Open", "High", "Low", "Close"]].copy())
    return out


def qualifiers_for(hourly_by_sym, prev_date, break_mode="close"):
    """Stocks whose prev-day 1h chart shows a green-candle low broken by a later red candle."""
    rows = []
    for s, df in hourly_by_sym.items():
        day = df[df.index.date == prev_date]
        if day.empty:
            continue
        hits = find_green_low_break(day, break_mode)
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
