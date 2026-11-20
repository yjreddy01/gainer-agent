"""Re-send the latest daily pattern charts (docs/charts/patterns) to Telegram and report the result."""
import glob
import os
import sys

from monitor import telegram, telegram_photo

files = sorted(glob.glob("docs/charts/patterns/*.png"))
if not files:
    print("::error::No pattern charts found")
    sys.exit(1)
telegram(f"Today's daily pattern charts ({len(files)}) - shaded candles = the pattern.")
ok = 0
for p in files:
    kind, sym = os.path.basename(p)[:-4].split("_", 1)
    if telegram_photo(p, f"{sym} · {kind} (1-day)"):
        ok += 1
print(f"::notice::Sent {ok} of {len(files)} charts to Telegram")
if ok < len(files):
    print(f"::error::Only {ok} of {len(files)} charts were sent")
    sys.exit(1)
