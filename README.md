# NSE Stock Scanner

A Python-based stock market scanner for Indian NSE stocks that identifies stocks near Traditional Pivot Point levels and calculates the custom Willy indicator.

## Features

- **Traditional Pivot Points**: Calculates P, R1-R5, S1-S5 levels
- **Willy Indicator**: Custom Williams %R-style indicator with EMA smoothing
- **Historical Date Scanning**: Scan for any past date, not just today
- **Multiple Timeframes**: 5m, 15m, 30m, 1h, 1d
- **Configurable Strategies**: Pivot-only or Pivot + Willy modes
- **NSE Calendar**: Handles weekends and holidays
- **Secure**: API credentials via environment variables

## Project Structure

```
nse_stock_scanner/
├── main.py                  # CLI entry point
├── config.py                # Configuration settings
├── requirements.txt         # Python dependencies
├── .env.example             # Environment variable template
├── README.md                # This file
├── data/
│   ├── stocks/              # Stock universe data
│   ├── pivots/              # Calculated pivot levels
│   └── cache/               # Cached candle data
├── src/
│   ├── fyers_api.py         # Fyers API client
│   ├── instruments.py       # Stock universe (Nifty 50)
│   ├── candles.py           # Candle data handling
│   ├── pivots.py            # Pivot point calculations
│   ├── willy.py             # Willy indicator calculations
│   ├── scanner.py           # Main scanner logic
│   ├── signals.py           # Configurable signal strategies
│   ├── utils.py             # Date/calendar utilities
│   └── scheduler.py         # Market session scheduling
├── tests/                   # Unit tests
├── results/                 # Scanner output
└── logs/                    # Log files
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your Fyers API credentials
```

### 3. Run Unit Tests

```bash
python main.py test
```

### 4. Run Scanner (Phase 1 - Sample Data)

```bash
# Scan today with sample data
python main.py scan

# Scan for a specific historical date
python main.py scan --date 2026-09-01

# Scan with custom parameters
python main.py scan --timeframe 15m --distance 0.5 --mode pivot_willy

# Calculate pivots for a date
python main.py pivots --date 2026-09-01
```

### 5. Run the Web Dashboard

```bash
streamlit run dashboard.py
```

Opens at http://localhost:8501. In the sidebar you can pick:

- **Universe** — full Nifty 50 or a single stock
- **Scan date** — any date within the last year (historical scanning)
- **Timeframe** — 5m / 15m / 30m / 1h / 1d / ALL
- **Max distance** — slider plus one-click presets (0.10 / 0.20 / 0.25 / 0.50 / 1.00 %)
- **Scan mode** — pivot or pivot_willy
- **Data source** — Fyers (live) or Sample (offline)

Main area shows:

- Summary metrics (scan date, previous trading day, stocks scanned, matches)
- **Instant filters** (symbol search, Willy zone, signal, pivot side) — these
  re-filter the already-fetched data without new API calls
- Ranked results table (closest to a pivot first) with CSV download
- **Pivot Inspector** — per-stock full pivot table (prev-day H/L/C shown),
  Willy/EMA metrics and a Willy chart, using cached scan data

## Willy Indicator

The custom Willy indicator is calculated as:

