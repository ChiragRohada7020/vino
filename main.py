"""
NSE Stock Scanner - Main Entry Point
=====================================

Command-line interface for the NSE stock scanner.

Usage:
    python main.py scan                              # Scan today
    python main.py scan --date 2026-09-01             # Scan specific date
    python main.py scan --timeframe 5m                # Specific timeframe
    python main.py scan --timeframe all               # All timeframes
    python main.py scan --distance 0.5                # Distance threshold
    python main.py scan --mode pivot_willy            # Scan mode
    python main.py scan --verbose                     # Show prev-day OHLC + pivot tables
    python main.py pivots                            # Calculate pivots for today
    python main.py pivots --date 2026-09-01           # Pivots for specific date
    python main.py test                              # Run unit tests
"""

import argparse
import csv
import sys
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Dict, List

from src.config import (
    MAX_DISTANCE_PERCENT,
    TIMEFRAMES,
    SCAN_MODES,
    DEFAULT_SCAN_MODE,
    DISTANCE_THRESHOLDS,
    RESULTS_DIR,
)
from src.utils import setup_logging, parse_date, is_trading_day, get_previous_trading_day
from src.pivots import (
    calculate_traditional_pivots,
    get_pivot_source_ohlc,
    days_needed_for_pivot_tf,
    periods_for_pivot_tf,
    PIVOT_TIMEFRAMES,
    PIVOT_TF_LABELS,
)
from src.willy import calculate_willy
from src.scanner import run_scanner, find_nearest_pivot
from src.candles import (
    create_sample_ohlc_data,
    create_intraday_ohlc_data,
    fetch_candles_from_api,
    fetch_daily_history_chunked,
)
from src.instruments import (
    get_nifty_50_symbols, get_universe_symbols, get_fyers_symbol,
)


def fetch_live_stock_data(
    symbols: List[str],
    scan_date: date,
    timeframes: List[str],
    pivot_tf: str = 'D',
) -> Dict[str, Dict]:
    """
    Fetch live data for each symbol from Fyers:
      - previous trading day's daily OHLC  (for pivot calculation)
      - intraday candles for the scan date (per timeframe)
    Caching is handled inside fetch_candles_from_api.

    pivot_tf: 'D'|'W'|'M'|'Q'|'Y'|'all' - when not 'D', also stores
    'daily_ohlc_by_tf' with the previous COMPLETED period's H/L/C per period.
    """
    prev_day = get_previous_trading_day(scan_date)
    if prev_day is None:
        print("ERROR: could not determine previous trading day.")
        return {}

    print(f"Previous trading day (for pivots): {prev_day}")
    print(f"Pivot timeframe: {PIVOT_TF_LABELS.get(pivot_tf.upper(), pivot_tf)}\n")
    stocks_data: Dict[str, Dict] = {}

    # Widen the daily window so W/M/Q/Y periods are fully covered
    days_back = days_needed_for_pivot_tf(pivot_tf)

    for idx, symbol in enumerate(symbols, 1):
        print(f"  [{idx}/{len(symbols)}] {symbol:12s} ...", end=' ', flush=True)

        # Chunked fetch: W/M/Q/Y windows can exceed Fyers' single-request
        # history limit (code -50 beyond ~1 year); chunks are cached too.
        daily_df = fetch_daily_history_chunked(
            symbol, prev_day - timedelta(days=days_back), prev_day
        )
        if daily_df is None or daily_df.empty:
            print("skipped (no daily data)")
            continue

        last = daily_df.iloc[-1]
        info = {
            'daily_ohlc': {
                'high': float(last['high']),
                'low': float(last['low']),
                'close': float(last['close']),
            },
        }

        # Multi-period pivot sources (W/M/Q/Y) via aggregation of dailies
        if pivot_tf != 'D':
            # 'auto' -> periods implied by the scanned timeframes (D, M),
            # 'all'  -> every period, explicit -> [period]
            periods = periods_for_pivot_tf(pivot_tf, timeframes)
            by_tf: Dict[str, Dict[str, float]] = {}
            for ptf in periods:
                src = get_pivot_source_ohlc(daily_df, ptf, scan_date)
                if src:
                    by_tf[ptf] = src
            if by_tf:
                info['daily_ohlc_by_tf'] = by_tf

        ok = []
        for tf in timeframes:
            if tf == '1d':
                # Daily candles up to scan date (need 21+ for Willy)
                df = fetch_candles_from_api(
                    symbol, '1d', scan_date - timedelta(days=90), scan_date
                )
            else:
                # Continuous intraday series (TradingView-style): include the
                # last few sessions so Willy(21)/EMA(13) are fully warmed up.
                # 4h candles: 7 days yields only ~8 candles (<21), so use 30
                # days (~47 candles) to satisfy the Willy lookback.
                lookback_days = 30 if tf == '4h' else 7
                df = fetch_candles_from_api(
                    symbol, tf, scan_date - timedelta(days=lookback_days), scan_date
                )
            info[f'candles_{tf}'] = df
            if df is not None and not df.empty:
                ok.append(tf)

        stocks_data[symbol] = info
        print(f"ok ({', '.join(ok) if ok else 'no intraday'})")

    return stocks_data


