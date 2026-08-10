"""Alpha Vantage adapter — FREE real intraday history for the backtester.

Finnhub's free tier doesn't serve stock candles, so historical replay uses
Alpha Vantage instead (free key: ~25 requests/day, ~5/min). One
TIME_SERIES_INTRADAY(full) call per ticker returns ~1 month of 1-min bars, which
covers "the last week" plus enough prior context for prev-close and follow-through.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import httpx
import pytz

BASE = "https://www.alphavantage.co/query"
_ET = pytz.timezone("America/New_York")


class AlphaVantageError(RuntimeError):
    pass


def _epoch_et(ts: str) -> int:
    """AV intraday timestamps are US/Eastern wall-clock, no tz suffix."""
    naive = dt.datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    return int(_ET.localize(naive).timestamp())


def parse_intraday(data: dict) -> list[dict]:
    """Parse an AV TIME_SERIES_INTRADAY payload -> ascending [{t,o,h,l,c,v}]."""
    if not isinstance(data, dict):
        raise AlphaVantageError("Unexpected response (not an object).")
    for k in ("Note", "Information", "Error Message"):
        if k in data:
            raise AlphaVantageError(str(data[k]))
    series_key = next((k for k in data if k.startswith("Time Series")), None)
    if not series_key:
        raise AlphaVantageError("No time series in response.")
    out = []
    for ts, row in data[series_key].items():
        out.append({
            "t": _epoch_et(ts),
            "o": float(row["1. open"]), "h": float(row["2. high"]),
            "l": float(row["3. low"]), "c": float(row["4. close"]),
            "v": float(row["5. volume"]),
        })
    out.sort(key=lambda b: b["t"])
    return out


class AlphaVantageProvider:
    name = "alphavantage"

    def __init__(self, api_key: str):
        self._key = api_key
        self._client = httpx.Client(timeout=30.0)

    def close(self) -> None:
        self._client.close()

    def _get(self, **params) -> dict:
        params["apikey"] = self._key
        r = self._client.get(BASE, params=params)
        r.raise_for_status()
        return r.json()

    def intraday_full(self, symbol: str, interval: str = "1min") -> list[dict]:
        data = self._get(function="TIME_SERIES_INTRADAY", symbol=symbol,
                         interval=interval, outputsize="full", extended_hours="false")
        return parse_intraday(data)
