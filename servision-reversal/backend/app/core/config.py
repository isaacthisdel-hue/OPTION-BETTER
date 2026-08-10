"""Application configuration. All secrets come from environment variables.

Never hardcode API keys or DB credentials here. Locally these load from a
git-ignored .env file; in production they are set in the Railway dashboard.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg2://postgres:postgres@localhost:5432/reversal",
        alias="DATABASE_URL",
    )

    # --- Data provider selection ---
    # "finnhub" (default free), "fmp", or "massive" (paid, add key + switch)
    provider: str = Field(default="finnhub", alias="PROVIDER")
    finnhub_api_key: str = Field(default="", alias="FINNHUB_API_KEY")
    fmp_api_key: str = Field(default="", alias="FMP_API_KEY")
    massive_api_key: str = Field(default="", alias="MASSIVE_API_KEY")
    alphavantage_api_key: str = Field(default="", alias="ALPHAVANTAGE_API_KEY")
    twelvedata_api_key: str = Field(default="", alias="TWELVEDATA_API_KEY")

    # --- Backtest (real data via Alpha Vantage) ---
    backtest_tickers: str = Field(default="NBIS,COIN,SMCI,TSLA,AMD", alias="BACKTEST_TICKERS")
    backtest_max_tickers: int = Field(default=5, alias="BACKTEST_MAX_TICKERS")
    backtest_lookback_days: int = Field(default=7, alias="BACKTEST_LOOKBACK_DAYS")
    backtest_min_gap_pct: float = Field(default=-4.0, alias="BACKTEST_MIN_GAP_PCT")

    # --- Scanner behaviour ---
    scan_interval_seconds: int = Field(default=60, alias="SCAN_INTERVAL_SECONDS")
    scan_time_budget_sec: int = Field(default=25, alias="SCAN_TIME_BUDGET_SEC")
    scan_batch_size: int = Field(default=12, alias="SCAN_BATCH_SIZE")
    scan_refresh_sec: int = Field(default=120, alias="SCAN_REFRESH_SEC")
    scan_cache_ttl_sec: int = Field(default=1800, alias="SCAN_CACHE_TTL_SEC")
    # Comma-separated watchlist used on the free tier (can't scan whole market
    # on 60 calls/min). Empty means "use the earnings-calendar universe".
    watchlist: str = Field(default="", alias="WATCHLIST")
    max_universe_size: int = Field(default=40, alias="MAX_UNIVERSE_SIZE")
    min_market_cap_billions: float = Field(default=10.0, alias="MIN_MARKET_CAP_BILLIONS")

    # --- Market hours (US/Eastern) ---
    market_tz: str = "America/New_York"

    # --- CORS: comma-separated allowed origins for the frontend ---
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")

    @property
    def watchlist_symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.watchlist.split(",") if s.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
