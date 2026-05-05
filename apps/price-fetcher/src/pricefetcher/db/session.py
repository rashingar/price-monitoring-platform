"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from pricefetcher.db.config import DatabaseNotConfiguredError, get_database_url, is_database_configured


@lru_cache(maxsize=4)
def _engine_for_url(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True, future=True)


def get_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or get_database_url()
    if resolved_url is None:
        raise DatabaseNotConfiguredError("PRICEFETCHER_DATABASE_URL is not configured.")
    return _engine_for_url(resolved_url)


def create_session_factory(database_url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(database_url), autoflush=False, expire_on_commit=False, future=True)


@contextmanager
def session_scope(database_url: str | None = None) -> Iterator[Session]:
    session_factory = create_session_factory(database_url)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def check_database_reachable(database_url: str | None = None) -> dict[str, object]:
    if database_url is None and not is_database_configured():
        return {"configured": False, "reachable": False, "dialect": None, "error": None}
    engine = get_engine(database_url)
    with engine.connect() as connection:
        connection.execute(text("select 1"))
    return {"configured": True, "reachable": True, "dialect": engine.dialect.name, "error": None}
