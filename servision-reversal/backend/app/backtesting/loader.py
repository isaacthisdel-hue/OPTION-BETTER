"""Real historical-event loader (Alpha Vantage).

Turns real recent 1-min bars into HistoricalEvent objects the backtester can
replay. For each ticker we take the last N trading sessions and keep the ones
that actually sold off (max intraday drawdown from the prior close past a floor),
so real down-days become test events. Each successfully-fetched ticker
contributes at least its single worst session, so a backtest always has data to
show. One API call per ticker.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pytz

from ..core.config import get_settings
from .engine import HistoricalEvent
from ..adapters.alphavantage import AlphaVantageProvider, AlphaVantageError

_ET = pytz.timezone("America/New_York")


class LoaderError(RuntimeError):
    pass


def _session_date(epoch: int) -> dt.date:
    return dt.datetime.fromtimestamp(epoch, _ET).date()


def _is_rate_limit(msg: str) -> bool:
    m = msg.lower()
    return any(k in m for k in ("rate limit", "frequency", "per day", "per minute",
                                "25 requests", "premium", "thank you"))


def load_recent_events(settings=None):
    settings = settings or get_settings()
    if not settings.alphavantage_api_key:
        raise LoaderError("No ALPHAVANTAGE_API_KEY configured.")

    tickers = [t.strip().upper() for t in settings.backtest_tickers.split(",") if t.strip()]
    tickers = tickers[: settings.backtest_max_tickers]
    lookback = settings.backtest_lookback_days
    floor = settings.backtest_min_gap_pct     # e.g. -4.0
    per_ticker_cap = 3

    prov = AlphaVantageProvider(settings.alphavantage_api_key)
    events: list[HistoricalEvent] = []
    per_ticker: list[dict] = []
    skipped: list[dict] = []
    rate_limited = 0
    try:
        for sym in tickers:
            try:
                bars = prov.intraday_full(sym)
            except AlphaVantageError as e:
                if _is_rate_limit(str(e)):
                    rate_limited += 1
                    skipped.append({"symbol": sym, "reason": "rate-limited"})
                else:
                    skipped.append({"symbol": sym, "reason": str(e)[:100]})
                continue
            except Exception as e:  # noqa
                skipped.append({"symbol": sym, "reason": f"fetch failed: {type(e).__name__}"})
                continue
            if not bars:
                skipped.append({"symbol": sym, "reason": "no bars returned"})
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
                    continue  # need prior session for prev_close
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

            # keep real sell-offs; if none clear the floor, keep the single worst
            keep = [c for c in cands if c["drawdown"] <= floor]
            if not keep:
                keep = [min(cands, key=lambda c: c["drawdown"])]
            keep = sorted(keep, key=lambda c: c["drawdown"])[:per_ticker_cap]

            for c in keep:
                vols = [x["v"] for x in c["session"] if x["v"]]
                events.append(HistoricalEvent(
                    symbol=sym, session_bars=c["session"], prev_close=c["prev_close"],
                    catalyst="news", avg_volume=(sum(vols) / len(vols)) if vols else None,
                ))
            per_ticker.append({
                "symbol": sym,
                "sessions_scanned": len(cands),
                "worst_drawdown_pct": min(c["drawdown"] for c in cands),
                "events_added": len(keep),
            })
    finally:
        prov.close()

    meta = {
        "source": "alphavantage",
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
        "note": ("Real 1-min data. Events are the worst recent sell-off sessions per ticker. "
                 "'Catalyst' is 'news' since free data can't confirm earnings dates."),
    }
    return events, meta
