# Reversal Research — Paper Trading & Strategy Research Tool

A **research and paper-trading** tool that scans the US stock market for a
short-term, catalyst-driven mean-reversion setup, scores candidates with a
transparent deterministic scoring engine, records **hypothetical** paper trades
(equity and simulated options), and measures whether the strategy actually has a
statistical edge via a backtester built to avoid look-ahead bias.

## What this tool is — and is not

- ✅ It scans **live** market data and scores candidates in real time.
- ✅ It records **hypothetical paper setups** with specific strikes/expiries and
  tracks simulated P/L.
- ✅ It backtests the strategy against historical data and reports edge metrics.
- ✅ It projects estimated paper P&L **from your own tracked results**, always
  shown next to the sample size behind it.
- ❌ It does **not** connect to a brokerage or place real orders.
- ❌ It does **not** present setups as "BUY CALL." Everything is labelled
  `QUALIFIED PAPER-TRADE SETUP` / `HISTORICAL PAPER SIMULATION`.

Every number the strategy produces is meant to be *measured*, not trusted. Until
the backtester shows an edge on out-of-sample data, treat all signals as
unproven hypotheses.

## Architecture

```
frontend (Next.js, Vercel)  ──SSE──>  backend (FastAPI, Railway)
                                          │
                                          ├── scanner package (deterministic scoring)
                                          ├── backtesting package (no-lookahead replay)
                                          ├── paper-trade engine
                                          └── PostgreSQL (append-only observations)
                                          │
                              data adapters ──> FMP + Finnhub (free tier)
```

The **same scoring code** runs in the live scanner and the backtester, so live
and historical results can't silently diverge.

## Repository layout

```
/backend        FastAPI app, scanner, backtester, paper engine, adapters
/frontend       Next.js dark dashboard
/database        Alembic migrations
/tests          pytest suite (scoring, VWAP, higher-low, no-lookahead, ...)
/docs           architecture, scoring spec, data-source notes
```

## Quick start (local)

See `docs/SETUP.md` for full steps. Short version:

```bash
# Backend
cd backend
cp .env.example .env        # fill in FMP_API_KEY and FINNHUB_API_KEY
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload

# Frontend
cd ../frontend
cp .env.example .env.local
npm install
npm run dev
```

## Deploy

See `docs/DEPLOY.md` for GitHub + Railway (backend/db/worker) and Vercel
(frontend). You set all secrets as environment variables in the Railway and
Vercel dashboards — no keys ever live in the repo.

## Data providers (v1: $0 tier)

- **Finnhub** — quotes, candles, earnings calendar, basic financials (free: 60 calls/min)
- **FMP** — fundamentals, earnings surprises, ratios (free: 250 calls/day)

Swap in Massive/Polygon for full real-time by adding a key and setting
`PROVIDER=massive` — the adapter interface is already there.

## License

Private / personal use.
