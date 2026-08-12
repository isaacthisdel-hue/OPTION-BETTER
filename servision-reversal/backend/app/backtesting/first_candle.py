"""First Candle Rule backtest engine.

Opening-range breakout with a Fair Value Gap (FVG) trigger:
  1. Opening range = the first 15-min candle (09:30-09:45 ET): its high and low.
  2. On the 5-min chart after 09:45, wait for the FIRST valid FVG that breaks the
     range: a 3-candle gap (c1.high < c3.low for longs; c1.low > c3.high for shorts)
     with at least one of the three candles closing outside the opening range.
  3. Entry = limit at the near edge of the gap; stop = FVG candle-1's low/high;
     target = fixed R:R (default 2:1). One trade per session, first setup only.

Outcomes are simulated on 1-min bars with a conservative stop-first assumption.
"""
from __future__ import annotations

import datetime as dt

import pytz

from ..scanner.config import StrategyConfig
from .engine import compute_metrics, _breakdown
from .reversal_model import equity_curve, _next_friday

_ET = pytz.timezone("America/New_York")
_OPEN = 9 * 60 + 30    # 570
_CLOSE = 16 * 60       # 960


def _mod(epoch: int) -> int:
    d = dt.datetime.fromtimestamp(epoch, _ET)
    return d.hour * 60 + d.minute


def _aggregate(bars: list[dict], minutes: int) -> list[dict]:
    """Aggregate 1-min bars into `minutes`-candles aligned to 09:30 ET."""
    out: dict[int, dict] = {}
    for b in bars:
        m = _mod(b["t"])
        if m < _OPEN or m >= _CLOSE:
            continue
        bucket = (m - _OPEN) // minutes
        g = out.get(bucket)
        if g is None:
            out[bucket] = {"t": b["t"], "o": b["o"], "h": b["h"], "l": b["l"],
                           "c": b["c"], "v": b["v"], "start_mod": _OPEN + bucket * minutes}
        else:
            g["h"] = max(g["h"], b["h"]); g["l"] = min(g["l"], b["l"])
            g["c"] = b["c"]; g["v"] += b["v"]
    return [out[k] for k in sorted(out)]


def _fcr_trade(bars: list[dict], cfg: StrategyConfig) -> dict | None:
    c15 = _aggregate(bars, cfg.fcr_range_minutes)
    c5 = _aggregate(bars, cfg.fcr_signal_minutes)
    if len(c15) < 1 or len(c5) < 3:
        return None
    hi, lo = c15[0]["h"], c15[0]["l"]
    after = cfg.fcr_range_minutes + _OPEN   # first signal candle after the opening range

    setup = None
    for i in range(len(c5) - 2):
        c1, c2, c3 = c5[i], c5[i + 1], c5[i + 2]
        if c3["start_mod"] < after:
            continue
        closes = (c1["c"], c2["c"], c3["c"])
        # the middle candle must be the expansive one that leaves the gap
        c2_range = c2["h"] - c2["l"]
        if c2_range < (c1["h"] - c1["l"]) or c2_range < (c3["h"] - c3["l"]):
            continue
        # bullish FVG that breaks THROUGH the opening-range high
        if (c1["h"] < c3["l"] and c3["l"] >= hi
                and (not cfg.fcr_require_close_outside or max(closes) > hi)):
            setup = ("long", c1["l"], c3["l"], c3)
            break
        # bearish FVG that breaks THROUGH the opening-range low
        if (c1["l"] > c3["h"] and c3["h"] <= lo
                and (not cfg.fcr_require_close_outside or min(closes) < lo)):
            setup = ("short", c1["h"], c3["h"], c3)
            break
    if not setup:
        return None

    direction, stop, entry, c3 = setup
    rr = cfg.fcr_risk_reward
    if direction == "long":
        risk = entry - stop
        if risk <= 0:
            return None
        target = entry + rr * risk
    else:
        risk = stop - entry
        if risk <= 0:
            return None
        target = entry - rr * risk

    c3_end = c3["start_mod"] + cfg.fcr_signal_minutes
    future = [b for b in bars if _mod(b["t"]) >= c3_end and _mod(b["t"]) < _CLOSE]
    if not future:
        return None

    filled = False
    entry_epoch = None
    for b in future:
        if not filled:
            if (direction == "long" and b["l"] <= entry) or (direction == "short" and b["h"] >= entry):
                filled = True
                entry_epoch = b["t"]
        if filled:
            if direction == "long":
                if b["l"] <= stop:
                    return _close(direction, entry, stop, risk, stop, b["t"], "loss", entry_epoch)
                if b["h"] >= target:
                    return _close(direction, entry, stop, risk, target, b["t"], "win", entry_epoch)
            else:
                if b["h"] >= stop:
                    return _close(direction, entry, stop, risk, stop, b["t"], "loss", entry_epoch)
                if b["l"] <= target:
                    return _close(direction, entry, stop, risk, target, b["t"], "win", entry_epoch)
    if filled:
        return _close(direction, entry, stop, risk, future[-1]["c"], future[-1]["t"], "eod", entry_epoch)
    return None


