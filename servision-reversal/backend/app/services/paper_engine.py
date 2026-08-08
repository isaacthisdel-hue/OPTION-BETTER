"""Paper trade engine.

Turns a QUALIFIED score into a HYPOTHETICAL paper trade, and tracks it to exit
using intraday bars. This is research bookkeeping — it produces statistics, not
instructions. The UI must always label output as a paper setup / simulation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..scanner.config import StrategyConfig


@dataclass
class PaperSetup:
    symbol: str
    setup: str
    entry_price: float
    stop_price: float
    target1: float
    target2: float
    entry_epoch: int
    score_at_entry: float
    instrument: str = "equity"
    # option simulation (HISTORICAL PAPER SIMULATION only)
    option_type: Optional[str] = None
    strike: Optional[float] = None
    expiration: Optional[str] = None
    entry_premium: Optional[float] = None

    # This label is intentional and load-bearing. Do not render as "BUY".
    label: str = "QUALIFIED PAPER-TRADE SETUP"


def build_equity_setup(symbol, entry_price, entry_epoch, score, cfg: StrategyConfig,
                       setup="Earnings reversal") -> PaperSetup:
    fill = entry_price * (1 + cfg.slippage_pct / 100.0)  # modelled adverse fill
    return PaperSetup(
        symbol=symbol,
        setup=setup,
        entry_price=round(fill, 2),
        stop_price=round(fill * (1 - cfg.stop_pct / 100.0), 2),
        target1=round(fill * (1 + cfg.target1_pct / 100.0), 2),
        target2=round(fill * (1 + cfg.target2_pct / 100.0), 2),
        entry_epoch=entry_epoch,
        score_at_entry=score,
    )


def track_equity_trade(setup: PaperSetup, bars_after_entry: list[dict],
                       cfg: StrategyConfig) -> dict:
    """Walk forward through bars (each t > entry_epoch) and resolve the trade.

    Exit priority within a bar is conservative: if a bar's range spans both the
    stop and a target, we assume the STOP hit first (worst case) to avoid
    flattering the results.
    """
    for b in bars_after_entry:
        if b["t"] <= setup.entry_epoch:
            continue
        hit_stop = b["l"] <= setup.stop_price
        hit_t2 = b["h"] >= setup.target2
        hit_t1 = b["h"] >= setup.target1
        if hit_stop:
            return _close(setup, setup.stop_price, b["t"], "stop", cfg)
        if hit_t2:
            return _close(setup, setup.target2, b["t"], "target2", cfg)
        if hit_t1:
            return _close(setup, setup.target1, b["t"], "target1", cfg)

    # End of day / data: close at last available close.
    if bars_after_entry:
        last = bars_after_entry[-1]
        return _close(setup, last["c"], last["t"], "eod", cfg)
    return _close(setup, setup.entry_price, setup.entry_epoch, "eod", cfg)


def _close(setup: PaperSetup, exit_price, exit_epoch, reason, cfg) -> dict:
    gross = (exit_price - setup.entry_price) / setup.entry_price * 100.0
    net = gross - cfg.commission_per_trade
    return {
        "exit_price": round(exit_price, 2),
        "exit_epoch": exit_epoch,
        "exit_reason": reason,
        "return_pct": round(net, 3),
        "status": "closed",
    }


def simulate_option_pl(entry_premium: float, exit_premium: float,
                       contracts: int = 1) -> dict:
    """HISTORICAL PAPER SIMULATION of an option position P/L.

    Requires historical option prices, which the free tier does NOT provide.
    Left here so the module is ready when a paid options feed is added. Until
    then the scanner does not create option paper trades.
    """
    pl_per_contract = (exit_premium - entry_premium) * 100.0
    total = pl_per_contract * contracts
    ret = (exit_premium - entry_premium) / entry_premium * 100.0 if entry_premium else 0.0
    return {
        "label": "HISTORICAL PAPER SIMULATION",
        "pl_dollars": round(total, 2),
        "return_pct": round(ret, 2),
    }
