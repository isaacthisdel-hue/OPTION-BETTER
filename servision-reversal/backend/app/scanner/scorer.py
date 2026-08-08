"""The reversal scoring engine.

Produces a ReversalScore that is transparent by construction: the total is just
the sum of named, signed components, each with the exact reason it was awarded.
The same function is called by the live scanner and the backtester.

NOTHING here predicts the market. It is a deterministic mapping from measured
facts (move %, volume ratio, confirmation flags, fundamentals) to a number,
using weights from StrategyConfig. Whether that number means anything is the
question the backtester exists to answer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .config import StrategyConfig


@dataclass
class ScoreComponent:
    name: str
    points: float          # signed; negative for penalties
    reason: str


@dataclass
class Candidate:
    """The measured facts about one stock at one point in time.
    All fields optional so partial data (free tier) still scores what it can."""
    symbol: str
    as_of_epoch: int
    catalyst: Optional[str] = None            # "earnings" | "news" | None
    move_pct: Optional[float] = None          # vs prev close (negative = down)
    volume_ratio: Optional[float] = None
    vwap_distance_pct: Optional[float] = None
    minutes_since_new_low: Optional[int] = None
    higher_low: Optional[bool] = None
    vwap_reclaim: Optional[bool] = None
    expected_move_pct: Optional[float] = None  # implied move from options, if avail
    eps_surprise_pct: Optional[float] = None
    revenue_surprise_pct: Optional[float] = None
    guidance: Optional[str] = None             # "raised"|"inline"|"lowered"|None
    pe: Optional[float] = None
    forward_pe: Optional[float] = None
    price_to_sales: Optional[float] = None
    market_cap: Optional[float] = None
    relative_strength_pct: Optional[float] = None  # stock vs sector today
    # context passthrough for storage / UI
    price: Optional[float] = None
    sector: Optional[str] = None


@dataclass
class ReversalScore:
    symbol: str
    as_of_epoch: int
    total: float
    components: list[ScoreComponent] = field(default_factory=list)
    status: str = "SKIP"      # SKIP | WATCH | QUALIFIED

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "as_of_epoch": self.as_of_epoch,
            "total": round(self.total, 1),
            "status": self.status,
            "components": [
                {"name": c.name, "points": round(c.points, 1), "reason": c.reason}
                for c in self.components
            ],
        }


def _scaled(value: float, floor: float, cap: float, max_points: float) -> float:
    """Linearly scale value in [floor, cap] to [0, max_points], clamped."""
    if cap == floor:
        return 0.0
    frac = (value - floor) / (cap - floor)
    frac = max(0.0, min(1.0, frac))
    return frac * max_points


def score_candidate(c: Candidate, cfg: StrategyConfig) -> ReversalScore:
    comps: list[ScoreComponent] = []

    # --- Catalyst strength ---
    if c.catalyst == "earnings":
        comps.append(ScoreComponent("catalyst", cfg.w_catalyst, "Earnings catalyst"))
    elif c.catalyst == "news":
        comps.append(ScoreComponent("catalyst", cfg.w_catalyst * 0.6, "News catalyst"))

    # --- Magnitude of move (more negative = more points, up to a cap) ---
    if c.move_pct is not None and c.move_pct <= cfg.min_catalyst_move_pct:
        pts = _scaled(abs(c.move_pct), abs(cfg.min_catalyst_move_pct), 20.0, cfg.w_move_magnitude)
        comps.append(ScoreComponent("move_magnitude", pts, f"Move {c.move_pct:.1f}%"))

    # --- Move vs options-implied expected move (H4) ---
    if c.move_pct is not None and c.expected_move_pct:
        ratio = abs(c.move_pct) / c.expected_move_pct if c.expected_move_pct else 0
        pts = _scaled(ratio, 1.0, 2.5, cfg.w_move_vs_expected)
        comps.append(ScoreComponent("move_vs_expected", pts,
                                    f"Move is {ratio:.1f}x implied"))

    # --- Volume anomaly ---
    if c.volume_ratio is not None and c.volume_ratio >= cfg.min_volume_ratio:
        pts = _scaled(c.volume_ratio, cfg.min_volume_ratio, 5.0, cfg.w_volume)
        comps.append(ScoreComponent("volume", pts, f"{c.volume_ratio:.1f}x avg volume"))

    # --- VWAP extension (extended BELOW vwap = stretched, reversion fuel) ---
    if c.vwap_distance_pct is not None and c.vwap_distance_pct < 0:
        dist = abs(c.vwap_distance_pct)
        if dist <= cfg.max_vwap_distance_pct:
            pts = _scaled(dist, 1.0, cfg.max_vwap_distance_pct, cfg.w_vwap_extension)
            comps.append(ScoreComponent("vwap_extension", pts,
                                        f"{c.vwap_distance_pct:.1f}% from VWAP"))

    # --- Momentum exhaustion: time since last new low ---
    if c.minutes_since_new_low is not None and c.minutes_since_new_low >= cfg.no_new_low_minutes:
        pts = _scaled(c.minutes_since_new_low, cfg.no_new_low_minutes,
                      cfg.no_new_low_minutes * 3, cfg.w_momentum_exhaustion)
        comps.append(ScoreComponent("momentum_exhaustion", pts,
                                    f"No new low for {c.minutes_since_new_low}m"))
        comps.append(ScoreComponent("morning_low", cfg.w_morning_low, "Morning low established"))

    # --- Higher low confirmation ---
    if c.higher_low:
        comps.append(ScoreComponent("higher_low", cfg.w_higher_low, "Higher low formed"))

    # --- VWAP reclaim confirmation ---
    if c.vwap_reclaim:
        comps.append(ScoreComponent("vwap_reclaim", cfg.w_vwap_reclaim, "Reclaimed VWAP"))

    # --- EPS surprise (beat = points, H1) ---
    if c.eps_surprise_pct is not None:
        if c.eps_surprise_pct >= 0:
            pts = _scaled(c.eps_surprise_pct, 0.0, 15.0, cfg.w_eps_surprise)
            comps.append(ScoreComponent("eps_surprise", pts,
                                        f"EPS beat +{c.eps_surprise_pct:.1f}%"))
        else:  # genuine miss reduces reversal odds (H2)
            pts = -_scaled(abs(c.eps_surprise_pct), 0.0, 15.0, cfg.w_eps_surprise)
            comps.append(ScoreComponent("eps_surprise", pts,
                                        f"EPS miss {c.eps_surprise_pct:.1f}%"))

    # --- Revenue surprise ---
    if c.revenue_surprise_pct is not None:
        if c.revenue_surprise_pct >= 0:
            pts = _scaled(c.revenue_surprise_pct, 0.0, 10.0, cfg.w_revenue_surprise)
            comps.append(ScoreComponent("revenue_surprise", pts,
                                        f"Rev beat +{c.revenue_surprise_pct:.1f}%"))
        else:
            pts = -_scaled(abs(c.revenue_surprise_pct), 0.0, 10.0, cfg.w_revenue_surprise)
            comps.append(ScoreComponent("revenue_surprise", pts,
                                        f"Rev miss {c.revenue_surprise_pct:.1f}%"))

    # --- Guidance quality ---
    if c.guidance == "raised":
        comps.append(ScoreComponent("guidance", cfg.w_guidance, "Guidance raised"))
    elif c.guidance == "lowered":
        comps.append(ScoreComponent("guidance", -cfg.w_guidance, "Guidance lowered"))

    # --- Valuation penalty (H3: rich valuation + negative catalyst = worse) ---
    if c.forward_pe is not None and c.forward_pe > 40:
        pen = -_scaled(c.forward_pe, 40.0, 100.0, cfg.w_valuation_penalty)
        comps.append(ScoreComponent("valuation_risk", pen, f"Fwd P/E {c.forward_pe:.0f}"))
    elif c.price_to_sales is not None and c.price_to_sales > 10:
        pen = -_scaled(c.price_to_sales, 10.0, 30.0, cfg.w_valuation_penalty)
        comps.append(ScoreComponent("valuation_risk", pen, f"P/S {c.price_to_sales:.0f}"))

    # --- Relative strength vs sector ---
    if c.relative_strength_pct is not None and c.relative_strength_pct > 0:
        pts = _scaled(c.relative_strength_pct, 0.0, 3.0, cfg.w_relative_strength)
        comps.append(ScoreComponent("relative_strength", pts,
                                    f"+{c.relative_strength_pct:.1f}% vs sector"))

    total = sum(c.points for c in comps)
    if total >= cfg.min_score_to_qualify:
        status = "QUALIFIED"
    elif total >= cfg.min_score_to_watch:
        status = "WATCH"
    else:
        status = "SKIP"

    return ReversalScore(
        symbol=c.symbol, as_of_epoch=c.as_of_epoch,
        total=total, components=comps, status=status,
    )
