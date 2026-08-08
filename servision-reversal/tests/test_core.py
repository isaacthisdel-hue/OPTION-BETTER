"""Core tests: indicators, scoring, no-lookahead, paper engine, backtest.

Run: cd backend && pytest ../tests -q
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from app.scanner import indicators as ind
from app.scanner.config import StrategyConfig
from app.scanner.scorer import Candidate, score_candidate
from app.services.paper_engine import build_equity_setup, track_equity_trade


def _bar(t, o, h, l, c, v=1000):
    return {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}


# --- VWAP ---
def test_vwap_basic():
    bars = [_bar(0, 10, 10, 10, 10, 100), _bar(60, 20, 20, 20, 20, 100)]
    assert ind.vwap(bars) == 15.0


def test_vwap_volume_weighted():
    bars = [_bar(0, 10, 10, 10, 10, 300), _bar(60, 20, 20, 20, 20, 100)]
    # (10*300 + 20*100) / 400 = 12.5
    assert ind.vwap(bars) == 12.5


# --- volume ratio ---
def test_volume_ratio():
    assert ind.volume_ratio(2000, 1000) == 2.0
    assert ind.volume_ratio(1000, 0) is None


# --- move / gap ---
def test_move_pct():
    assert round(ind.move_pct(90, 100), 2) == -10.0


# --- no new low as-of (look-ahead guard) ---
def test_minutes_since_new_low_ignores_future():
    bars = [_bar(0, 100, 100, 95, 96), _bar(60, 96, 97, 92, 93),
            _bar(120, 93, 95, 93, 94), _bar(180, 94, 96, 90, 91)]
    # As of t=120, the last new low was at t=60 (92); the 90 at t=180 is future.
    m = ind.minutes_since_new_low(bars, 120)
    assert m == 1  # (120-60)/60


# --- higher low detection ---
def test_higher_low_detected():
    # low at start, then a higher trough later
    bars = [
        _bar(0, 100, 100, 90, 91),
        _bar(60, 91, 93, 91, 92),
        _bar(120, 92, 95, 92, 94),
        _bar(180, 94, 96, 93, 95),   # pullback trough at 93 > 90
        _bar(240, 95, 98, 95, 97),
    ]
    assert ind.has_higher_low(bars, 240, min_separation_min=1) is True


def test_higher_low_absent_when_making_new_lows():
    bars = [_bar(i * 60, 100 - i, 100 - i, 95 - i, 96 - i) for i in range(6)]
    assert ind.has_higher_low(bars, 300) is False


# --- vwap reclaim ---
def test_vwap_reclaim():
    bars = [_bar(0, 100, 100, 98, 98, 1000),   # below
            _bar(60, 98, 99, 97, 97, 1000),    # below
            _bar(120, 97, 105, 97, 104, 1000)] # jumps above vwap
    assert ind.reclaimed_vwap(bars, 120) is True


# --- scoring is transparent and additive ---
def test_score_components_sum_to_total():
    cfg = StrategyConfig()
    c = Candidate(symbol="X", as_of_epoch=0, catalyst="earnings",
                  move_pct=-12.0, volume_ratio=3.0, vwap_distance_pct=-4.0,
                  minutes_since_new_low=30, higher_low=True, vwap_reclaim=True,
                  eps_surprise_pct=7.5)
    s = score_candidate(c, cfg)
    assert abs(s.total - sum(x.points for x in s.components)) < 1e-9
    assert s.status in ("WATCH", "QUALIFIED")


def test_eps_miss_penalizes():
    cfg = StrategyConfig()
    beat = score_candidate(Candidate("X", 0, catalyst="earnings", move_pct=-10,
                                     eps_surprise_pct=10), cfg).total
    miss = score_candidate(Candidate("X", 0, catalyst="earnings", move_pct=-10,
                                     eps_surprise_pct=-10), cfg).total
    assert beat > miss


# --- paper engine outcome resolution ---
def test_paper_trade_hits_target():
    cfg = StrategyConfig(stop_pct=2, target1_pct=1, target2_pct=3, slippage_pct=0)
    setup = build_equity_setup("X", 100.0, 0, 85, cfg)
    bars = [_bar(60, 100, 102, 100, 101)]  # high 102 >= target1 101
    out = track_equity_trade(setup, bars, cfg)
    assert out["exit_reason"] in ("target1", "target2")
    assert out["return_pct"] > 0


def test_paper_trade_hits_stop_conservatively():
    cfg = StrategyConfig(stop_pct=1, target1_pct=1, target2_pct=3, slippage_pct=0)
    setup = build_equity_setup("X", 100.0, 0, 85, cfg)
    # bar spans both stop (99) and target (101): stop assumed first (worst case)
    bars = [_bar(60, 100, 101, 98, 100)]
    out = track_equity_trade(setup, bars, cfg)
    assert out["exit_reason"] == "stop"
    assert out["return_pct"] < 0


# --- backtest no-lookahead: fundamentals not used before available_at ---
def test_backtest_respects_fundamental_timing():
    from app.backtesting.engine import HistoricalEvent, _candidate_at
    cfg = StrategyConfig()
    bars = [_bar(1000 + i * 60, 100, 101, 99, 100) for i in range(5)]
    ev = HistoricalEvent(symbol="X", session_bars=bars, prev_close=110,
                         catalyst="earnings",
                         fundamentals={"eps_surprise_pct": 10.0},
                         fundamentals_available_at=5000)
    before = _candidate_at(ev, 1000, cfg)   # earnings not public yet
    after = _candidate_at(ev, 6000, cfg)    # earnings public
    assert before.eps_surprise_pct is None
    assert after.eps_surprise_pct == 10.0


# --- metrics sample gate ---
def test_metrics_flags_small_sample():
    from app.backtesting.engine import compute_metrics
    trades = [{"return_pct": 1.0}, {"return_pct": -0.5}]
    m = compute_metrics(trades)
    assert m["insufficient_sample"] is True
    assert m["trades"] == 2
