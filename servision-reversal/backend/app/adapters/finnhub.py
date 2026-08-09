"""Finnhub adapter (free tier: 60 calls/min).

Covers quotes, intraday candles, earnings calendar, earnings surprises and basic
financials. Note: Finnhub's free candle access has changed over time; if intraday
candles are gated on your key, the backtester can fall back to daily bars and the
adapter degrades gracefully (returns []). Nothing crashes on missing data.
"""
from __future__ import annotations

import time
from typing import Optional

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .base import MarketDataProvider

BASE = "https://finnhub.io/api/v1"

_RES_MAP = {"1": "1", "5": "5", "15": "15", "D": "D"}


class FinnhubProvider(MarketDataProvider):
    name = "finnhub"

    def __init__(self, api_key: str):
        self._key = api_key
        self._client = httpx.AsyncClient(timeout=20.0)

    async def aclose(self) -> None:
        await self._client.aclose()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=8), reraise=True)
    async def _get(self, path: str, **params) -> dict | list:
        params["token"] = self._key
        r = await self._client.get(f"{BASE}{path}", params=params)
        r.raise_for_status()
        return r.json()

    async def intraday_bars(self, symbol, resolution, start_epoch, end_epoch):
        res = _RES_MAP.get(resolution, "5")
        try:
            data = await self._get(
                "/stock/candle", symbol=symbol, resolution=res,
                **{"from": start_epoch, "to": end_epoch},
            )
        except httpx.HTTPError:
            return []
        if not isinstance(data, dict) or data.get("s") != "ok":
            return []
        return [
            {"t": t, "o": o, "h": h, "l": l, "c": c, "v": v}
            for t, o, h, l, c, v in zip(
                data["t"], data["o"], data["h"], data["l"], data["c"], data["v"]
            )
        ]

    async def daily_bars(self, symbol, days):
        now = int(time.time())
        start = now - days * 86400 * 2  # pad for weekends/holidays
        return await self.intraday_bars(symbol, "D", start, now)

    async def quote(self, symbol):
        try:
            d = await self._get("/quote", symbol=symbol)
        except httpx.HTTPError:
            return None
        if not d or d.get("c") in (None, 0):
            return None
        return {
            "price": d.get("c"),
            "open": d.get("o"),
            "high": d.get("h"),
            "low": d.get("l"),
            "prev_close": d.get("pc"),
        }

    async def earnings_calendar(self, from_date, to_date):
        try:
            d = await self._get(
                "/calendar/earnings",
                **{"from": from_date, "to": to_date},
            )
        except httpx.HTTPError:
            return []
        out = []
        for e in (d or {}).get("earningsCalendar", []):
            out.append({
                "symbol": e.get("symbol"),
                "date": e.get("date"),
                "hour": e.get("hour"),          # bmo | amc | dmh
                "eps_estimate": e.get("epsEstimate"),
                "eps_actual": e.get("epsActual"),
                "revenue_estimate": e.get("revenueEstimate"),
                "revenue_actual": e.get("revenueActual"),
            })
        return out

    async def earnings_surprise(self, symbol):
        try:
            d = await self._get("/stock/earnings", symbol=symbol, limit=1)
        except httpx.HTTPError:
            return None
        if not d:
            return None
        e = d[0]
        actual, est = e.get("actual"), e.get("estimate")
        surprise_pct = None
        if actual is not None and est not in (None, 0):
            surprise_pct = (actual - est) / abs(est) * 100.0
        return {
            "eps_actual": actual,
            "eps_estimate": est,
            "eps_surprise_pct": surprise_pct,
            "revenue_actual": None,
            "revenue_estimate": None,
            "revenue_surprise_pct": None,
        }

    async def fundamentals(self, symbol):
        try:
            d = await self._get("/stock/metric", symbol=symbol, metric="all")
        except httpx.HTTPError:
            return None
        m = (d or {}).get("metric", {})
        if not m:
            return None
        return {
            "pe": m.get("peTTM"),
            "forward_pe": m.get("forwardPE") or m.get("peNTM"),
            "price_to_sales": m.get("psTTM"),
            "market_cap": m.get("marketCapitalization"),
            "week52_high": m.get("52WeekHigh"),
            "week52_low": m.get("52WeekLow"),
        }
