"""Async SQLAlchemy engine, session factory and declarative base.

The application runs against **PostgreSQL + PostGIS** in production.  For local
unit-testing without a database daemon the engine can fall back to SQLite via
``DATABASE_URL=sqlite+aiosqlite:///...`` - the spatial query layer
(:mod:`app.core.geo`) transparently switches strategies based on dialect.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _on_connect_statement_timeout(dbapi_conn, connection_record) -> None:  # type: ignore[no-untyped-def]
    """Apply a per-connection statement timeout on PostgreSQL only."""
    try:
        cursor = dbapi_conn.cursor()
        cursor.execute(f"SET statement_timeout = {settings.db_statement_timeout_ms}")
        cursor.execute("SET timezone = 'UTC'")
        cursor.close()
        dbapi_conn.commit()
    except Exception:  # pragma: no cover - non-postgres / permissions
        pass


def _build_engine(url: str) -> AsyncEngine:
    engine = create_async_engine(
        url,
        echo=settings.sqlalchemy_echo,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_timeout=settings.db_pool_timeout,
        pool_recycle=settings.db_pool_recycle,
    )
    if url.startswith("postgresql"):
        event.listen(Engine, "connect", _on_connect_statement_timeout)
    return engine


engine: AsyncEngine = _build_engine(settings.async_database_url)
async_session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: yield a session and guarantee cleanup."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def close_db_engine() -> None:
    """Dispose the async engine (used in app shutdown / tests)."""
    await engine.dispose()


@contextlib.asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Context-manager wrapper used by background jobs and scripts."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def init_sync_schema() -> None:
    """IDEMPOTENT sync schema bootstrap used by scripts and seed.

    - enables the PostGIS extension (PostgreSQL only)
    - creates all tables
    """
    from sqlalchemy import create_engine

    import app.models  # noqa: F401  ensure model modules are imported

    sync = create_engine(settings.sync_database_url)
    try:
        if sync.url.get_backend_name() == "postgresql":
            with sync.begin() as conn:
                conn.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS postgis")
        Base.metadata.create_all(sync)
    finally:
        sync.dispose()


def is_postgres(dialect_or_session: object) -> bool:
    """True when the target database is PostgreSQL."""
    from sqlalchemy.engine import Dialect

    if isinstance(dialect_or_session, Dialect):
        return dialect_or_session.name.startswith("postgresql")
    return str(getattr(getattr(dialect_or_session, "bind", dialect_or_session), "dialect", None)).find(
        "postgresql"
    ) >= 0 or str(
        getattr(getattr(dialect_or_session, "engine", dialect_or_session), "url", dialect_or_session)
    ).startswith("postgresql")


def geo_backend_active() -> str:
    """Effective geo backend for the configured DSN."""
    if settings.geo_backend.value != "auto":
        return settings.geo_backend.value
    return "postgis" if settings.async_database_url.startswith("postgresql") else "sqlite"


__all__ = [
    "Base",
    "async_session_factory",
    "close_db_engine",
    "engine",
    "geo_backend_active",
    "get_db",
    "init_sync_schema",
    "is_postgres",
    "session_scope",
]
