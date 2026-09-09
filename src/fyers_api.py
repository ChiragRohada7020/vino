"""
Fyers API Client
================

Handles authentication and market-data fetching from Fyers API v3.
This module is deliberately separated from indicator calculations.

Fyers API v3 Documentation: https://myapi.fyers.in/docsv3

ENDPOINT LAYOUT (verified against the official fyers-apiv3 SDK source):
    Auth/account endpoints -> https://api-t1.fyers.in/api/v3/...
        POST  /validate-authcode   exchange auth code for access token
        GET   /profile             validate access token / account info
    Market-data endpoints  -> https://api-t1.fyers.in/data/...
        GET   /history             candle data
        GET   /quotes              latest prices

    Authorization header : "Authorization: <APP_ID>:<ACCESS_TOKEN>"
    History params       : symbol, resolution, date_format=1,
                           range_from=YYYY-MM-DD, range_to=YYYY-MM-DD, cont_flag=1
    Auth-code exchange   : POST /validate-authcode
                           {"grant_type": "authorization_code",
                            "appIdHash": sha256(f"{APP_ID}:{APP_SECRET}"),
                            "code": <auth_code_jwt>}
"""

import hashlib
import logging
import time
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional

import pytz
import requests

from .config import (
    FYERS_APP_ID,
    FYERS_APP_SECRET,
    FYERS_REDIRECT_URL,
    FYERS_ACCESS_TOKEN,
    FYERS_API_BASE_URL,
    FYERS_DATA_BASE_URL,
    API_RATE_LIMIT_PER_SECOND,
    API_RETRY_ATTEMPTS,
    API_RETRY_DELAY,
    AUTO_LOGIN_ENABLED,
)

logger = logging.getLogger(__name__)

# Fyers candle timestamps are exchange time (IST)
IST = pytz.timezone('Asia/Kolkata')

# Project root .env file (used to persist refreshed access tokens)
ENV_FILE = Path(__file__).resolve().parent.parent / '.env'


