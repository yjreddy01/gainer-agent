"""Sends one test message and reports exactly what went wrong if Telegram rejects it."""
import os
import sys

import requests


def gh_error(msg):
    print(f"::error::{msg}")          # shows as a red annotation on the run page


from monitor import tg_creds

raw = os.getenv("TELEGRAM_BOT_TOKEN") or ""
token, chat = tg_creds()
# safe diagnostics (never prints the token itself)
print(f"Token secret: {len(raw)} characters; contains 'http': {'http' in raw}; "
      f"contains 'bot': {'bot' in raw.lower()}; contains spaces/newlines: {any(ch.isspace() for ch in raw)}; "
      f"valid token found inside: {token != raw.strip() or ':' in token}")
print(f"TELEGRAM_BOT_TOKEN set: {'yes' if token else 'NO'} | TELEGRAM_CHAT_ID set: {'yes' if chat else 'NO'}")
if not token or not chat:
    gh_error("Telegram secret missing: "
             + ", ".join(n for n, v in [("TELEGRAM_BOT_TOKEN", token), ("TELEGRAM_CHAT_ID", chat)] if not v)
             + " (check the secret names on Settings > Secrets and variables > Actions)")
    sys.exit(1)

me = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json()
if not me.get("ok"):
    gh_error(f"Bot token rejected by Telegram ({me.get('description')}). Secret has {len(raw)} characters "
             f"(a token is about 46); contains 'http': {'http' in raw}; spaces/newlines: {any(ch.isspace() for ch in raw)}; "
             f"looks like a token: {bool(__import__('re').fullmatch(r'[0-9]{6,}:[A-Za-z0-9_-]{30,}', token))}")
    sys.exit(1)
print(f"Token OK - bot @{me['result']['username']}")

r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                  data={"chat_id": chat, "text": "Test from your gainer-agent: alerts are working ✅"},
                  timeout=20).json()
if not r.get("ok"):
    hint = ("Chat ID is wrong, or you have not pressed START in your bot @" + me["result"]["username"]
            if "chat not found" in str(r.get("description", "")).lower() else "")
    gh_error(f"Telegram refused the message: {r.get('description')}. {hint} "
             f"(chat id has {len(chat)} characters, starts with '{chat[:2]}')")
    sys.exit(1)
print("::notice::Telegram test message sent successfully")
