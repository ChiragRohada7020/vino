"""
Fyers Login Helper
==================

Fyers access tokens expire DAILY. When scans stop returning data with
"Your token has expired", regenerate it in two steps:

Step 1 - get a fresh auth code:
    python login.py
    -> opens/prints the Fyers authorize URL. Log in, approve the app,
       copy the `code=...` value from the redirected URL.

Step 2 - exchange it for a new access token:
    python login.py --code <PASTE_THE_CODE_HERE>
    -> exchanges it, saves the token to .env, and verifies your profile.

Optional - test TOTP auto-login (no browser needed):
    python login.py --auto
    -> requires FYERS_USER_ID / FYERS_PIN / FYERS_TOTP_SECRET in .env.
       If it works here, the scanner will re-login BY ITSELF whenever the
       daily token expires.
"""

import argparse
import sys

from src.fyers_api import FyersAPI, ENV_FILE


def run_auto_login_test(api: FyersAPI) -> None:
    """Exercise the production auto-relogin path end to end."""
    from src.auto_login import read_env_credentials

    creds = read_env_credentials(ENV_FILE)
    if not (creds.get('FYERS_USER_ID') and creds.get('FYERS_PIN')
            and creds.get('FYERS_TOTP_SECRET')):
        print('Auto-login NOT configured. Add these keys to .env:')
        print('  FYERS_USER_ID=<your fyers id, e.g. YC00160>')
        print('  FYERS_PIN=<your login pin>')
        print('  FYERS_TOTP_SECRET=<base32 secret from MyAccount -> TOTP>')
        sys.exit(1)

    print('Testing TOTP auto-login (production path)...')
    # Blank the token so _try_auto_relogin runs exactly as it would on an
    # expired-token API failure.
    api.access_token = None
    ok = api._try_auto_relogin()
    if not ok:
        print('FAILED - auto-login did not produce a valid token. '
              'Check FYERS_USER_ID / FYERS_PIN / FYERS_TOTP_SECRET in .env '
              '(and logs/ for the failing step).')
        sys.exit(1)

    profile = api.get_profile()
    if profile and profile.get('s') == 'ok':
        d = profile.get('data', {})
        print(f"OK - auto-login works! Logged in as {d.get('name', '?')} "
              f"({d.get('display_name', '')}). New token saved to .env.")
        print('From now on the scanner re-logins automatically every day.')
    else:
        print(f'WARNING - token refreshed but profile check failed: {profile}')
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Generate/refresh the Fyers access token (.env)')
    parser.add_argument('--code', type=str,
                        help='Auth code from the redirect URL (step 2)')
    parser.add_argument('--auto', action='store_true',
                        help='Test the TOTP auto-login flow '
                             '(requires FYERS_USER_ID/PIN/TOTP_SECRET in .env)')
    args = parser.parse_args()

    api = FyersAPI()

    if args.auto:
        run_auto_login_test(api)
        return

    if not args.code:
        print('=' * 64)
        print('STEP 1 - open this URL in your browser and log in:')
        print('=' * 64)
        print()
        print(api.get_auth_code_url())
        print()
        print('After approving, you will be redirected to a URL like:')
        print('  https://trade.fyers.in/api-login/redirect-uri/index.html')
        print('                                 ?code=eyJhbGciOi...&status=ok')
        print()
        print('Copy the code value, then run:')
        print('  python login.py --code <PASTE_THE_CODE_HERE>')
        return

    print('Exchanging auth code for a fresh access token...')
    token = api.exchange_auth_code(args.code, save=True)
    if not token:
        print('FAILED - could not exchange the code (expired or already '
              'used). Generate a new one: python login.py')
        sys.exit(1)

    print('Token saved to .env')
    profile = api.get_profile()
    if profile and profile.get('s') == 'ok':
        d = profile.get('data', {})
        print(f"OK - logged in as {d.get('name', '?')} ({d.get('display_name', '')})")
        print('You can now run scans: python main.py scan / streamlit run dashboard.py')
    else:
        print(f'WARNING - token saved but profile check failed: {profile}')
        sys.exit(1)


if __name__ == '__main__':
    main()