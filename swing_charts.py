"""
Swing high / swing low charts for the TOP 5 Nifty 50 stocks by market capitalisation.

- Ranks the Nifty 50 constituents by live market cap (Yahoo Finance) and takes the top 5.
- Daily candles for the last ~6 months.
- Swing high: a candle whose HIGH is the highest of the SWING candles on each side (default 5).
  Swing low : a candle whose LOW  is the lowest  of the SWING candles on each side.
- Saves charts to docs/charts/<SYMBOL>.png and the swing points to signals/swings_<SYMBOL>.csv.

Also lists the 5 F&O stocks whose close is nearest ABOVE their latest swing low (within 3%),
with charts -> docs/charts/near/, signals/near_swing_low.csv, and Telegram.

Charts include a volume panel (green/red bars + 20-day average).

Usage: python swing_charts.py [--swing 5] [--months 6] [--top 5]
"""

import argparse
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker
import pandas as pd
import yfinance as yf

NIFTY50 = """ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL
CIPLA COALINDIA DRREDDY EICHERMOT ETERNAL GRASIM HCLTECH HDFCBANK HDFCLIFE HEROMOTOCO HINDALCO HINDUNILVR
ICICIBANK INDIGO INFY ITC JIOFIN JSWSTEEL KOTAKBANK LT M&M MARUTI MAXHEALTH NESTLEIND NTPC ONGC POWERGRID
RELIANCE SBILIFE SBIN SHRIRAMFIN SUNPHARMA TATACONSUM TMPV TATASTEEL TCS TECHM TITAN TRENT ULTRACEMCO WIPRO""".split()


def top_by_mcap(n):
    caps = []
    for s in NIFTY50:
        try:
            mc = yf.Ticker(s + ".NS").fast_info["market_cap"]
            if mc:
                caps.append((s, float(mc)))
        except Exception:
            pass
    caps.sort(key=lambda x: x[1], reverse=True)
    return caps[:n]


def swings(df, k):
    hi, lo = [], []
    for i in range(k, len(df) - k):
        w = df.iloc[i - k:i + k + 1]
        left = df.iloc[i - k:i]
        # highest of the window, and strictly above the candles before it (equal highs count once)
        if df["High"].iloc[i] == w["High"].max() and df["High"].iloc[i] > left["High"].max():
            hi.append(i)
        if df["Low"].iloc[i] == w["Low"].min() and df["Low"].iloc[i] < left["Low"].min():
            lo.append(i)
    return hi, lo


