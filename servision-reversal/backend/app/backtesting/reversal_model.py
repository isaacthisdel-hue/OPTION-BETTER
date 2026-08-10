"""Learned reversal-magnitude model.

Instead of assuming how big a bounce to expect, this measures it from the real
events in the backtest. For each event we compute the intraday reversion you'd
have captured entering in the strategy window and holding to the close, then
group events into tiers and report the OBSERVED distribution per tier. Output
frames a next-Friday options 'aim' (direction + expiry + expected move) — research
only, never an instruction. Confidence is flagged by sample size.
"""
from __future__ import annotations

import datetime as dt
import statistics

from ..scanner.config import StrategyConfig
from ..scanner import indicators as ind
from .engine import HistoricalEvent, _minute_of_day_et


def _next_friday(today: dt.date | None = None) -> str:
    today = today or dt.date.today()
    ahead = (4 - today.weekday()) % 7  # Friday = 4
    ahead = ahead or 7                 # if today is Friday, aim next Friday
    return (today + dt.timedelta(days=ahead)).isoformat()


def _event_outcome(ev: HistoricalEvent, cfg: StrategyConfig) -> dict | None:
    """Reversion captured entering at the window open and holding to close."""
    window = [b for b in ev.session_bars
              if cfg.earliest_entry_min <= _minute_of_day_et(b["t"]) <= cfg.observation_end_min]
    if not window:
        return None
    entry = window[0]["c"]
    later = [b for b in ev.session_bars if b["t"] >= window[0]["t"]]
    if not later or not entry:
        return None
    close = later[-1]["c"]
    max_high = max(b["h"] for b in later)
    reversion_pct = (close - entry) / entry * 100.0
    max_favorable_pct = (max_high - entry) / entry * 100.0
    session_low = min(b["l"] for b in ev.session_bars)
    drop_pct = (session_low - ev.prev_close) / ev.prev_close * 100.0
    return {"symbol": ev.symbol, "drop_pct": round(drop_pct, 2), "entry": entry,
            "reversion_pct": reversion_pct, "max_favorable_pct": max_favorable_pct}


_TIER_ORDER = [
    "Severe drop (<= -15%)",
    "Large drop (-15% to -10%)",
    "Moderate drop (-10% to -6%)",
    "Mild drop (> -6%)",
]


def _tier(drop_pct: float) -> str:
    if drop_pct <= -15:
        return _TIER_ORDER[0]
    if drop_pct <= -10:
        return _TIER_ORDER[1]
    if drop_pct <= -6:
        return _TIER_ORDER[2]
    return _TIER_ORDER[3]


def _confidence(n: int) -> str:
    return "high" if n >= 30 else "medium" if n >= 10 else "low"


def build_reversal_model(events: list[HistoricalEvent], cfg: StrategyConfig) -> dict:
    outcomes = [o for ev in events if (o := _event_outcome(ev, cfg))]
    friday = _next_friday()
    buckets: dict[str, list[dict]] = {}
    for o in outcomes:
        buckets.setdefault(_tier(o["drop_pct"]), []).append(o)

    tiers = []
    for label in _TIER_ORDER:
        rows = buckets.get(label, [])
        n = len(rows)
        if n == 0:
            continue
        rev = sorted(r["reversion_pct"] for r in rows)
        favs = sorted(r["max_favorable_pct"] for r in rows)
        med = statistics.median(rev)
        p25 = rev[int(0.25 * (n - 1))]
        p75 = rev[int(0.75 * (n - 1))]
        med_fav = statistics.median(favs)
        hit = sum(1 for r in rev if r > 0) / n * 100.0
        tiers.append({
            "tier": label,
            "n": n,
            "confidence": _confidence(n),
            "median_reversion_pct": round(med, 2),
            "p25_reversion_pct": round(p25, 2),
            "p75_reversion_pct": round(p75, 2),
            "median_max_favorable_pct": round(med_fav, 2),
            "positive_rate_pct": round(hit, 1),
            "option_aim": {
                "direction": "CALL (upside reversal)",
                "expiry_next_friday": friday,
                "expected_move_pct": round(max(med, 0.0), 2),
                "stretch_move_pct": round(max(med_fav, 0.0), 2),
                "label": "RESEARCH SIGNAL — not an order",
            },
        })
    return {
        "tiers": tiers,
        "events_measured": len(outcomes),
        "insufficient_sample": len(outcomes) < 30,
        "expiry_next_friday": friday,
        "method": ("Observed intraday reversion (enter in window, hold to close) grouped "
                   "by gap-down severity. Expected move = median of real outcomes per tier."),
    }


