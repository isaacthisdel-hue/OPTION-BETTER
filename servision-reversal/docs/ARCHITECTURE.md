# Architecture

## Services

```
┌────────────────────┐         SSE / REST        ┌──────────────────────┐
│  Frontend (Vercel) │ ────────────────────────> │  API (Railway)       │
│  Next.js 14        │ <──────────────────────── │  FastAPI + uvicorn   │
└────────────────────┘                           └──────────┬───────────┘
                                                             │
                          ┌──────────────────────────────────┼───────────────┐
                          │                                   │               │
                  ┌───────▼────────┐                 ┌────────▼──────┐  ┌─────▼─────┐
                  │ Worker (Railway)│                 │ PostgreSQL    │  │ Data APIs │
                  │ scan + resolve  │ ───────────────>│ (Railway)     │  │ Finnhub   │
                  │ paper trades    │                 │ append-only   │  │ FMP       │
                  └─────────────────┘                 └───────────────┘  └───────────┘
```

## Backend packages

- `app/adapters` — data providers behind one interface (`MarketDataProvider`).
  `CompositeProvider` = Finnhub (market data) + FMP (fundamentals). Add a paid
  provider by writing one subclass; nothing else changes.
- `app/scanner` — the deterministic core:
  - `config.py` — all thresholds/weights (`StrategyConfig`), versionable.
  - `indicators.py` — pure market math, no-lookahead `_as_of` functions.
  - `scorer.py` — transparent additive scoring.
  - `service.py` — live scan: fetch → score → persist observation → maybe paper trade.
- `app/backtesting` — `engine.py` (replay + controls + metrics),
  `validation.py` (train/val/oos split), `sample.py` (synthetic demo data).
- `app/services` — `paper_engine.py` (build/track hypothetical trades),
  `stats.py` (statistics + revenue projection).
- `app/models` — SQLAlchemy models. **observations is append-only.**
- `app/main.py` — FastAPI routes + SSE. `app/worker.py` — background loop.

## Data model

- `strategy_versions` — immutable snapshots of `StrategyConfig`. Every
  observation and paper trade references the version that produced it, so
  changing thresholds never rewrites history.
- `observations` — **append-only**. One row per symbol per scan with the full
  score breakdown and a raw snapshot of the candidate facts. This is what lets
  you answer "what did the algorithm know about X at 12:17 PM?" — you replay the
  stored snapshot.
- `paper_trades` — hypothetical trades with entry/stop/targets and resolved
  outcomes. Never orders.
- `backtests` — stored backtest runs (params + results).

## Why the same scoring code runs live and in backtest

If the backtester reimplemented the scoring, live and historical results could
drift apart and you'd never fully trust either. Instead both call
`score_candidate()`. The only difference is the *source* of the candidate facts
(live provider vs stored historical bars), and the historical path is guarded so
it can't see the future.

## Free-tier constraints (v1)

- Universe is a watchlist or the day's earnings names, capped by
  `MAX_UNIVERSE_SIZE` — you can't scan the whole market on 60 calls/min.
- No free options history → option paper trades stubbed until a paid feed.
- Swap to real-time by adding `PROVIDER=massive` (+ key) and a Massive adapter.
