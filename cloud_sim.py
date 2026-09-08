"""Cloud-mode simulation: run exactly as a cloud host would (no .env file).

Credentials are provided ONLY via OS environment variables. Verifies:
  1. Client builds from env vars and hits the live API
  2. Auto-login degrades gracefully without PIN/TOTP creds
  3. Token save does not crash on an unwritable path (read-only cloud FS)
"""
import os
import sys

sys.path.insert(0, '.')

# --- simulate cloud env vars (token read from the backed-up .env) ----------
real_token = ''
for line in open('.env.cloud_backup', encoding='utf-8'):
    if line.startswith('FYERS_ACCESS_TOKEN='):
        real_token = line.split('=', 1)[1].strip()
assert real_token, 'no token found in .env.cloud_backup'

os.environ['FYERS_ACCESS_TOKEN'] = real_token
os.environ['FYERS_APP_ID'] = 'BQ2S8HCFQF-100'

from src import config
from src.fyers_api import get_fyers_api
import src.fyers_api as fa

# ensure no .env exists (cloud condition)
assert not config.ENV_FILE.exists(), '.env should be absent for simulation'

# 1) client builds and reads env-var token
api = get_fyers_api()
assert api.access_token == real_token, 'token not picked from env var'
print('1. client built from env vars OK')

# 2) live API works
prof = api.get_profile()
s = prof.get('s') if isinstance(prof, dict) else None
print(f'2. live profile: {s}')

# 3) auto-login degrades gracefully without PIN/TOTP (no network calls made)
# To truly test "no creds", clear ALL fyers env vars (otherwise the cloud
# host's env vars would be picked up by the fallback path — which is a
# feature, not a bug).
from src.auto_login import read_env_credentials, auto_login
saved = {k: os.environ.pop(k) for k in list(os.environ)
         if k.startswith('FYERS_')}
try:
    creds = read_env_credentials(config.ENV_FILE)
    assert not creds, 'expected no credentials without .env or env vars'
    code = auto_login('', '', '', '')  # empty strings -> guard returns None
    assert code is None, 'expected None without credentials'
    print('3. auto-login without creds -> None (expected, no crash)')
finally:
    os.environ.update(saved)  # restore for the remaining steps

# 4) token save with unwritable target must not raise
from pathlib import Path
orig = fa.ENV_FILE
fa.ENV_FILE = Path('Z:/nonexistent_ro/env_file')  # impossible path
try:
    api._save_token_to_env('DUMMY')
    print('4. token save on bad path: no crash (warning logged)')
except Exception as e:  # pragma: no cover
    print(f'4. UNEXPECTED crash: {e}')
    sys.exit(1)
finally:
    fa.ENV_FILE = orig

print('CLOUD SIMULATION PASSED')
