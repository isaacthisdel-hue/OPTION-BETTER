"""Live scanner service.

For each symbol in the universe: pull data from the provider, compute indicators,
build a Candidate, score it, and persist an Observation. Qualified scores spawn a
paper setup. Everything the scanner used is stored so history is reproducible.

Free-tier reality: we can't scan the whole market on 60 calls/min, so the
universe is either an explicit WATCHLIST or today's earnings names, capped at
MAX_UNIVERSE_SIZE.
"""
from __future__ import annotations

import datetime as dt
import time

import pytz
from sqlalchemy.orm import Session

from ..adapters import get_provider
from ..adapters.base import MarketDataProvider
from ..core.config import get_settings
from ..models import Observation, PaperTrade, StrategyVersion
from ..services.paper_engine import build_equity_setup
from . import indicators as ind
from .config import StrategyConfig
from .scorer import Candidate, score_candidate
from ..backtesting.reversal_model import estimate_reversal


def _et_minute_of_day(epoch: int, tz: str) -> int:
    d = dt.datetime.fromtimestamp(epoch, pytz.timezone(tz))
    return d.hour * 60 + d.minute


async def build_candidate(
    provider: MarketDataProvider, symbol: str, cfg: StrategyConfig,
    now_epoch: int, tz: str, catalyst: str | None,
) -> Candidate | None:
    quote = await provider.quote(symbol)
    if not quote or not quote.get("price") or not quote.get("prev_close"):
        return None

    price = quote["price"]
    prev_close = quote["prev_close"]
    move = ind.move_pct(price, prev_close)

    # intraday bars for the session so far
    session_start = now_epoch - 8 * 3600
    bars = await provider.intraday_bars(symbol, "1", session_start, now_epoch)

    vwap_val = ind.vwap_as_of(bars, now_epoch) if bars else None
    vwap_dist = ind.vwap_distance_pct(price, vwap_val)
    mins_since_low = ind.minutes_since_new_low(bars, now_epoch) if bars else None
    higher_low = ind.has_higher_low(bars, now_epoch) if bars else None
    reclaim = ind.reclaimed_vwap(bars, now_epoch) if bars else None

    # daily bars for average volume
    daily = await provider.daily_bars(symbol, 30)
    avg_vol = None
    if daily:
        vols = [b["v"] for b in daily[-20:] if b["v"]]
        avg_vol = sum(vols) / len(vols) if vols else None
    today_vol = sum(b["v"] for b in bars) if bars else None
    vol_ratio = ind.volume_ratio(today_vol, avg_vol) if (today_vol and avg_vol) else None

    # fundamentals + surprise (cached upstream ideally; scarce on free tier)
    surprise = await provider.earnings_surprise(symbol) if catalyst == "earnings" else None
    funda = await provider.fundamentals(symbol)

    spark = None
    if bars:
        step = max(1, len(bars) // 40)
        spark = [round(b["c"], 2) for b in bars[::step]]

    return Candidate(
        symbol=symbol,
        as_of_epoch=now_epoch,
        catalyst=catalyst,
        move_pct=move,
        volume_ratio=vol_ratio,
        vwap_distance_pct=vwap_dist,
        minutes_since_new_low=mins_since_low,
        higher_low=higher_low,
        vwap_reclaim=reclaim,
        eps_surprise_pct=(surprise or {}).get("eps_surprise_pct"),
        revenue_surprise_pct=(surprise or {}).get("revenue_surprise_pct"),
        pe=(funda or {}).get("pe"),
        forward_pe=(funda or {}).get("forward_pe"),
        price_to_sales=(funda or {}).get("price_to_sales"),
        market_cap=(funda or {}).get("market_cap"),
        price=price,
        spark=spark,
    )


async def scan_once(db: Session, cfg: StrategyConfig, strat_version_id: int,
                    reversal_model: dict | None = None) -> list[dict]:
    """Run one scan pass over the universe. Returns scored dicts for the API/SSE."""
    settings = get_settings()
    provider = get_provider()
    now = int(time.time())
    et_min = _et_minute_of_day(now, settings.market_tz)

    universe, catalysts = await _resolve_universe(provider, settings)
    results: list[dict] = []

    try:
        for symbol in universe:
            cand = await build_candidate(
                provider, symbol, cfg, now, settings.market_tz,
                catalysts.get(symbol),
            )
            if cand is None:
                continue

            score = score_candidate(cand, cfg)

            obs = Observation(
                symbol=symbol, as_of_epoch=now, strategy_version_id=strat_version_id,
                price=cand.price, move_pct=cand.move_pct, volume_ratio=cand.volume_ratio,
                vwap_distance_pct=cand.vwap_distance_pct, higher_low=cand.higher_low,
                vwap_reclaim=cand.vwap_reclaim, eps_surprise_pct=cand.eps_surprise_pct,
                revenue_surprise_pct=cand.revenue_surprise_pct, catalyst=cand.catalyst,
                score_total=score.total, status=score.status,
                components_json=[c.__dict__ for c in score.components],
                snapshot_json=cand.__dict__,
            )
            db.add(obs)

            # Qualified + within the entry window -> hypothetical paper setup.
            in_window = cfg.earliest_entry_min <= et_min <= cfg.observation_end_min
            if score.status == "QUALIFIED" and in_window and cand.price:
                setup = build_equity_setup(symbol, cand.price, now, score.total, cfg)
                db.add(PaperTrade(
                    symbol=symbol, strategy_version_id=strat_version_id,
                    setup=setup.setup, instrument="equity",
                    entry_price=setup.entry_price, stop_price=setup.stop_price,
                    target1=setup.target1, target2=setup.target2,
                    entry_epoch=setup.entry_epoch, score_at_entry=score.total,
                    components_json=[c.__dict__ for c in score.components],
                ))

            est = estimate_reversal(cand.move_pct, reversal_model)
            d = score.to_dict()
            d.update({"price": cand.price, "move_pct": cand.move_pct,
                      "volume_ratio": cand.volume_ratio,
                      "vwap_distance_pct": cand.vwap_distance_pct,
                      "higher_low": cand.higher_low, "vwap_reclaim": cand.vwap_reclaim,
                      "catalyst": cand.catalyst,
                      "estimated_reversal_pct": est["estimated_reversal_pct"],
                      "reversal_tier": est["tier"],
                      "reversal_confidence": est["confidence"],
                      "option_aim": est["option_aim"],
                      "spark": cand.spark})
            results.append(d)

        db.commit()
    finally:
        await provider.aclose()

    results.sort(key=lambda r: r["total"], reverse=True)
    return results


async def _resolve_universe(provider, settings) -> tuple[list[str], dict[str, str]]:
    """Union of the watchlist and today's earnings names, deduped, capped."""
    watch = list(settings.watchlist_symbols)
    catalysts = {s: "earnings" for s in watch}
    cal_syms: list[str] = []
    try:
        today = dt.date.today().isoformat()
        cal = await provider.earnings_calendar(today, today)
        cal_syms = [e["symbol"] for e in cal if e.get("symbol")]
    except Exception:
        cal_syms = []
    for sym in cal_syms:
        catalysts.setdefault(sym, "earnings")
    universe = list(dict.fromkeys(watch + cal_syms))[: settings.max_universe_size]
    return universe, catalysts
