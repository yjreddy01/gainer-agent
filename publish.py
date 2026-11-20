"""
Daily auto-publisher (runs on GitHub Actions at ~9:32 IST, Mon-Fri).

  1. Runs today's scan (top 10 F&O gainers, previous-day 1h green-low-break pattern).
  2. Runs a rolling backtest (last 5 sessions, top 5 gainers) for the current win rate.
  3. Saves CSVs in signals/, appends to signals/history.csv.
  4. Builds the web page docs/index.html (served by GitHub Pages).
  5. Sends a Telegram message if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set.
"""

import datetime as dt
import html
import os
import sys
import time

import pandas as pd

from gainer_agent import scan
from backtest import run_backtest, summarize

TOP_SCAN = int(os.getenv("TOP_SCAN", "10"))
BT_DAYS = int(os.getenv("BT_DAYS", "5"))
BT_TOP = int(os.getenv("BT_TOP", "5"))
BREAK_MODE = os.getenv("BREAK_MODE", "close")
PAGE_URL = os.getenv("PAGE_URL", "")

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))


def retry(fn, *args, tries=3, wait=20):
    for i in range(tries):
        try:
            return fn(*args)
        except Exception as e:
            print(f"[warn] attempt {i + 1} failed: {e}")
            if i == tries - 1:
                raise
            time.sleep(wait)


def send_telegram(text):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        print("[info] Telegram not configured - skipping message.")
        return
    import requests
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "parse_mode": "HTML",
                            "disable_web_page_preview": True}, timeout=20)
    print(f"[info] Telegram: {r.status_code}")


def fmt(v, suffix="%"):
    return "–" if v is None else f"{v}{suffix}"


