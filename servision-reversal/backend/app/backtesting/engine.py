"""Backtesting engine.

Replays historical intraday bars through the SAME scoring code the live scanner
uses, so live and backtest can't diverge. Look-ahead bias is prevented
structurally:

  * At decision time T, indicators only see bars with t <= T (enforced in
    indicators.py via *_as_of functions).
  * Fundamentals/earnings carry an `available_at` epoch; the backtester refuses
    to use any fundamental whose available_at > T.
  * Entry is decided at T; outcome is evaluated only on bars with t > T.

Every assumption is documented inline. Results include control strategies so you
can see whether the reversal rules add anything over naive baselines.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from typing import Callable, Optional

from ..scanner.config import StrategyConfig
from ..scanner import indicators as ind
from ..scanner.scorer import Candidate, score_candidate
from ..services.paper_engine import build_equity_setup, track_equity_trade


@dataclass
class HistoricalEvent:
    """One catalyst day for one symbol, with everything needed to replay it.

    fundamentals_available_at: epoch at which the earnings numbers were public.
    The backtester will NOT use these before that time (no look-ahead).
    """
    symbol: str
    session_bars: list[dict]              # 1-min bars for the session, ascending
    prev_close: float
    catalyst: str
    fundamentals: dict = field(default_factory=dict)
    fundamentals_available_at: int = 0
    sector: Optional[str] = None
    avg_volume: Optional[float] = None
    expected_move_pct: Optional[float] = None


def _minute_of_day_et(epoch: int, tz="America/New_York") -> int:
    import datetime as dt
    import pytz
    d = dt.datetime.fromtimestamp(epoch, pytz.timezone(tz))
    return d.hour * 60 + d.minute


def _candidate_at(ev: HistoricalEvent, t: int, cfg: StrategyConfig) -> Candidate:
    up = [b for b in ev.session_bars if b["t"] <= t]
    price = up[-1]["c"] if up else ev.prev_close
    vwap_val = ind.vwap_as_of(ev.session_bars, t)
    today_vol = sum(b["v"] for b in up)
    vol_ratio = ind.volume_ratio(today_vol, ev.avg_volume) if ev.avg_volume else None

    # Fundamentals only if already public at time t.
    funda = ev.fundamentals if (ev.fundamentals_available_at and
                                ev.fundamentals_available_at <= t) else {}

    return Candidate(
        symbol=ev.symbol, as_of_epoch=t, catalyst=ev.catalyst,
        move_pct=ind.move_pct(price, ev.prev_close),
        volume_ratio=vol_ratio,
        vwap_distance_pct=ind.vwap_distance_pct(price, vwap_val),
        minutes_since_new_low=ind.minutes_since_new_low(ev.session_bars, t),
        higher_low=ind.has_higher_low(ev.session_bars, t),
        vwap_reclaim=ind.reclaimed_vwap(ev.session_bars, t),
        expected_move_pct=ev.expected_move_pct,
        eps_surprise_pct=funda.get("eps_surprise_pct"),
        revenue_surprise_pct=funda.get("revenue_surprise_pct"),
        forward_pe=funda.get("forward_pe"),
        price_to_sales=funda.get("price_to_sales"),
        market_cap=funda.get("market_cap"),
        price=price, sector=ev.sector,
    )


def replay_event(ev: HistoricalEvent, cfg: StrategyConfig) -> Optional[dict]:
    """Replay one event. Returns a trade result dict, or None if never qualified.

    Walks minute-by-minute from earliest_entry_min. At the FIRST minute where the
    score qualifies, it enters. Outcome uses only later bars. No look-ahead.
    """
    for b in ev.session_bars:
        t = b["t"]
        mod = _minute_of_day_et(t)
        if mod < cfg.earliest_entry_min:
            continue
        if mod > cfg.observation_end_min:
            break

        cand = _candidate_at(ev, t, cfg)
        score = score_candidate(cand, cfg)
        if score.status == "QUALIFIED":
            entry_price = cand.price
            setup = build_equity_setup(ev.symbol, entry_price, t, score.total, cfg)
            later = [x for x in ev.session_bars if x["t"] > t]
            outcome = track_equity_trade(setup, later, cfg)
            return {
                "symbol": ev.symbol, "catalyst": ev.catalyst,
                "entry_epoch": t, "entry_price": setup.entry_price,
                "score": score.total, "sector": ev.sector,
                "eps_surprise_pct": cand.eps_surprise_pct,
                "revenue_surprise_pct": cand.revenue_surprise_pct,
                "forward_pe": cand.forward_pe, "market_cap": cand.market_cap,
                "move_pct": cand.move_pct,
                "vwap_reclaim": cand.vwap_reclaim, "higher_low": cand.higher_low,
                **outcome,
            }
    return None


# --------------------------------------------------------------------------
# Control strategies (baselines to beat)
# --------------------------------------------------------------------------
def control_buy_the_dip(ev: HistoricalEvent, cfg: StrategyConfig) -> Optional[dict]:
    """Enter at earliest_entry_min if move <= min_catalyst_move_pct. No confirmation."""
    for b in ev.session_bars:
        if _minute_of_day_et(b["t"]) >= cfg.earliest_entry_min:
            cand = _candidate_at(ev, b["t"], cfg)
            if cand.move_pct is not None and cand.move_pct <= cfg.min_catalyst_move_pct:
                setup = build_equity_setup(ev.symbol, cand.price, b["t"], 0, cfg)
                later = [x for x in ev.session_bars if x["t"] > b["t"]]
                return {"symbol": ev.symbol, **track_equity_trade(setup, later, cfg)}
            return None
    return None


def control_vwap_only(ev: HistoricalEvent, cfg: StrategyConfig) -> Optional[dict]:
    """Enter on first VWAP reclaim after earliest_entry_min, ignore fundamentals."""
    for b in ev.session_bars:
        if _minute_of_day_et(b["t"]) < cfg.earliest_entry_min:
            continue
        if ind.reclaimed_vwap(ev.session_bars, b["t"]):
            cand = _candidate_at(ev, b["t"], cfg)
            setup = build_equity_setup(ev.symbol, cand.price, b["t"], 0, cfg)
            later = [x for x in ev.session_bars if x["t"] > b["t"]]
            return {"symbol": ev.symbol, **track_equity_trade(setup, later, cfg)}
    return None


# --------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------
def compute_metrics(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0, "insufficient_sample": True}

    rets = [t["return_pct"] for t in trades if t.get("return_pct") is not None]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    n = len(rets)

    gross_win = sum(wins)
    gross_loss = abs(sum(losses))
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else math.inf

    # equity curve for max drawdown (compounding the % returns)
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in rets:
        equity *= (1 + r / 100.0)
        peak = max(peak, equity)
        max_dd = min(max_dd, (equity - peak) / peak * 100.0)

    mean = statistics.mean(rets)
    stdev = statistics.pstdev(rets) if n > 1 else 0.0
    sharpe_like = (mean / stdev) if stdev > 0 else 0.0

    return {
        "trades": n,
        "insufficient_sample": n < 30,   # gate: don't trust small buckets
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_return": round(mean, 3),
        "median_return": round(statistics.median(rets), 3),
        "avg_winner": round(statistics.mean(wins), 3) if wins else 0.0,
        "avg_loser": round(statistics.mean(losses), 3) if losses else 0.0,
        "profit_factor": round(profit_factor, 2) if profit_factor != math.inf else None,
        "max_drawdown": round(max_dd, 2),
        "sharpe_like": round(sharpe_like, 2),
        "expected_value": round(mean, 3),
        "largest_win": round(max(rets), 3),
        "largest_loss": round(min(rets), 3),
    }


def _breakdown(trades: list[dict], key: Callable[[dict], str]) -> dict:
    buckets: dict[str, list[dict]] = {}
    for t in trades:
        buckets.setdefault(key(t), []).append(t)
    return {k: compute_metrics(v) for k, v in buckets.items()}


def run_backtest(events: list[HistoricalEvent], cfg: StrategyConfig) -> dict:
    """Run the strategy + controls over a list of historical events."""
    strat = [r for ev in events if (r := replay_event(ev, cfg))]
    dip = [r for ev in events if (r := control_buy_the_dip(ev, cfg))]
    vwap = [r for ev in events if (r := control_vwap_only(ev, cfg))]

    def beat(t):
        return "beat" if (t.get("eps_surprise_pct") or 0) >= 0 else "miss"

    def valuation(t):
        fpe = t.get("forward_pe")
        if fpe is None:
            return "unknown"
        return "high" if fpe > 40 else "low"

    def capbucket(t):
        mc = t.get("market_cap")
        if not mc:
            return "unknown"
        return "large" if mc >= 10_000 else "small"  # FMP mktcap in millions varies

    return {
        "strategy": compute_metrics(strat),
        "controls": {
            "buy_the_dip": compute_metrics(dip),
            "vwap_only": compute_metrics(vwap),
        },
        "breakdowns": {
            "eps": _breakdown(strat, beat),
            "valuation": _breakdown(strat, valuation),
            "market_cap": _breakdown(strat, capbucket),
            "vwap_confirmation": _breakdown(
                strat, lambda t: "reclaimed" if t.get("vwap_reclaim") else "not"),
            "higher_low": _breakdown(
                strat, lambda t: "yes" if t.get("higher_low") else "no"),
            "sector": _breakdown(strat, lambda t: t.get("sector") or "unknown"),
        },
        "trades": strat,
    }
