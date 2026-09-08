"""
Instrument Management
======================

Manages stock universe (Nifty 50, 100, 200, 500) and Fyers instrument symbols.

Fyers uses symbol format: NSE:SBIN-EQ, NSE:RELIANCE-EQ, etc.
For NSE stocks, the format is: NSE:<SYMBOL>-EQ
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
from pathlib import Path

from .config import STOCKS_DIR


@dataclass
class StockInstrument:
    """Represents a stock with its Fyers instrument details."""
    symbol: str          # Short symbol (e.g., 'SBIN')
    name: str            # Full name (e.g., 'State Bank of India')
    fyers_symbol: str    # Fyers symbol format (e.g., 'NSE:SBIN-EQ')
    exchange: str = 'NSE'
    instrument_type: str = 'EQ'


# Nifty 50 Stocks with Fyers Symbol Format
# Fyers symbol format: NSE:<SYMBOL>-EQ for equity stocks

NIFTY_50: Dict[str, StockInstrument] = {
    'RELIANCE': StockInstrument('RELIANCE', 'Reliance Industries', 'NSE:RELIANCE-EQ'),
    'TCS': StockInstrument('TCS', 'Tata Consultancy Services', 'NSE:TCS-EQ'),
    'HDFCBANK': StockInstrument('HDFCBANK', 'HDFC Bank', 'NSE:HDFCBANK-EQ'),
    'INFY': StockInstrument('INFY', 'Infosys', 'NSE:INFY-EQ'),
    'ICICIBANK': StockInstrument('ICICIBANK', 'ICICI Bank', 'NSE:ICICIBANK-EQ'),
    'HINDUNILVR': StockInstrument('HINDUNILVR', 'Hindustan Unilever', 'NSE:HINDUNILVR-EQ'),
    'SBIN': StockInstrument('SBIN', 'State Bank of India', 'NSE:SBIN-EQ'),
    'BHARTIARTL': StockInstrument('BHARTIARTL', 'Bharti Airtel', 'NSE:BHARTIARTL-EQ'),
    'ITC': StockInstrument('ITC', 'ITC Limited', 'NSE:ITC-EQ'),
    'KOTAKBANK': StockInstrument('KOTAKBANK', 'Kotak Mahindra Bank', 'NSE:KOTAKBANK-EQ'),
    'LT': StockInstrument('LT', 'Larsen & Toubro', 'NSE:LT-EQ'),
    'AXISBANK': StockInstrument('AXISBANK', 'Axis Bank', 'NSE:AXISBANK-EQ'),
    'BAJFINANCE': StockInstrument('BAJFINANCE', 'Bajaj Finance', 'NSE:BAJFINANCE-EQ'),
    'ASIANPAINT': StockInstrument('ASIANPAINT', 'Asian Paints', 'NSE:ASIANPAINT-EQ'),
    'MARUTI': StockInstrument('MARUTI', 'Maruti Suzuki', 'NSE:MARUTI-EQ'),
    'TITAN': StockInstrument('TITAN', 'Titan Company', 'NSE:TITAN-EQ'),
    'SUNPHARMA': StockInstrument('SUNPHARMA', 'Sun Pharmaceutical', 'NSE:SUNPHARMA-EQ'),
    'WIPRO': StockInstrument('WIPRO', 'Wipro Limited', 'NSE:WIPRO-EQ'),
    'ULTRACEMCO': StockInstrument('ULTRACEMCO', 'UltraTech Cement', 'NSE:ULTRACEMCO-EQ'),
    'NESTLEIND': StockInstrument('NESTLEIND', 'Nestle India', 'NSE:NESTLEIND-EQ'),
    # Tata Motors demerged (Oct 2025): TMPV = passenger vehicles, TMCV = CV
    'TMPV': StockInstrument('TMPV', 'Tata Motors Passenger Vehicles', 'NSE:TMPV-EQ'),
    'TMCV': StockInstrument('TMCV', 'Tata Motors Commercial Vehicles', 'NSE:TMCV-EQ'),
    'HCLTECH': StockInstrument('HCLTECH', 'HCL Technologies', 'NSE:HCLTECH-EQ'),
    'ONGC': StockInstrument('ONGC', 'Oil & Natural Gas Corp', 'NSE:ONGC-EQ'),
    'POWERGRID': StockInstrument('POWERGRID', 'Power Grid Corp', 'NSE:POWERGRID-EQ'),
    'NTPC': StockInstrument('NTPC', 'NTPC Limited', 'NSE:NTPC-EQ'),
    'BAJAJFINSV': StockInstrument('BAJAJFINSV', 'Bajaj Finserv', 'NSE:BAJAJFINSV-EQ'),
    'M&M': StockInstrument('M&M', 'Mahindra & Mahindra', 'NSE:M&M-EQ'),
    'TATASTEEL': StockInstrument('TATASTEEL', 'Tata Steel', 'NSE:TATASTEEL-EQ'),
    'JSWSTEEL': StockInstrument('JSWSTEEL', 'JSW Steel', 'NSE:JSWSTEEL-EQ'),
    'ADANIPORTS': StockInstrument('ADANIPORTS', 'Adani Ports', 'NSE:ADANIPORTS-EQ'),
    'COALINDIA': StockInstrument('COALINDIA', 'Coal India', 'NSE:COALINDIA-EQ'),
    'GRASIM': StockInstrument('GRASIM', 'Grasim Industries', 'NSE:GRASIM-EQ'),
    'BRITANNIA': StockInstrument('BRITANNIA', 'Britannia Industries', 'NSE:BRITANNIA-EQ'),
    'CIPLA': StockInstrument('CIPLA', 'Cipla Limited', 'NSE:CIPLA-EQ'),
    'EICHERMOT': StockInstrument('EICHERMOT', 'Eicher Motors', 'NSE:EICHERMOT-EQ'),
    'TECHM': StockInstrument('TECHM', 'Tech Mahindra', 'NSE:TECHM-EQ'),
    'INDUSINDBK': StockInstrument('INDUSINDBK', 'IndusInd Bank', 'NSE:INDUSINDBK-EQ'),
    'HEROMOTOCO': StockInstrument('HEROMOTOCO', 'Hero MotoCorp', 'NSE:HEROMOTOCO-EQ'),
    'DRREDDY': StockInstrument('DRREDDY', 'Dr Reddys Labs', 'NSE:DRREDDY-EQ'),
    'SHREECEM': StockInstrument('SHREECEM', 'Shree Cements', 'NSE:SHREECEM-EQ'),
    'DIVISLAB': StockInstrument('DIVISLab', 'Divis Laboratories', 'NSE:DIVISLAB-EQ'),
    'SBILIFE': StockInstrument('SBILIFE', 'SBI Life Insurance', 'NSE:SBILIFE-EQ'),
    'HDFCLIFE': StockInstrument('HDFCLIFE', 'HDFC Life Insurance', 'NSE:HDFCLIFE-EQ'),
    'APOLLOHOSP': StockInstrument('APOLLOHOSP', 'Apollo Hospitals', 'NSE:APOLLOHOSP-EQ'),
    'BPCL': StockInstrument('BPCL', 'Bharat Petroleum', 'NSE:BPCL-EQ'),
    'TATACONSUM': StockInstrument('TATACONSUM', 'Tata Consumer Products', 'NSE:TATACONSUM-EQ'),
    'UPL': StockInstrument('UPL', 'UPL Limited', 'NSE:UPL-EQ'),
    'ADANIENT': StockInstrument('ADANIENT', 'Adani Enterprises', 'NSE:ADANIENT-EQ'),
}


def get_nifty_50_symbols() -> List[str]:
    """Get list of Nifty 50 stock symbols."""
    return list(NIFTY_50.keys())


# ---------------------------------------------------------------------------
# NIFTY 100 universe (Nifty 50 + ~50 additional major constituents)
#
# This is a curated approximation of the NSE NIFTY 100 constituent list.
# Symbols/fyers format follow Fyers' NSE:<SYMBOL>-EQ convention.
# NOTE: it is EASY to extend - see get_custom_symbols() / data/stocks/custom.csv
# ---------------------------------------------------------------------------
NIFTY_100_EXTRA: Dict[str, StockInstrument] = {
    'ABB': StockInstrument('ABB', 'ABB India', 'NSE:ABB-EQ'),
    'ADANIGREEN': StockInstrument('ADANIGREEN', 'Adani Green Energy', 'NSE:ADANIGREEN-EQ'),
    'ADANIPOWER': StockInstrument('ADANIPOWER', 'Adani Power', 'NSE:ADANIPOWER-EQ'),
    'AMBUJACEM': StockInstrument('AMBUJACEM', 'Ambuja Cements', 'NSE:AMBUJACEM-EQ'),
    'APOLLOTYRE': StockInstrument('APOLLOTYRE', 'Apollo Tyres', 'NSE:APOLLOTYRE-EQ'),
    'ASHOKLEY': StockInstrument('ASHOKLEY', 'Ashok Leyland', 'NSE:ASHOKLEY-EQ'),
    'ATGL': StockInstrument('ATGL', 'Adani Total Gas', 'NSE:ATGL-EQ'),
    'AUROBINDO': StockInstrument('AUROBINDO', 'Aurobindo Pharma', 'NSE:AUROBINDO-EQ'),
    'BANDHANBNK': StockInstrument('BANDHANBNK', 'Bandhan Bank', 'NSE:BANDHANBNK-EQ'),
    'BANKBARODA': StockInstrument('BANKBARODA', 'Bank of Baroda', 'NSE:BANKBARODA-EQ'),
    'BATAINDIA': StockInstrument('BATAINDIA', 'Bata India', 'NSE:BATAINDIA-EQ'),
    'BHARATFORGE': StockInstrument('BHARATFORGE', 'Bharat Forge', 'NSE:BHARATFORGE-EQ'),
    'BIOCON': StockInstrument('BIOCON', 'Biocon', 'NSE:BIOCON-EQ'),
    'BOSCH': StockInstrument('BOSCH', 'Bosch India', 'NSE:BOSCH-EQ'),
    'BSE': StockInstrument('BSE', 'BSE Limited', 'NSE:BSE-EQ'),
    'CANBK': StockInstrument('CANBK', 'Canara Bank', 'NSE:CANBK-EQ'),
    'CHOLAFIN': StockInstrument('CHOLAFIN', 'Cholamandalam Fin', 'NSE:CHOLAFIN-EQ'),
    'COLPAL': StockInstrument('COLPAL', 'Colgate-Palmolive', 'NSE:COLPAL-EQ'),
    'CONCOR': StockInstrument('CONCOR', 'Container Corp of India', 'NSE:CONCOR-EQ'),
    'CUMMINSIND': StockInstrument('CUMMINSIND', 'Cummins India', 'NSE:CUMMINSIND-EQ'),
    'DABUR': StockInstrument('DABUR', 'Dabur India', 'NSE:DABUR-EQ'),
    'DLF': StockInstrument('DLF', 'DLF Limited', 'NSE:DLF-EQ'),
    'GAIL': StockInstrument('GAIL', 'GAIL India', 'NSE:GAIL-EQ'),
    'GODREJCP': StockInstrument('GODREJCP', 'Godrej Consumer', 'NSE:GODREJCP-EQ'),
    'HAVELLS': StockInstrument('HAVELLS', 'Havells India', 'NSE:HAVELLS-EQ'),
    'HINDALCO': StockInstrument('HINDALCO', 'Hindalco Industries', 'NSE:HINDALCO-EQ'),
    'HINDZINC': StockInstrument('HINDZINC', 'Hindustan Zinc', 'NSE:HINDZINC-EQ'),
    'ICICIPRULI': StockInstrument('ICICIPRULI', 'ICICI Prudential Life', 'NSE:ICICIPRULI-EQ'),
    'IDFCFIRSTB': StockInstrument('IDFCFIRSTB', 'IDFC First Bank', 'NSE:IDFCFIRSTB-EQ'),
    'IOC': StockInstrument('IOC', 'Indian Oil Corp', 'NSE:IOC-EQ'),
    'IRCTC': StockInstrument('IRCTC', 'IRCTC', 'NSE:IRCTC-EQ'),
    'JINDALSTEL': StockInstrument('JINDALSTEL', 'Jindal Steel', 'NSE:JINDALSTEL-EQ'),
    'JSWENERGY': StockInstrument('JSWENERGY', 'JSW Energy', 'NSE:JSWENERGY-EQ'),
    'LICI': StockInstrument('LICI', 'LIC India', 'NSE:LICI-EQ'),
    'LTIM': StockInstrument('LTIM', 'LTIMindtree', 'NSE:LTIM-EQ'),
    'MACROTECH': StockInstrument('MACROTECH', 'Macrotech Developers', 'NSE:MACROTECH-EQ'),
    'NMDC': StockInstrument('NMDC', 'NMDC Limited', 'NSE:NMDC-EQ'),
    'OIL': StockInstrument('OIL', 'Oil India', 'NSE:OIL-EQ'),
    'PAGEIND': StockInstrument('PAGEIND', 'Page Industries', 'NSE:PAGEIND-EQ'),
    'PIDILITE': StockInstrument('PIDILITE', 'Pidilite Industries', 'NSE:PIDILITE-EQ'),
    'ROUTEMOBILE': StockInstrument('ROUTEMOBILE', 'Route Mobile', 'NSE:ROUTEMOBILE-EQ'),
    'SBICARD': StockInstrument('SBICARD', 'SBI Cards', 'NSE:SBICARD-EQ'),
    'SHRIRAMFIN': StockInstrument('SHRIRAMFIN', 'Shriram Finance', 'NSE:SHRIRAMFIN-EQ'),
    'SIEMENS': StockInstrument('SIEMENS', 'Siemens India', 'NSE:SIEMENS-EQ'),
    'SRF': StockInstrument('SRF', 'SRF Limited', 'NSE:SRF-EQ'),
    'TATAPOWER': StockInstrument('TATAPOWER', 'Tata Power', 'NSE:TATAPOWER-EQ'),
    'TORRENTPWR': StockInstrument('TORRENTPWR', 'Torrent Power', 'NSE:TORRENTPWR-EQ'),
    'TVSMOTOR': StockInstrument('TVSMOTOR', 'TVS Motor', 'NSE:TVSMOTOR-EQ'),
    'VEDL': StockInstrument('VEDL', 'Vedanta', 'NSE:VEDL-EQ'),
}

NIFTY_100: Dict[str, StockInstrument] = {**NIFTY_50, **NIFTY_100_EXTRA}


def get_nifty_100_symbols() -> List[str]:
    """Get list of Nifty 100 (approx.) stock symbols (Nifty 50 + 50 more)."""
    return list(NIFTY_100.keys())


def get_nifty_50_instruments() -> Dict[str, StockInstrument]:
    """Get Nifty 50 instruments dictionary."""
    return NIFTY_50


def get_nifty_100_instruments() -> Dict[str, StockInstrument]:
    """Get Nifty 100 (approx.) instruments dictionary (Nifty 50 + 50 more)."""
    return NIFTY_100


_UNIVERSE_REGISTRY: Dict[str, Dict[str, StockInstrument]] = {
    'nifty50': NIFTY_50,
    'nifty100': NIFTY_100,
}


def get_universe_symbols(universe: str = 'nifty50') -> List[str]:
    """
    Resolve a universe name to a list of stock symbols.

    Handles: 'nifty50', 'nifty100', plus 'custom' via
    data/stocks/custom.csv (columns: symbol,name,fyers_symbol).

    If the universe is unknown, falls back to Nifty 50 (never crashes).
    """
    key = (universe or 'nifty50').lower().replace(' ', '')
    if key in _UNIVERSE_REGISTRY:
        return list(_UNIVERSE_REGISTRY[key].keys())
    if key == 'custom':
        return list(get_custom_instruments().keys())
    return list(NIFTY_50.keys())


# ---------------------------------------------------------------------------
# Full Exchange Masters (data/stocks/nse_all.csv, bse_all.csv)
#
# Produced by  python main.py update-stocks  (or build_masters.py).
#   nse_all.csv -> every NSE EQ-series equity as NSE:<SYMBOL>-EQ
#   bse_all.csv -> dual-listed tickers as BSE:<SYMBOL>-EQ
# Columns: symbol,name,fyers_symbol  (one per line)
# ---------------------------------------------------------------------------
MASTER_FILES: Dict[str, Path] = {
    'allnse': STOCKS_DIR / 'nse_all.csv',
    'allbse': STOCKS_DIR / 'bse_all.csv',
}


def _load_master_csv(key: str) -> Dict[str, StockInstrument]:
    """Load (and cache) a master instrument CSV from data/stocks."""
    cache_attr = f'_master_cache_{key}'
    cached = getattr(_load_master_csv, cache_attr, None)
    if cached is not None:
        return cached
    result: Dict[str, StockInstrument] = {}
    path = MASTER_FILES.get(key)
    if path is not None and path.exists():
        import csv as _csv
        try:
            with open(path, 'r', encoding='utf-8') as fh:
                for row in _csv.DictReader(fh):
                    sym = (row.get('symbol') or '').strip().upper()
                    name = (row.get('name') or '').strip()
                    fsym = (row.get('fyers_symbol') or '').strip()
                    if sym and fsym:
                        result[sym] = StockInstrument(sym, name, fsym)
        except OSError:
            pass
    setattr(_load_master_csv, cache_attr, result)
    return result


def get_allnse_instruments() -> Dict[str, StockInstrument]:
    return _load_master_csv('allnse')


def get_allbse_instruments() -> Dict[str, StockInstrument]:
    return _load_master_csv('allbse')


def get_nse_all_symbols() -> List[str]:
    return list(get_allnse_instruments().keys())


def get_bse_all_symbols() -> List[str]:
    return list(get_allbse_instruments().keys())


_UNIVERSE_REGISTRY.update({
    'allnse': get_allnse_instruments(),
    'allbse': get_allbse_instruments(),
})


def get_stock_instrument(symbol: str) -> Optional[StockInstrument]:
    """Get instrument details for a specific stock (all universes + masters)."""
    s = symbol.upper()
    for reg in _UNIVERSE_REGISTRY.values():
        if s in reg:
            return reg[s]
    return get_custom_instruments().get(s)


def get_fyers_symbol(symbol: str) -> Optional[str]:
    """Get Fyers symbol format for a stock symbol."""
    instrument = get_stock_instrument(symbol)
    return instrument.fyers_symbol if instrument else None


# ---------------------------------------------------------------------------
# Custom universe (data/stocks/custom.csv)
#
# Optional file with columns: symbol,name,fyers_symbol
# e.g.  VBL,Varun Beverages,NSE:VBL-EQ
# Create it to scan your own watchlist; it doesn't have to be an index.
# ---------------------------------------------------------------------------
CUSTOM_STOCKS_FILE: Path = STOCKS_DIR / 'custom.csv'


def get_custom_instruments() -> Dict[str, StockInstrument]:
    """Load the custom stock list from data/stocks/custom.csv (cached in-memory)."""
    if getattr(get_custom_instruments, '_cache', None) is not None:
        return get_custom_instruments._cache
    result: Dict[str, StockInstrument] = {}
    if CUSTOM_STOCKS_FILE.exists():
        try:
            with open(CUSTOM_STOCKS_FILE, 'r', encoding='utf-8') as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) < 3:
                        continue
                    symbol, name, fsym = parts[0].upper(), parts[1], parts[2]
                    result[symbol] = StockInstrument(symbol, name, fsym)
        except OSError:
            pass
    get_custom_instruments._cache = result
    return result


get_custom_instruments._cache: Optional[Dict[str, StockInstrument]] = None
