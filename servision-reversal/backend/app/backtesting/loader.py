"""Real historical-event loader (multi-source).

Pulls recent 1-min bars from whichever provider key is available, preferring the
most generous free tier: Twelve Data (800/day) -> FMP (250/day) -> Alpha Vantage
(25/day). For each ticker it keeps the worst recent sell-off sessions (largest
intraday drawdown from the prior close), guaranteeing at least the single worst
session per ticker so a backtest always has data. One request per ticker.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import httpx
import pytz

from ..core.config import get_settings
from .engine import HistoricalEvent
from ..adapters.alphavantage import parse_intraday

_ET = pytz.timezone("America/New_York")


class LoaderError(RuntimeError):
    pass


class RateLimited(Exception):
    pass


def _session_date(epoch: int) -> dt.date:
    return dt.datetime.fromtimestamp(epoch, _ET).date()


def _et_epoch(ts: str) -> int:
    ts = ts.strip()
    if len(ts) <= 10:
        ts = ts + " 00:00:00"
    naive = dt.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
    return int(_ET.localize(naive).timestamp())


# ---- per-provider fetchers: return ascending [{t,o,h,l,c,v}] ----
def _fetch_twelvedata(client, key, sym):
    r = client.get("https://api.twelvedata.com/time_series", params={
        "symbol": sym, "interval": "1min", "outputsize": 5000,
        "timezone": "America/New_York", "apikey": key})
    r.raise_for_status()
    d = r.json()
    if isinstance(d, dict) and d.get("status") == "error":
        msg = str(d.get("message", ""))
        if any(k in msg.lower() for k in ("limit", "run out", "credits")):
            raise RateLimited(msg)
        raise RuntimeError(msg)
    vals = (d or {}).get("values") or []
    out = [{"t": _et_epoch(v["datetime"]), "o": float(v["open"]), "h": float(v["high"]),
            "l": float(v["low"]), "c": float(v["close"]), "v": float(v.get("volume") or 0)}
           for v in vals]
    out.sort(key=lambda b: b["t"])
    return out


def _fetch_fmp(client, key, sym):
    r = client.get(f"https://financialmodelingprep.com/api/v3/historical-chart/1min/{sym}",
                   params={"apikey": key})
    if r.status_code in (401, 403):
        raise RuntimeError("FMP intraday not available on this plan.")
    r.raise_for_status()
    d = r.json()
    if isinstance(d, dict):
        m = str(d.get("Error Message") or d.get("message") or "")
        if "limit" in m.lower():
            raise RateLimited(m)
        raise RuntimeError(m or "FMP unexpected response.")
    out = [{"t": _et_epoch(row["date"]), "o": float(row["open"]), "h": float(row["high"]),
            "l": float(row["low"]), "c": float(row["close"]), "v": float(row.get("volume") or 0)}
           for row in (d or [])]
    out.sort(key=lambda b: b["t"])
    return out


def _fetch_av(client, key, sym):
    r = client.get("https://www.alphavantage.co/query", params={
        "function": "TIME_SERIES_INTRADAY", "symbol": sym, "interval": "1min",
        "outputsize": "full", "extended_hours": "false", "apikey": key})
    r.raise_for_status()
    d = r.json()
    for k in ("Note", "Information"):
        if k in d:
            raise RateLimited(str(d[k]))
    return parse_intraday(d)


def _providers(settings):
    p = []
    if settings.twelvedata_api_key:
        p.append(("twelvedata", settings.twelvedata_api_key, _fetch_twelvedata))
    if settings.fmp_api_key:
        p.append(("fmp", settings.fmp_api_key, _fetch_fmp))
    if settings.alphavantage_api_key:
        p.append(("alphavantage", settings.alphavantage_api_key, _fetch_av))
    return p


def load_recent_events(settings=None, tickers_csv=None, max_tickers=None):
    settings = settings or get_settings()
    providers = _providers(settings)
    if not providers:
        raise LoaderError("No data key configured.")

    src = tickers_csv if tickers_csv is not None else settings.backtest_tickers
    tickers = list(dict.fromkeys(t.strip().upper() for t in src.split(",") if t.strip()))
    tickers = tickers[: (max_tickers or settings.backtest_max_tickers)]
    lookback = settings.backtest_lookback_days
    floor = settings.backtest_min_gap_pct
    per_ticker_cap = 3

    events: list[HistoricalEvent] = []
    per_ticker: list[dict] = []
    skipped: list[dict] = []
    rate_limited = 0
    sources_used: set[str] = set()

    with httpx.Client(timeout=30.0) as client:
        for sym in tickers:
            bars = None
            last_reason = "no data"
            rl_here = False
            for pname, pkey, fn in providers:
                try:
                    bars = fn(client, pkey, sym)
                    if bars:
                        sources_used.add(pname)
                        break
                    last_reason = f"{pname}: empty"
                    bars = None
                except RateLimited as e:
                    rl_here = True
                    last_reason = f"{pname}: rate-limited"
                except Exception as e:  # noqa
                    last_reason = f"{pname}: {str(e)[:60]}"
            if not bars:
                if rl_here:
                    rate_limited += 1
                    skipped.append({"symbol": sym, "reason": "rate-limited"})
                else:
                    skipped.append({"symbol": sym, "reason": last_reason})
                continue

            by_day: dict[dt.date, list[dict]] = defaultdict(list)
            for b in bars:
                by_day[_session_date(b["t"])].append(b)
            days = sorted(by_day.keys())
            recent = days[-lookback:] if len(days) > lookback else days

            cands = []
            for day in recent:
                idx = days.index(day)
                if idx == 0:
                    continue
                prev_close = by_day[days[idx - 1]][-1]["c"]
                session = by_day[day]
                if not session or not prev_close:
                    continue
                low = min(b["l"] for b in session)
                drawdown = (low - prev_close) / prev_close * 100.0
                cands.append({"day": day, "prev_close": prev_close,
                              "session": session, "drawdown": round(drawdown, 2)})
            if not cands:
                skipped.append({"symbol": sym, "reason": "no complete sessions"})
                continue

            keep = [c for c in cands if c["drawdown"] <= floor]
            if not keep:
                keep = [min(cands, key=lambda c: c["drawdown"])]
            keep = sorted(keep, key=lambda c: c["drawdown"])[:per_ticker_cap]
            for c in keep:
                vols = [x["v"] for x in c["session"] if x["v"]]
                events.append(HistoricalEvent(
                    symbol=sym, session_bars=c["session"], prev_close=c["prev_close"],
                    catalyst="news", avg_volume=(sum(vols) / len(vols)) if vols else None))
            per_ticker.append({"symbol": sym, "sessions_scanned": len(cands),
                               "worst_drawdown_pct": min(c["drawdown"] for c in cands),
                               "events_added": len(keep)})

    meta = {
        "source": "+".join(sorted(sources_used)) or "none",
        "providers_available": [p[0] for p in providers],
        "tickers_requested": tickers,
        "events": len(events),
        "per_ticker": per_ticker,
        "skipped": skipped,
        "rate_limited": rate_limited,
        "min_drop_floor_pct": floor,
        "lookback_days": lookback,
        "used": [{"symbol": e.symbol,
                  "date": _session_date(e.session_bars[0]["t"]).isoformat(),
                  "gap_pct": round((e.session_bars[0]["o"] - e.prev_close) / e.prev_close * 100.0, 2)}
                 for e in events],
        "note": "Real 1-min data. Events are the worst recent sell-off sessions per ticker.",
    }
    return events, meta


def load_all_sessions(settings=None, tickers_csv=None, max_tickers=None):
    """Return ALL recent trading sessions (not gap-filtered) as
    [{symbol, date, bars}] for intraday strategies like the First Candle Rule."""
    settings = settings or get_settings()
    providers = _providers(settings)
    if not providers:
        raise LoaderError("No data key configured.")
    src = tickers_csv if tickers_csv is not None else settings.backtest_tickers
    tickers = list(dict.fromkeys(t.strip().upper() for t in src.split(",") if t.strip()))
    tickers = tickers[: (max_tickers or settings.backtest_max_tickers)]
    lookback = settings.backtest_lookback_days

    sessions = []
    skipped = []
    rate_limited = 0
    with httpx.Client(timeout=30.0) as client:
        for sym in tickers:
            bars = None
            rl = False
            reason = "no data"
            for pname, pkey, fn in providers:
                try:
                    bars = fn(client, pkey, sym)
                    if bars:
                        break
                    bars = None
                except RateLimited:
                    rl = True
                except Exception as e:  # noqa
                    reason = f"{pname}: {str(e)[:50]}"
            if not bars:
                if rl:
                    rate_limited += 1
                    skipped.append({"symbol": sym, "reason": "rate-limited"})
                else:
                    skipped.append({"symbol": sym, "reason": reason})
                continue
            by_day = defaultdict(list)
            for b in bars:
                by_day[_session_date(b["t"])].append(b)
            for day in sorted(by_day)[-lookback:]:
                sess = by_day[day]
                if len(sess) >= 30:
                    sessions.append({"symbol": sym, "date": day.isoformat(), "bars": sess})
    meta = {"source": "multi", "tickers": tickers, "sessions": len(sessions),
            "skipped": skipped, "rate_limited": rate_limited, "lookback_days": lookback,
            "note": "All recent sessions for intraday strategies."}
    return sessions, meta


def load_symbol_sessions(symbol, settings=None):
    """Recent intraday sessions for ONE symbol: [{date, bars}] ascending."""
    settings = settings or get_settings()
    providers = _providers(settings)
    if not providers:
        raise LoaderError("No data key configured.")
    bars = None
    with httpx.Client(timeout=30.0) as client:
        for pname, pkey, fn in providers:
            try:
                bars = fn(client, pkey, symbol)
                if bars:
                    break
                bars = None
            except Exception:  # noqa
                bars = None
    if not bars:
        return []
    by_day = defaultdict(list)
    for b in bars:
        by_day[_session_date(b["t"])].append(b)
    return [{"date": d.isoformat(), "bars": by_day[d]}
            for d in sorted(by_day) if len(by_day[d]) >= 30]
