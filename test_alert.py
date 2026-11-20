"""Sends one test message to every configured channel (WhatsApp / Telegram / SMS)."""
import os
from monitor import notify

os.environ.setdefault("SMS_KINDS", "test")
notify("Test from your gainer-agent: alerts are working ✅", "test")
