"""Strategy configuration — every threshold the strategy uses lives here.

This object is what gets versioned (Strategy V1, V2, ...). Two runs with the
same StrategyConfig must produce identical scores given identical input data.
Nothing here is asserted to be *correct* — these are hypotheses to be measured.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any


@dataclass(frozen=True)
class StrategyConfig:
    # --- Catalyst / move thresholds ---
    min_catalyst_move_pct: float = -7.0       # % vs previous close (negative)
    min_volume_ratio: float = 2.0             # today's vol / avg vol
    max_vwap_distance_pct: float = 8.0        # max |distance| from VWAP to consider

    # --- Timing (US/Eastern, minutes since midnight) ---
    earliest_entry_min: int = 11 * 60 + 30    # 11:30 ET
    observation_end_min: int = 13 * 60 + 30   # 13:30 ET
    max_hold_end_of_day: bool = True

    # --- Confirmation ---
    no_new_low_minutes: int = 15              # X minutes without a new low
    require_higher_low: bool = True
    require_vwap_reclaim: bool = True

    # --- Paper trade sizing / risk (for hypothetical P/L only) ---
    stop_pct: float = 1.5                     # % below entry
    target1_pct: float = 1.5                  # % above entry
    target2_pct: float = 3.0                  # % above entry
    slippage_pct: float = 0.1                 # modelled fill slippage
    commission_per_trade: float = 0.0         # paper; set if you want to model it

    # --- Score component weights (max points each) ---
    w_catalyst: float = 15.0
    w_move_magnitude: float = 18.0
    w_move_vs_expected: float = 10.0
    w_volume: float = 10.0
    w_vwap_extension: float = 8.0
    w_momentum_exhaustion: float = 8.0
    w_morning_low: float = 6.0
    w_higher_low: float = 15.0
    w_vwap_reclaim: float = 12.0
    w_eps_surprise: float = 5.0
    w_revenue_surprise: float = 5.0
    w_guidance: float = 4.0
    w_valuation_penalty: float = 6.0          # subtracted, not added
    w_relative_strength: float = 4.0

    # --- Qualification gate ---
    min_score_to_watch: float = 60.0
    min_score_to_qualify: float = 80.0

    version_label: str = "V1"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "StrategyConfig":
        valid = {f for f in cls.__dataclass_fields__}  # noqa
        return cls(**{k: v for k, v in d.items() if k in valid})
