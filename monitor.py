"""
Live monitor - runs every 5 minutes from 9:20 AM to 2:00 PM IST on GitHub Actions.

Each run:
  1. Builds today's qualifier list from yesterday's 1h candles (once a day, then cached).
  2. Replays today's completed 5-min candles: qualified + top-10 gainer + close above first 5-min high.
  3. For every NEW trigger: opens a GitHub issue (GitHub emails / pushes it to you) and
     sends a Telegram message if TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are set.
  4. Updates the web page.
Replaying the whole day each run means a delayed or skipped run never misses an alert.
"""

import datetime as dt
import json
import os
import sys
import time

import pandas as pd

import page
from strategy import download, get_fo_symbols, qualifiers_for, day_triggers

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
TOP_N = int(os.getenv("TOP_N", "10"))
CUTOFF = dt.time(*map(int, os.getenv("CUTOFF", "14:00").split(":")))
PAGE_URL = os.getenv("PAGE_URL", "")


def retry(fn, *args, tries=3, wait=15):
    for i in range(tries):
        try:
            out = fn(*args)
            if out:
                return out
            raise RuntimeError("empty download")
        except Exception as e:
            print(f"[warn] attempt {i + 1}: {e}")
            if i == tries - 1:
                raise
            time.sleep(wait)


def github_issue(title, body):
    token, repo = os.getenv("GITHUB_TOKEN"), os.getenv("GITHUB_REPOSITORY")
    if not (token and repo):
        print("[info] Not on GitHub Actions - skipping issue.")
        return
    import requests
    r = requests.post(f"https://api.github.com/repos/{repo}/issues",
                      headers={"Authorization": f"Bearer {token}",
                               "Accept": "application/vnd.github+json"},
                      json={"title": title, "body": body, "labels": ["buy-alert"]}, timeout=20)
    print(f"[info] GitHub issue: {r.status_code}")


def telegram(text):
    token, chat = os.getenv("TELEGRAM_BOT_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not (token and chat):
        return
    import requests
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                      data={"chat_id": chat, "text": text, "disable_web_page_preview": True},
                      timeout=20)
    print(f"[info] Telegram: {r.status_code}")


def main():
    now = dt.datetime.now(IST)
    if now.weekday() >= 5:
        print("[info] Weekend - nothing to do.")
        return

    symbols = get_fo_symbols()
    m5 = retry(download, symbols, "5m", "5d")
    dates = sorted({d for df in m5.values() for d in df.index.date})
    today = dates[-1]
    if today != now.date() or len(dates) < 2:
        print(f"[info] No session today ({now.date()}) - market holiday.")
        return
    prev = dates[-2]
    os.makedirs("signals", exist_ok=True)

    # 1. Qualifiers (cached once per day)
    qpath = f"signals/qualifiers_{today}.csv"
    if os.path.exists(qpath):
        quals = pd.read_csv(qpath)
    else:
        h1 = retry(download, symbols, "60m", "5d")
        quals = qualifiers_for(h1, prev)
        quals.to_csv(qpath, index=False)
        print(f"[info] {len(quals)} qualified stocks from {prev}.")
    qual_set = set(quals["symbol"]) if not quals.empty else set()

    # 2. Triggers so far today
    trig, snap = day_triggers(m5, today, prev, qual_set, TOP_N, CUTOFF, now=pd.Timestamp(now))
    json.dump({"date": str(today), **snap}, open("signals/snapshot.json", "w"))

    # 3. New alerts
    apath = f"signals/alerts_{today}.csv"
    old = pd.read_csv(apath) if os.path.exists(apath) else pd.DataFrame(columns=["symbol"])
    new = trig[~trig["symbol"].isin(old["symbol"])] if not trig.empty else trig
    owner = os.getenv("GITHUB_REPOSITORY_OWNER", "")
    for _, t in new.iterrows():
        q = quals[quals["symbol"] == t["symbol"]].iloc[0]
        title = f"BUY {t['symbol']} future · {t['time']} · +{t['gain_%']}% (gainer #{t['rank']}) · {today:%d %b}"
        body = (f"{'@' + owner if owner else ''}\n\n"
                f"**BUY {t['symbol']} (stock future)**\n\n"
                f"- 5-min candle {t['time']} closed at **{t['entry']}**, above today's first 5-min high **{t['first5_high']}**\n"
                f"- Top-10 gainer: #{t['rank']}, +{t['gain_%']}% vs yesterday's close\n"
                f"- Qualified on {prev:%d %b} 1h chart: green {q['green_candle']} broken by red {q['red_candle']}\n\n"
                f"{PAGE_URL}")
        github_issue(title, body)
        telegram(f"BUY {t['symbol']} future at {t['time']} — price {t['entry']} "
                 f"(> first 5-min high {t['first5_high']}), gainer #{t['rank']} +{t['gain_%']}%\n{PAGE_URL}")
    if not new.empty:
        new = new.astype({"rank": int})
        (new if old.empty else pd.concat([old, new], ignore_index=True)[new.columns]).to_csv(apath, index=False)
        hpath = "signals/alert_history.csv"
        hist = pd.read_csv(hpath) if os.path.exists(hpath) else pd.DataFrame()
        pd.concat([hist, new], ignore_index=True).to_csv(hpath, index=False)
    elif not os.path.exists(apath):
        pd.DataFrame(columns=["date", "time", "symbol", "rank", "gain_%", "entry",
                              "first5_high", "qualified"]).to_csv(apath, index=False)
    print(f"[info] {now:%H:%M} IST: {len(trig)} trigger(s) today, {len(new)} new.")

    # 4. Page
    page.build()


if __name__ == "__main__":
    main()