def chart(sym, mcap, df, hi, lo, k, path, highlight=None, title_extra=""):
    """highlight: optional list of (date, label, colour) - shades those candles (e.g. the pattern candles)."""
    has_vol = "Volume" in df.columns and df["Volume"].fillna(0).sum() > 0
    if has_vol:
        fig, (ax, axv) = plt.subplots(2, 1, figsize=(13, 8), dpi=110, sharex=True,
                                      gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05})
    else:
        fig, ax = plt.subplots(figsize=(13, 6.5), dpi=110)
    x = range(len(df))
    up = df["Close"] >= df["Open"]
    for i, (o, h, l, c) in enumerate(df[["Open", "High", "Low", "Close"]].itertuples(index=False)):
        col = "#16a34a" if c >= o else "#dc2626"
        ax.vlines(i, l, h, color=col, linewidth=0.8)
        ax.add_patch(plt.Rectangle((i - 0.3, min(o, c)), 0.6, max(abs(c - o), 1e-9), color=col))
    rng = df["High"].max() - df["Low"].min()
    for n, (d, label, colr) in enumerate(highlight or []):
        pos = [j for j, ix in enumerate(df.index) if ix.date() == d]
        if pos:
            p = pos[0]
            ax.axvspan(p - 0.5, p + 0.5, color=colr, alpha=0.18)
            ax.annotate(label, (p, df["High"].iloc[p]), xytext=(0, 28 + 14 * n), textcoords="offset points",
                        ha="center", fontsize=8, color=colr, fontweight="bold",
                        arrowprops=dict(arrowstyle="-", color=colr, lw=0.6))
    for i in hi:
        p = df["High"].iloc[i]
        ax.plot(i, p + rng * 0.015, marker="v", color="#b91c1c", markersize=8)
        ax.annotate(f"{p:,.0f}", (i, p + rng * 0.035), ha="center", fontsize=8, color="#b91c1c")
    for i in lo:
        p = df["Low"].iloc[i]
        ax.plot(i, p - rng * 0.015, marker="^", color="#15803d", markersize=8)
        ax.annotate(f"{p:,.0f}", (i, p - rng * 0.06), ha="center", fontsize=8, color="#15803d")
    # swing line connecting the pivots in time order
    piv = sorted([(i, df["High"].iloc[i]) for i in hi] + [(i, df["Low"].iloc[i]) for i in lo])
    if piv:
        ax.plot([p[0] for p in piv], [p[1] for p in piv], color="#2563eb", linewidth=1, alpha=0.6)
    # latest swing high / low as reference levels
    if hi:
        h = df["High"].iloc[hi[-1]]
        ax.axhline(h, color="#b91c1c", linestyle="--", linewidth=0.9, alpha=0.7)
        ax.text(len(df) - 0.5, h, f" last swing high {h:,.1f}", va="bottom", ha="right", fontsize=9, color="#b91c1c")
    if lo:
        l = df["Low"].iloc[lo[-1]]
        ax.axhline(l, color="#15803d", linestyle="--", linewidth=0.9, alpha=0.7)
        ax.text(len(df) - 0.5, l, f" last swing low {l:,.1f}", va="top", ha="right", fontsize=9, color="#15803d")
    step = max(1, len(df) // 10)
    if has_vol:
        cols = ["#16a34a" if c >= o else "#dc2626" for o, c in zip(df["Open"], df["Close"])]
        axv.bar(list(x), df["Volume"], color=cols, width=0.7, alpha=0.8)
        axv.plot(list(x), df["Volume"].rolling(20).mean(), color="#2563eb", linewidth=1.2, label="20-day avg volume")
        axv.legend(loc="upper left", fontsize=8, frameon=False)
        axv.set_ylabel("Volume", fontsize=9)
        axv.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
            lambda v, _: f"{v / 1e7:.1f} Cr" if v >= 1e7 else f"{v / 1e5:.0f} L"))
        axv.grid(alpha=0.25)
        axv.set_xticks(list(x)[::step])
        axv.set_xticklabels([d.strftime("%d %b") for d in df.index[::step]], fontsize=9)
    ax.set_xticks(list(x)[::step])
    ax.set_xticklabels([d.strftime("%d %b") for d in df.index[::step]], fontsize=9)
    ax.set_xlim(-1, len(df) + 1)
    ax.set_ylim(df["Low"].min() - rng * 0.1, df["High"].max() + rng * 0.08)
    ax.grid(alpha=0.25)
    mc = f"mcap ₹{mcap / 1e12:,.2f} lakh cr · " if mcap else ""
    ax.set_title(f"{sym} — daily, swing highs ▼ / lows ▲ ({k} candles each side) · "
                 f"{mc}last close {df['Close'].iloc[-1]:,.2f}{title_extra}", fontsize=11)
    if not has_vol:
        fig.tight_layout()
    else:
        fig.subplots_adjust(left=0.06, right=0.98, top=0.95, bottom=0.06)
    fig.savefig(path)
    plt.close(fig)


def near_swing_low(k, months, n=5, max_pct=3.0):
    """F&O stocks whose last daily close is just ABOVE their latest swing low (within max_pct %)."""
    from strategy import download, get_fo_symbols
    data = download(get_fo_symbols(), "1d", f"{months}mo")
    rows = []
    for s, df in data.items():
        df = df.dropna()
        if len(df) < 2 * k + 5:
            continue
        hi, lo = swings(df, k)
        if not lo:
            continue
        sl = float(df["Low"].iloc[lo[-1]])
        close = float(df["Close"].iloc[-1])
        dist = (close / sl - 1) * 100
        if 0 <= dist <= max_pct:
            rows.append({"symbol": s, "close": round(close, 2), "swing_low": round(sl, 2),
                         "swing_low_date": df.index[lo[-1]].date(), "distance_%": round(dist, 2),
                         "df": df, "hi": hi, "lo": lo})
    rows.sort(key=lambda r: r["distance_%"])
    return rows[:n]


