"""
Trading Sim price fetcher - runs on GitHub Actions, where Yahoo Finance isn't blocked.

1. Reads the list of symbols the sim needs from the server (feed/symbols.json).
2. Downloads daily closes and dividends with yfinance.
3. Writes output/prices.json, which the workflow uploads to the server over FTP.

Today's bar is left out until 20 minutes after the 4:00 pm Eastern close,
so the sim never mistakes a live intraday price for a closing price.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import yfinance as yf

FEED_URL = os.environ.get(
    "SIM_SYMBOLS_URL",
    "https://pacificlogo.ca/sandbox/index-fund-forecaster/feed/symbols.json",
)
DEFAULT_SYMBOLS = ["CAD=X", "XEQT.TO", "VEQT.TO", "ZAG.TO", "XIC.TO", "VFV.TO", "VOO",
                   "CASH.TO", "XEF.TO", "XEC.TO", "QQQ"]
OUT = os.path.join(os.path.dirname(__file__), "output", "prices.json")


def wanted():
    try:
        req = urllib.request.Request(FEED_URL, headers={"User-Agent": "trading-sim-fetcher"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.load(r)
        syms = [s for s in data.get("symbols", []) if isinstance(s, str) and s.strip()]
        start = data.get("from") or "2018-11-01"
        print(f"Server wants {len(syms)} symbols from {start}")
        return sorted(set(syms) | {"CAD=X"}), start
    except Exception as e:  # server unreachable: fall back to the starter list
        print(f"Couldn't read {FEED_URL} ({e}); using default list")
        return DEFAULT_SYMBOLS, "2018-11-01"


def main():
    symbols, start = wanted()
    et = datetime.now(ZoneInfo("America/Toronto"))
    today = et.strftime("%Y-%m-%d")
    closed = et.weekday() >= 5 or (et.hour, et.minute) >= (16, 20)
    out = {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "from": start,
           "symbols": {}, "errors": {}}

    for s in symbols:
        for attempt in range(3):
            try:
                t = yf.Ticker(s)
                h = t.history(start=start, interval="1d", auto_adjust=False, actions=True)
                if h is None or h.empty:
                    raise ValueError("no data returned (check the symbol)")
                meta = getattr(t, "history_metadata", None) or {}
                closes, divs = {}, {}
                for idx, row in h.iterrows():
                    d = idx.strftime("%Y-%m-%d")
                    if d == today and not closed:
                        continue
                    c = row.get("Close")
                    if c is not None and c == c and c > 0:  # c == c filters NaN
                        closes[d] = round(float(c), 6)
                    dv = row.get("Dividends", 0) or 0
                    if dv and dv == dv and dv > 0:
                        divs[d] = round(float(dv), 6)
                if not closes:
                    raise ValueError("no closing prices")
                out["symbols"][s] = {
                    "currency": (meta.get("currency") or ("CAD" if s.endswith(".TO") or s == "CAD=X" else "USD")).upper(),
                    "name": meta.get("longName") or meta.get("shortName"),
                    "closes": closes,
                    "divs": divs,
                }
                print(f"  {s}: {len(closes)} closes, {len(divs)} dividends, last {max(closes)}")
                break
            except Exception as e:
                if attempt == 2:
                    out["errors"][s] = str(e)[:200]
                    print(f"  {s}: FAILED - {e}")
                else:
                    time.sleep(5 * (attempt + 1))
        time.sleep(0.5)

    # CAD=X is quoted as CAD per USD, which is what the sim expects
    if "CAD=X" in out["symbols"]:
        out["symbols"]["CAD=X"]["currency"] = "CAD"

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Wrote {OUT}: {len(out['symbols'])} ok, {len(out['errors'])} failed")
    if not out["symbols"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
