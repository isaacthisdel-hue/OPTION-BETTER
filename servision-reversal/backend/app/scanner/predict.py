"""Directional movement prediction.

For each scanned stock, weigh reversal evidence against continuation evidence
from the SAME measured facts the scorer uses, then call a direction (REVERSAL vs
CONTINUATION), a predicted % move, a confidence, and the matching option side
(CALL/PUT) aimed at next Friday. Transparent by construction — the two signal
scores are returned so nothing is hidden.
"""
from __future__ import annotations

from .scorer import Candidate
from ..backtesting.reversal_model import _next_friday, estimate_reversal


def predict_movement(cand: Candidate, saved_model: dict | None = None) -> dict:
    move = cand.move_pct if cand.move_pct is not None else 0.0

    rev = 0.0
    cont = 0.0
    if cand.higher_low:
        rev += 2.0
    if cand.vwap_reclaim:
        rev += 2.0
    if cand.minutes_since_new_low is not None and cand.minutes_since_new_low >= 15:
        rev += 1.5
    if cand.vwap_distance_pct is not None and cand.vwap_distance_pct <= -3:
        rev += 1.0  # stretched below VWAP = oversold snap-back fuel

    if cand.higher_low is False:
        cont += 1.0
    if cand.vwap_reclaim is False:
        cont += 1.5
    if cand.minutes_since_new_low is not None and cand.minutes_since_new_low < 10:
        cont += 2.0  # fresh lows = trend still pushing
    if (cand.vwap_distance_pct is not None and cand.vwap_distance_pct < 0
            and not cand.vwap_reclaim):
        cont += 1.0
    if (cand.volume_ratio or 0) >= 2 and abs(move) >= 3:
        cont += 1.0  # heavy volume behind the move

    total = rev + cont
    direction = "REVERSAL" if rev > cont else "CONTINUATION"
    margin = (abs(rev - cont) / total) if total else 0.0
    confidence = "high" if margin >= 0.5 else "medium" if margin >= 0.25 else "low"

    rev_mag = estimate_reversal(move, saved_model)["estimated_reversal_pct"]

    if direction == "REVERSAL":
        # reversal of a down move is up (and vice-versa)
        predicted = rev_mag if move < 0 else -rev_mag
    else:
        # continuation extends the current move in the same direction
        mag = min(abs(move) * 0.5, 10.0)
        predicted = -mag if move < 0 else mag

    predicted = round(predicted, 1)
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
