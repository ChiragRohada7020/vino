"""
NSE Stock Scanner - Streamlit Dashboard
=======================================

Interactive web interface for the pivot-point + Willy scanner.

Run:
    streamlit run dashboard.py

Features:
    - Pick ANY scan date, timeframe, distance threshold and scan mode
    - Live Fyers data (file-cached) or offline sample data
    - Ranked table: stocks nearest to Traditional Pivot levels
    - Instant post-scan filters (zone / signal / pivot side / symbol search)
      -- filter changes re-use already-fetched data (no new API calls)
    - Per-stock pivot inspector with Willy chart
    - CSV download
"""

import csv
import io
from dataclasses import asdict
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from src.candles import fetch_candles_from_api, fetch_daily_history_chunked
from src.config import DEFAULT_SCAN_MODE, MAX_DISTANCE_PERCENT, SCAN_MODES
from src.instruments import get_nifty_50_symbols, get_universe_symbols, get_stock_instrument
from src.pivots import (
    calculate_traditional_pivots,
    get_pivot_levels_list,
    get_pivot_source_ohlc,
    days_needed_for_pivot_tf,
    periods_for_pivot_tf,
    resolve_pivot_tf,
    PIVOT_TIMEFRAMES,
    PIVOT_TF_LABELS,
)
from src.scanner import run_scanner
from src.utils import get_previous_trading_day, is_trading_day
from src.willy import calculate_willy, detect_willy_zone, detect_willy_signal

from main import fetch_sample_stock_data, save_results_csv  # reuse existing orchestration

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

ALL_TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1d']

TIMEFRAME_LABELS = {
    '5m': '5 min', '15m': '15 min', '30m': '30 min',
    '1h': '1 hour', '4h': '4 hours', '1d': '1 day', 'ALL': 'ALL (5m to 1D)',
}

SIGNAL_EMOJI = {
    'Bullish Cross': '🔺 Bullish Cross',
    'Bearish Cross': '🔻 Bearish Cross',
}
ZONE_EMOJI = {
    'Overbought': '🔥 Overbought',
    'Oversold': '❄️ Oversold',
    'Neutral': '⚪ Neutral',
}


# ----------------------------------------------------------------------------
# Data fetching (mirrors main.fetch_live_stock_data, with progress callback)
# ----------------------------------------------------------------------------

@st.cache_data(ttl=300, show_spinner=False, hash_funcs={date: lambda d: d.isoformat()})
def fetch_live_data_cached(
    symbols_tuple: tuple,
    scan_date: date,
    timeframes_tuple: tuple,
    pivot_tf: str = 'D',
    use_cache: bool = True,
) -> Tuple[Dict[str, Dict], Optional[date]]:
    """Cached wrapper — converts lists to tuples for hashability."""
    return _fetch_live_data_impl(
        list(symbols_tuple), scan_date, list(timeframes_tuple),
        pivot_tf, use_cache=use_cache,
    )


