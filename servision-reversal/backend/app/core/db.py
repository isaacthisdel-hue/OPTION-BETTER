"""Database engine and session factory."""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings

_settings = get_settings()

# Railway provides DATABASE_URL as postgresql://...; SQLAlchemy 2.x + psycopg2
# wants postgresql+psycopg2://. Normalise it.
_url = _settings.database_url
if _url.startswith("postgresql://"):
    _url = _url.replace("postgresql://", "postgresql+psycopg2://", 1)

# Pool args apply to real DB servers (Postgres on Railway). SQLite ignores them
# and needs a different connect arg, so branch to stay robust in local dev.
if _url.startswith("sqlite"):
    engine = create_engine(_url, connect_args={"check_same_thread": False})
else:
    engine = create_engine(_url, pool_pre_ping=True, pool_size=5, max_overflow=10)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
