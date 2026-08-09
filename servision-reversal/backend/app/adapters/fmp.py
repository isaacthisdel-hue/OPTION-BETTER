"""Financial Modeling Prep adapter (free tier: 250 calls/day).

Used mainly for fundamentals and earnings surprises, where it's stronger than
Finnhub. On the free tier calls are scarce, so the scanner caches these per
symbol per day (see services/cache). FMP is NOT used for intraday scanning.
"""
from __future__ import annotations

from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import MarketDataProvider

BASE = "https://financialmodelingprep.com/api/v3"


class FMPProvider(MarketDataProvider):
    name = "fmp"

    def __init__(self, api_key: str):
        self._key = api_key
        self._client = httpx.AsyncClient(timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _get(self, path: str, **params) -> list | dict:
        params["apikey"] = self._key
        r = await self._client.get(f"{BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()

    async def intraday_bars(self, symbol, resolution, start_epoch, end_epoch):
        interval = {"1": "1min", "5": "5min", "15": "15min"}.get(resolution, "5min")
        try:
            d = await self._get(f"/historical-chart/{interval}/{symbol}")
        except httpx.HTTPError:
            return []
        import datetime as dt
        out = []
        for row in d or []:
            ts = int(dt.datetime.fromisoformat(row["date"]).timestamp())
            if start_epoch <= ts <= end_epoch:
                out.append({"t": ts, "o": row["open"], "h": row["high"],
                            "l": row["low"], "c": row["close"], "v": row["volume"]})
        return sorted(out, key=lambda b: b["t"])

    async def daily_bars(self, symbol, days):
        try:
            d = await self._get(f"/historical-price-full/{symbol}", timeseries=days)
        except httpx.HTTPError:
            return []
        import datetime as dt
        out = []
        for row in (d or {}).get("historical", []):
            ts = int(dt.datetime.fromisoformat(row["date"]).timestamp())
            out.append({"t": ts, "o": row["open"], "h": row["high"],
                        "l": row["low"], "c": row["close"], "v": row["volume"]})
        return sorted(out, key=lambda b: b["t"])

    async def quote(self, symbol):
        try:
            d = await self._get(f"/quote/{symbol}")
        except httpx.HTTPError:
            return None
        if not d:
            return None
        q = d[0]
        return {"price": q.get("price"), "open": q.get("open"),
                "prev_close": q.get("previousClose")}

    async def earnings_calendar(self, from_date, to_date):
        try:
            d = await self._get("/earning_calendar", **{"from": from_date, "to": to_date})
        except httpx.HTTPError:
            return []
        return [{
            "symbol": e.get("symbol"), "date": e.get("date"),
            "hour": e.get("time"), "eps_estimate": e.get("epsEstimated"),
            "eps_actual": e.get("eps"), "revenue_estimate": e.get("revenueEstimated"),
            "revenue_actual": e.get("revenue"),
        } for e in (d or [])]

    async def earnings_surprise(self, symbol):
        try:
            d = await self._get(f"/earnings-surprises/{symbol}")
        except httpx.HTTPError:
            return None
        if not d:
            return None
        e = d[0]
        actual, est = e.get("actualEarningResult"), e.get("estimatedEarning")
        eps_surprise = None
        if actual is not None and est not in (None, 0):
            eps_surprise = (actual - est) / abs(est) * 100.0
        return {
            "eps_actual": actual, "eps_estimate": est,
            "eps_surprise_pct": eps_surprise,
            "revenue_actual": None, "revenue_estimate": None,
            "revenue_surprise_pct": None,
        }

    async def fundamentals(self, symbol):
        try:
            ratios = await self._get(f"/ratios-ttm/{symbol}")
            profile = await self._get(f"/profile/{symbol}")
        except httpx.HTTPError:
            return None
        r = (ratios or [{}])[0]
        p = (profile or [{}])[0]
        return {
            "pe": r.get("peRatioTTM"),
            "forward_pe": r.get("forwardPERatioTTM"),
            "price_to_sales": r.get("priceToSalesRatioTTM"),
            "market_cap": p.get("mktCap"),
            "week52_high": None,
            "week52_low": None,
        }
