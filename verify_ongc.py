"""
Cross-validate Fyers DAILY candles vs Fyers INTRADAY aggregation.
If they differ, the daily endpoint is unreliable and TradingView-style
pivots must be built from intraday data.
"""
import sys
sys.path.insert(0, '.')

import pandas as pd
from src.fyers_api import get_fyers_api
from src.pivots import calculate_traditional_pivots
from datetime import date, timedelta

today = date(2026, 9, 7)
api = get_fyers_api()

print("Fetching ONGC 5-minute candles for last 10 days...")
intra = api.get_historical_candles('NSE:ONGC-EQ', '5', today - timedelta(days=10), today)
if intra is None:
    print("   intraday API FAILED")
    sys.exit(1)
print(f"   got {len(intra)} 5-min candles")

df = pd.DataFrame(intra)
df['datetime'] = pd.to_datetime(df['datetime'])
df = df.sort_values('datetime')
df['day'] = df['datetime'].dt.date

agg = df.groupby('day').agg(
    open=('open', 'first'),
    high=('high', 'max'),
    low=('low', 'min'),
    close=('close', 'last'),
    n=('close', 'count'),
).reset_index()

print()
print("Fetching ONGC DAILY candles for same period...")
daily = api.get_historical_candles('NSE:ONGC-EQ', '1D', today - timedelta(days=10), today)
ddf = pd.DataFrame(daily)
ddf['day'] = pd.to_datetime(ddf['datetime']).dt.date

merged = pd.merge(agg, ddf, on='day', suffixes=('_intra', '_daily'))

print()
print("DAY        |  INTRADAY AGG  H    L    C    |  DAILY ENDPOINT H    L    C    | MATCH?")
print("-" * 100)
for _, r in merged.iterrows():
    match = (abs(r['high_intra'] - r['high_daily']) < 0.005 and
             abs(r['low_intra'] - r['low_daily']) < 0.005 and
             abs(r['close_intra'] - r['close_daily']) < 0.005)
    flag = "OK" if match else "*** MISMATCH ***"
    print(f"{r['day']} |  {r['high_intra']:8.2f} {r['low_intra']:6.2f} {r['close_intra']:6.2f}  "
          f"|  {r['high_daily']:8.2f} {r['low_daily']:6.2f} {r['close_daily']:6.2f}  | {flag} "
          f"(bars={r['n']})")

print()
print("=" * 100)
print("TODAY's pivots from each source:")
fri = merged[merged['day'] == date(2026, 9, 4)]
if len(fri):
    r = fri.iloc[0]
    p_intra = calculate_traditional_pivots(r['high_intra'], r['low_intra'], r['close_intra'])
    p_daily = calculate_traditional_pivots(r['high_daily'], r['low_daily'], r['close_daily'])
    print(f"  From INTRADAY-agg Friday:  P={p_intra['P']:.2f}  R1={p_intra['R1']:.2f}  S1={p_intra['S1']:.2f}")
    print(f"  From DAILY-endpoint Friday: P={p_daily['P']:.2f}  R1={p_daily['R1']:.2f}  S1={p_daily['S1']:.2f}")
print()
print("  TradingView chart labels:   P=235.66  R1=240.94  S1=230.82")
print("  (implied prev day: H=240.50 L=230.38 C=236.10 - a big-range day)")