def equity_curve(trades: list[dict]) -> list[dict]:
    equity = 1.0
    curve = [{"i": 0, "equity": 1.0}]
    for i, t in enumerate(trades, start=1):
        r = t.get("return_pct")
        if r is None:
            continue
        equity *= (1 + r / 100.0)
        curve.append({"i": i, "equity": round(equity, 4)})
    return curve


def per_stock_series(events: list[HistoricalEvent], trades: list[dict],
                     cfg: StrategyConfig, max_points: int = 120) -> list[dict]:
    trade_by_key = {(t["symbol"], t["entry_epoch"]): t for t in trades if "entry_epoch" in t}
    out = []
    for ev in events:
        bars = ev.session_bars
        if not bars:
            continue
        step = max(1, len(bars) // max_points)
        series = [{"t": b["t"], "c": b["c"]} for b in bars[::step]]
        first_day = dt.datetime.fromtimestamp(bars[0]["t"], tz=dt.timezone.utc)
        matched = next((t for (s, e), t in trade_by_key.items() if s == ev.symbol
                        and bars[0]["t"] <= e <= bars[-1]["t"]), None)
        entry = matched["entry_price"] if matched else None
        row = {
            "symbol": ev.symbol,
            "date": _session_date_str(bars[0]["t"]),
            "series": series,
            "prev_close": round(ev.prev_close, 2),
            "gap_pct": round(ind.move_pct(bars[0]["o"], ev.prev_close), 2),
            "qualified": matched is not None,
        }
        if matched and entry:
            row.update({
                "entry_price": entry,
                "entry_epoch": matched["entry_epoch"],
                "stop_price": round(entry * (1 - cfg.stop_pct / 100.0), 2),
                "target1": round(entry * (1 + cfg.target1_pct / 100.0), 2),
                "target2": round(entry * (1 + cfg.target2_pct / 100.0), 2),
                "exit_price": matched.get("exit_price"),
                "exit_epoch": matched.get("exit_epoch"),
                "exit_reason": matched.get("exit_reason"),
                "return_pct": matched.get("return_pct"),
                "score": matched.get("score"),
            })
        out.append(row)
    return out


def _session_date_str(epoch: int) -> str:
    import pytz
    return dt.datetime.fromtimestamp(epoch, pytz.timezone("America/New_York")).strftime("%Y-%m-%d")


def backtest_insights(result: dict, meta: dict, cfg) -> list[dict]:
    """Plain-language 'what went wrong / what to try' recommendations."""
    out = []
    def add(level, text):
        out.append({"level": level, "text": text})

    skipped = meta.get("skipped", []) if meta else []
    if skipped:
        names = ", ".join(x.get("symbol", "?") for x in skipped)
        if meta.get("rate_limited"):
            add("warn", f"Rate-limited on {names}. Wait a minute, or add a Twelve Data key (800/day) for headroom.")
        else:
            add("warn", f"No usable data for {names}. Swap them out in the watchlist below.")

    events = (meta or {}).get("events", 0)
    if events and events < 6:
        add("info", f"Only {events} event(s) loaded — add more tickers or widen the lookback for a firmer read.")

    s_ = result.get("strategy", {})
    n = s_.get("trades", 0)
    if n == 0:
        add("warn", f"No setup reached QUALIFIED (score ≥ {cfg.min_score_to_qualify}). Lower 'Score → qualify' in Settings, or loosen entry criteria, to actually test entries.")
    else:
        if s_.get("insufficient_sample"):
            add("info", f"{n} trades — small sample. Treat results as directional, not proof.")
        wr = s_.get("win_rate")
        if wr is not None and wr < 40:
            add("warn", f"Win rate {wr}% is low — the reversal edge isn't showing on this sample.")
        pf = s_.get("profit_factor")
        if pf is not None and pf < 1:
            add("warn", "Profit factor under 1 — losing expectancy on this sample.")
        ctrl = (result.get("controls") or {}).get("buy_the_dip", {})
        if ctrl.get("avg_return") is not None and s_.get("avg_return") is not None \
                and ctrl["avg_return"] >= s_["avg_return"] and ctrl.get("trades", 0) >= 3:
            add("warn", "'Buy the dip' baseline matched or beat the strategy — the confirmations may not be adding value here.")

    rm = result.get("reversal_model", {})
    best = None
    for t in rm.get("tiers", []):
        if t.get("n", 0) >= 3 and (best is None or t["median_reversion_pct"] > best["median_reversion_pct"]):
            best = t
    if best:
        add("good", f"Strongest tier: {best['tier']} bounced a median {best['median_reversion_pct']}% by close ({best['positive_rate_pct']}% positive, n={best['n']}).")

    if not out:
        add("good", "Clean run — no issues flagged.")
    return out
