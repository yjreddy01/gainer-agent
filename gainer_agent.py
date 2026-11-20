"""
Top-Gainer Hourly Break Agent (NSE F&O stocks)
==============================================

What it does, every trading day after the first 15 minutes (run at ~9:32 IST):

  1. Gets the NSE F&O stock list (live from NSE, falls back to a built-in list).
  2. Ranks them by % gain at the close of the first 15-min candle (9:15-9:30)
     versus yesterday's close, and takes the TOP N gainers (default 10).
  3. For each gainer, looks at YESTERDAY's 1-hour candles and checks:
        Was a GREEN candle's low broken by a LATER RED candle?
  4. If yes -> flags it as a BUY candidate for the stock future.

Prices come from Yahoo Finance (cash/spot prices, which the stock futures track).
This is a scanner that flags setups; it does not place orders.

Usage:
    python gainer_agent.py                 # normal daily run
    python gainer_agent.py --top 10        # number of gainers to scan
    python gainer_agent.py --break-mode low   # count a wick below the low as a break
    python gainer_agent.py --adjacent      # red candle must come right after the green one
"""

import argparse
import datetime as dt
import io
import os
import sys

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance not installed. Run:  pip install yfinance pandas requests")

# ---------------------------------------------------------------------------
# F&O universe
# ---------------------------------------------------------------------------
NSE_FO_LOTS_URL = "https://nsearchives.nseindia.com/content/fo/fo_mktlots.csv"

# Fallback list (NSE F&O stocks). Delisted/renamed symbols are skipped automatically.
FALLBACK_FO = """
AARTIIND ABB ABCAPITAL ABFRL ACC ADANIENSOL ADANIENT ADANIGREEN ADANIPORTS ALKEM
AMBUJACEM ANGELONE APLAPOLLO APOLLOHOSP APOLLOTYRE ASHOKLEY ASIANPAINT ASTRAL ATGL
AUBANK AUROPHARMA AXISBANK BAJAJ-AUTO BAJAJFINSV BAJFINANCE BALKRISIND BANDHANBNK
BANKBARODA BANKINDIA BEL BHARATFORG BHARTIARTL BHEL BIOCON BLUESTARCO BOSCHLTD BPCL
BRITANNIA BSE BSOFT CAMS CANBK CDSL CESC CGPOWER CHAMBLFERT CHOLAFIN CIPLA COALINDIA
COFORGE COLPAL CONCOR CROMPTON CUMMINSIND CYIENT DABUR DALBHARAT DELHIVERY DIVISLAB
DIXON DLF DMART DRREDDY EICHERMOT ESCORTS ETERNAL EXIDEIND FEDERALBNK GAIL GLENMARK
GMRAIRPORT GODREJCP GODREJPROP GRANULES GRASIM HAL HAVELLS HCLTECH HDFCAMC HDFCBANK
HDFCLIFE HEROMOTOCO HFCL HINDALCO HINDCOPPER HINDPETRO HINDUNILVR HINDZINC HUDCO
ICICIBANK ICICIGI ICICIPRULI IDEA IDFCFIRSTB IEX IGL IIFL INDHOTEL INDIANB INDIGO
INDUSINDBK INDUSTOWER INFY INOXWIND IOC IRB IRCTC IREDA IRFC ITC JINDALSTEL JIOFIN
JSWENERGY JSWSTEEL JUBLFOOD KALYANKJIL KEI KOTAKBANK KPITTECH LAURUSLABS LICHSGFIN
LICI LODHA LT LTF LTIM LUPIN M&M MANAPPURAM MANKIND MARICO MARUTI MAXHEALTH MAZDOCK
MCX MFSL MGL MOTHERSON MPHASIS MUTHOOTFIN NATIONALUM NAUKRI NBCC NCC NESTLEIND NHPC
NMDC NTPC NYKAA OBEROIRLTY OFSS OIL ONGC PAGEIND PATANJALI PAYTM PEL PERSISTENT
PETRONET PFC PHOENIXLTD PIDILITIND PIIND PNB PNBHOUSING POLICYBZR POLYCAB POONAWALLA
POWERGRID PRESTIGE RBLBANK RECLTD RELIANCE SAIL SBICARD SBILIFE SBIN SHREECEM
SHRIRAMFIN SIEMENS SJVN SOLARINDS SONACOMS SRF SUNPHARMA SUPREMEIND SYNGENE TATACHEM
TATACOMM TATACONSUM TATAELXSI TATAMOTORS TATAPOWER TATASTEEL TATATECH TCS TECHM
TIINDIA TITAGARH TITAN TORNTPHARM TORNTPOWER TRENT TVSMOTOR ULTRACEMCO UNIONBANK
UNITDSPR UPL VBL VEDL VOLTAS WIPRO YESBANK ZYDUSLIFE
""".split()


