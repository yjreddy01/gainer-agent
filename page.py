"""Builds docs/index.html from the state files in signals/."""

import datetime as dt
import glob
import html
import json
import os

import pandas as pd

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def _read_csv(path):
    try:
        return pd.read_csv(path) if os.path.exists(path) else pd.DataFrame()
    except pd.errors.EmptyDataError:
        return pd.DataFrame()


def _latest(pattern):
    files = sorted(glob.glob(pattern))
    return files[-1] if files else None


def _table(df, cols, hit_col=None):
    if df is None or df.empty:
        return "<p class='muted'>None.</p>"
    cols = [c for c in cols if c in df.columns]
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = ""
    for _, r in df.iterrows():
        cls = " class='hit'" if hit_col and bool(r.get(hit_col)) in (True,) and str(r.get(hit_col)) not in ("False", "no") else ""
        cells = ""
        for c in cols:
            v = r[c]
            st = ""
            if c in ("return_%",) and isinstance(v, (int, float)):
                st = " class='pos'" if v > 0 else " class='neg'"
            if c == "result":
                st = " class='pos'" if v == "WIN" else " class='neg'"
            cells += f"<td{st}>{html.escape(str(v))}</td>"
        body += f"<tr{cls}>{cells}</tr>"
    return f"<div class='scroll'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def _card(label, s):
    if not s or not s.get("trades"):
        return f"<div class='card'><div class='muted'>{label}</div><div class='big'>–</div><div class='muted'>no trades</div></div>"
    return (f"<div class='card'><div class='muted'>{label}</div><div class='big'>{s['win_rate']}%</div>"
            f"<div class='muted'>{s['wins']}/{s['trades']} wins · avg {s['avg_return']:+}% · total {s['total_return']:+}%</div></div>")