def table_html(df, cols):
    if df.empty:
        return "<p class='muted'>No rows.</p>"
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body = ""
    for _, r in df.iterrows():
        cls = ""
        if "setup" in r and r["setup"] == "YES":
            cls = " class='hit'"
        cells = ""
        for c in cols:
            v = r[c]
            style = ""
            if c in ("return_%",) and isinstance(v, (int, float)):
                style = " class='pos'" if v > 0 else " class='neg'"
            if c == "result":
                style = " class='pos'" if v == "WIN" else " class='neg'"
            cells += f"<td{style}>{html.escape(str(v))}</td>"
        body += f"<tr{cls}>{cells}</tr>"
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def build_page(today_df, session, prev, bt_df, bt_days, stats, history):
    picks = today_df[today_df["setup"] == "YES"] if not today_df.empty else today_df
    picks_html = ("".join(f"<div class='pick'><b>{html.escape(p['symbol'])}</b> &nbsp;+{p['gain_%']}% "
                          f"<span class='muted'>· green {html.escape(p['green_candle'])} → "
                          f"red {html.escape(p['red_candle'])}</span></div>"
                          for _, p in picks.iterrows())
                  or "<p class='muted'>No BUY signal today.</p>")
    s_yes, s_no, s_all = stats["with"], stats["without"], stats["all"]
    period = f"{bt_days[0]} → {bt_days[-1]}" if bt_days else "–"
    hist_tail = history.sort_values("date", ascending=False).head(60) if not history.empty else history
    updated = dt.datetime.now(IST).strftime("%d %b %Y, %H:%M IST")

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Top-Gainer Break Agent</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;margin:0;background:#f6f7f9;color:#1d2330}}
 .wrap{{max-width:1000px;margin:0 auto;padding:20px}}
 h1{{font-size:22px;margin:0 0 4px}} h2{{font-size:17px;margin:28px 0 10px}}
 .muted{{color:#6b7280;font-size:13px}}
 .cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}}
 .card{{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:14px}}
 .big{{font-size:28px;font-weight:700}}
 .pick{{background:#ecfdf3;border:1px solid #a7f3c4;border-radius:8px;padding:10px 12px;margin:6px 0}}
 table{{border-collapse:collapse;width:100%;background:#fff;font-size:13px}}
 th,td{{border-bottom:1px solid #eef0f3;padding:6px 8px;text-align:left;white-space:nowrap}}
 th{{background:#f1f3f6}} tr.hit td{{background:#f0fdf4}}
 .pos{{color:#047857;font-weight:600}} .neg{{color:#b91c1c;font-weight:600}}
 .scroll{{overflow-x:auto}}
</style></head><body><div class="wrap">
<h1>Top-Gainer Hourly Break Agent</h1>
<div class="muted">Updated {updated} · Session {session} · pattern checked on 1h candles of {prev}</div>

<h2>Today's BUY signals (stock futures)</h2>
{picks_html}

<h2>Win rate — last {len(bt_days)} sessions ({period}), top {BT_TOP} gainers/day</h2>
<div class="cards">
 <div class="card"><div class="muted">With pattern (agent's signals)</div>
  <div class="big">{fmt(s_yes['win_rate'])}</div>
  <div class="muted">{s_yes['wins']}/{s_yes['trades']} wins · avg {fmt(s_yes['avg_return'])}</div></div>
 <div class="card"><div class="muted">Without pattern (skipped)</div>
  <div class="big">{fmt(s_no['win_rate'])}</div>
  <div class="muted">{s_no['wins']}/{s_no['trades']} wins · avg {fmt(s_no['avg_return'])}</div></div>
 <div class="card"><div class="muted">All top gainers (no filter)</div>
  <div class="big">{fmt(s_all['win_rate'])}</div>
  <div class="muted">{s_all['wins']}/{s_all['trades']} wins · avg {fmt(s_all['avg_return'])}</div></div>
</div>
<p class="muted">Simulated trade: buy at the 9:30 price, sell at the day's close. WIN = close above entry.
Small samples are unreliable — trust the win rate only after 20+ signal trades.</p>

<h2>Today's top {TOP_SCAN} gainers</h2>
<div class="scroll">{table_html(today_df, ["symbol","gain_%","first15_close","first15_high","first15_low","setup","green_candle","red_candle"])}</div>

<h2>Backtest trades</h2>
<div class="scroll">{table_html(bt_df, ["date","symbol","gain15_%","setup","entry_9:30","exit_close","return_%","result","best_move_%","worst_move_%"])}</div>

<h2>Signal history (all days)</h2>
<div class="scroll">{table_html(hist_tail, ["date","symbol","gain_%","first15_close","green_candle","red_candle"])}</div>

<p class="muted">Data: Yahoo Finance cash-market prices (futures track these with a small premium).
Scanner only — not investment advice; no orders are placed.</p>
</div></body></html>"""


def main():
    now = dt.datetime.now(IST)
    today_df, session, prev = retry(scan, TOP_SCAN, BREAK_MODE)
    if today_df.empty or session != now.date():
        print(f"[info] No session today ({now.date()}) - market holiday or no data. Nothing published.")
        return

    try:
        bt_df, bt_days = retry(run_backtest, BT_DAYS, BT_TOP, BREAK_MODE)
    except Exception as e:
        print(f"[warn] backtest failed: {e}")
        bt_df, bt_days = pd.DataFrame(), []

    stats = {"with": summarize(bt_df[bt_df["setup"] == "YES"]) if not bt_df.empty else summarize(bt_df),
             "without": summarize(bt_df[bt_df["setup"] == "no"]) if not bt_df.empty else summarize(bt_df),
             "all": summarize(bt_df)}

    os.makedirs("signals", exist_ok=True)
    today_df.to_csv(f"signals/signals_{session}.csv", index=False)
    if not bt_df.empty:
        bt_df.to_csv("signals/backtest_latest.csv", index=False)

    hist_path = "signals/history.csv"
    picks = today_df[today_df["setup"] == "YES"]
    history = pd.read_csv(hist_path) if os.path.exists(hist_path) else pd.DataFrame()
    if not history.empty:
        history = history[history["date"].astype(str) != str(session)]
    history = pd.concat([history, picks], ignore_index=True)
    history.to_csv(hist_path, index=False)

    os.makedirs("docs", exist_ok=True)
    with open("docs/index.html", "w", encoding="utf-8") as f:
        f.write(build_page(today_df, session, prev, bt_df, bt_days, stats, history))
    print("[info] Page written: docs/index.html")

    # Telegram message
    lines = [f"<b>Top-Gainer Break Agent — {session:%d %b %Y}</b>"]
    if picks.empty:
        lines.append("No BUY signal today.")
    else:
        lines.append("BUY (stock futures):")
        for _, p in picks.iterrows():
            lines.append(f"• <b>{p['symbol']}</b> +{p['gain_%']}% (9:30 price {p['first15_close']})")
    s = stats["with"]
    lines.append(f"\nWin rate, last {len(bt_days)} sessions: {fmt(s['win_rate'])} "
                 f"({s['wins']}/{s['trades']}), all gainers: {fmt(stats['all']['win_rate'])}")
    if PAGE_URL:
        lines.append(PAGE_URL)
    send_telegram("\n".join(lines))


if __name__ == "__main__":
    main()
