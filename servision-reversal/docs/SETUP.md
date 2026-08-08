# Local setup

## 0. Get free API keys (5 min)

- **Finnhub** — https://finnhub.io/register → copy the API key.
- **FMP (Financial Modeling Prep)** — https://site.financialmodelingprep.com/developer/docs → free plan → copy the API key.

Both have free tiers. Finnhub gives you 60 calls/min (quotes, candles, earnings
calendar). FMP gives you 250 calls/day (fundamentals, earnings surprises).

## 1. Backend

```bash
cd backend
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# edit .env: set FINNHUB_API_KEY and FMP_API_KEY.
# For local DB, install Postgres and set DATABASE_URL, OR use Railway's DB URL.
```

Create the tables:

```bash
alembic upgrade head
```

Run the API:

```bash
uvicorn app.main:app --reload
# http://localhost:8000/health  -> {"status":"ok"}
# http://localhost:8000/docs    -> interactive API docs
```

(Optional) run the background worker in a second terminal — it scans on an
interval during US market hours and resolves open paper trades:

```bash
python -m app.worker
```

## 2. Frontend

```bash
cd frontend
cp .env.example .env.local
# set NEXT_PUBLIC_API_BASE=http://localhost:8000
npm install
npm run dev
# http://localhost:3000
```

## 3. First run

1. Open the app → **Scanner** tab → **RUN SCAN**.
   - On the free tier the universe is your `WATCHLIST` (in `.env`) or, if empty,
     today's earnings names. To test any time, set e.g. `WATCHLIST=AAPL,MSFT,NVDA`.
2. **Backtest** tab → **RUN BACKTEST** — runs on a built-in synthetic sample so
   you can see the pipeline immediately. Replace with real historical data later
   (see `docs/DEPLOY.md` "Wiring real backtest data").

## Tests

```bash
cd backend
pytest ../tests -q
```

## Notes on the free tier

- You cannot scan the whole US market on 60 calls/min. Use a focused watchlist
  or the earnings-day universe (capped by `MAX_UNIVERSE_SIZE`).
- Options prices are not available free, so option paper trades are stubbed
  (`simulate_option_pl`) until you add a paid options feed.
- Finnhub's free intraday candle access has changed over time; if candles are
  gated on your key the app degrades gracefully (no crash) and you'll see fewer
  confirmation signals. FMP intraday can be used as a fallback by setting
  `PROVIDER=fmp`.
