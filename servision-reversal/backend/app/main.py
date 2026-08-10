"""FastAPI application.

Endpoints:
  GET  /health                     health check (Railway)
  GET  /api/candidates             latest scored candidates
  POST /api/scan                   trigger one scan pass now
  GET  /api/paper-trades           list paper trades
  GET  /api/stats                  strategy statistics
  GET  /api/projection             estimated paper revenue (from tracked results)
  POST /api/backtest               run a backtest (events supplied or synthetic)
  GET  /api/strategy-versions      list versions
  POST /api/strategy-versions      create a version
  GET  /api/stream                 SSE stream of latest scan results
"""
from __future__ import annotations

import asyncio
import json

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from .core.config import get_settings
from .core.db import get_db, engine
from .core.market import market_status
from .models import Base, Backtest, Observation, PaperTrade, StrategyVersion
from .scanner.config import StrategyConfig
from .scanner.service import scan_once
from .services.stats import paper_trade_stats, project_paper_revenue

settings = get_settings()
app = FastAPI(title="Reversal Research API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"], allow_headers=["*"],
)

# Latest scan results kept in memory for the SSE/candidates endpoints.
_latest: list[dict] = []


@app.on_event("startup")
def _startup():
    Base.metadata.create_all(bind=engine)
    # Ensure a default strategy version exists.
    from .core.db import SessionLocal
    db = SessionLocal()
    try:
        exists = db.execute(select(StrategyVersion)).first()
        if not exists:
            cfg = StrategyConfig()
            db.add(StrategyVersion(label=cfg.version_label,
                                   config_json=cfg.to_dict(), notes="default"))
            db.commit()
    finally:
        db.close()


def _active_version(db: Session) -> StrategyVersion:
    return db.execute(select(StrategyVersion).order_by(StrategyVersion.id.desc())).scalars().first()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/api/candidates")
def candidates():
    return {"candidates": _latest, "count": len(_latest)}


@app.get("/api/market-status")
def market_status_route():
    return market_status()


@app.post("/api/scan")
async def scan(force: bool = False, db: Session = Depends(get_db)):
    """Run one scan pass. If the US market is closed we short-circuit with a
    clear market_open=false payload (instead of scanning stale/empty data and
    appearing to hang). Pass ?force=true to scan anyway (e.g. to test a
    watchlist after hours)."""
    ms = market_status()
    if not ms["open"] and not force:
        return {"scanned": 0, "candidates": [], "market_open": False,
                "market_status": ms}
    global _latest
    sv = _active_version(db)
    cfg = StrategyConfig.from_dict(sv.config_json)
    _latest = await scan_once(db, cfg, sv.id)
    return {"scanned": len(_latest), "candidates": _latest,
            "market_open": ms["open"], "market_status": ms}


@app.get("/api/paper-trades")
def paper_trades(db: Session = Depends(get_db)):
    rows = db.execute(select(PaperTrade).order_by(PaperTrade.id.desc()).limit(200)).scalars().all()
    return {"paper_trades": [
        {"id": t.id, "symbol": t.symbol, "setup": t.setup, "instrument": t.instrument,
         "label": "QUALIFIED PAPER-TRADE SETUP", "entry_price": t.entry_price,
         "stop_price": t.stop_price, "target1": t.target1, "target2": t.target2,
         "status": t.status, "exit_price": t.exit_price, "exit_reason": t.exit_reason,
         "return_pct": t.return_pct, "score_at_entry": t.score_at_entry}
        for t in rows
    ]}


@app.get("/api/stats")
def stats(db: Session = Depends(get_db)):
    return paper_trade_stats(db)


@app.get("/api/projection")
def projection(capital: float = 10000.0, trades_per_day: float = 2.0,
               days: int = 5, db: Session = Depends(get_db)):
    return project_paper_revenue(db, capital=capital,
                                 trades_per_day=trades_per_day, days=days)


@app.get("/api/strategy-versions")
def list_versions(db: Session = Depends(get_db)):
    rows = db.execute(select(StrategyVersion).order_by(StrategyVersion.id.desc())).scalars().all()
    return {"versions": [
        {"id": v.id, "label": v.label, "config": v.config_json, "notes": v.notes}
        for v in rows
    ]}


@app.post("/api/strategy-versions")
def create_version(payload: dict, db: Session = Depends(get_db)):
    cfg = StrategyConfig.from_dict(payload.get("config", {}))
    v = StrategyVersion(label=payload.get("label", cfg.version_label),
                        config_json=cfg.to_dict(), notes=payload.get("notes", ""))
    db.add(v)
    db.commit()
    return {"id": v.id, "label": v.label}


@app.post("/api/backtest")
def backtest(payload: dict, db: Session = Depends(get_db)):
    """Run a backtest on REAL recent intraday data (Alpha Vantage). Needs a free
    ALPHAVANTAGE_API_KEY set in the environment. No synthetic fallback."""
    from .backtesting.engine import run_backtest
    from .backtesting.loader import load_recent_events, LoaderError
    from .backtesting.reversal_model import (
        build_reversal_model, equity_curve, per_stock_series,
    )
    from .core.config import get_settings

    settings = get_settings()
    sv = _active_version(db)
    cfg = StrategyConfig.from_dict(sv.config_json)

    if not settings.alphavantage_api_key:
        return {
            "available": False,
            "error": "No real-data key set. Add a free ALPHAVANTAGE_API_KEY to backtest on real market data.",
            "how": "alphavantage.co (free key, ~20s) -> Railway API service -> Variables -> ALPHAVANTAGE_API_KEY -> redeploy.",
        }

    try:
        events, meta = load_recent_events(settings)
    except LoaderError as e:
        return {"available": False, "error": str(e)}

    if not events:
        reqn = len(meta.get("tickers_requested") or [1])
        rl = meta.get("rate_limited", 0)
        if rl and rl >= reqn:
            msg = ("Alpha Vantage rate limit reached (free tier: 25 requests/day, 5/min). "
                   "Wait a minute - or until tomorrow if you've used 25 today - then retry.")
        elif rl:
            msg = ("Some tickers were rate-limited by Alpha Vantage (free: 25/day, 5/min). Wait a minute and retry.")
        else:
            msg = ("Loaded data but found no usable sessions for: "
                   + ", ".join(meta.get("tickers_requested", []))
                   + ". Try different BACKTEST_TICKERS on Railway.")
        return {"available": False, "error": msg, "meta": meta}

    result = run_backtest(events, cfg)
    result["available"] = True
    result["meta"] = meta
    result["reversal_model"] = build_reversal_model(events, cfg)
    result["equity_curve"] = equity_curve(result.get("trades", []))
    result["per_stock"] = per_stock_series(events, result.get("trades", []), cfg)

    bt = Backtest(strategy_version_id=sv.id, params_json=payload or {},
                  results_json=result["strategy"], label=(payload or {}).get("label", "real"))
    db.add(bt)
    db.commit()
    return result


@app.get("/api/stream")
async def stream():
    async def gen():
        while True:
            yield {"event": "candidates", "data": json.dumps(_latest)}
            await asyncio.sleep(settings.scan_interval_seconds)
    return EventSourceResponse(gen())
