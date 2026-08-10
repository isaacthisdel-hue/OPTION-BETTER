"""Directional movement prediction.

For each scanned stock we (a) decide direction — REVERSAL vs CONTINUATION — by
weighing reversal evidence against continuation evidence, and (b) estimate a
CONTINUOUS predicted % move from the actual signals (move size, VWAP stretch,
volume, confirmation), scaled by confidence and optionally calibrated against the
learned backtest tiers. No flat constants — the number moves with the setup.
"""
from __future__ import annotations

from .scorer import Candidate
from ..backtesting.reversal_model import _next_friday, estimate_reversal


def predict_movement(cand: Candidate, saved_model: dict | None = None) -> dict:
    move = cand.move_pct if cand.move_pct is not None else 0.0
    mv = abs(move)
    vwap_d = cand.vwap_distance_pct or 0.0
    vext = abs(vwap_d) if vwap_d < 0 else 0.0          # stretched BELOW vwap
    vol = cand.volume_ratio or 0.0
    fresh_low = (cand.minutes_since_new_low is not None and cand.minutes_since_new_low < 10)
    stalled = (cand.minutes_since_new_low is not None and cand.minutes_since_new_low >= 15)

    # --- direction evidence ---
    rev = 0.0
    cont = 0.0
    if cand.higher_low:
        rev += 2.0
    if cand.vwap_reclaim:
        rev += 2.0
    if stalled:
        rev += 1.5
    if vext >= 3:
        rev += 1.0
    if cand.higher_low is False:
        cont += 1.0
    if cand.vwap_reclaim is False:
        cont += 1.5
    if fresh_low:
        cont += 2.0
    if vwap_d < 0 and not cand.vwap_reclaim:
        cont += 1.0
    if vol >= 2 and mv >= 3:
        cont += 1.0

    total = rev + cont
    direction = "REVERSAL" if rev > cont else "CONTINUATION"
    margin = (abs(rev - cont) / total) if total else 0.0
    confidence = "high" if margin >= 0.5 else "medium" if margin >= 0.25 else "low"
    conf_mult = {"high": 1.15, "medium": 1.0, "low": 0.8}[confidence]

    # --- continuous magnitudes ---
    # reversal: retrace a slice of the drop + snap-back from vwap stretch + volume kicker
    rev_mag = 0.35 * mv + 0.40 * vext + min(vol, 5.0) * 0.20
    # continuation: momentum persists — a slice of the move + volume + fresh-low push
    cont_mag = 0.45 * mv + min(vol, 5.0) * 0.25 + (1.0 if fresh_low else 0.0)

    # calibrate reversal magnitude against the learned tiers when available
    if saved_model:
        est = estimate_reversal(move, saved_model)
        if est.get("confidence") != "heuristic":
            rev_mag = 0.5 * rev_mag + 0.5 * est["estimated_reversal_pct"]

    if direction == "REVERSAL":
        mag = rev_mag * conf_mult
        predicted = mag if move < 0 else -mag       # reversal of a down move is up
    else:
        mag = cont_mag * conf_mult
        predicted = -mag if move < 0 else mag        # continuation extends the move

    predicted = round(max(-25.0, min(25.0, predicted)), 1)
    if abs(predicted) < 0.3:
        predicted = 0.3 if predicted >= 0 else -0.3
    opt = "CALL" if predicted >= 0 else "PUT"

    return {
        "prediction": direction,
        "direction_bias": "UP" if predicted >= 0 else "DOWN",
        "predicted_move_pct": predicted,
        "prediction_confidence": confidence,
        "reversal_score": round(rev, 1),
        "continuation_score": round(cont, 1),
        "option_aim": {"direction": opt, "expiry_next_friday": _next_friday(),
                       "target_move_pct": round(abs(predicted), 1)},
    }
