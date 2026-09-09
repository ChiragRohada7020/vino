"""
Fyers TOTP Auto-Login
=====================

Fyers access tokens expire DAILY. With the optional credentials below in
.env, the scanner re-authenticates BY ITSELF when a token expires - no
manual login.py ritual:

    FYERS_USER_ID      = YC00160            (Fyers id, no dashes)
    FYERS_PIN          = 1234               (login PIN)
    FYERS_TOTP_SECRET  = ABCDEFGHIJK...     (base32 secret from
                        MyAccount -> TOTP -> 'show secret')
    FYERS_AUTO_LOGIN   = 1                  (default on; set 0 to disable)

Flow (Fyers v3, 'vagator' endpoints):
  1. send_login_otp_v2  (fy_id base64)            -> request_key
  2. verify_otp         (request_key + TOTP)      -> temp access_token
  3. verify_pin_v2      (pin base64)              -> temp access_token
  4. GET /api/v3/token  (Bearer temp)             -> redirect Url containing
                                                     auth_code=...
  5. exchange auth_code via /api/v3/validate-authcode  -> access_token
     (reuses FyersAPI.exchange_auth_code, which saves to .env)

All responses are parsed defensively; any failure returns None and the
caller falls back to the manual login.py flow.
"""
import base64
import logging
import re
import time
import uuid
from typing import Optional
from urllib.parse import urlparse, parse_qs

import requests

try:
    import pyotp
except ImportError:                                   # pragma: no cover
    pyotp = None

logger = logging.getLogger(__name__)

API_BASE = 'https://api-t1.fyers.in/api/v2'
TIMEOUT = 30


def generate_totp(secret: str) -> Optional[str]:
    """6-digit TOTP from a base32 secret (handles spaces/case)."""
    if not pyotp or not secret:
        return None
    try:
        return pyotp.TOTP(secret.replace(' ', '').upper()).now()
    except Exception as exc:                          # bad secret formats
        logger.error('TOTP generation failed: %s', exc)
        return None


def _b64(text: str) -> str:
    """Fyers vagator endpoints expect base64-encoded fy_id / pin."""
    return base64.b64encode(text.encode()).decode()


def _post_json(url: str, payload: dict) -> dict:
    resp = requests.post(url, json=payload, timeout=TIMEOUT,
                         headers={'Content-Type': 'application/json'})
    try:
        return resp.json()
    except ValueError:
        return {'s': 'error', 'message': f'non-JSON HTTP {resp.status_code}'}


def _get_json(url: str, params: dict = None) -> dict:
    resp = requests.get(url, params=params, timeout=TIMEOUT)
    try:
        return resp.json()
    except ValueError:
        return {'s': 'error', 'message': f'non-JSON HTTP {resp.status_code}'}


def extract_auth_code(url: str) -> Optional[str]:
    """Pull auth_code=... out of the redirect Url returned by step 4."""
    if not url:
        return None
    try:
        qs = parse_qs(urlparse(url).query)
        code = (qs.get('auth_code') or [None])[0]
        return code or None
    except Exception:                                 # pragma: no cover
        return None


def auto_login(app_id: str, user_id: str, pin: str,
               totp_secret: str) -> Optional[str]:
    """
    Run the full TOTP flow and return a fresh AUTH CODE.

    The caller exchanges it for an access token via
    FyersAPI.exchange_auth_code() (which also saves it to .env).

    Returns None on any failure (errors logged, never raised).
    """
    if not (app_id and user_id and pin and totp_secret):
        logger.debug('auto_login: missing credentials, skipping')
        return None
    if pyotp is None:
        logger.error("auto_login: pyotp missing - run 'pip install pyotp'")
        return None

    otp = generate_totp(totp_secret)
    if not otp:
        return None
    otp = int(otp)

    session = requests.Session()

    # 1) send login OTP challenge (request_key for the TOTP step)
    r1 = _post_json(f'{API_BASE}/send_login_otp',
                    {'fy_id': _b64(user_id), 'app_type': '2'})
    request_key = r1.get('request_key') or r1.get('data', {}).get('request_key')
    if not request_key:
        logger.error('auto_login step 1 failed: %s', r1)
        return None

    # 2) verify TOTP
    r2 = _post_json(f'{API_BASE}/verify_totp',
                    {'request_key': request_key, 'totp': str(otp)})
    temp_token = r2.get('access_token') or r2.get('data', {}).get('access_token')
    if not temp_token:
        logger.error('auto_login step 2 failed (TOTP): %s', r2)
        return None

    # 3) verify PIN
    time.sleep(0.3)
    r3 = _post_json(f'{API_BASE}/verify_pin',
                    {'request_key': temp_token, 'identity_type': 'pin',
                     'identifier': _b64(pin)})
    pin_token = r3.get('access_token') or r3.get('data', {}).get('access_token')
    if not pin_token:
        logger.error('auto_login step 3 failed (PIN): %s', r3)
        return None

    # 4) request the app authorization -> redirect Url with auth_code
    time.sleep(0.3)
    try:
        r4 = session.get(
            f'{API_BASE}/token',
            params={'client_id': app_id, 'front_id': user_id,
                    'is_new_token': 'true', 'app_id': '2',
                    'device_id': str(uuid.uuid4()),
                    'nonce': str(uuid.uuid4())},
            headers={'Authorization': f'Bearer {pin_token}'},
            timeout=TIMEOUT,
        )
        r4.raise_for_status()
        data = r4.json()
    except (requests.exceptions.RequestException, ValueError) as exc:
        logger.error('auto_login step 4 failed: %s', exc)
        return None

    # Url may be nested under data.Url / body.Url / Url
    url = (data.get('Url') or data.get('data', {}).get('Url')
           or data.get('body', {}).get('Url'))
    auth_code = extract_auth_code(url)
    if not auth_code:
        logger.error('auto_login: no auth_code in response: %s',
                     str(data)[:300])
        return None

    logger.info('auto_login: auth_code obtained, exchanging for access token')
    return auth_code


def read_env_credentials(env_file) -> dict:
    """
    Credentials from every supported source, merged: .env file, OS
    environment variables and st.secrets (see config.read_credentials).

    Re-evaluated on every call so a long-running dashboard always uses the
    LATEST credentials - even if they were added after this process
    started (e.g. on Streamlit Cloud, where they live in st.secrets).
    """
    from .config import read_credentials
    return read_credentials(env_file)