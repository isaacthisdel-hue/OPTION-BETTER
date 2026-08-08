"""Strategy statistics and estimated paper-revenue projection.

The projection is deliberately anchored to the ACTUAL tracked paper trades. It
never invents a forward number from nothing. When the sample is small, the range
is wide and the sample size is returned alongside so the UI can warn the user not
to trust it. This is the guardrail against a seductive fake "$X/month" figure.
"""
from __future__ import annotations

import math
import statistics

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PaperTrade


def paper_trade_stats(db: Session, strategy_version_id: int | None = None) -> dict:
    q = select(PaperTrade).where(PaperTrade.status == "closed")
    if strategy_version_id is not None:
        q = q.where(PaperTrade.strategy_version_id == strategy_version_id)
    trades = db.execute(q).scalars().all()

    rets = [t.return_pct for t in trades if t.return_pct is not None]
    n = len(rets)
    if n == 0:
        return {"trades": 0, "insufficient_sample": True,
                "note": "No closed paper trades yet."}

    wins = [r for r in rets if r > 0]
    mean = statistics.mean(rets)
    stdev = statistics.pstdev(rets) if n > 1 else 0.0

    return {
        "trades": n,
        "insufficient_sample": n < 30,
        "win_rate": round(len(wins) / n * 100, 1),
        "avg_return": round(mean, 3),
        "expected_value": round(mean, 3),
        "return_stdev": round(stdev, 3),
    }


def project_paper_revenue(
    db: Session, capital: float = 10_000.0, risk_per_trade_pct: float = 100.0,
    trades_per_day: float = 2.0, days: int = 5, strategy_version_id: int | None = None,
) -> dict:
    """Project estimated paper P&L forward FROM tracked results.

    Returns a central estimate AND a wide uncertainty band derived from the
    standard error of the mean return. Always returns sample_size and a
    trust flag so the UI can show the warning prominently.
    """
    stats = paper_trade_stats(db, strategy_version_id)
    n = stats.get("trades", 0)
    if n == 0:
        return {"available": False,
                "note": "Need closed paper trades before projecting revenue."}

    ev_pct = stats["avg_return"]
    stdev = stats["return_stdev"]
    position = capital * (risk_per_trade_pct / 100.0)
    total_trades = trades_per_day * days

    central = position * (ev_pct / 100.0) * total_trades

    # Standard error of the mean scales as stdev/sqrt(n); band widens when n small.
    sem = (stdev / math.sqrt(n)) if n > 0 else stdev
    band = position * (sem / 100.0) * total_trades * 1.96  # ~95% band on the mean

    return {
        "available": True,
        "sample_size": n,
        "insufficient_sample": n < 30,
        "central_estimate": round(central, 2),
        "low_estimate": round(central - band, 2),
        "high_estimate": round(central + band, 2),
        "assumptions": {
            "capital": capital, "position_per_trade": position,
            "trades_per_day": trades_per_day, "days": days,
            "observed_ev_per_trade_pct": ev_pct,
        },
        "warning": (
            "Projection is based on only %d paper trades — treat as noise, not a "
            "forecast. Small samples produce extreme extrapolations." % n
        ) if n < 30 else (
            "Projection assumes future trades resemble past paper trades, which "
            "may not hold. This is paper research, not a promise of returns."
        ),
    }
