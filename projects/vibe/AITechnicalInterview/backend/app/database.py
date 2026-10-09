from collections.abc import AsyncGenerator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def _engine_connect_args(database_url: str) -> dict:
    if database_url.startswith("sqlite"):
        return {"timeout": 60}
    return {}


def _engine_kwargs(database_url: str) -> dict:
    kwargs: dict = {
        "echo": False,
        "connect_args": _engine_connect_args(database_url),
    }
    # SQLite + asyncio: отдельное соединение на запрос — меньше «database is locked».
    if database_url.startswith("sqlite"):
        kwargs["poolclass"] = NullPool
    return kwargs


settings = get_settings()
engine = create_async_engine(settings.database_url, **_engine_kwargs(settings.database_url))

if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=60000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
