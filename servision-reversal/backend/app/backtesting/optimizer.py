"""Auto-optimizer.

Loads the real events ONCE (done by the caller), then hill-climbs over the key
strategy parameters entirely in memory — each trial is a pure backtest, no
network — keeping any change that improves the objective and reverting the rest,
until it converges or runs out of iterations. Returns the best config found, its
metrics, and a trace so the search is transparent.
"""
from __future__ import annotations

import random

from ..scanner.config import StrategyConfig
from .engine import run_backtest

# param -> (low, high, step)
PARAM_BOUNDS = {
    "min_score_to_qualify": (40.0, 90.0, 5.0),
    "min_score_to_watch": (40.0, 80.0, 5.0),
    "min_catalyst_move_pct": (-12.0, -3.0, 1.0),
    "min_volume_ratio": (1.0, 4.0, 0.5),
    "no_new_low_minutes": (5.0, 30.0, 5.0),
    "stop_pct": (1.0, 3.0, 0.5),
    "target1_pct": (1.0, 5.0, 0.5),
    "target2_pct": (2.0, 8.0, 0.5),
}


def _objective(res: dict) -> float:
    m = res.get("strategy", {})
    n = m.get("trades", 0)
    if n < 3:
        return -1e6 + n            # need a real sample to mean anything
    ev = m.get("avg_return") or 0.0
    pf = m.get("profit_factor") or 0.0
    return ev + min(n, 30) * 0.02 + pf * 0.1


def _sane(cfg: dict) -> dict:
    if cfg["min_score_to_watch"] > cfg["min_score_to_qualify"]:
        cfg["min_score_to_watch"] = cfg["min_score_to_qualify"]
    if cfg["target2_pct"] < cfg["target1_pct"]:
        cfg["target2_pct"] = cfg["target1_pct"]
    return cfg


def optimize(events, base_cfg: StrategyConfig, iterations: int = 40, seed: int = 7) -> dict:
    rng = random.Random(seed)
    params = list(PARAM_BOUNDS.keys())

    best = _sane(base_cfg.to_dict())
    base_res = run_backtest(events, StrategyConfig.from_dict(best))
    best_obj = _objective(base_res)
    base_metrics = base_res["strategy"]
    best_metrics = base_metrics

    # Warm start: if the base produces no trades, sweep the qualify gate down
    # until a region with a real sample appears, so hill-climbing has a gradient.
    if base_metrics.get("trades", 0) < 3:
        for gate in (80, 70, 60, 55, 50, 45, 40):
            trial = _sane({**best, "min_score_to_qualify": float(gate)})
            r = run_backtest(events, StrategyConfig.from_dict(trial))
            if r["strategy"].get("trades", 0) >= 3:
                best, best_obj, best_metrics = trial, _objective(r), r["strategy"]
                break

    trace = []
    for _ in range(iterations):
        cand = dict(best)
        p = rng.choice(params)
        lo, hi, step = PARAM_BOUNDS[p]
        cand[p] = max(lo, min(hi, cand[p] + rng.choice([-step, step])))
        cand = _sane(cand)
        res = run_backtest(events, StrategyConfig.from_dict(cand))
        obj = _objective(res)
        accepted = obj > best_obj
        if accepted:
            best, best_obj, best_metrics = cand, obj, res["strategy"]
        trace.append({"param": p, "value": cand[p], "objective": round(obj, 3),
                      "trades": res["strategy"].get("trades", 0), "accepted": accepted})

    changed = {k: best[k] for k in PARAM_BOUNDS if best[k] != _sane(base_cfg.to_dict())[k]}
    return {
        "best_config": best,
        "best_metrics": best_metrics,
        "base_metrics": base_metrics,
        "objective": round(best_obj, 3),
        "improved": best_obj > _objective(base_res),
        "changed_params": changed,
        "iterations": iterations,
        "trace": trace[-12:],
    }
