"""
Diagnose ONGC 1D TradingView pivot labels - EXTENDED search.

Labels seen on the user's TradingView 1D chart:
    R5 (265.29), R4 (260.22), R3 (255.15), R2 (250.07), R1 (240.94)
Earlier 15m chart also showed:
    P (235.66), S1 (230.82), S2 (233.90)

Strategy: the last-20-session search found NO source for R2-R5, so search:
1. ~180 days of DAILY candles (both R4/R5 conventions)
2. WEEKLY aggregated candles
3. MONTHLY aggregated candles
Whichever source reproduces the labels exactly identifies both the origin
candle AND TradingView's true R4/R5 extension convention.
"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from src.fyers_api import get_fyers_api

LABELS = {
    'R1': 240.94, 'R2': 250.07, 'R3': 255.15, 'R4': 260.22, 'R5': 265.29,
    'P': 235.66, 'S1': 230.82, 'S2': 233.90,
}


def pivots(h, l, c, convention):
    p = (h + l + c) / 3
    x = h - l
    out = {
        'P': p,
        'R1': 2 * p - l, 'S1': 2 * p - h,
        'R2': p + x, 'S2': p - x,
        'R3': h + 2 * (p - l), 'S3': l - 2 * (h - p),
    }
    if convention == 'ladder':
        out['R4'] = out['R3'] + x
        out['R5'] = out['R4'] + x
        out['S4'] = out['S3'] - x
        out['S5'] = out['S4'] - x
    else:  # tv-ext
        out['R4'] = out['R3'] + (out['R2'] - out['R1'])   # = R3 + (H-P)
        out['R5'] = out['R4'] + (out['R2'] - out['R1'])
        out['S4'] = out['S3'] - (out['S1'] - out['S2'])   # = S3 - (P-L)
        out['S5'] = out['S4'] - (out['S1'] - out['S2'])
    return out


def match(candles, source_name, used_on_map=None):
    """Find which candles reproduce chart labels under which convention."""
    hits_found = 0
    for i in range(len(candles) - 1):
        d, o, h, l, c = candles[i]
        used_on = candles[i + 1][0] if used_on_map is None else used_on_map[i]
        for conv in ('ladder', 'tv-ext'):
            pv = pivots(h, l, c, conv)
            hits = [f"{name}={pv[name]:.2f}" for name, val in LABELS.items()
                    if abs(pv[name] - val) < 0.02]
            if hits:
                hits_found += len(hits)
                print(f"  [{source_name}] candle {d} (H={h:.2f} L={l:.2f} C={c:.2f}) "
                      f"[{conv:7s}] -> during {used_on}: {', '.join(hits)}")
    return hits_found


api = get_fyers_api()
end = pd.Timestamp.today().date()
rows = api.get_historical_candles('NSE:ONGC-EQ', '1D', end - pd.Timedelta(days=190), end)
if rows is None:
    print("API failed")
    sys.exit(1)

daily = []
for r in rows:
    d = pd.to_datetime(r['datetime']).date()
    daily.append((d, float(r['open']), float(r['high']), float(r['low']), float(r['close'])))

df = pd.DataFrame(daily, columns=['day', 'open', 'high', 'low', 'close'])
df['day'] = pd.to_datetime(df['day'])
df = df.sort_values('day').reset_index(drop=True)

print(f"Fetched {len(daily)} daily candles: {daily[0][0]} .. {daily[-1][0]}")
print("\n=== 1) DAILY candle search ===")
n = match(daily, 'daily')

# Weekly aggregation (ISO week)
df['week'] = df['day'].dt.isocalendar().week.astype(int)
df['year'] = df['day'].dt.year
weekly = []
for (y, w), g in df.groupby(['year', 'week']):
    g = g.sort_values('day')
    weekly.append((g['day'].iloc[-1].date(), float(g['open'].iloc[0]),
                   float(g['high'].max()), float(g['low'].min()),
                   float(g['close'].iloc[-1])))
weekly.sort(key=lambda t: t[0])

print("\n=== 2) WEEKLY candle search ===")
n += match(weekly, 'weekly')

# Monthly aggregation
df['month'] = df['day'].dt.to_period('M')
monthly = []
for m, g in df.groupby('month'):
    g = g.sort_values('day')
    monthly.append((g['day'].iloc[-1].date(), float(g['open'].iloc[0]),
                    float(g['high'].max()), float(g['low'].min()),
                    float(g['close'].iloc[-1])))
monthly.sort(key=lambda t: t[0])

print("\n=== 3) MONTHLY candle search ===")
n += match(monthly, 'monthly')

print("\nWeekly candles (for reference):")
print(f"{'WEEK END':<12}{'HIGH':>9}{'LOW':>9}{'CLOSE':>9}")
for d, o, h, l, c in weekly[-10:]:
    print(f"{str(d):<12}{h:>9.2f}{l:>9.2f}{c:>9.2f}")
print("\nMonthly candles (for reference):")
for d, o, h, l, c in monthly:
    print(f"{str(d):<12}{h:>9.2f}{l:>9.2f}{c:>9.2f}")

if n == 0:
    print("\nNo exact source found even in 190 days - labels may be from an even older set.")