def get_fo_symbols():
    """Try NSE's live F&O lot-size file; fall back to the built-in list."""
    try:
        import requests
        s = requests.Session()
        hdrs = {"User-Agent": "Mozilla/5.0", "Accept": "*/*", "Referer": "https://www.nseindia.com/"}
        s.get("https://www.nseindia.com", headers=hdrs, timeout=10)
        r = s.get(NSE_FO_LOTS_URL, headers=hdrs, timeout=10)
        r.raise_for_status()
        df = pd.read_csv(io.StringIO(r.text))
        col = [c for c in df.columns if c.strip().upper() == "SYMBOL"][0]
        syms = [str(x).strip() for x in df[col]]
        skip = {"SYMBOL", "NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY", "NIFTYNXT50"}
        syms = [x for x in syms if x and x.upper() not in skip and not x.startswith("NIFTY")]
        if len(syms) > 100:
            print(f"[info] Loaded {len(syms)} F&O stocks from NSE.")
            return syms
    except Exception as e:
        print(f"[info] NSE list unavailable ({type(e).__name__}); using built-in list.")
    return FALLBACK_FO


def yf_ticker(sym):
    return sym + ".NS"


# ---------------------------------------------------------------------------
# Step 1-2: top gainers after the first 15 minutes
# ---------------------------------------------------------------------------
def first15_gainers(symbols, top_n):
    tickers = [yf_ticker(s) for s in symbols]
    data = yf.download(tickers, period="5d", interval="15m", group_by="ticker",
                       auto_adjust=False, progress=False, threads=True)
    rows = []
    for sym, tk in zip(symbols, tickers):
        try:
            df = data[tk].dropna(subset=["Close"])
        except (KeyError, TypeError):
            continue
        if df.empty:
            continue
        df.index = df.index.tz_convert("Asia/Kolkata") if df.index.tz else df.index.tz_localize("Asia/Kolkata")
        dates = sorted(set(df.index.date))
        if len(dates) < 2:
            continue
        today, prev = dates[-1], dates[-2]
        prev_close = df[df.index.date == prev]["Close"].iloc[-1]
        today_df = df[df.index.date == today]
        first = today_df[today_df.index.time == dt.time(9, 15)]
        if first.empty:
            continue
        c15 = first["Close"].iloc[0]
        rows.append({"symbol": sym, "prev_close": prev_close, "first15_close": c15,
                     "first15_high": first["High"].iloc[0], "first15_low": first["Low"].iloc[0],
                     "pct_change": (c15 / prev_close - 1) * 100, "session": today, "prev_session": prev})
    if not rows:
        return pd.DataFrame()
    out = pd.DataFrame(rows).sort_values("pct_change", ascending=False)
    return out[out["pct_change"] > 0].head(top_n).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Step 3: the hourly pattern on the previous day
# ---------------------------------------------------------------------------
def find_green_low_break(hourly, break_mode="close", adjacent=False):
    """
    hourly: DataFrame of ONE day's 1h candles (Open, High, Low, Close), time-ordered.
    Returns a list of breaks: a green candle whose low was broken by a later red candle.
      break_mode="close": red candle CLOSES below the green candle's low (default)
      break_mode="low"  : red candle's LOW trades below the green candle's low
    """
    hits = []
    c = hourly.reset_index()
    tcol = c.columns[0]
    for i in range(len(c)):
        g = c.iloc[i]
        if not g["Close"] > g["Open"]:
            continue  # not green
        later = range(i + 1, min(i + 2, len(c))) if adjacent else range(i + 1, len(c))
        for j in later:
            r = c.iloc[j]
            if not r["Close"] < r["Open"]:
                continue  # not red
            level = r["Close"] if break_mode == "close" else r["Low"]
            if level < g["Low"]:
                hits.append({"green_time": pd.Timestamp(g[tcol]).strftime("%H:%M"),
                             "green_low": round(float(g["Low"]), 2),
                             "red_time": pd.Timestamp(r[tcol]).strftime("%H:%M"),
                             "red_close": round(float(r["Close"]), 2),
                             "red_low": round(float(r["Low"]), 2)})
                break  # first red candle that breaks this green low
    return hits


