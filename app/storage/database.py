from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.base import Base
import app.models.approval  # noqa: F401
import app.models.gift  # noqa: F401
import app.models.job  # noqa: F401
import app.models.market  # noqa: F401

_engine = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


async def init_db(db_url: str) -> None:
    global _engine, _session_factory
    _engine = create_async_engine(db_url, echo=False)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if db_url.startswith("sqlite"):
            await _ensure_sqlite_schema(conn)


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    if _session_factory is None:
        raise RuntimeError("Database not initialised. Call init_db() first.")
    return _session_factory


async def _ensure_sqlite_schema(conn) -> None:
    """Small additive migration layer for existing MVP SQLite databases."""
    await _add_sqlite_column_if_missing(conn, "jobs", "destination_peer", "VARCHAR(128)")
    await _add_sqlite_column_if_missing(
        conn,
        "gifts",
        "owner_peer",
        "VARCHAR(128) NOT NULL DEFAULT 'self'",
    )
    await _add_sqlite_column_if_missing(conn, "gifts", "transferred_to", "VARCHAR(128)")
    await _add_sqlite_column_if_missing(conn, "gifts", "transferred_at", "DATETIME")


async def _add_sqlite_column_if_missing(conn, table: str, column: str, definition: str) -> None:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    columns = {row[1] for row in result.fetchall()}
    if column not in columns:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {definition}"))
