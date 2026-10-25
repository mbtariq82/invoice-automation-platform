from collections.abc import AsyncGenerator
import asyncio
from functools import lru_cache
from threading import Lock
from sqlalchemy import text

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from ..config.secrets import get_secret

_initialization_lock = Lock()
DATABASE_STARTUP_TIMEOUT = 15


def database_url() -> str:
    return get_secret("DATABASE_URL")


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    # psycopg supports both sync (Alembic) and async (API) with the same URL.
    return create_async_engine(
        database_url(), pool_pre_ping=True, connect_args={"connect_timeout": 10}
    )


@lru_cache(maxsize=1)
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=get_engine(), autoflush=False, expire_on_commit=False
    )


def _initialize_session_factory() -> async_sessionmaker[AsyncSession]:
    # lru_cache permits concurrent initial calls; avoid creating unused pools.
    with _initialization_lock:
        return get_session_factory()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    # Secret Manager is synchronous and may be accessed on first initialization.
    factory = await asyncio.to_thread(_initialize_session_factory)
    async with factory() as session:
        yield session


async def initialize_database() -> None:
    # Secret reads have their own 10-second timeout. Bound the connection/query
    # separately so a cancelled background initialization cannot leak a pool.
    factory = await asyncio.to_thread(_initialize_session_factory)
    async with asyncio.timeout(DATABASE_STARTUP_TIMEOUT):
        async with factory() as session:
            await session.execute(text("SELECT 1"))


async def close_database() -> None:
    if get_engine.cache_info().currsize:
        await get_engine().dispose()
    get_session_factory.cache_clear()
    get_engine.cache_clear()