```
t**: Willy >= -20
- **Oversold**: Willy <= -80
- **Neutral**: -80 < Willy < -20

### Signals
- **Bullish Cross**: Willy crosses above its EMA
- **Bearish Cross**: Willy crosses below its EMA

## Traditional Pivot Points

Calculated using previous trading day's High, Low, Close:

```
P  = (H + L + C) / 3
R1 = 2P - L
R2 = P + (H - L)
R3 = H + 2(P - L)
R4 = H + 3(P - L)
R5 = H + 4(P - L)
S1 = 2P - H
S2 = P - (H - L)
S3 = L - 2(H - P)
S4 = L - 3(H - P)
S5 = L - 4(H - P)
```

### Pivot Timeframes (D / W / M / Q / Y / Auto)

Like TradingView, pivots for the **current** period are computed from the
**previous completed** period's H/L/C.  Pick a specific period from the
dropdown, or choose **Auto** to match TradingView's behaviour automatically:

- **Auto mapping** (intraday chart on the left picks Daily, etc.):
  - 5m / 15m / 30m → **Daily** pivots
  - 1h / 4h → **Weekly** pivots
  - 1D chart → **Monthly** pivots
- Explicit **D / W / M / Q / Y** override Auto for that scan.
- The **Pivot Inspector** resolves the period the same way the scan does,
  and shows the underlying **source candle date + H/L/C**, so results can
  be cross-checked against a TradingView chart 1:1.

### Deploy to Streamlit Community Cloud (free, recommended)

Streamlit Community Cloud hosts Streamlit apps natively and is free.

1. Push the project to **GitHub** (your `.gitignore` already excludes
   `.env`, caches, logs, and any token files).
2. Open https://share.streamlit.io → **New app** → pick the repo,
   branch `main`, main file `dashboard.py` → **Deploy**.
3. Add credentials in **Settings → Secrets** (paste as TOML):

   ```toml
   FYERS_APP_ID = "BQ2S8HCFQF-100"
   FYERS_APP_SECRET = "your_app_secret"
   FYERS_REDIRECT_URL = "https://trade.fyers.in/api-login/redirect-uri/index.html"
   FYERS_ACCESS_TOKEN = "your_daily_jwt"

   # OPTIONAL - enables automatic daily re-login in the cloud:
   FYERS_USER_ID = "YC00160"
   FYERS_PIN = "1234"
   FYERS_TOTP_SECRET = "YOUR_BASE32_TOTP_SECRET"
   ```

   The app reads these automatically — `.env`, environment variables and
   `st.secrets` are all supported, with hot-reload when you update them.

Notes:
- The cloud filesystem is **ephemeral**: candle caches last for the app
  session only, and results/logs are not persisted. Scans still work fully.
- Free cloud apps sleep after inactivity; the first scan after a wake-up
  takes a little longer.
- If you skip the auto-login secrets, update `FYERS_ACCESS_TOKEN` in
  Secrets each morning (cloud + `.env` flows are independent).

### Deploy to Render (onrender.com) — one click

The repo ships a `render.yaml` Blueprint.

1. Push the project to **GitHub** (your `.gitignore` already excludes
   `.env`, caches, and logs).
2. Open https://dashboard.render.com/blueprint/new → connect the repo.
3. In **Settings → Environment → Secrets**, add your Fyers credentials
   (these must NEVER be committed):

   | Name | Value |
   |------|-------|
   | `FYERS_APP_ID` | your App ID (e.g. `BQ2S8HCFQF-100`) |
   | `FYERS_APP_SECRET` | your app secret |
   | `FYERS_REDIRECT_URL` | your redirect URL |
   | `FYERS_ACCESS_TOKEN` | your daily-access JWT |

4. Deploy — builds on push, live at the assigned Render URL.

Locally, start the dashboard with:

```bash
streamlit run dashboard.py   # http://localhost:8501
```


## Fyers API Integration

This project uses Fyers API v3 for market data. 

### Setup Fyers API

1. Create a Fyers account at [Fyers](https://fyers.in/)
2. Create an app at [Fyers API Dashboard](https://myapi.fyers.in/) to get:
   - App ID
   - App Secret
   - Redirect URL
3. Copy `.env.example` to `.env`
4. Fill in your credentials:
   ```
   FYERS_APP_ID=your_app_id
   FYERS_APP_SECRET=your_app_secret
   FYERS_REDIRECT_URL=https://127.0.0.1:8080
   FYERS_ACCESS_TOKEN=your_access_token
   ```

### Getting Access Token

1. Run the scanner - it will provide a URL to visit
2. Login to Fyers and authorize the app
3. Copy the auth code from the redirect URL
4. Run: `api.login(auth_code='your_auth_code')`

### Fyers Symbol Format

Fyers uses the following symbol format for NSE stocks:
- Equity: `NSE:SBIN-EQ`, `NSE:RELIANCE-EQ`
- Index: `NSE:NIFTY50-INDEX`

## Configuration

Edit `src/config.py` to customize:

- `MAX_DISTANCE_PERCENT`: Default 0.50%
- `WILLY_LENGTH`: Default 21
- `WILLY_EMA_LENGTH`: Default 13
- `TIMEFRAMES`: ['5m', '15m', '30m', '1h', '1d']
- `STOCK_UNIVERSES`: ['nifty50', 'nifty100', 'nifty200', 'nifty500']

## Testing

```bash
# Run all tests
python main.py test

# Run specific test file
pytest tests/test_willy.py -v
pytest tests/test_pivots.py -v
pytest tests/test_scanner.py -v
pytest tests/test_dates.py -v
```

## License

This project is for educational and research purposes only. Not financial advice.

upper = highest HIGH over previous 21 candles
lower = lowest LOW over previous 21 candles
willy = 100 * (close - upper) / (upper - lower)
willy_ema = 13-period EMA of willy
```

### Zones
- **Overbough