def make_pdf(pngs, path, title, rows=None):
    """Combine chart PNGs into one PDF: a summary page (title + optional table rows) then one chart per page."""
    from matplotlib.backends.backend_pdf import PdfPages
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27))                       # A4 landscape
        fig.text(0.05, 0.92, title, fontsize=18, fontweight="bold")
        y = 0.85
        for line in (rows or []):
            fig.text(0.05, y, line, fontsize=10, family="monospace")
            y -= 0.032
            if y < 0.05:
                break
        pdf.savefig(fig)
        plt.close(fig)
        for p in pngs:
            img = plt.imread(p)
            fig = plt.figure(figsize=(11.69, 8.27))
            ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
            ax.imshow(img)
            ax.axis("off")
            pdf.savefig(fig, dpi=150)
            plt.close(fig)
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--swing", type=int, default=5)
    ap.add_argument("--months", type=int, default=6)
    ap.add_argument("--top", type=int, default=5)
    a = ap.parse_args()

    top = top_by_mcap(a.top)
    print("[info] Top by market cap:", ", ".join(f"{s} (₹{m / 1e12:.2f} lakh cr)" for s, m in top))
    os.makedirs("docs/charts", exist_ok=True)
    os.makedirs("signals", exist_ok=True)
    rows = []
    for rank, (s, mc) in enumerate(top, 1):
        df = yf.download(s + ".NS", period=f"{a.months}mo", interval="1d", auto_adjust=False, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df = df[[c for c in ["Open", "High", "Low", "Close", "Volume"] if c in df.columns]].dropna()
        hi, lo = swings(df, a.swing)
        chart(s, mc, df, hi, lo, a.swing, f"docs/charts/{s}.png")
        pts = ([{"date": df.index[i].date(), "type": "swing high", "price": round(float(df["High"].iloc[i]), 2)} for i in hi] +
               [{"date": df.index[i].date(), "type": "swing low", "price": round(float(df["Low"].iloc[i]), 2)} for i in lo])
        pd.DataFrame(pts).sort_values("date").to_csv(f"signals/swings_{s}.csv", index=False)
        rows.append({"rank": rank, "symbol": s, "mcap_lakh_cr": round(mc / 1e12, 2),
                     "last_close": round(float(df["Close"].iloc[-1]), 2),
                     "last_swing_high": round(float(df["High"].iloc[hi[-1]]), 2) if hi else None,
                     "last_swing_high_date": df.index[hi[-1]].date() if hi else None,
                     "last_swing_low": round(float(df["Low"].iloc[lo[-1]]), 2) if lo else None,
                     "last_swing_low_date": df.index[lo[-1]].date() if lo else None})
        print(f"[info] {s}: {len(hi)} swing highs, {len(lo)} swing lows")
    pd.DataFrame(rows).to_csv("signals/swing_summary.csv", index=False)

    # (top-5 market-cap charts stay on the web page only; Telegram gets the 5 near-swing-low charts)

    # 5 F&O stocks nearest above their swing low
    near = near_swing_low(a.swing, a.months)
    os.makedirs("docs/charts/near", exist_ok=True)
    for f in os.listdir("docs/charts/near"):
        os.remove(os.path.join("docs/charts/near", f))
    for r in near:
        chart(r["symbol"], 0, r["df"], r["hi"], r["lo"], a.swing, f"docs/charts/near/{r['symbol']}.png")
    nd = pd.DataFrame([{k: v for k, v in r.items() if k not in ("df", "hi", "lo")} for r in near])
    nd.to_csv("signals/near_swing_low.csv", index=False)
    print(f"[info] Near swing low: {', '.join(nd['symbol']) if not nd.empty else 'none'}")
    from monitor import telegram, telegram_photo
    if nd.empty:
        telegram("Near swing low (1-day): no F&O stock is within 3% above its last swing low today.")
    else:
        telegram("Near swing low (1-day) - 5 F&O stocks closest above their last swing low:\n" +
                 "\n".join(f"{r['symbol']}: close {r['close']}, swing low {r['swing_low']} "
                           f"({r['swing_low_date']:%d %b}), {r['distance_%']}% above" for r in near))
        for r in near:
            telegram_photo(f"docs/charts/near/{r['symbol']}.png",
                           f"{r['symbol']} (1-day) · close {r['close']} · {r['distance_%']}% above swing low "
                           f"{r['swing_low']} ({r['swing_low_date']:%d %b})")

    try:
        import page
        page.build()
    except Exception as e:
        print(f"[warn] page not rebuilt: {e}")


if __name__ == "__main__":
    main()
