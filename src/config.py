"""
Configuration Module
====================

Loads configuration from environment variables and .env file.
All sensitive credentials are read from environment variables.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from project root
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / '.env'

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)

# ============================================
# Fyers API Credentials
# ============================================
FYERS_APP_ID = os.getenv('FYERS_APP_ID', '')
FYERS_APP_SECRET = os.getenv('FYERS_APP_SECRET', '')
FYERS_REDIRECT_URL = os.getenv('FYERS_REDIRECT_URL', 'https://127.0.0.1:8080')
FYERS_ACCESS_TOKEN = os.getenv('FYERS_ACCESS_TOKEN', '')

# TOTP auto-login (optional). Fill these in .env to let the scanner
# re-login BY ITSELF when the daily token expires:
#   FYERS_USER_ID      - Fyers user id, e.g. YC00160 (no dashes)
#   FYERS_PIN          - Fyers login PIN (4 or 6 digits)
#   FYERS_TOTP_SECRET  - base32 secret from Fyers TOTP setup
#                        (MyAccount -> TOTP -> 'show secret'/QR)
FYERS_USER_ID = os.getenv('FYERS_USER_ID', '')
FYERS_PIN = os.getenv('FYERS_PIN', '')
FYERS_TOTP_SECRET = os.getenv('FYERS_TOTP_SECRET', '').replace(' ', '')
AUTO_LOGIN_ENABLED = os.getenv('FYERS_AUTO_LOGIN', '1') not in ('0', 'false', 'False')

# ============================================
# Scanner Configuration
# ============================================

# Distance threshold (percentage) for pivot proximity
MAX_DISTANCE_PERCENT = float(os.getenv('MAX_DISTANCE_PERCENT', '0.50'))

# Available distance thresholds
DISTANCE_THRESHOLDS = [0.10, 0.20, 0.25, 0.50, 1.00]

# Timeframes to scan
TIMEFRAMES = ['5m', '15m', '30m', '1h', '4h', '1d']

# Willy indicator parameters
WILLY_LENGTH = int(os.getenv('WILLY_LENGTH', '21'))
WILLY_EMA_LENGTH = int(os.getenv('WILLY_EMA_LENGTH', '13'))

# Willy zone thresholds
WILLY_OVERSOLD_THRESHOLD = -80
WILLY_OVERBOUGHT_THRESHOLD = -20

# Scan modes
SCAN_MODES = ['pivot', 'pivot_willy']
DEFAULT_SCAN_MODE = 'pivot_willy'

# Stock universe
STOCK_UNIVERSES = ['nifty50', 'nifty100', 'nifty200', 'nifty500', 'custom']
DEFAULT_UNIVERSE = 'nifty50'

# ============================================
# Data Paths
# ============================================
DATA_DIR = PROJECT_ROOT / 'data'
STOCKS_DIR = DATA_DIR / 'stocks'
PIVOTS_DIR = DATA_DIR / 'pivots'
CACHE_DIR = DATA_DIR / 'cache'
RESULTS_DIR = PROJECT_ROOT / 'results'
LOGS_DIR = PROJECT_ROOT / 'logs'

# Create directories if they don't exist
for dir_path in [DATA_DIR, STOCKS_DIR, PIVOTS_DIR, CACHE_DIR, RESULTS_DIR, LOGS_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)

for dir_path in [DATA_DIR, STOCKS_DIR, PIVOTS_DIR, CACHE_DIR, RESULTS_DIR, LOGS_DIR]:
# Create directories if they don't exist (also covers fresh cloud clones
# where the data/results/logs folders are not committed to git)
    dir_path.mkdir(parents=True, exist_ok=True)


# ----------------------------------------------------------------------------
# CLOUD-READY CREDENTIAL ACCESS
# ----------------------------------------------------------------------------

# Every Fyers credential key the app understands (used for env-var and
# st.secrets lookups on cloud platforms).
CREDENTIAL_KEYS = [
    'FYERS_APP_ID', 'FYERS_APP_SECRET', 'FYERS_REDIRECT_URL',
    'FYERS_ACCESS_TOKEN', 'FYERS_USER_ID', 'FYERS_PIN',
    'FYERS_TOTP_SECRET', 'FYERS_AUTO_LOGIN',
]


def read_credentials(env_file=None) -> dict:
    """
    Read Fyers credentials from every supported source, merged into one
    dict.  Later sources win:

        1. .env file   (local development; re-read from disk on every call
                        so a long-running dashboard always sees the latest
                        values written by login.py / auto-login)
        2. OS env vars (Render, Docker, CI, GitHub Actions)
        3. st.secrets  (Streamlit Community Cloud - flat keys or a
                        [fyers] section in secrets.toml)

    Never raises: a missing source simply contributes no keys.  This makes
    the exact same code run locally, on Render and on Streamlit Cloud.
    """
    creds: dict = {}

    # 1) .env file (if present)
    env_path = Path(env_file) if env_file else ENV_FILE
    try:
        if env_path.exists():
            for line in env_path.read_text(encoding='utf-8').splitlines():
                line = line.strip()
                if not line or line.startswith('#') or '=' not in line:
                    continue
                key, _, value = line.partition('=')
                creds[key.strip()] = value.strip().strip('"').strip("'")
    except OSError:
        pass

    # 2) OS environment variables
    for key in CREDENTIAL_KEYS:
        val = os.getenv(key)
        if val:
            creds[key] = val

    # 3) Streamlit secrets (only available when running under Streamlit)
    try:
        import streamlit as st
        try:                                   # [fyers] section style
            for key, val in dict(st.secrets.get('fyers', {}) or {}).items():
                if val:
                    creds[str(key).upper()] = str(val)
        except Exception:
            pass
        for key in CREDENTIAL_KEYS:            # flat FYERS_XXX style
            try:
                val = st.secrets.get(key)
            except Exception:
                val = None
            if val:
                creds[key] = str(val)
    except Exception:
        pass

    return creds
# ============================================
# API Configuration
# ============================================
# Auth/account endpoints live under /api/v3
FYERS_API_BASE_URL = 'https://api-t1.fyers.in/api/v3'
# Market-data endpoints live under /data (NOT under /api/v3)
FYERS_DATA_BASE_URL = 'https://api-t1.fyers.in/data'

# Rate limiting (Fyers allows ~5 req/sec for free tier; stay conservative)
API_RATE_LIMIT_PER_SECOND = 5
# Retries for TRANSIENT errors only (HTTP 429 / API code 429 / 5xx / JSON
# parse failures). Exponential backoff: 1,2,4,8,16,60s. This lets the scanner
# ride through rate-limit windows instead of dropping whole stocks.
# (4xx API errors like bad symbol / holiday are NOT retried.)
API_RETRY_ATTEMPTS = 6
API_RETRY_DELAY = 2  # seconds (base; exponential backoff supersedes for 429)

# ============================================
# Caching Configuration
# ============================================
CACHE_EXPIRY_HOURS = 24
PIVOT_CACHE_FILE = PIVOTS_DIR / 'pivot_cache.json'


def validate_credentials() -> bool:
    """
    Validate that all required API credentials are set.

    Returns
    -------
    bool
        True if all credentials are present
    """
    required = [FYERS_APP_ID, FYERS_ACCESS_TOKEN]
    return all(required)
