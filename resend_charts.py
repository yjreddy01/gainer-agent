"""Re-send the latest daily pattern charts to Telegram as one PDF and report the result."""
import glob
import os
import sys

from monitor import telegram_file
from swing_charts import make_pdf

files = sorted(glob.glob("docs/charts/patterns/*.png"))
if not files:
    print("::error::No pattern charts found")
    sys.exit(1)
pdf = "docs/charts/patterns/daily_patterns_latest.pdf"
make_pdf(files, pdf, f"Daily pattern charts ({len(files)} stocks)",
         ["Shaded candles = the pattern (green / red / blue = today's break). Swing highs v, lows ^, volume below.", ""]
         + [os.path.basename(p)[:-4].replace("_", "  ") for p in files])
print(f"[info] PDF size: {os.path.getsize(pdf) / 1e6:.1f} MB")
telegram_file(pdf, f"Daily pattern charts - {len(files)} stocks")
print("::notice::PDF sent")