def prev_day_hourly(sym, prev_date):
    df = yf.download(yf_ticker(sym), period="10d", interval="60m",
                     auto_adjust=False, progress=False)
    if df.empty:
        return df
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df.index = df.index.tz_convert("Asia/Kolkata") if df.index.tz else df.index.tz_localize("Asia/Kolkata")
    return df[df.index.date == prev_date][["Open", "High", "Low", "Close"]].dropna()


def scan(top=10, break_mode="close", adjacent=False):
    """Returns (results DataFrame, session date, previous session date)."""
    symbols = get_fo_symbols()
    print(f"[info] Ranking {len(symbols)} F&O stocks by first-15-min gain...")
    gainers = first15_gainers(symbols, top)
    if gainers.empty:
        return pd.DataFrame(), None, None
    session, prev = gainers["session"].iloc[0], gainers["prev_session"].iloc[0]
    results = []
    for _, g in gainers.iterrows():
        hourly = prev_day_hourly(g["symbol"], prev)
        hits = find_green_low_break(hourly, break_mode, adjacent) if not hourly.empty else []
        last = hits[-1] if hits else {}
        results.append({
            "date": session, "symbol": g["symbol"], "gain_%": round(g["pct_change"], 2),
            "prev_close": round(g["prev_close"], 2), "first15_close": round(g["first15_close"], 2),
            "first15_high": round(g["first15_high"], 2), "first15_low": round(g["first15_low"], 2),
            "setup": "YES" if hits else "no", "suggestion": "BUY FUTURE" if hits else "-",
            "breaks_found": len(hits),
            "green_candle": f"{last['green_time']} low {last['green_low']}" if hits else "",
            "red_candle": f"{last['red_time']} close {last['red_close']}" if hits else "",
            "candles_checked": len(hourly),
        })
    return pd.DataFrame(results), session, prev


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Top-gainer hourly green-low-break agent")
    ap.add_argument("--top", type=int, default=10, help="number of top gainers to scan (default 10)")
    ap.add_argument("--break-mode", choices=["close", "low"], default="close",
                    help="close = red candle closes below green low (default); low = wick below")
    ap.add_argument("--adjacent", action="store_true",
                    help="red candle must be the very next candle after the green one")
    ap.add_argument("--outdir", default="signals", help="folder for the CSV log")
    a = ap.parse_args()

    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=5, minutes=30)))
    if now.time() < dt.time(9, 31) and now.weekday() < 5:
        print("[warn] First 15-min candle may not be complete yet - run after 9:31 IST.")

    res, session, prev = scan(a.top, a.break_mode, a.adjacent)
    if res.empty:
        sys.exit("[error] No intraday data (market holiday, pre-open, or Yahoo unreachable).")
    print(f"\nSession {session}  |  checking 1h candles of {prev}  |  break mode: {a.break_mode}"
          f"{'  (adjacent only)' if a.adjacent else ''}\n")

    show = ["symbol", "gain_%", "first15_close", "setup", "suggestion", "green_candle", "red_candle"]
    print(res[show].to_string(index=False))

    picks = res[res["setup"] == "YES"]
    print("\n" + ("=" * 60))
    if picks.empty:
        print("No top gainer had a green-candle low broken by a red candle yesterday. No trade.")
    else:
        print("BUY candidates (stock futures):")
        for _, p in picks.iterrows():
            print(f"  -> {p['symbol']:<12} +{p['gain_%']}%   yesterday: green {p['green_candle']}, "
                  f"broken by red {p['red_candle']}")
    print("=" * 60)

    os.makedirs(a.outdir, exist_ok=True)
    path = os.path.join(a.outdir, f"signals_{session}.csv")
    res.to_csv(path, index=False)
    print(f"\nSaved: {path}")


if __name__ == "__main__":
    main()