def _close(direction, entry, stop, risk, exit_price, exit_epoch, reason, entry_epoch) -> dict:
    pnl = (exit_price - entry) if direction == "long" else (entry - exit_price)
    r = pnl / risk if risk else 0.0
    return {
        "direction": direction, "entry": entry, "stop": stop,
        "target": entry + (2 * risk if direction == "long" else -2 * risk),
        "exit": exit_price, "exit_reason": reason, "entry_epoch": entry_epoch,
        "r_multiple": round(r, 2),
        "return_pct": round(pnl / entry * 100.0, 3) if entry else 0.0,
    }


def _fcr_insights(strat: dict, sessions: int) -> list[dict]:
    out = []
    n = strat.get("trades", 0)
    out.append({"level": "info", "text": f"{n} setups triggered across {sessions} sessions "
                f"({sessions - n} days had no valid FVG break / no fill)."})
    if n:
        wr = strat.get("win_rate")
        out.append({"level": "good" if (wr or 0) >= 50 else "warn",
                    "text": f"Win rate {wr}% · avg {strat.get('avg_R')}R · total {strat.get('total_R')}R."})
        if strat.get("insufficient_sample"):
            out.append({"level": "info", "text": "Small sample — add more tickers or a longer lookback."})
    else:
        out.append({"level": "warn", "text": "No trades. Widen the ticker list/lookback, or the FVG rule was never met."})
    return out


def run_first_candle(sessions: list[dict], cfg: StrategyConfig) -> dict:
    trades = []
    per_stock = []
    for s in sessions:
        tr = _fcr_trade(s["bars"], cfg)
        if not tr:
            continue
        tr["symbol"] = s["symbol"]
        tr["date"] = s["date"]
        trades.append(tr)
        bars = s["bars"]
        step = max(1, len(bars) // 120)
        per_stock.append({
            "symbol": s["symbol"], "date": s["date"],
            "series": [{"t": b["t"], "c": b["c"]} for b in bars[::step]],
            "prev_close": round(bars[0]["o"], 2), "gap_pct": 0.0, "qualified": True,
            "entry_price": round(tr["entry"], 2), "entry_epoch": tr.get("entry_epoch"),
            "stop_price": round(tr["stop"], 2), "target1": round(tr["target"], 2),
            "target2": round(tr["target"], 2), "exit_price": round(tr["exit"], 2),
            "exit_reason": tr["exit_reason"], "return_pct": tr["return_pct"],
            "score": tr["r_multiple"],
        })

    strat = compute_metrics([{"return_pct": t["return_pct"]} for t in trades])
    Rs = [t["r_multiple"] for t in trades]
    strat["avg_R"] = round(sum(Rs) / len(Rs), 2) if Rs else 0.0
    strat["total_R"] = round(sum(Rs), 2)

    return {
        "first_candle": True, "available": True,
        "strategy": strat,
        "controls": {"buy_the_dip": {"trades": 0, "insufficient_sample": True},
                     "vwap_only": {"trades": 0, "insufficient_sample": True}},
        "breakdowns": {"direction": _breakdown(trades, lambda t: t["direction"])},
        "reversal_model": {"tiers": [], "events_measured": 0, "insufficient_sample": True,
                           "expiry_next_friday": _next_friday(),
                           "method": "n/a for First Candle Rule"},
        "equity_curve": equity_curve(trades),
        "per_stock": per_stock,
        "trades": trades,
        "insights": _fcr_insights(strat, len(sessions)),
    }
