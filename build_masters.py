"""Download NSE equity master and build Fyers-format instrument files.

Produces:
  data/stocks/nse_all.csv  -> NSE:<SYMBOL>-EQ for every EQ-series equity
  data/stocks/bse_all.csv  -> BSE:<SYMBOL>-EQ  (dual-listed; nearly every
                               NSE equity also trades on BSE under the same
                               ticker, so we reuse the NSE master)

Run:  python build_masters.py
Refreshed by:  python main.py update-stocks
"""
import csv
import io
import sys
from pathlib import Path

import requests

OUT = Path('data/stocks')
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
NSE_URL = 'https://archives.nseindia.com/content/equities/EQUITY_L.csv'


def _normalise_key(k: str) -> str:
    """The NSE CSV headers are ' SYMBOL' / 'NAME OF COMPANY' (leading space)."""
    return k.strip()


def build_nse() -> list:
    print('Downloading NSE equity master ...', flush=True)
    r = requests.get(NSE_URL, headers=HEADERS, timeout=40)
    r.raise_for_status()
    text = r.content.decode('utf-8-sig', errors='replace')
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [_normalise_key(k) for k in reader.fieldnames]

    out = []
    seen = set()
    for row in reader:
        sym = (row.get('SYMBOL') or '').strip()
        series = (row.get('SERIES') or '').strip()
        name = (row.get('NAME OF COMPANY') or '').strip()
        if not sym or sym in seen:
            continue
        if series and series.upper() != 'EQ':
            continue            # keep only equity series (drop BE/BZ/others)
        seen.add(sym)
        out.append({'symbol': sym, 'name': name, 'fyers_symbol': f'NSE:{sym}-EQ'})

    _write_csv('nse_all.csv', out)
    print(f'  NSE EQ: {len(out)} -> data/stocks/nse_all.csv', flush=True)
    return out


def build_bse(nse_rows: list) -> int:
    """BSE master: NSE EQ list mapped to BSE:<SYMBOL>-EQ (dual-listed)."""
    print('Building BSE master from NSE list (dual-listed tickers) ...', flush=True)
    out = []
    for row in nse_rows:
        sym = row['symbol']
        out.append({
            'symbol': sym,
            'name': row['name'],
            'fyers_symbol': f'BSE:{sym}-EQ',
        })
    _write_csv('bse_all.csv', out)
    print(f'  BSE EQ: {len(out)} -> data/stocks/bse_all.csv', flush=True)
    return len(out)


def _write_csv(fname: str, rows: list) -> None:
    path = OUT / fname
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=['symbol', 'name', 'fyers_symbol'])
        w.writeheader()
        w.writerows(rows)


if __name__ == '__main__':
    OUT.mkdir(parents=True, exist_ok=True)
    nse = build_nse()
    bse = build_bse(nse)
    print(f'DONE: NSE={len(nse)} BSE={bse}', flush=True)