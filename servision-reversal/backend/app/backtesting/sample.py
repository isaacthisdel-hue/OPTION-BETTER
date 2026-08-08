"""Synthetic historical events for demonstrating the backtest pipeline.

This is NOT real market data and NOT a source of edge — it exists so you can run
`POST /api/backtest` and see metrics/breakdowns render before you wire in a real
historical data loader. Replace `synthetic_events()` with a loader that pulls
real intraday bars + point-in-time fundamentals from your data provider.
"""
from __future__ import annotations

import datetime as dt
import random

from .engine import HistoricalEvent


def _session(day: dt.date, prev_close: float, shape: str) -> list[dict]:
    """Build 1-min bars 09:30-16:00 ET with a rough intraday 'shape'."""
    import pytz
    et = pytz.timezone("America/New_York")
    start = et.localize(dt.datetime(day.year, day.month, day.day, 9, 30))
    bars = []
    # Gap down 9-14% after a bad reaction so the move clears the -7% threshold
    # with room to spare and produces meaningful VWAP extension.
    price = prev_close * random.uniform(0.86, 0.91)
    for i in range(390):
        t = int((start + dt.timedelta(minutes=i)).timestamp())
        if shape == "reversal":
            # Sharp morning flush for ~75 min, clean recovery afterwards so a
            # higher low forms and price reclaims VWAP mid-session.
            drift = -0.0012 if i < 75 else 0.0011
        elif shape == "faller":
            drift = -0.0006
        else:
            drift = 0.0
        price *= (1 + drift + random.uniform(-0.0008, 0.0008))
        o = price
        c = price * (1 + random.uniform(-0.0006, 0.0006))
        h = max(o, c) * (1 + random.uniform(0, 0.0007))
        l = min(o, c) * (1 - random.uniform(0, 0.0007))
        # Heavy volume early (the anomaly), tapering through the day.
        vol = random.randint(120000, 260000) if i < 90 else random.randint(30000, 90000)
        bars.append({"t": t, "o": o, "h": h, "l": l, "c": c, "v": vol})
    return bars


def synthetic_events(n: int = 60) -> list[HistoricalEvent]:
    random.seed(42)
    events = []
    for i in range(n):
        year = random.choice([2022, 2023, 2024, 2025, 2026])
        day = dt.date(year, random.randint(1, 12), random.randint(1, 28))
        prev_close = random.uniform(20, 300)
        shape = random.choice(["reversal", "faller", "flat"])
        beat = random.choice([True, False])
        events.append(HistoricalEvent(
            symbol=f"SYN{i:03d}",
            session_bars=_session(day, prev_close, shape),
            prev_close=prev_close,
            catalyst="earnings",
            fundamentals={
                "eps_surprise_pct": random.uniform(0, 12) if beat else random.uniform(-12, 0),
                "revenue_surprise_pct": random.uniform(-5, 5),
                "forward_pe": random.uniform(8, 80),
                "market_cap": random.uniform(500, 50000),
            },
            fundamentals_available_at=int(dt.datetime(day.year, day.month, day.day,
                                                      6, 0).timestamp()),
            sector=random.choice(["Tech", "Health", "Energy", "Financials"]),
            # Avg per-minute-equivalent volume base so the heavy synthetic
            # session clears the 2x ratio (demo data only).
            avg_volume=random.randint(8_000_000, 18_000_000),
            expected_move_pct=random.uniform(4, 10),
        ))
    return events
