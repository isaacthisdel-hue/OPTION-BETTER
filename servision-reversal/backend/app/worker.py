"""Background worker (separate Railway service).

Runs the scanner on an interval during market hours and resolves open paper
trades using intraday bars. Kept simple and defensive: any error in one cycle is
logged and the loop continues.

Run with:  python -m app.worker
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import time

import pytz
from sqlalchemy import select

from .adapters import get_provider
from .core.config import get_settings
from .core.db import SessionLocal, engine
from .models import Base, PaperTrade, StrategyVersion
from .scanner.config import StrategyConfig
from .scanner.service import scan_once
from .services.paper_engine import PaperSetup, track_equity_trade

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("worker")
settings = get_settings()


def _is_market_hours() -> bool:
    now = dt.datetime.now(pytz.timezone(settings.market_tz))
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


async def _resolve_open_trades():
    db = SessionLocal()
    provider = get_provider()
    try:
        open_trades = db.execute(
            select(PaperTrade).where(PaperTrade.status == "open",
                                     PaperTrade.instrument == "equity")
        ).scalars().all()
        now = int(time.time())
        for t in open_trades:
            bars = await provider.intraday_bars(t.symbol, "1", t.entry_epoch, now)
            later = [b for b in bars if b["t"] > t.entry_epoch]
            if not later:
                continue
            cfg = StrategyConfig()
            setup = PaperSetup(
                symbol=t.symbol, setup=t.setup, entry_price=t.entry_price,
                stop_price=t.stop_price, target1=t.target1, target2=t.target2,
                entry_epoch=t.entry_epoch, score_at_entry=t.score_at_entry or 0,
            )
            # Only force-close at end of day; else leave running intraday.
            end_of_day = not _is_market_hours()
            outcome = track_equity_trade(setup, later, cfg)
            reached = outcome["exit_reason"] in ("stop", "target1", "target2")
            if reached or end_of_day:
                t.status = "closed"
                t.exit_price = outcome["exit_price"]
                t.exit_epoch = outcome["exit_epoch"]
                t.exit_reason = outcome["exit_reason"]
                t.return_pct = outcome["return_pct"]
        db.commit()
    finally:
        await provider.aclose()
        db.close()


async def main_loop():
    Base.metadata.create_all(bind=engine)
    log.info("Worker started. Scan interval: %ss", settings.scan_interval_seconds)
    while True:
        try:
            if _is_market_hours():
                db = SessionLocal()
                try:
                    sv = db.execute(
                        select(StrategyVersion).order_by(StrategyVersion.id.desc())
                    ).scalars().first()
                    if sv is None:
                        cfg = StrategyConfig()
                        sv = StrategyVersion(label=cfg.version_label,
                                             config_json=cfg.to_dict(), notes="default")
                        db.add(sv)
                        db.commit()
                    cfg = StrategyConfig.from_dict(sv.config_json)
                    results = await scan_once(db, cfg, sv.id)
                    log.info("Scanned %d symbols", len(results))
                finally:
                    db.close()
                await _resolve_open_trades()
            else:
                log.info("Market closed — idle.")
                await _resolve_open_trades()  # close out EOD stragglers
        except Exception as e:  # noqa
            log.exception("Worker cycle error: %s", e)
        await asyncio.sleep(settings.scan_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main_loop())