def fetch_sample_stock_data(
    symbols: List[str],
    scan_date: date,
    timeframes: List[str],
    pivot_tf: str = 'D',
) -> Dict[str, Dict]:
    """Generate sample data (Phase 1 fallback / offline testing)."""
    stocks_data: Dict[str, Dict] = {}
    for symbol in symbols:
        daily_df = create_sample_ohlc_data(symbol=symbol, periods=80)
        if len(daily_df) > 0:
            last_daily = daily_df.iloc[-1]
            daily_ohlc = {
                'high': last_daily['high'],
                'low': last_daily['low'],
                'close': last_daily['close'],
            }
        else:
            daily_ohlc = {}

        info: Dict[str, Dict] = {'daily_ohlc': daily_ohlc}

        if pivot_tf != 'D' and len(daily_df) > 0:
            periods = periods_for_pivot_tf(pivot_tf, timeframes)
            by_tf: Dict[str, Dict[str, float]] = {}
            for ptf in periods:
                src = get_pivot_source_ohlc(daily_df, ptf, scan_date)
                if src:
                    by_tf[ptf] = src
            if by_tf:
                info['daily_ohlc_by_tf'] = by_tf

        stocks_data[symbol] = info

        minutes_map = {'5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440}
        for tf in timeframes:
            stocks_data[symbol][f'candles_{tf}'] = create_intraday_ohlc_data(
                symbol=symbol,
                trading_date=scan_date,
                timeframe_minutes=minutes_map.get(tf, 5),
            )
    return stocks_data


def save_results_csv(results, scan_date: date) -> str:
    """Save scan results to results/CSV and return the file path."""
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{scan_date.isoformat()}_scanner_results.csv"
    if not results:
        path.write_text('', encoding='utf-8')
        return str(path)
    fieldnames = list(asdict(results[0]).keys())
    with open(path, 'w', newline='', encoding='utf-8') as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            writer.writerow(asdict(r))
    return str(path)


def timeframe_minutes_map(timeframes: List[str]) -> List[int]:
    """Convert timeframe strings to minutes."""
    mapping = {
        '5m': 5,
        '15m': 15,
        '30m': 30,
        '1h': 60,
        '4h': 240,
        '1d': 1440
    }
    return [mapping.get(tf, 5) for tf in timeframes]


def print_verbose_stock_details(stocks_data: Dict[str, Dict]) -> None:
    """
    Verbose diagnostics: for every scanned stock, print the previous
    trading day's OHLC used for pivots and the full pivot level table.

    The values printed here come from the exact same `daily_ohlc` that
    scan_stock_for_date() uses internally, so they match the scan
    results 1:1 and can be cross-checked against TradingView.
    """
    print(f"\n{'='*70}")
    print("VERBOSE: source-period OHLC + full pivot table (per stock)")
    print(f"{'='*70}")
    for symbol, info in stocks_data.items():
        by_tf = info.get('daily_ohlc_by_tf') or {}
        # When multi-period data exists, print a table per period (D/W/M/Q/Y)
        sources = ([(ptf, ohlc) for ptf, ohlc in by_tf.items()]
                   if by_tf else [('D', info.get('daily_ohlc') or {})])
        for ptf, ohlc in sources:
            if not ohlc:
                print(f"\n{symbol}: no daily OHLC available")
                continue
            try:
                pivots = calculate_traditional_pivots(
                    high=float(ohlc['high']),
                    low=float(ohlc['low']),
                    close=float(ohlc['close'])
                )
            except (ValueError, KeyError) as e:
                print(f"\n{symbol}: pivot calculation failed ({e})")
                continue
            period_end = ohlc.get('period_end')
            period_note = f"  (period ended {period_end})" if period_end else ""
            print(f"\n{symbol} [{ptf}]   src: H={ohlc['high']:>9.2f}  "
                  f"L={ohlc['low']:>9.2f}  C={ohlc['close']:>9.2f}{period_note}")
            print(f"    R5={pivots['R5']:>9.2f}  R4={pivots['R4']:>9.2f}  "
                  f"R3={pivots['R3']:>9.2f}  R2={pivots['R2']:>9.2f}  R1={pivots['R1']:>9.2f}")
            print(f"    P ={pivots['P']:>9.2f}")
            print(f"    S1={pivots['S1']:>9.2f}  S2={pivots['S2']:>9.2f}  "
                  f"S3={pivots['S3']:>9.2f}  S4={pivots['S4']:>9.2f}  S5={pivots['S5']:>9.2f}")
    print()


def cmd_scan(args):
    """Run the stock scanner."""
    logger = setup_logging()

    # Parse date
    scan_date = date.today()
    if args.date:
        scan_date = parse_date(args.date)

    # Validate date
    if not is_trading_day(scan_date):
        print(f"Warning: {scan_date} is not a trading day. Results may be limited.")

    # Get parameters
    timeframes = TIMEFRAMES if args.timeframe == 'all' else [args.timeframe]
    distance = args.distance if args.distance else MAX_DISTANCE_PERCENT
    mode = args.mode if args.mode else DEFAULT_SCAN_MODE
    pivot_tf = (getattr(args, 'pivot_tf', 'D') or 'D').lower()
    if pivot_tf != 'all':
        pivot_tf = pivot_tf.upper()

    print(f"\n{'='*60}")
    print(f"NSE STOCK SCANNER")
    print(f"{'='*60}")
    print(f"Scan Date: {scan_date}")
    print(f"Timeframes: {', '.join(timeframes)}")
    print(f"Pivot Timeframe: {PIVOT_TF_LABELS.get(pivot_tf, pivot_tf)}")
    print(f"Distance Threshold: {distance}%")
    print(f"Scan Mode: {mode}")
    print(f"{'='*60}\n")

    # Fetch data: live from Fyers (default) or generated sample data
    universe = getattr(args, 'universe', 'nifty50')
    symbols = get_universe_symbols(universe)
    if getattr(args, 'symbols', None):
        symbols = [s.strip().upper() for s in args.symbols.split(',') if s.strip()]
    if getattr(args, 'limit', None):
        symbols = symbols[:args.limit]

    if getattr(args, 'sample', False):
        print("DATA SOURCE: sample (offline) data\n")
        stocks_data = fetch_sample_stock_data(symbols, scan_date, timeframes, pivot_tf)
    else:
        print("DATA SOURCE: Fyers API (live)\n")
        stocks_data = fetch_live_stock_data(symbols, scan_date, timeframes, pivot_tf)
        if not stocks_data:
            print("\nLive data unavailable - falling back to sample data.\n")
            stocks_data = fetch_sample_stock_data(symbols, scan_date, timeframes, pivot_tf)

    # Verbose mode: show previous-day OHLC + full pivot table for every stock
    if getattr(args, 'verbose', False):
        print_verbose_stock_details(stocks_data)

    results = run_scanner(
        stocks_data=stocks_data,
        scan_date=scan_date,
        timeframes=timeframes,
        max_distance_percent=distance,
        scan_mode=mode,
        pivot_tf=pivot_tf
    )

    if results:
        verbose = getattr(args, 'verbose', False)
        show_ptf = pivot_tf == 'all' or any(
            getattr(r, 'pivot_tf', 'D') != 'D' for r in results
        )
        ptf_hdr = 'PIVOT_TF  ' if verbose else 'PTF  '
        print(f"\nFound {len(results)} stocks near pivot levels:\n")
        if verbose:
            # Extended table: full Willy details + last candle time
            ptf_part = ptf_hdr if show_ptf else ''
            print(f"{'STOCK':<12} {'TF':<5} {ptf_part}{'PRICE':>10} {'PIVOT':<6} {'PIVOT_PRICE':>12} "
                  f"{'DIST':>8} {'DIST%':>8} {'WILLY':>8} {'WILLY_EMA':>10} {'ZONE':<11} "
                  f"{'SIGNAL':<15} {'LAST_CANDLE':<17}")
            print("-" * 165)
        else:
            ptf_part = ptf_hdr if show_ptf else ''
            print(f"{'STOCK':<12} {'TF':<5} {ptf_part}{'PRICE':>10} {'PIVOT':<6} {'PIVOT_PRICE':>12} {'DIST%':>8} {'WILLY':>8} {'SIGNAL':<15}")
            print("-" * 100)
        for r in results[:20]:
            willy_str = f"{r.willy:.2f}" if r.willy is not None else "N/A"
            signal_str = r.willy_signal if r.willy_signal else "N/A"
            ptf_col = f"{getattr(r, 'pivot_tf', 'D'):<9} " if verbose else f"{getattr(r, 'pivot_tf', 'D'):<4} "
            ptf_col = ptf_col if show_ptf else ''
            if verbose:
                ema_str = f"{r.willy_ema:.2f}" if r.willy_ema is not None else "N/A"
                zone_str = r.willy_zone if r.willy_zone else "N/A"
                lct = str(r.last_candle_time) if r.last_candle_time else "N/A"
                print(f"{r.stock:<12} {r.timeframe:<5} {ptf_col}{r.current_price:>10.2f} {r.nearest_pivot:<6} "
                      f"{r.pivot_price:>12.2f} {r.distance:>8.2f} {r.distance_percent:>7.3f}% "
                      f"{willy_str:>8} {ema_str:>10} {zone_str:<11} {signal_str:<15} {lct:<17}")
            else:
                print(f"{r.stock:<12} {r.timeframe:<5} {ptf_col}{r.current_price:>10.2f} {r.nearest_pivot:<6} "
                      f"{r.pivot_price:>12.2f} {r.distance_percent:>7.3f}% {willy_str:>8} {signal_str:<15}")

        csv_path = save_results_csv(results, scan_date)
        print(f"\nResults saved to: {csv_path}")
    else:
        print("\nNo stocks found near pivot levels with current settings.")


def cmd_pivots(args):
    """Calculate and display pivot levels."""
    logger = setup_logging()

    calc_date = date.today()
    if args.date:
        calc_date = parse_date(args.date)

    print(f"\n{'='*60}")
    print(f"PIVOT POINTS CALCULATOR")
    print(f"{'='*60}")
    print(f"Calculation Date: {calc_date}")
    print(f"{'='*60}\n")

    symbols = get_nifty_50_symbols()[:5]
    prev_day = get_previous_trading_day(calc_date)

    if not getattr(args, 'sample', False) and prev_day:
        print(f"Previous trading day: {prev_day}")
        print("DATA SOURCE: Fyers API (live)\n")
        for symbol in symbols:
            daily_df = fetch_candles_from_api(
                symbol, '1d', prev_day - timedelta(days=15), prev_day
            )
            if daily_df is None or daily_df.empty:
                print(f"\n{symbol}: no daily data from API, skipped")
                continue
            last = daily_df.iloc[-1]
            try:
                pivots = calculate_traditional_pivots(
                    high=float(last['high']),
                    low=float(last['low']),
                    close=float(last['close'])
                )
                print(f"\n{symbol} (H={last['high']:.2f}, L={last['low']:.2f}, C={last['close']:.2f})")
                print(f"  P:  {pivots['P']:.2f}")
                print(f"  R1: {pivots['R1']:.2f}  |  S1: {pivots['S1']:.2f}")
                print(f"  R2: {pivots['R2']:.2f}  |  S2: {pivots['S2']:.2f}")
                print(f"  R3: {pivots['R3']:.2f}  |  S3: {pivots['S3']:.2f}")
                print(f"  R4: {pivots['R4']:.2f}  |  S4: {pivots['S4']:.2f}")
                print(f"  R5: {pivots['R5']:.2f}  |  S5: {pivots['S5']:.2f}")
            except ValueError as e:
                print(f"\n{symbol}: Error calculating pivots - {e}")
        return

    print("DATA SOURCE: sample (offline) data\n")
    for symbol in symbols:
        daily_df = create_sample_ohlc_data(symbol=symbol, periods=30)
        if len(daily_df) > 0:
            last = daily_df.iloc[-1]
            try:
                pivots = calculate_traditional_pivots(
                    high=last['high'],
                    low=last['low'],
                    close=last['close']
                )
                print(f"\n{symbol} (H={last['high']:.2f}, L={last['low']:.2f}, C={last['close']:.2f})")
                print(f"  P:  {pivots['P']:.2f}")
                print(f"  R1: {pivots['R1']:.2f}  |  S1: {pivots['S1']:.2f}")
                print(f"  R2: {pivots['R2']:.2f}  |  S2: {pivots['S2']:.2f}")
                print(f"  R3: {pivots['R3']:.2f}  |  S3: {pivots['S3']:.2f}")
                print(f"  R4: {pivots['R4']:.2f}  |  S4: {pivots['S4']:.2f}")
                print(f"  R5: {pivots['R5']:.2f}  |  S5: {pivots['S5']:.2f}")
            except ValueError as e:
                print(f"\n{symbol}: Error calculating pivots - {e}")


def cmd_update_stocks(args):
    """Download the latest NSE/BSE equity masters into data/stocks/."""
    print(f"\n{'='*60}")
    print('UPDATE STOCK UNIVERSE (NSE + BSE)')
    print(f"{'='*60}\n")
    print('Downloading NSE equity master from nseindia.com ...')
    try:
        import build_masters
        nse = build_masters.build_nse()
        bse = build_masters.build_bse(nse)
        print(f"\nDone: {len(nse)} NSE stocks + {bse} BSE stocks saved")
        print('Universes now available: nifty50, nifty100, allnse, allbse, custom')
    except Exception as e:  # noqa: BLE001
        print(f'ERROR updating stock masters: {e}')


def cmd_test(args):
    """Run unit tests."""
    import subprocess
    result = subprocess.run(
        [sys.executable, '-m', 'pytest', 'tests/', '-v'],
        cwd=__file__.rsplit('/', 1)[0]
    )
    sys.exit(result.returncode)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='NSE Stock Scanner - Find stocks near pivot points',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py scan
  python main.py scan --date 2026-09-01
  python main.py scan --timeframe 5m --distance 0.5
  python main.py scan --mode pivot_willy
  python main.py scan --symbols SBIN,TCS --verbose
  python main.py pivots --date 2026-09-01
  python main.py test
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    scan_parser = subparsers.add_parser('scan', help='Run stock scanner')
    scan_parser.add_argument('--date', type=str, help='Scan date (YYYY-MM-DD)')
    scan_parser.add_argument('--timeframe', type=str, default='5m',
                            choices=['5m', '15m', '30m', '1h', '4h', '1d', 'all'],
                            help='Timeframe to scan')
    scan_parser.add_argument('--distance', type=float, help='Distance threshold %%')
    scan_parser.add_argument('--mode', type=str, default=DEFAULT_SCAN_MODE,
                            choices=SCAN_MODES, help='Scan mode')
    scan_parser.add_argument('--pivot-tf', dest='pivot_tf', type=str, default='auto',
                            choices=['auto', 'D', 'W', 'M', 'Q', 'Y', 'all'],
                            help='Pivot period: auto=TradingView style (intraday '
                                 'charts->Daily, 1d chart->Monthly), D=day, W=week, '
                                 'M=month, Q=quarter, Y=year, all=scan every period')
    scan_parser.add_argument('--universe', type=str, default='nifty50',
                            choices=['nifty50', 'nifty100', 'allnse', 'allbse',
                                     'custom'],
                            help='Stock universe: nifty50, nifty100, allnse '
                                 '(every NSE EQ stock), allbse (BSE dual-listed), '
                                 'or custom (data/stocks/custom.csv)')
    scan_parser.add_argument('--limit', type=int,
                             help='Limit number of stocks to scan (default: all in universe)')
    scan_parser.add_argument('--symbols', type=str,
                             help='Comma-separated stock symbols, e.g. SBIN,TCS,RELIANCE')
    scan_parser.add_argument('--sample', action='store_true',
                             help='Use generated sample data instead of live Fyers data')
    scan_parser.add_argument('--verbose', '-v', action='store_true',
                             help='Show previous-day OHLC + full pivot table per stock')

    pivots_parser = subparsers.add_parser('pivots', help='Calculate pivot points')
    pivots_parser.add_argument('--date', type=str, help='Date (YYYY-MM-DD)')
    pivots_parser.add_argument('--sample', action='store_true',
                               help='Use generated sample data instead of live Fyers data')

    subparsers.add_parser('test', help='Run unit tests')
    subparsers.add_parser('update-stocks',
                          help='Download latest NSE/BSE equity masters')

    args = parser.parse_args()

    if args.command == 'scan':
        cmd_scan(args)
    elif args.command == 'pivots':
        cmd_pivots(args)
    elif args.command == 'test':
        cmd_test(args)
    elif args.command == 'update-stocks':
        cmd_update_stocks(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
