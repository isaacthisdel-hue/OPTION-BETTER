"""Twelve Data adapter for the LIVE scanner (free tier: 8 req/min, 800/day).

To stay under the rate limit we make ONE time_series call per symbol per scan and
derive quote + intraday bars + (synthetic) daily bars from that single fetch.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx
import pytz

from .base import MarketDataProvider

BASE = "https://api.twelvedata.com"
_ET = pytz.timezone("America/New_York")


class TwelveDataError(RuntimeError):
    pass


class RateLimited(TwelveDataError):
    pass


def _epoch(ts: str) -> int:
    ts = ts.strip()
    if len(ts) <= 10:
        ts += " 00:00:00"
    return int(_ET.localize(dt.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")).timestamp())


def _et_date(epoch: int) -> dt.date:
    return dt.datetime.fromtimestamp(epoch, _ET).date()


class TwelveDataProvider(MarketDataProvider):
    name = "twelvedata"

    def __init__(self, api_key: str):
        self._key = api_key
        self._client = httpx.AsyncClient(timeout=25.0)
        self._cache: dict[str, list[dict]] = {}

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _bars(self, symbol: str) -> list[dict]:
        if symbol in self._cache:
            return self._cache[symbol]
        r = await self._client.get(f"{BASE}/time_series", params={
            "symbol": symbol, "interval": "1min", "outputsize": 1560,
            "timezone": "America/New_York", "apikey": self._key})
        r.raise_for_status()
        d = r.json()
        if isinstance(d, dict) and d.get("status") == "error":
            msg = str(d.get("message", ""))
            if any(k in msg.lower() for k in ("limit", "credits", "run out")):
                raise RateLimited(msg)
            raise TwelveDataError(msg)
        vals = (d or {}).get("values") or []
        bars = [{"t": _epoch(v["datetime"]), "o": float(v["open"]), "h": float(v["high"]),
                 "l": float(v["low"]), "c": float(v["close"]), "v": float(v.get("volume") or 0)}
                for v in vals]
        bars.sort(key=lambda b: b["t"])
        self._cache[symbol] = bars
        return bars

    async def intraday_bars(self, symbol, resolution, start_epoch, end_epoch):
        try:
            bars = await self._bars(symbol)
        except TwelveDataError:
            return []
        return [b for b in bars if start_epoch <= b["t"] <= end_epoch]

    async def daily_bars(self, symbol, days):
        try:
            bars = await self._bars(symbol)
        except TwelveDataError:
            return []
        by_day: dict[dt.date, list[dict]] = {}
        for b in bars:
            by_day.setdefault(_et_date(b["t"]), []).append(b)
        out = []
        for day in sorted(by_day):
            s = by_day[day]
            out.append({"t": s[0]["t"], "o": s[0]["o"], "h": max(x["h"] for x in s),
                        "l": min(x["l"] for x in s), "c": s[-1]["c"],
                        "v": sum(x["v"] for x in s)})
        return out[-days:]

    async def quote(self, symbol):
        try:
            bars = await self._bars(symbol)
        except TwelveDataError:
            return None
        if not bars:
            return None
        by_day: dict[dt.date, list[dict]] = {}
        for b in bars:
            by_day.setdefault(_et_date(b["t"]), []).append(b)
        days = sorted(by_day)
        today = by_day[days[-1]]
        prev_close = by_day[days[-2]][-1]["c"] if len(days) >= 2 else today[0]["o"]
        return {"price": today[-1]["c"], "open": today[0]["o"],
                "high": max(b["h"] for b in today), "low": min(b["l"] for b in today),
                "prev_close": prev_close}

    async def earnings_calendar(self, from_date, to_date):
        return []

    async def earnings_surprise(self, symbol):
        return None

    async def fundamentals(self, symbol):
        return None
