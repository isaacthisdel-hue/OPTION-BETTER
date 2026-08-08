"""Anti-overfitting utilities.

Splits historical events into train / validation / out-of-sample by date and
runs the backtest on each, so you can see whether an edge that appears in the
development period survives on data the strategy never touched.

The honest warning: if train looks great and out-of-sample doesn't, the strategy
is probably overfit. This module flags that automatically.
"""
from __future__ import annotations

import datetime as dt

from .engine import HistoricalEvent, run_backtest
from ..scanner.config import StrategyConfig


def _year_of(ev: HistoricalEvent) -> int:
    first_t = ev.session_bars[0]["t"] if ev.session_bars else 0
    return dt.datetime.utcfromtimestamp(first_t).year


def split_by_year(
    events: list[HistoricalEvent],
    train_years: set[int],
    validation_years: set[int],
    oos_years: set[int],
):
    train, val, oos = [], [], []
    for ev in events:
        y = _year_of(ev)
        if y in train_years:
            train.append(ev)
        elif y in validation_years:
            val.append(ev)
        elif y in oos_years:
            oos.append(ev)
    return train, val, oos


def run_split_backtest(
    events: list[HistoricalEvent], cfg: StrategyConfig,
    train_years=frozenset({2022, 2023, 2024}),
    validation_years=frozenset({2025}),
    oos_years=frozenset({2026}),
) -> dict:
    train, val, oos = split_by_year(events, set(train_years),
                                    set(validation_years), set(oos_years))
    r_train = run_backtest(train, cfg)["strategy"] if train else {"trades": 0}
    r_val = run_backtest(val, cfg)["strategy"] if val else {"trades": 0}
    r_oos = run_backtest(oos, cfg)["strategy"] if oos else {"trades": 0}

    warning = None
    tw = r_train.get("win_rate")
    ow = r_oos.get("win_rate")
    if tw and ow and r_oos.get("trades", 0) >= 10 and (tw - ow) >= 10:
        warning = ("Strategy may be overfit: out-of-sample win rate is materially "
                   "below the development period.")

    return {
        "train": r_train,
        "validation": r_val,
        "out_of_sample": r_oos,
        "overfit_warning": warning,
    }
