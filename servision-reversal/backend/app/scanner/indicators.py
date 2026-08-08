"""Deterministic market-math primitives.

Every function here is pure: same input bars -> same output. These are the
building blocks the scorer and backtester share. Bars are dicts with keys:
    t (epoch seconds, int), o, h, l, c (float), v (int)
sorted ascending by t.

CRITICAL for backtesting: functions that "detect confirmation as of time T"
only ever look at bars with t <= T. There is no look-ahead here.
"""
from __future__ import annotations

from typing import Iterable, Optional


Bar = dict


def _bars_up_to(bars: list[Bar], t_cutoff: int) -> list[Bar]:
    """Return only bars at or before t_cutoff. This is the no-lookahead guard."""
    return [b for b in bars if b["t"] <= t_cutoff]


def vwap(bars: Iterable[Bar]) -> Optional[float]:
    """Volume-weighted average price using typical price (h+l+c)/3."""
    num = 0.0
    den = 0.0
    for b in bars:
        typical = (b["h"] + b["l"] + b["c"]) / 3.0
        num += typical * b["v"]
        den += b["v"]
    if den == 0:
        return None
    return num / den


def vwap_as_of(bars: list[Bar], t_cutoff: int) -> Optional[float]:
    return vwap(_bars_up_to(bars, t_cutoff))


def vwap_distance_pct(price: float, vwap_value: Optional[float]) -> Optional[float]:
    if vwap_value is None or vwap_value == 0:
        return None
    return (price - vwap_value) / vwap_value * 100.0


def volume_ratio(today_volume: float, avg_volume: float) -> Optional[float]:
    if avg_volume <= 0:
        return None
    return today_volume / avg_volume


def session_low_as_of(bars: list[Bar], t_cutoff: int) -> Optional[float]:
    up = _bars_up_to(bars, t_cutoff)
    if not up:
        return None
    return min(b["l"] for b in up)


def minutes_since_new_low(bars: list[Bar], t_cutoff: int) -> Optional[int]:
    """How many minutes since the session made its most recent new intraday low,
    evaluated as of t_cutoff. Assumes 1-minute bars but works with any spacing
    (returns minutes based on bar timestamps)."""
    up = _bars_up_to(bars, t_cutoff)
    if not up:
        return None
    running_low = up[0]["l"]
    t_of_last_new_low = up[0]["t"]
    for b in up[1:]:
        if b["l"] < running_low:
            running_low = b["l"]
            t_of_last_new_low = b["t"]
    return int((t_cutoff - t_of_last_new_low) // 60)


def has_higher_low(
    bars: list[Bar], t_cutoff: int, min_separation_min: int = 5, tolerance_pct: float = 0.05
) -> bool:
    """Detect a higher-low structure as of t_cutoff.

    Definition used here (documented, so it's testable and configurable):
      1. Find the session low (L1) and its time.
      2. After L1 + min_separation, require price to have moved up, then form a
         second local trough (L2) that is strictly higher than L1.
    This is intentionally simple and deterministic. It is NOT claimed to be the
    "true" definition of a higher low — swap the rule and re-measure.
    """
    up = _bars_up_to(bars, t_cutoff)
    if len(up) < 3:
        return False

    # Index of the absolute session low so far.
    low_idx = min(range(len(up)), key=lambda i: up[i]["l"])
    l1 = up[low_idx]["l"]
    t1 = up[low_idx]["t"]

    # Look only at bars strictly after the first low.
    after = [b for b in up if b["t"] > t1 + (min_separation_min - 1) * 60]
    if len(after) < 2:
        return False

    threshold = l1 * (1 + tolerance_pct / 100.0)

    # Require evidence of a bounce first: price must rise above L1 by the
    # tolerance at some point after the low.
    bounced = any(b["h"] > threshold for b in after)
    if not bounced:
        return False

    # Then require a subsequent pullback that holds ABOVE L1 — i.e. a higher low.
    # We take the minimum low across the post-bounce window and check it stayed
    # above L1. This captures a higher low whether it's a sharp V or a shallow
    # dip on a rising leg.
    first_bounce_idx = next(i for i, b in enumerate(after) if b["h"] > threshold)
    post = after[first_bounce_idx:]
    if len(post) < 2:
        return False
    pullback_low = min(b["l"] for b in post[1:])  # after the bounce bar
    return pullback_low > threshold


def reclaimed_vwap(bars: list[Bar], t_cutoff: int) -> bool:
    """True if the latest price (as of t_cutoff) is at or above session VWAP,
    after having been below it earlier in the session."""
    up = _bars_up_to(bars, t_cutoff)
    if len(up) < 2:
        return False
    vw = vwap(up)
    if vw is None:
        return False
    last_close = up[-1]["c"]
    was_below = any(b["c"] < vwap(up[: i + 1]) for i, b in enumerate(up[:-1]) if vwap(up[: i + 1]))
    return last_close >= vw and was_below


def gap_pct(open_price: float, prev_close: float) -> Optional[float]:
    if prev_close == 0:
        return None
    return (open_price - prev_close) / prev_close * 100.0


def move_pct(current: float, prev_close: float) -> Optional[float]:
    if prev_close == 0:
        return None
    return (current - prev_close) / prev_close * 100.0