def _fetch_live_data_impl(
    symbols: List[str],
    scan_date: date,
    timeframes: List[str],
    pivot_tf: str = 'D',
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    use_cache: bool = True,
) -> Tuple[Dict[str, Dict], Optional[date]]:
    """
    Fetch previous-trading-day daily OHLC + per-timeframe candles for symbols.

    Same windows as main.fetch_live_stock_data:
      - daily pivots source : prev_day - N days .. prev_day
        (N widens for W/M/Q/Y pivot periods; 'all' -> 560 days)
      - intraday series     : scan_date - 7 days .. scan_date (Willy warm-up)
      - daily series        : scan_date - 90 days .. scan_date (Willy warm-up)

    pivot_tf: 'D'|'W'|'M'|'Q'|'Y'|'all' - when not 'D', stores
    'daily_ohlc_by_tf' with the previous COMPLETED period's H/L/C per period.

    use_cache: False bypasses the JSON cache for a real-time snapshot
    (today's data is otherwise cached for 5 minutes; past days forever).

    Returns (stocks_data, prev_day). stocks_data is {} when no data at all.
    """
    prev_day = get_previous_trading_day(scan_date)
    if prev_day is None:
        return {}, None

    stocks_data: Dict[str, Dict] = {}
    total = len(symbols)
    days_back = days_needed_for_pivot_tf(pivot_tf)

    for idx, symbol in enumerate(symbols, 1):
        if progress_callback:
            progress_callback(idx, total, symbol)

        # Chunked fetch: W/M/Q/Y windows can exceed Fyers' single-request
        # history limit (code -50 beyond ~1 year); chunks are cached too.
        daily_df = fetch_daily_history_chunked(
            symbol, prev_day - timedelta(days=days_back), prev_day,
            use_cache=use_cache,
        )
        if daily_df is None or daily_df.empty:
            continue  # skip stock entirely (same policy as CLI)

        last = daily_df.iloc[-1]
        info: Dict = {
            'daily_ohlc': {
                'high': float(last['high']),
                'low': float(last['low']),
                'close': float(last['close']),
            },
        }

        if pivot_tf != 'D':
            periods = periods_for_pivot_tf(pivot_tf, timeframes)
            by_tf: Dict[str, Dict[str, float]] = {}
            for ptf in periods:
                src = get_pivot_source_ohlc(daily_df, ptf, scan_date)
                if src:
                    by_tf[ptf] = src
            if by_tf:
                info['daily_ohlc_by_tf'] = by_tf

        for tf in timeframes:
            if tf == '1d':
                df = fetch_candles_from_api(
                    symbol, '1d', scan_date - timedelta(days=90), scan_date,
                    use_cache=use_cache,
                )
            else:
                # 4h needs a longer lookback for Willy(21) warm-up (~47 candles)
                lookback_days = 30 if tf == '4h' else 7
                df = fetch_candles_from_api(
                    symbol, tf, scan_date - timedelta(days=lookback_days),
                    scan_date, use_cache=use_cache,
                )
            info[f'candles_{tf}'] = df

        stocks_data[symbol] = info

    return stocks_data, prev_day


# ----------------------------------------------------------------------------
# Result formatting / filtering (pure pandas - testable without Streamlit)
# ----------------------------------------------------------------------------

def build_results_df(results: List) -> pd.DataFrame:
    """Convert List[ScanResult] to the display DataFrame (MAIN OUTPUT spec)."""
    rows = []
    for r in results:
        d = asdict(r)
        lc = d.get('last_candle_time')
        try:
            lc_disp = pd.to_datetime(lc).strftime('%Y-%m-%d %H:%M') if lc else ''
        except (TypeError, ValueError):
            lc_disp = str(lc or '')
        signal = d.get('willy_signal') or ''
        zone = d.get('willy_zone') or ''
        rows.append({
            'STOCK': d['stock'],
            'TF': d['timeframe'],
            'P-TF': d.get('pivot_tf', 'D'),
            'PRICE': d['current_price'],
            'NEAREST_PIVOT': d['nearest_pivot'],
            'PIVOT_PRICE': d['pivot_price'],
            'DIST': d['distance'],
            'DIST%': d['distance_percent'],
            'WILLY': d.get('willy'),
            'WILLY_EMA': d.get('willy_ema'),
            'ZONE': ZONE_EMOJI.get(zone, zone),
            'SIGNAL': SIGNAL_EMOJI.get(signal, signal),
            'LAST_CANDLE': lc_disp,
        })
    return pd.DataFrame(rows)


