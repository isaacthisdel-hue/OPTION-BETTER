"""Data provider interface.

Every provider (Finnhub, FMP, Massive) implements this contract so the scanner
and backtester never know which vendor is behind the data. Add a paid provider
later by writing one more subclass — no changes to scoring or scanning code.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional


class MarketDataProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def intraday_bars(
        self, symbol: str, resolution: str, start_epoch: int, end_epoch: int
    ) -> list[dict]:
        """Return 1/5-min bars: [{t,o,h,l,c,v}, ...] ascending by t."""

    @abstractmethod
    async def daily_bars(self, symbol: str, days: int) -> list[dict]:
        """Return recent daily bars for average-volume / prev-close context."""

    @abstractmethod
    async def quote(self, symbol: str) -> Optional[dict]:
        """Latest quote: {price, prev_close, open, ...} or None."""

    @abstractmethod
    async def earnings_calendar(self, from_date: str, to_date: str) -> list[dict]:
        """Companies reporting: [{symbol, date, hour, eps_estimate, ...}]."""

    @abstractmethod
    async def earnings_surprise(self, symbol: str) -> Optional[dict]:
        """Most recent actual vs estimate: {eps_actual, eps_estimate,
        eps_surprise_pct, revenue_actual, revenue_estimate,
        revenue_surprise_pct} or None."""

    @abstractmethod
    async def fundamentals(self, symbol: str) -> Optional[dict]:
        """Valuation metrics: {pe, forward_pe, price_to_sales, market_cap,
        week52_high, week52_low} or None."""

    async def options_expected_move(self, symbol: str) -> Optional[float]:
        """Implied earnings move (%). Optional — free providers return None.
        Overridden by a paid options provider later."""
        return None

    async def aclose(self) -> None:
        """Release any HTTP resources."""
        return None
