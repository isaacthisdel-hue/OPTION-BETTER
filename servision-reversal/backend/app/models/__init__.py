"""Database models.

Design principle: `observations` is append-only. Every scan writes one row per
symbol per scan with a full snapshot + the score components as JSON, so you can
reconstruct exactly what the algorithm knew at any past timestamp. Nothing
overwrites history.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class StrategyVersion(Base):
    __tablename__ = "strategy_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(50), index=True)
    config_json: Mapped[dict] = mapped_column(JSON)          # full StrategyConfig
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                    server_default=func.now())
    notes: Mapped[str] = mapped_column(Text, default="")


class Observation(Base):
    """One scored snapshot of one symbol at one instant. APPEND ONLY."""
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    observed_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                     index=True, server_default=func.now())
    as_of_epoch: Mapped[int] = mapped_column(Integer, index=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))

    price: Mapped[float | None] = mapped_column(Float)
    move_pct: Mapped[float | None] = mapped_column(Float)
    volume_ratio: Mapped[float | None] = mapped_column(Float)
    vwap_distance_pct: Mapped[float | None] = mapped_column(Float)
    higher_low: Mapped[bool | None] = mapped_column(Boolean)
    vwap_reclaim: Mapped[bool | None] = mapped_column(Boolean)
    eps_surprise_pct: Mapped[float | None] = mapped_column(Float)
    revenue_surprise_pct: Mapped[float | None] = mapped_column(Float)
    catalyst: Mapped[str | None] = mapped_column(String(20))

    score_total: Mapped[float] = mapped_column(Float, index=True)
    status: Mapped[str] = mapped_column(String(12), index=True)   # SKIP/WATCH/QUALIFIED
    components_json: Mapped[list] = mapped_column(JSON)           # full breakdown
    snapshot_json: Mapped[dict] = mapped_column(JSON)            # raw candidate facts


class PaperTrade(Base):
    """A hypothetical trade. NEVER a real order. NEVER a recommendation."""
    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(12), index=True)
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    opened_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                   server_default=func.now())
    setup: Mapped[str] = mapped_column(String(60), default="Earnings reversal")
    instrument: Mapped[str] = mapped_column(String(10), default="equity")  # equity|option

    entry_price: Mapped[float] = mapped_column(Float)
    stop_price: Mapped[float] = mapped_column(Float)
    target1: Mapped[float | None] = mapped_column(Float)
    target2: Mapped[float | None] = mapped_column(Float)
    entry_epoch: Mapped[int] = mapped_column(Integer)

    # option-only fields (HISTORICAL PAPER SIMULATION)
    option_type: Mapped[str | None] = mapped_column(String(4))   # call|put
    strike: Mapped[float | None] = mapped_column(Float)
    expiration: Mapped[str | None] = mapped_column(String(12))
    entry_premium: Mapped[float | None] = mapped_column(Float)

    # outcome (filled by the tracker)
    status: Mapped[str] = mapped_column(String(12), default="open")  # open|closed
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_epoch: Mapped[int | None] = mapped_column(Integer)
    exit_reason: Mapped[str | None] = mapped_column(String(20))   # target|stop|eod
    return_pct: Mapped[float | None] = mapped_column(Float)
    score_at_entry: Mapped[float | None] = mapped_column(Float)
    components_json: Mapped[list | None] = mapped_column(JSON)


class Backtest(Base):
    __tablename__ = "backtests"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True),
                                                    server_default=func.now())
    strategy_version_id: Mapped[int] = mapped_column(ForeignKey("strategy_versions.id"))
    params_json: Mapped[dict] = mapped_column(JSON)      # date range, filters, split
    results_json: Mapped[dict] = mapped_column(JSON)     # metrics + breakdowns
    label: Mapped[str] = mapped_column(String(120), default="")


class AppSetting(Base):
    """Simple key/value store for runtime app settings (editable watchlist,
    active strategy version) that shouldn't require an env var / redeploy."""
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON)