class FyersAPI:
    """Fyers API v3 client for authentication and market data."""

    def __init__(self, access_token: Optional[str] = None):
        self.app_id = FYERS_APP_ID
        self.app_secret = FYERS_APP_SECRET
        self.redirect_url = FYERS_REDIRECT_URL
        self.api_base = FYERS_API_BASE_URL      # /api/v3 endpoints (auth, profile)
        self.data_base = FYERS_DATA_BASE_URL    # /data endpoints (history, quotes)
        self.access_token = access_token or FYERS_ACCESS_TOKEN
        self.session = requests.Session()
        self._last_request_time: Optional[float] = None
        self._auto_login_attempted: bool = False   # one TOTP attempt max
        self._auto_login_hint_logged: bool = False

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------
    def _get_headers(self) -> Dict[str, str]:
        """Build request headers (Authorization: APP_ID:ACCESS_TOKEN)."""
        if not self.access_token:
            raise ValueError(
                'No access token available. Run login() or set FYERS_ACCESS_TOKEN in .env'
            )
        return {
            'Authorization': f'{self.app_id}:{self.access_token}',
            'Content-Type': 'application/json',
        }

    def get_auth_code_url(self) -> str:
        """Return the URL the user must visit to generate an auth code."""
        # Fyers expects app_id in format "XXXXXXXXXX-100"
        client_id = f'{self.app_id}-100' if '-' not in self.app_id else self.app_id
        return (
            f'{self.api_base}/generate-authcode'
            f'?client_id={client_id}'
            f'&redirect_uri={self.redirect_url}'
            f'&response_type=code'
            f'&state=None'
        )


    def exchange_auth_code(self, auth_code: str, save: bool = True) -> str:
        """
        Exchange an auth-code JWT for a long-lived access token.

        The auth code is the JWT returned in the redirect URL after the user
        authorises the app (its JWT 'sub' claim is 'auth_code'). It is NOT
        the access token and cannot be used directly for data requests.
        """
        app_id_hash = hashlib.sha256(
            f'{self.app_id}:{self.app_secret}'.encode()
        ).hexdigest()
        payload = {
            'grant_type': 'authorization_code',   # snake_case per official SDK
            'appIdHash': app_id_hash,             # sha256 hex of "APP_ID:SECRET"
            'code': auth_code,
        }
        response = requests.post(
            f'{self.api_base}/validate-authcode', json=payload, timeout=30
        )
        try:
            data = response.json()
        except ValueError:
            raise ValueError(
                f'Auth code exchange failed (HTTP {response.status_code}): '
                f'{response.text[:200]}'
            )
        if not data.get('access_token'):
            raise ValueError(f'Auth code exchange failed: {data}')

        self.access_token = data['access_token']
        if save:
            self._save_token_to_env(self.access_token)
        logger.info('Auth code exchanged successfully; access token saved')
        return self.access_token

    def _save_token_to_env(self, token: str) -> None:
        """Persist the access token to .env so it survives restarts."""
        try:
            lines = (
                ENV_FILE.read_text(encoding='utf-8').splitlines()
                if ENV_FILE.exists() else ['# Fyers API Credentials']
            )
            out_lines, found = [], False
            for line in lines:
                if line.startswith('FYERS_ACCESS_TOKEN='):
                    out_lines.append(f'FYERS_ACCESS_TOKEN={token}')
                    found = True
                else:
                    out_lines.append(line)
            if not found:
                out_lines.append(f'FYERS_ACCESS_TOKEN={token}')
            ENV_FILE.write_text('\n'.join(out_lines) + '\n', encoding='utf-8')
        except OSError as exc:
            logger.warning('Could not persist access token to .env: %s', exc)

    # ------------------------------------------------------------------
    # Automatic re-login (TOTP) when the daily token expires
    # ------------------------------------------------------------------
    @staticmethod
    def _is_auth_error(data: Dict) -> bool:
        """True when an API response indicates an expired/invalid token."""
        code = data.get('code')
        msg = str(data.get('message', '')).lower()
        if code in (-8, -15, -16, -17, 401):
            return True
        if 'token' in msg and ('expire' in msg or 'invalid' in msg):
            return True
        return 'authenticate' in msg

    def _try_auto_relogin(self) -> bool:
        """
        Attempt a TOTP auto-relogin when the token has expired (Fyers tokens
        are valid for one day). Requires FYERS_USER_ID / FYERS_PIN /
        FYERS_TOTP_SECRET in .env; credentials are read straight from disk so
        a long-running dashboard picks them up the moment they are added.

        On success the fresh token is stored on this client AND saved to
        .env (via exchange_auth_code). One real attempt per client instance
        to avoid hammering the TOTP endpoint; a missing-credentials state is
        not marked permanent so the client can pick credentials up later.
        """
        if not AUTO_LOGIN_ENABLED or self._auto_login_attempted:
            return False

        from .auto_login import auto_login as fyers_auto_login
        from .auto_login import read_env_credentials   # local import (no cycle)

        creds = read_env_credentials(ENV_FILE)
        user_id = creds.get('FYERS_USER_ID', '')
        pin = creds.get('FYERS_PIN', '')
        totp_secret = creds.get('FYERS_TOTP_SECRET', '')

        if not (user_id and pin and totp_secret):
            if not self._auto_login_hint_logged:
                self._auto_login_hint_logged = True
                logger.info(
                    'Token invalid and auto-login not configured. Add '
                    'FYERS_USER_ID / FYERS_PIN / FYERS_TOTP_SECRET to .env '
                    'for automatic re-login, or run: python login.py'
                )
            return False

        self._auto_login_attempted = True
        logger.info('Access token invalid - attempting TOTP auto-relogin')
        try:
            auth_code = fyers_auto_login(self.app_id, user_id, pin, totp_secret)
            if not auth_code:
                return False
            self.exchange_auth_code(auth_code)   # updates client + saves .env
            logger.info('Auto-relogin successful - new access token active')
            return True
        except (ValueError, OSError,
                requests.exceptions.RequestException) as exc:
            logger.error('Auto-relogin failed: %s', exc)
            return False

    def is_token_valid(self) -> bool:
        """Check whether the current access token works against /profile."""
        if not self.access_token:
            return False
        try:
            response = self.session.get(
                f'{self.api_base}/profile',
                headers=self._get_headers(),
                timeout=15,
            )
            data = response.json()
            return data.get('s') == 'ok'
        except (requests.exceptions.RequestException, ValueError):
            return False

    def get_profile(self) -> Optional[Dict]:
        """Return the account profile (also proves the token is valid)."""
        try:
            response = self.session.get(
                f'{self.api_base}/profile',
                headers=self._get_headers(),
                timeout=15,
            )
            data = response.json()
            # expired token -> one TOTP auto-relogin attempt, then retry
            if (data.get('s') != 'ok' and self._is_auth_error(data)
                    and self._try_auto_relogin()):
                return self.get_profile()
            return data
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error('Profile request failed: %s', exc)
            return None

    def login(self, auth_code: Optional[str] = None) -> bool:
        """
        Authenticate. If a valid access token is already configured, reuse it.
        Otherwise exchange the provided auth code. If no auth code is given,
        print the URL the user must visit to obtain one.
        """
        if self.access_token and not auth_code and self.is_token_valid():
            logger.info('Existing access token is valid')
            return True

        if auth_code:
            self.exchange_auth_code(auth_code)
            return self.is_token_valid()

        print('Visit this URL in a browser and log in to Fyers:')
        print(self.get_auth_code_url())
        print(
            "After authorising, copy the 'code' param from the redirect URL and "
            'exchange it via FyersAPI().exchange_auth_code("<CODE>")'
        )
        return False

    # ------------------------------------------------------------------
    # Market data
    # ------------------------------------------------------------------
    def get_historical_candles(
        self,
        symbol: str,
        timeframe: str,
        from_date: date,
        to_date: date,
        ) -> Optional[List[Dict]]:
        """
        Fetch historical candles for a Fyers symbol (e.g. 'NSE:SBIN-EQ').

        Returns a list of dicts: datetime, open, high, low, close, volume.
        Returns None on failure (errors are logged, never raised).

        Rate-limit resilience:
          - HTTP 429  -> honour ``Retry-After`` header, then exponential backoff
          - API code 429 on HTTP 200 ("request limit reached") -> retry
          - Other 4xx API errors (bad token / symbol / holiday) -> NO retry
          - 5xx / connection / JSON parse errors -> exponential backoff
        """
        self._rate_limit()
        resolution = self._timeframe_to_resolution(timeframe)
        params = {
            'symbol': symbol,
            'resolution': resolution,
            'date_format': 1,  # 1 => range_from/range_to as yyyy-mm-dd
            'range_from': from_date.strftime('%Y-%m-%d'),
            'range_to': to_date.strftime('%Y-%m-%d'),
            'cont_flag': 1,
        }

        url = f'{self.data_base}/history'
        last_error: Optional[str] = None

        for attempt in range(1, API_RETRY_ATTEMPTS + 1):
            try:
                response = self.session.get(
                    url, params=params, headers=self._get_headers(), timeout=30
                )

                # --- HTTP 429: rate-limited -> honour Retry-After, then backoff
                if response.status_code == 429:
                    delay = max(self._parse_retry_after(response),
                                min(2 ** attempt, 60))
                    logger.warning(
                        'Rate-limited (HTTP 429) for %s %s; backing off %ss '
                        '(attempt %d/%d)', symbol, timeframe, int(delay),
                        attempt, API_RETRY_ATTEMPTS,
                    )
                    time.sleep(delay)
                    last_error = 'HTTP 429'
                    continue

                data = response.json()

                # Fyers also signals "request limit reached" via API code 429
                # on a 200 response -- treat it as retryable, NOT permanent.
                if data.get('code') == 429:
                    delay = max(self._parse_retry_after(response),
                                min(2 ** attempt, 60))
                    logger.warning(
                        'Rate-limited (code 429) for %s %s; backing off %ss '
                        '(attempt %d/%d)', symbol, timeframe, int(delay),
                        attempt, API_RETRY_ATTEMPTS,
                    )
                    time.sleep(delay)
                    last_error = 'API 429'
                    continue

                if data.get('s') == 'ok':
                    candles = data.get('candles', [])
                    if not candles:
                        logger.info('No candle data for %s %s', symbol, timeframe)
                    return self._format_candles(candles)

                # Other logical/API errors (bad token, bad symbol, holiday) -> no retry,
                # EXCEPT expired-token errors: try one TOTP auto-relogin, then
                # the loop retries with the fresh token (attempt is consumed).
                logger.error(
                    'Fyers history error for %s (%s): code=%s message=%s',
                    symbol, timeframe, data.get('code'), data.get('message'),
                )
                if self._is_auth_error(data) and self._try_auto_relogin():
                    continue
                return None

            except ValueError as exc:
                # Non-JSON body (e.g. 429 returned as HTML) -> backoff & retry
                last_error = str(exc)
            except requests.exceptions.RequestException as exc:
                last_error = str(exc)

            # Exponential backoff for transient / rate-limit errors
            if attempt < API_RETRY_ATTEMPTS:
                delay = min(2 ** attempt, 60)
                logger.debug('Retrying %s %s in %ss (attempt %d): %s',
                             symbol, timeframe, delay, attempt, last_error)
                time.sleep(delay)

        logger.error(
            'Failed to fetch history for %s (%s) after %d attempts: %s',
            symbol, timeframe, API_RETRY_ATTEMPTS, last_error,
        )
        return None

    def get_daily_ohlc(self, symbol: str, for_date: date) -> Optional[Dict]:
        """Fetch a single day's daily OHLC dict (datetime/open/high/low/close/volume)."""
        candles = self.get_historical_candles(symbol, '1d', for_date, for_date)
        if candles:
            return candles[-1]
        return None

    def get_quotes(self, symbols: List[str]) -> Optional[Dict[str, Dict]]:
        """Fetch latest quotes for one or more Fyers symbols."""
        if not symbols:
            return None
        self._rate_limit()
        params = {'symbols': ','.join(symbols)}
        try:
            response = self.session.get(
                f'{self.data_base}/quotes',
                params=params,
                headers=self._get_headers(),
                timeout=15,
            )
            data = response.json()
            if data.get('s') != 'ok':
                logger.error('Fyers quotes error: %s', data)
                # expired token -> one TOTP auto-relogin attempt, then retry
                if self._is_auth_error(data) and self._try_auto_relogin():
                    return self.get_quotes(symbols)
                return None
            result: Dict[str, Dict] = {}
            for item in data.get('d', []):
                v = item.get('v', {}) or {}
                key = v.get('symbol') or item.get('n')
                if key:
                    result[key] = v
            return result
        except (requests.exceptions.RequestException, ValueError) as exc:
            logger.error('Quotes request failed: %s', exc)
            return None

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """Fetch the last traded price (LTP) for a Fyers symbol."""
        quotes = self.get_quotes([symbol])
        if quotes:
            quote = next(iter(quotes.values()), None)
            if quote and quote.get('lp') is not None:
                return float(quote['lp'])
        return None

    @staticmethod
    def _timeframe_to_resolution(timeframe: str) -> str:
        """Convert project timeframe strings to Fyers resolution codes."""
        mapping = {
            '1m': '1', '2m': '2', '3m': '3', '5m': '5', '10m': '10',
            '15m': '15', '20m': '20', '30m': '30', '45m': '45',
            '1h': '60', '60m': '60', '2h': '120', '4h': '240',
            '1d': '1D', '1D': '1D', '1w': '1W', '1M': '1M',
        }
        return mapping.get(timeframe, '5')

    def logout(self) -> bool:
        """Clear the in-memory token (does not revoke it server-side)."""
        self.access_token = None
        return True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_retry_after(response) -> float:
        """Seconds to wait from an HTTP 429 Retry-After header.

        Handles integer seconds and HTTP-date formats.
        """
        raw = response.headers.get("Retry-After")
        if not raw:
            return 0.0
        try:
            return max(0.0, float(raw))
        except ValueError:
            try:
                import email.utils
                dt = email.utils.parsedate_to_datetime(raw)
                if dt is None:
                    return 0.0
                return max(0.0, (dt - datetime.now(IST)).total_seconds())
            except (ValueError, TypeError):
                return 0.0


    def _format_candles(self, candles: List) -> List[Dict]:
        """
        Convert raw Fyers candles to standard dicts.

        Fyers format: [epoch_seconds, open, high, low, close, volume]
        Epochs represent exchange time (IST).
        """
        formatted = []
        for candle in candles:
            if len(candle) >= 6:
                formatted.append({
                    'datetime': datetime.fromtimestamp(int(candle[0]), tz=IST),
                    'open': float(candle[1]),
                    'high': float(candle[2]),
                    'low': float(candle[3]),
                    'close': float(candle[4]),
                    'volume': float(candle[5]),
                })
        return formatted

    def _rate_limit(self) -> None:
        """Enforce a simple client-side rate limit between requests."""
        min_interval = 1.0 / max(1, API_RATE_LIMIT_PER_SECOND)
        now = time.time()
        if self._last_request_time is not None:
            elapsed = now - self._last_request_time
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)
        self._last_request_time = time.time()


