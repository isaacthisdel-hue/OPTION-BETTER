"""Provider factory.

Returns a provider based on settings. The default free-tier setup is a composite:
Finnhub for quotes/candles/calendar, FMP for fundamentals & surprises. Add a
Massive provider module and register it here to go full real-time later.
"""
from __future__ import annotations

from typing import Optional

from ..core.config import get_settings
from .base import MarketDataProvider
from .finnhub import FinnhubProvider
from .fmp import FMPProvider


class CompositeProvider(MarketDataProvider):
    """Free-tier default: Finnhub for market data, FMP for fundamentals."""
    name = "composite(finnhub+fmp)"

    def __init__(self, finnhub: FinnhubProvider, fmp: Optional[FMPProvider]):
        self._fh = finnhub
        self._fmp = fmp

    async def intraday_bars(self, *a, **k):
        return await self._fh.intraday_bars(*a, **k)

    async def daily_bars(self, *a, **k):
        return await self._fh.daily_bars(*a, **k)

    async def quote(self, *a, **k):
        return await self._fh.quote(*a, **k)

    async def earnings_calendar(self, *a, **k):
        return await self._fh.earnings_calendar(*a, **k)

    async def earnings_surprise(self, symbol):
        if self._fmp:
            fmp_res = await self._fmp.earnings_surprise(symbol)
            if fmp_res:
                return fmp_res
        return await self._fh.earnings_surprise(symbol)

    async def fundamentals(self, symbol):
        if self._fmp:
            fmp_res = await self._fmp.fundamentals(symbol)
            if fmp_res:
                return fmp_res
        return await self._fh.fundamentals(symbol)

    async def aclose(self):
        await self._fh.aclose()
        if self._fmp:
            await self._fmp.aclose()


def get_provider() -> MarketDataProvider:
    s = get_settings()
    if s.provider == "fmp":
        return FMPProvider(s.fmp_api_key)
    if s.provider == "massive":
        # Placeholder: implement MassiveProvider and import here when you add
        # a paid key. Falls back to Finnhub so the app still runs.
        return FinnhubProvider(s.finnhub_api_key)
    # default: composite free tier
    fmp = FMPProvider(s.fmp_api_key) if s.fmp_api_key else None
    return CompositeProvider(FinnhubProvider(s.finnhub_api_key), fmp)
