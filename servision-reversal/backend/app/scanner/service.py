"""Live scanner service.

Free market-data tiers rate-limit hard (~8 req/min), so a single scan can only
fetch a handful of names. To make this usable we:
  * fetch a rotating BATCH each scan (symbols not seen recently), concurrently,
    under a hard time budget so the request never hangs;
  * cache each scored candidate briefly and MERGE across scans, so results
    accumulate as you scan again instead of vanishing when a pass is thin.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time

import httpx

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
from .predict import predict_movement

# symbol -> {"fetched_at": epoch, "d": enriched_result_dict}
_CACHE: dict[str, dict] = {}
_MCAP_CACHE: dict[str, tuple] = {}   # symbol -> (fetched_at, billions|None)
_MCAP_TTL = 86400
LAST_SCAN_META: dict = {}


async def _market_cap_billions(provider, symbol: str):
    """Market cap in $B, cached for a day. Normalises provider units (Finnhub
    reports millions, FMP reports absolute dollars). Returns None if unknown."""
    e = _MCAP_CACHE.get(symbol)
    if e and (time.time() - e[0]) < _MCAP_TTL:
        return e[1]
    val = None
    try:
        f = await provider.fundamentals(symbol)
        raw = (f or {}).get("market_cap")
        if raw:
            raw = float(raw)
            val = raw / 1e9 if raw > 1e7 else raw / 1000.0  # dollars vs millions
    except Exception:  # noqa
        val = None
    _MCAP_CACHE[symbol] = (time.time(), val)
    return val


def _et_minute_of_day(epoch: int, tz: str) -> int:
    d = dt.datetime.fromtimestamp(epoch, pytz.timezone(tz))
    return d.hour * 60 + d.minute


async def build_candidate(
    provider: MarketDataProvider, symbol: str, cfg: StrategyConfig,
    now_epoch: int, tz: str, catalyst: str | None, lite: bool = False,
) -> Candidate | None:
    quote = await provider.quote(symbol)
    if not quote or not quote.get("price") or not quote.get("prev_close"):
        return None

    price = quote["price"]
    prev_close = quote["prev_close"]
    move = ind.move_pct(price, prev_close)

    session_start = now_epoch - 8 * 3600
    bars = await provider.intraday_bars(symbol, "1", session_start, now_epoch)

    vwap_val = ind.vwap_as_of(bars, now_epoch) if bars else None
    vwap_dist = ind.vwap_distance_pct(price, vwap_val)
    mins_since_low = ind.minutes_since_new_low(bars, now_epoch) if bars else None
    higher_low = ind.has_higher_low(bars, now_epoch) if bars else None
    reclaim = ind.reclaimed_vwap(bars, now_epoch) if bars else None

    daily = await provider.daily_bars(symbol, 30)
    avg_vol = None
    if daily:
        vols = [b["v"] for b in daily[-20:] if b["v"]]
        avg_vol = sum(vols) / len(vols) if vols else None
    today_vol = sum(b["v"] for b in bars) if bars else None
    vol_ratio = ind.volume_ratio(today_vol, avg_vol) if (today_vol and avg_vol) else None

    surprise = None
    funda = {}
    if not lite:
        surprise = await provider.earnings_surprise(symbol) if catalyst == "earnings" else None
        funda = await provider.fundamentals(symbol) or {}

    spark = None
    if bars:
        step = max(1, len(bars) // 40)
        spark = [round(b["c"], 2) for b in bars[::step]]

    return Candidate(
        symbol=symbol, as_of_epoch=now_epoch, catalyst=catalyst,
        move_pct=move, volume_ratio=vol_ratio, vwap_distance_pct=vwap_dist,
        minutes_since_new_low=mins_since_low, higher_low=higher_low, vwap_reclaim=reclaim,
        eps_surprise_pct=(surprise or {}).get("eps_surprise_pct"),
        revenue_surprise_pct=(surprise or {}).get("revenue_surprise_pct"),
        pe=(funda or {}).get("pe"), forward_pe=(funda or {}).get("forward_pe"),
        price_to_sales=(funda or {}).get("price_to_sales"),
        market_cap=(funda or {}).get("market_cap"),
        price=price, spark=spark,
    )


async def scan_once(db: Session, cfg: StrategyConfig, strat_version_id: int,
                    reversal_model: dict | None = None) -> list[dict]:
    global LAST_SCAN_META
    settings = get_settings()
    provider = get_provider()
    now = int(time.time())
    et_min = _et_minute_of_day(now, settings.market_tz)

    universe, catalysts = await _resolve_universe(provider, settings)
    budget = getattr(settings, "scan_time_budget_sec", 25)
    batch_size = getattr(settings, "scan_batch_size", 12)
    refresh_sec = getattr(settings, "scan_refresh_sec", 120)
    ttl = getattr(settings, "scan_cache_ttl_sec", 1800)

    def age(sym: str) -> int:
        e = _CACHE.get(sym)
        return (now - e["fetched_at"]) if e else 10 ** 9

    # rotate: fetch the stalest symbols first (never-seen count as oldest)
    stale = sorted([s for s in universe if age(s) >= refresh_sec], key=age, reverse=True)
    batch = stale[:batch_size]

    fetched = 0
    try:
        min_cap = getattr(settings, "min_market_cap_billions", 0.0)

        async def _one(symbol: str):
            try:
                cand = await build_candidate(
                    provider, symbol, cfg, now, settings.market_tz,
                    catalysts.get(symbol), lite=True)
                if cand is None:
                    return symbol, None, None
                mcap_b = await _market_cap_billions(provider, symbol)
                # fail open: only drop when we KNOW it's below the floor
                if mcap_b is not None and min_cap and mcap_b < min_cap:
                    return symbol, None, mcap_b
                return symbol, cand, mcap_b
            except Exception:  # noqa
                return symbol, None, None

        tasks = [asyncio.create_task(_one(sym)) for sym in batch]
        pairs = []
        try:
            for fut in asyncio.as_completed(tasks, timeout=budget):
                pairs.append(await fut)
        except asyncio.TimeoutError:
            pass
        for t in tasks:
            if not t.done():
                t.cancel()

        for symbol, cand, mcap_b in pairs:
            if cand is None:
                continue
            fetched += 1
            score = score_candidate(cand, cfg)
            db.add(Observation(
                symbol=symbol, as_of_epoch=now, strategy_version_id=strat_version_id,
                price=cand.price, move_pct=cand.move_pct, volume_ratio=cand.volume_ratio,
                vwap_distance_pct=cand.vwap_distance_pct, higher_low=cand.higher_low,
                vwap_reclaim=cand.vwap_reclaim, eps_surprise_pct=cand.eps_surprise_pct,
                revenue_surprise_pct=cand.revenue_surprise_pct, catalyst=cand.catalyst,
                score_total=score.total, status=score.status,
                components_json=[c.__dict__ for c in score.components],
                snapshot_json=cand.__dict__,
            ))
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
            pred = predict_movement(cand, reversal_model)
            d = score.to_dict()
            d.update({"price": cand.price, "move_pct": cand.move_pct,
                      "volume_ratio": cand.volume_ratio,
                      "vwap_distance_pct": cand.vwap_distance_pct,
                      "higher_low": cand.higher_low, "vwap_reclaim": cand.vwap_reclaim,
                      "catalyst": cand.catalyst, "as_of_epoch": now,
                      "estimated_reversal_pct": est["estimated_reversal_pct"],
                      "reversal_tier": est["tier"], "reversal_confidence": est["confidence"],
                      "prediction": pred["prediction"],
                      "direction_bias": pred["direction_bias"],
                      "predicted_move_pct": pred["predicted_move_pct"],
                      "prediction_confidence": pred["prediction_confidence"],
                      "reversal_score": pred["reversal_score"],
                      "continuation_score": pred["continuation_score"],
                      "option_aim": pred["option_aim"], "spark": cand.spark,
                      "market_cap_billions": round(mcap_b, 1) if mcap_b else None})
            _CACHE[symbol] = {"fetched_at": now, "d": d}
        db.commit()
    finally:
        await provider.aclose()

    # merge everything still fresh + still in the universe, best first
    merged = [_CACHE[s]["d"] for s in universe
              if s in _CACHE and (now - _CACHE[s]["fetched_at"]) <= ttl]
    merged.sort(key=lambda r: r["total"], reverse=True)
    LAST_SCAN_META = {"universe": len(universe), "fetched_this_scan": fetched,
                      "batch": len(batch), "showing": len(merged)}
    return merged


async def _fetch_movers(settings) -> list[str]:
    """Today's most active + biggest gainers/losers (FMP). Best-effort."""
    key = getattr(settings, "fmp_api_key", "")
    if not key:
        return []
    endpoints = ["stock_market/actives", "stock_market/losers", "stock_market/gainers"]
    syms: list[str] = []
    async with httpx.AsyncClient(timeout=12.0) as c:
        async def grab(ep):
            try:
                r = await c.get(f"https://financialmodelingprep.com/api/v3/{ep}",
                                params={"apikey": key})
                if r.status_code != 200:
                    return []
                d = r.json()
                if not isinstance(d, list):
                    return []
                return [(x.get("symbol") or x.get("ticker")) for x in d
                        if isinstance(x, dict) and (x.get("symbol") or x.get("ticker"))]
            except Exception:
                return []
        for part in await asyncio.gather(*[grab(e) for e in endpoints]):
            syms.extend(part)
    # keep order, dedupe
    return list(dict.fromkeys(syms))


async def _resolve_universe(provider, settings) -> tuple[list[str], dict[str, str]]:
    """Watchlist + today's most-active movers + earnings names, deduped, capped."""
    watch = list(settings.watchlist_symbols)
    catalysts = {s: "earnings" for s in watch}

    movers = await _fetch_movers(settings)
    for sym in movers:
        catalysts.setdefault(sym, "active")

    cal_syms: list[str] = []
    try:
        today = dt.date.today().isoformat()
        cal = await provider.earnings_calendar(today, today)
        cal_syms = [e["symbol"] for e in cal if e.get("symbol")]
    except Exception:
        cal_syms = []
    for sym in cal_syms:
        catalysts.setdefault(sym, "earnings")

    universe = list(dict.fromkeys(watch + movers + cal_syms))[: settings.max_universe_size]
    return universe, catalysts