def build():
    snap = {}
    if os.path.exists("signals/snapshot.json"):
        snap = json.load(open("signals/snapshot.json"))
    session = snap.get("date", "–")
    quals = _read_csv(f"signals/qualifiers_{session}.csv")
    alerts = _read_csv(f"signals/alerts_{session}.csv")
    history = _read_csv("signals/alert_history.csv")
    bt = _read_csv("signals/backtest_latest.csv")
    p2, p3 = _latest("signals/daily_2candle_*.csv"), _latest("signals/daily_3candle_*.csv")
    two = _read_csv(p2) if p2 else pd.DataFrame()
    three = _read_csv(p3) if p3 else pd.DataFrame()
    d2 = os.path.basename(p2)[14:24] if p2 else "–"
    d3 = os.path.basename(p3)[14:24] if p3 else "–"
    i2, i3 = _latest("signals/index_2candle_*.csv"), _latest("signals/index_3candle_*.csv")
    idx2 = _read_csv(i2) if i2 else pd.DataFrame()
    idx3 = _read_csv(i3) if i3 else pd.DataFrame()
    di = os.path.basename(i2)[14:24] if i2 else "–"
    isf = _latest("signals/index_short_*.csv")
    idxs = _read_csv(isf) if isf else pd.DataFrame()
    repo = os.getenv("GITHUB_REPOSITORY", "yjreddy01/gainer-agent")
    dl = lambda f: f"<a href='https://raw.githubusercontent.com/{repo}/main/{f}' download>download CSV</a>" if f else ""
    bts = json.load(open("signals/backtest_summary.json")) if os.path.exists("signals/backtest_summary.json") else {}

    if alerts.empty:
        alert_html = "<p class='muted'>No BUY alert yet today.</p>"
    else:
        alert_html = "".join(
            f"<div class='pick'><b>{html.escape(str(a['symbol']))}</b> &nbsp;BUY at {a['time']} · "
            f"price {a['entry']} (broke first 5-min high {a['first5_high']}) · "
            f"<span class='muted'>gainer #{a['rank']}, +{a['gain_%']}%</span></div>"
            for _, a in alerts.iterrows())

    top_rows = "".join(
        f"<tr{' class=hit' if q else ''}><td>{i}</td><td>{html.escape(s)}</td><td>+{g}%</td>"
        f"<td>{'✔ qualified' if q else ''}</td></tr>"
        for i, (s, g, q) in enumerate(snap.get("top", []), start=1))
    top_html = (f"<div class='scroll'><table><thead><tr><th>#</th><th>symbol</th><th>gain</th><th>yesterday's 1h pattern</th>"
                f"</tr></thead><tbody>{top_rows}</tbody></table></div>") if top_rows else "<p class='muted'>–</p>"

    period = f"{bts.get('from', '–')} → {bts.get('to', '–')}"
    hist = history.sort_values(["date", "time"], ascending=False).head(100) if not history.empty else history
    updated = dt.datetime.now(IST).strftime("%d %b %Y, %H:%M IST")

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="300">
<title>Top-Gainer Break Agent</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}}
 .wrap{{max-width:1000px;margin:0 auto;padding:20px}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 10px}}
 .muted{{color:#6b7280;font-size:13px}}
 .rule{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:12px 14px;font-size:14px;line-height:1.6}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
 .card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px}}
 .big{{font-size:28px;font-weight:700}}
 .pick{{background:#ecfdf3;border:1px solid #a7f3c4;border-radius:8px;padding:10px 12px;margin:6px 0}}
 table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
 th,td{{border-bottom:1px solid #eef0f3;padding:6px 8px;text-align:left;white-space:nowrap}}
 th{{background:#f1f3f6}} tr.hit td{{background:#f0fdf4}}
 .pos{{color:#047857;font-weight:600}} .neg{{color:#b91c1c;font-weight:600}}
 .scroll{{overflow-x:auto}}
</style></head><body><div class="wrap">
<h1>Top-Gainer Break Agent</h1>
<div class="muted">Updated {updated} · Session {session} · last 5-min candle {snap.get('time', '–')}</div>

<div class="rule" style="margin-top:14px"><b>Rule:</b> (1) Qualified = on yesterday's 1-hour chart, a red candle broke the low of the
green candle right before it (closed below it). (2) Today, BUY the stock future when a qualified stock is in the
<b>top 10 F&O gainers</b> and a 5-min candle <b>closes above the high of today's first 5-min candle</b> (until 2:00 PM).</div>

<h2>Today's BUY alerts</h2>
{alert_html}

<h2>Top 10 gainers now</h2>
{top_html}

<h2>Qualified stocks today ({len(quals)}) — from 1h chart of {quals['qual_date'].iloc[0] if not quals.empty else '–'}</h2>
{_table(quals, ["symbol", "green_candle", "red_candle"])}

<h2>Index 15-min formations — NIFTY, SENSEX, BANKNIFTY, CRUDE ({di})</h2>
<p class="muted">CRUDE = WTI crude futures (CL=F, USD) as a proxy for MCX crude; formations reported 5:00 PM – 11:30 PM IST.</p>
<p class="muted"><b>(a) 2-candle</b> ({len(idx2)}): green 15-min candle → next candle red, closing below its low. {dl(i2)}</p>
{_table(idx2, ["index", "time", "green_candle", "red_close"])}
<p class="muted"><b>(b) 3-candle</b> ({len(idx3)}): green → next red breaks its low → within 5 candles a close above the
green candle's high. {dl(i3)}</p>
{_table(idx3, ["index", "time", "green_candle", "red_candle", "close", "candles_since_red"])}
<p class="muted"><b>SHORT signals</b> ({len(idxs)}): green → next candle red with its high above the green high → within
5 candles a close below the red candle's low (red high = stop-loss reference). {dl(isf)}</p>
{_table(idxs, ["index", "time", "green_candle", "red_candle", "close", "red_high_sl"])}

<h2>(a) Daily 2-candle formation ({len(two)}) — {d2}</h2>
<p class="muted">Yesterday green → today red, closing below the green candle's low. {dl(p2)}</p>
{_table(two, ["symbol", "today_close", "change_%", "green_candle", "red_candle"])}

<h2>(b) Daily 3-candle formation ({len(three)}) — {d3}</h2>
<p class="muted">Green → next candle red, closing below its low (within the last 5 sessions) → today closed above
the green candle's high. {dl(p3)}</p>
{_table(three, ["symbol", "today_close", "change_%", "green_candle", "red_candle", "days_since_red"])}

<h2>Backtest — {bts.get('days', '–')} sessions ({period})</h2>
<div class="cards">
 {_card("Agent's alerts (qualified)", bts.get('qualified'))}
 {_card("Same trigger, NOT qualified", bts.get('not_qualified'))}
 {_card("All triggers", bts.get('all'))}
</div>
<p class="muted">Simulated trade: buy at the close of the trigger candle, sell at the day's close. WIN = sold above entry.
Compare the first two cards: the 1h pattern only helps if the first card is clearly better than the second.</p>
{_table(bt[bt['qualified'] == True] if not bt.empty else bt, ["date", "time", "symbol", "rank", "gain_%", "entry", "exit_close", "return_%", "result", "best_move_%", "worst_move_%"])}

<h2>Alert history</h2>
{_table(hist, ["date", "time", "symbol", "rank", "gain_%", "entry", "first5_high"])}

<p class="muted">Data: Yahoo Finance cash-market prices (stock futures track these with a small premium).
Scanner only — not investment advice; no orders are placed. Page refreshes every 5 minutes.</p>
</div></body></html>"""
    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(page)
    print("[info] Page written: docs/index.html")


if __name__ == "__main__":
    build()
