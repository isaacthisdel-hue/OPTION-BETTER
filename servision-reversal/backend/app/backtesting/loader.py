"""Real historical-event loader (Alpha Vantage).

Turns real recent 1-min bars into HistoricalEvent objects the backtester can
replay. For each ticker we take the last N trading sessions and, for any session
that gapped DOWN past the strategy's catalyst-move floor, treat it as a candidate
event (a real 'catalyst-driven drop' to test reversion on). Prev-close comes from
the prior session in the same fetch, so it's one API call per ticker.
"""
from __future__ import annotations

import datetime as dt
from collections import defaultdict

import pytz

from ..core.config import get_settings
from ..scanner.config import StrategyConfig
from .engine import HistoricalEvent
from ..adapters.alphavantage import AlphaVantageProvider, AlphaVantageError

_ET = pytz.timezone("America/New_York")


class LoaderError(RuntimeError):
    pass


def _session_date(epoch: int) -> dt.date:
    return dt.datetime.fromtimestamp(epoch, _ET).date()


def load_recent_events(settings=None):
    settings = settings or get_settings()
    if not settings.alphavantage_api_key:
        raise LoaderError("No ALPHAVANTAGE_API_KEY configured.")
    cfg = StrategyConfig()
    tickers = [t.strip().upper() for t in settings.backtest_tickers.split(",") if t.strip()]
    tickers = tickers[: settings.backtest_max_tickers]
    lookback = settings.backtest_lookback_days

    prov = AlphaVantageProvider(settings.alphavantage_api_key)
    events: list[HistoricalEvent] = []
    used: list[dict] = []
    skipped: list[dict] = []
    try:
        for sym in tickers:
            try:
                bars = prov.intraday_full(sym)
            except AlphaVantageError as e:
                skipped.append({"symbol": sym, "reason": str(e)[:120]})
                continue
            except Exception as e:  # noqa
                skipped.append({"symbol": sym, "reason": f"fetch failed: {type(e).__name__}"})
                continue
            if not bars:
                skipped.append({"symbol": sym, "reason": "no bars"})
                continue

            by_day: dict[dt.date, list[dict]] = defaultdict(list)
            for b in bars:
                by_day[_session_date(b["t"])].append(b)
            days = sorted(by_day.keys())
            recent = days[-lookback:] if len(days) > lookback else days

            for i, day in enumerate(days):
                if day not in recent:
                    continue
                idx = days.index(day)
                if idx == 0:
                    continue  # need a prior session for prev_close
                prev_close = by_day[days[idx - 1]][-1]["c"]
                session = by_day[day]
                if not session or not prev_close:
                    continue
                open_px = session[0]["o"]
                gap_pct = (open_px - prev_close) / prev_close * 100.0
                # Only keep real catalyst-style gap-downs past the floor.
                if gap_pct > cfg.min_catalyst_move_pct:
                    continue
                vols = [x["v"] for x in session if x["v"]]
                avg_vol = (sum(vols) / len(vols)) if vols else None
                events.append(HistoricalEvent(
                    symbol=sym, session_bars=session, prev_close=prev_close,
                    catalyst="news",  # real gap-down; we can't verify earnings on free data
                    avg_volume=avg_vol,
                ))
                used.append({"symbol": sym, "date": day.isoformat(),
                             "gap_pct": round(gap_pct, 2)})
    finally:
        prov.close()

    meta = {
        "source": "alphavantage",
        "tickers_requested": tickers,
        "events": len(events),
        "used": used,
        "skipped": skipped,
        "lookback_days": lookback,
        "note": ("Real 1-min data. 'Catalyst' is marked 'news' because free data "
                 "can't confirm earnings. Small samples are flagged low-confidence."),
    }
    return events, meta