# Module-level shared client (lazy singleton)
_client: Optional[FyersAPI] = None
# .env mtime when the client was last (re)built - used for hot-reload
_client_env_mtime: Optional[float] = None


def _read_env_token() -> str:
    """Re-read FYERS_ACCESS_TOKEN from .env into os.environ (override=True).

    Needed because os.environ is only populated once at import time; when
    the .env file is rewritten (e.g. by login.py in another process), the
    long-running process must refresh it before building a new client.
    """
    import os
    from dotenv import load_dotenv
    if ENV_FILE.exists():
        load_dotenv(ENV_FILE, override=True)
    token = os.getenv('FYERS_ACCESS_TOKEN', '')
    if token:
        return token
    # Cloud fallback: Streamlit Community Cloud stores credentials in
    # st.secrets (no .env file exists there).
    try:
        import streamlit as st
        val = st.secrets.get('FYERS_ACCESS_TOKEN')
        if val:
            return str(val)
    except Exception:
        pass
    return ''


def get_fyers_api() -> FyersAPI:
    """Return a shared FyersAPI instance.

    Hot-reload: if the .env file changes on disk while this process is
    alive (e.g. the user re-logs in via login.py, which rewrites
    FYERS_ACCESS_TOKEN), the shared client is automatically rebuilt with
    the fresh token - no restart of the Streamlit dashboard needed.
    """
    global _client, _client_env_mtime
    try:
        env_mtime = ENV_FILE.stat().st_mtime if ENV_FILE.exists() else None
    except OSError:
        env_mtime = None

    if _client is None or (
        env_mtime is not None and env_mtime != _client_env_mtime
    ):
        fresh_token = _read_env_token()
        if _client is None or fresh_token != _client.access_token:
            action = 'rebuilt' if _client is not None else 'created'
            _client = FyersAPI(access_token=fresh_token or None)
            logger.info('Fyers API client %s', action)
            if fresh_token:
                logger.info('Using FYERS_ACCESS_TOKEN from .env (mtime=%s)',
                            env_mtime)
        _client_env_mtime = env_mtime
    return _client