def filter_results_df(
    df: pd.DataFrame,
    symbol_search: str = '',
    zones: Optional[List[str]] = None,
    signal_choice: str = 'All',
    sides: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Apply instant post-scan filters (no data re-fetch).

    sides: list containing any of 'Supports', 'Resistances', 'Pivot (P)'.
    """
    if df.empty:
        return df

    out = df

    if symbol_search:
        needle = symbol_search.strip().upper()
        out = out[out['STOCK'].str.contains(needle, na=False)]

    if zones:
        # ZONE column contains emoji-decorated labels; match on substring
        out = out[out['ZONE'].apply(
            lambda z: any(zn.lower() in str(z).lower() for zn in zones)
        )]

    if signal_choice == 'Bullish Cross only':
        out = out[out['SIGNAL'].str.contains('Bullish', na=False)]
    elif signal_choice == 'Bearish Cross only':
        out = out[out['SIGNAL'].str.contains('Bearish', na=False)]
    elif signal_choice == 'Any cross':
        out = out[out['SIGNAL'].str.contains('Cross', na=False)]

    if sides and len(sides) < 3:
        allowed = set()
        if 'Supports' in sides:
            allowed |= {f'S{i}' for i in range(1, 6)}
        if 'Resistances' in sides:
            allowed |= {f'R{i}' for i in range(1, 6)}
        if 'Pivot (P)' in sides:
            allowed.add('P')
        out = out[out['NEAREST_PIVOT'].isin(allowed)]

    return out


def results_to_csv_bytes(results: List) -> bytes:
    """Serialize raw ScanResults (no emoji decoration) to CSV bytes."""
    if not results:
        return b''
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(asdict(results[0]).keys()))
    writer.writeheader()
    for r in results:
        writer.writerow(asdict(r))
    return buf.getvalue().encode('utf-8')


# ----------------------------------------------------------------------------
# Pivot inspector helpers (pure pandas)
# ----------------------------------------------------------------------------

def build_pivot_table(daily_ohlc: Dict[str, float], ref_price: float) -> pd.DataFrame:
    """Full P/R1-R5/S1-S5 table with distance from ref_price for one stock."""
    pivots = calculate_traditional_pivots(
        high=float(daily_ohlc['high']),
        low=float(daily_ohlc['low']),
        close=float(daily_ohlc['close']),
    )
    rows = []
    for level in get_pivot_levels_list():          # R5..P..S5 ordered
        price = pivots[level]
        side = ('Resistance' if level.startswith('R')
                else 'Support' if level.startswith('S') else 'Pivot')
        rows.append({
            'LEVEL': level,
            'SIDE': side,
            'PRICE': round(price, 2),
            'DIST': round(abs(ref_price - price), 2),
            'DIST%': round(abs(ref_price - price) / price * 100, 3) if price else None,
        })
    return pd.DataFrame(rows)


def willy_summary(df: pd.DataFrame, length: int = 21, ema_length: int = 13) -> Dict:
    """Latest Willy / EMA / zone / signal for one stock-timeframe."""
    if df is None or len(df) < length:
        return {}
    w = calculate_willy(df, length, ema_length)
    cur_w, cur_e = w['willy'].iloc[-1], w['willy_ema'].iloc[-1]
    prev_w, prev_e = w['willy'].iloc[-2], w['willy_ema'].iloc[-2]
    return {
        'df': w,
        'willy': round(float(cur_w), 2),
        'willy_ema': round(float(cur_e), 2),
        'zone': detect_willy_zone(cur_w),
        'signal': detect_willy_signal(cur_w, cur_e, prev_w, prev_e),
    }


# ----------------------------------------------------------------------------
# Streamlit UI
# ----------------------------------------------------------------------------

st.set_page_config(
    page_title='NSE Pivot Scanner',
    page_icon='🎯',
    layout='wide',
)


@st.cache_data(ttl=600, show_spinner=False)
def cached_universe(universe: str = 'nifty50') -> List[str]:
    return get_universe_symbols(universe)


def run() -> None:
    st.title('🎯 NSE Pivot Point Scanner')
    st.caption('Stocks near Traditional Pivot levels · Willy(21) / EMA(13) · Fyers data')

    # ------------------------------ sidebar ------------------------------
    with st.sidebar:
        st.header('⚙️ Scan Settings')

        universe_options_meta = [
            ('Nifty 50', 'nifty50', 'Index constituents (Nifty 50)'),
            ('Nifty 100', 'nifty100', 'Nifty 50 + 50 more major stocks'),
            ('ALL NSE', 'allnse', 'Every NSE equity stock (~2300)'),
            ('ALL BSE', 'allbse', 'BSE dual-listed tickers (~2300)'),
            ('Custom (CSV)', 'custom', 'data/stocks/custom.csv'),
        ]
        # cache() ensures get_universe_symbols runs AFTER our nifty100/allnse
        universe_index = st.selectbox(
            'Universe',
            range(len(universe_options_meta)),
            format_func=lambda i: universe_options_meta[i][0],
            help='\n'.join(f'{n}: {d}' for n, _, d in universe_options_meta),
        )
        universe_name, universe_key, _ = universe_options_meta[universe_index]
        universe = cached_universe(universe_key)
        universe_options = [f'{universe_name} (all)'] + universe
        universe_sel = st.selectbox('or pick one stock', universe_options, index=0)

        max_date = date.today()
        scan_date = st.date_input(
            'Scan date',
            value=max_date,
            min_value=max_date - timedelta(days=365),
            max_value=max_date,
            help='Scanner uses the previous trading day for pivots '
                 '(weekends/holidays handled automatically).',
        )

        tf_choice = st.selectbox(
            'Timeframe',
            ALL_TIMEFRAMES + ['ALL'],
            format_func=lambda t: TIMEFRAME_LABELS.get(t, t),
        )
        timeframes = ALL_TIMEFRAMES if tf_choice == 'ALL' else [tf_choice]

        pivot_tf_sel = st.selectbox(
            'Pivot timeframe',
            ['auto', 'D', 'W', 'M', 'Q', 'Y', 'all'],
            index=0,
            format_func=lambda t: ('Auto (TradingView)' if t == 'auto'
                                   else PIVOT_TF_LABELS.get(t, t) if t != 'all'
                                   else 'ALL (D+W+M+Q+Y)'),
            help='Auto = TradingView style: intraday charts use Daily pivots, '
                 'the 1D chart uses Monthly pivots. Or force a fixed period: '
                 'D=daily (prev day), W=weekly, M=monthly, Q=quarterly, '
                 'Y=yearly. ALL checks every period at once.',
        )

        distance = st.slider(
            'Max distance from pivot (%)',
            min_value=0.05, max_value=2.0,
            step=0.05, value=float(MAX_DISTANCE_PERCENT),
            key='distance_slider',
            help='Only stocks within this % of a pivot level are shown.',
        )
        preset_cols = st.columns(5)
        for i, p in enumerate([0.10, 0.20, 0.25, 0.50, 1.00]):
            if preset_cols[i].button(f'{p}', key=f'preset_{p}'):
                st.session_state['distance_slider'] = p
                st.rerun()

        mode = st.radio(
            'Scan mode',
            SCAN_MODES,
            index=SCAN_MODES.index(DEFAULT_SCAN_MODE),
            horizontal=True,
            help='pivot: distance only · pivot_willy: distance + Willy data',
        )

        data_source = st.radio('Data source', ['Fyers (live)', 'Sample (offline)'],
                               horizontal=True)

        freshness = st.radio(
            'Live data freshness',
            ['Auto (cached, up to 5 min old)', 'Always live (fresh fetch)'],
            index=0,
            help="Auto: today's candles are reused for 5 minutes, then "
                 "re-fetched on the next scan (past days are cached "
                 "permanently - they never change). Always live: every scan "
                 "hits the Fyers API for the latest prices right now - "
                 "slower, and uses more of your rate limit. Tip: use it with "
                 "a single stock or Nifty 50, not ALL NSE (~2300 stocks).",
        )
        use_cache = freshness.startswith('Auto')

        if not is_trading_day(scan_date):
            st.warning(f'{scan_date} is a weekend/holiday — results may be limited.')

        run_btn = st.button('🔍 RUN SCAN', type='primary', use_container_width=True)

    # ------------------------------ state ------------------------------
    ss = st.session_state
    for key, default in {
        'results': [], 'df': pd.DataFrame(), 'scan_meta': {},
        'prev_day': None, 'error': None, 'csv_bytes': b'',
    }.items():
        ss.setdefault(key, default)

    if run_btn:
        is_all = universe_sel.startswith(universe_name) and ' (all)' in universe_sel
        symbols = (universe if is_all else [universe_sel.split(' (all)')[0]])

        progress = st.progress(0.0, text='Starting scan…')
        status = st.empty()

        def cb(done: int, total: int, symbol: str) -> None:
            progress.progress(done / total,
                              text=f'Fetching {symbol} ({done}/{total})')

        try:
            if data_source.startswith('Sample'):
                status.info('Generating sample data…')
                stocks_data = fetch_sample_stock_data(
                    symbols, scan_date, timeframes, pivot_tf_sel)
                prev_day = get_previous_trading_day(scan_date)
            else:
                stocks_data, prev_day = fetch_live_data_cached(
                    tuple(symbols), scan_date, tuple(timeframes),
                    pivot_tf_sel, use_cache)
            progress.empty()

            if not stocks_data:
                ss['error'] = ('No data fetched. Check your Fyers access token '
                               '(it expires daily) or try Sample mode.')
            else:
                status.info(f'Scanning {len(stocks_data)} stocks × '
                            f'{len(timeframes)} timeframes…')
                results = run_scanner(
                    stocks_data, scan_date, timeframes,
                    max_distance_percent=distance, scan_mode=mode,
                    pivot_tf=pivot_tf_sel)
                ss['results'] = results
                ss['df'] = build_results_df(results)
                ss['csv_bytes'] = results_to_csv_bytes(results)
                ss['scan_meta'] = {
                    'date': scan_date, 'tfs': timeframes, 'dist': distance,
                    'mode': mode, 'source': data_source,
                    'stocks': len(stocks_data), 'prev_day': prev_day,
                    'pivot_tf': pivot_tf_sel,
                    'fetched_at': datetime.now().strftime('%d-%b %I:%M:%S %p'),
                    'fresh': not use_cache,
                }
                ss['error'] = None
                ss['_stocks_data'] = stocks_data
        except Exception as exc:                      # noqa: BLE001 - UI guard
            ss['error'] = f'Scan failed: {exc}'
        finally:
            progress.empty()
            status.empty()

    if ss['error']:
        st.error(ss['error'])

    if not ss['results'] and not ss['error']:
        st.info('👈 Set your filters and press **RUN SCAN**')
        return


    # ------------------------------ results ------------------------------
    meta = ss['scan_meta']
    if meta:
        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric('Scan date', str(meta.get('date', '')))
        c2.metric('Prev trading day', str(meta.get('prev_day') or '—'))
        c3.metric('Pivot TF', str(meta.get('pivot_tf', 'D')).replace('AUTO', 'Auto'))
        c4.metric('Stocks scanned', meta.get('stocks', 0))
        c5.metric('Distance ≤', f"{meta.get('dist', 0):.2f}%")
        c6.metric('Matches', len(ss['results']))
        fetched = meta.get('fetched_at')
        if fetched and meta.get('source', '').startswith('Fyers'):
            note = ('fresh fetch, right now' if meta.get('fresh')
                    else 'cached, up to 5 min old')
            st.caption(f'Data as of {fetched} IST ({note}) - the exact candle '
                       f'age per row is in the LAST_CANDLE column.')

    df_all = ss['df']

    # Instant filters (no re-fetch)
    with st.container(border=True):
        fc1, fc2, fc3, fc4 = st.columns([2, 2, 2, 2])
        search = fc1.text_input('Symbol contains', placeholder='e.g. ONGC')
        zones = fc2.multiselect('Willy zone',
                                ['Overbought', 'Oversold', 'Neutral'])
        signal_choice = fc3.selectbox(
            'Signal', ['All', 'Bullish Cross only', 'Bearish Cross only',
                       'Any cross'])
        sides = fc4.multiselect('Pivot side',
                                ['Supports', 'Resistances', 'Pivot (P)'])

    df_view = filter_results_df(df_all, search, zones, signal_choice, sides)

    left, right = st.columns([3, 1])
    with left:
        st.subheader(f'Results ({len(df_view)} shown / {len(df_all)} total)')
    with right:
        if ss['csv_bytes']:
            st.download_button(
                '⬇️ Download CSV', data=ss['csv_bytes'],
                file_name=f"{meta.get('date', 'scan')}_scanner_results.csv",
                mime='text/csv', use_container_width=True)

    if df_view.empty:
        st.warning('No matches for the current filters.')
    else:
        st.dataframe(
            df_view,
            use_container_width=True,
            hide_index=True,
            height=min(28 + 35 * len(df_view), 640),
            column_config={
                'PRICE': st.column_config.NumberColumn(format='%.2f'),
                'PIVOT_PRICE': st.column_config.NumberColumn(format='%.2f'),
                'DIST': st.column_config.NumberColumn(format='%.2f'),
                'DIST%': st.column_config.NumberColumn(format='%.3f'),
                'WILLY': st.column_config.NumberColumn(format='%.2f'),
                'WILLY_EMA': st.column_config.NumberColumn(format='%.2f'),
            },
        )
        st.caption('Sorted by distance % ascending — closest to a pivot first.')

    # ------------------------------ pivot inspector ------------------------------
    st.divider()
    st.subheader('🔎 Pivot Inspector')
    st.caption('Full pivot table + Willy chart for one stock '
               '(uses already-fetched scan data — no new API calls)')

    stocks_data = ss.get('_stocks_data', {})
    if not stocks_data:
        st.info('Run a scan first to enable the inspector.')
        return

    available = sorted(stocks_data.keys())
    ins_cols = st.columns([1, 1])
    ins_symbol = ins_cols[0].selectbox('Stock', available)
    tf_options = [tf for tf in ALL_TIMEFRAMES
                  if stocks_data[ins_symbol].get(f'candles_{tf}') is not None]
    ins_tf = (ins_cols[1].selectbox('Timeframe', tf_options)
              if tf_options else None)

    info = stocks_data[ins_symbol]
    by_tf = info.get('daily_ohlc_by_tf') or {}
    if not by_tf and info.get('daily_ohlc'):
        by_tf = {'D': info['daily_ohlc']}

    # Which pivot period applies to the selected inspector timeframe?
    # (auto: intraday -> Daily, 1d -> Monthly; explicit periods pass through)
    scan_ptf = (ss.get('scan_meta') or {}).get('pivot_tf', 'D')
    default_ptf = (resolve_pivot_tf(scan_ptf, ins_tf) if ins_tf else 'D')
    period_order = sorted(by_tf.keys())
    if period_order and default_ptf not in period_order:
        default_ptf = period_order[0]

    # Reference price: prefer the results row for THIS stock + timeframe
    sym_rows = df_all[df_all['STOCK'] == ins_symbol]
    row_tf = sym_rows[sym_rows['TF'] == ins_tf] if ins_tf else pd.DataFrame()
    if not row_tf.empty:
        ref_price = float(row_tf['PRICE'].iloc[0])
    elif not sym_rows.empty:
        ref_price = float(sym_rows['PRICE'].iloc[0])
    else:
        ref_price = None

    col_a, col_b = st.columns([1, 2])
    with col_a:
        if by_tf:
            if len(period_order) > 1:
                sel_ptf = st.radio(
                    'Pivot period',
                    period_order,
                    index=period_order.index(default_ptf),
                    format_func=lambda p: f"{PIVOT_TF_LABELS.get(p, p)} ({p})",
                    horizontal=True,
                )
            else:
                sel_ptf = period_order[0]
            ohlc = by_tf[sel_ptf]
            label = PIVOT_TF_LABELS.get(sel_ptf, sel_ptf)
            pe = ohlc.get('period_end')
            pe_str = (pd.to_datetime(pe).strftime('%Y-%m-%d')
                      if pe is not None else 'previous period')
            st.markdown(f'**{ins_symbol}** — {label} pivots')
            st.caption(f'Source candle: {pe_str}  ·  '
                       f'H {ohlc["high"]:.2f} · L {ohlc["low"]:.2f} · '
                       f'C {ohlc["close"]:.2f}')
            if ref_price:
                st.metric('Reference price', f'{ref_price:.2f}')
            st.dataframe(build_pivot_table(ohlc, ref_price or float(ohlc['close'])),
                         hide_index=True, use_container_width=True)
        else:
            st.warning('No daily OHLC available for this stock.')
    with col_b:
        if ins_tf:
            summary = willy_summary(info[f'candles_{ins_tf}'])
            if summary:
                m1, m2, m3, m4 = st.columns(4)
                m1.metric('Willy', summary['willy'])
                m2.metric('Willy EMA', summary['willy_ema'])
                m3.metric('Zone', summary['zone'])
                m4.metric('Signal', summary['signal'] or '—')
                wdf = summary['df'].tail(120)
                st.line_chart(
                    wdf.set_index('datetime')[['willy', 'willy_ema']],
                    height=260)
                st.caption(f'Willy(21)/EMA(13) · last {len(wdf)} {ins_tf} candles')
            else:
                st.info('Not enough candles for Willy on this timeframe.')
        else:
            st.info('No candle data available for this stock.')

    # ------------------------------ footer ------------------------------
    st.divider()
    st.markdown(
        '<div style="text-align:center; color:gray; font-size:0.9em;">'
        'Developed by <b>Chirag Rohada</b> · NSE/BSE Pivot Point Scanner · '
        'Data: Fyers API · For analysis only, not trading advice'
        '</div>',
        unsafe_allow_html=True,
    )


if __name__ == '__main__':
    run()
