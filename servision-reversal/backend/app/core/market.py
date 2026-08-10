"""US equity market session helper (US/Eastern).

Single source of truth for "is the regular session open right now?" used by the
API to short-circuit a scan when the market is closed (so the UI can show a clear
message instead of scanning stale/empty data), and by the worker.
"""
from __future__ import annotations

import datetime as dt

import pytz

from .config import get_settings

_OPEN_MIN = 9 * 60 + 30    # 09:30 ET
_CLOSE_MIN = 16 * 60       # 16:00 ET


def market_status(now: dt.datetime | None = None) -> dict:
    settings = get_settings()
    tz = pytz.timezone(settings.market_tz)
    now = now.astimezone(tz) if now else dt.datetime.now(tz)
    minutes = now.hour * 60 + now.minute
    is_weekday = now.weekday() < 5
    is_open = is_weekday and _OPEN_MIN <= minutes <= _CLOSE_MIN

    if is_open:
        reason = "Regular session open (09:30-16:00 ET)."
    elif not is_weekday:
        reason = "Weekend - US market is closed."
    elif minutes < _OPEN_MIN:
        reason = "Pre-market - regular session opens at 09:30 ET."
    else:
        reason = "After-hours - regular session closed at 16:00 ET."

    return {
        "open": is_open,
        "reason": reason,
        "now_et": now.strftime("%a %Y-%m-%d %H:%M ET"),
    }
