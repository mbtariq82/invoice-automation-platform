import os
import asyncio
import sys
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from invoice_automation_platform.db.models import Base

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@pytest.fixture(autouse=True)
def local_secret_configuration(monkeypatch):
    # Tests must not use cloud secret references from a developer's environment.
    monkeypatch.delenv("DATABASE_URL_SECRET_VERSION", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY_SECRET_VERSION", raising=False)


@pytest.fixture(scope="session")
def test_engine():
    engine = create_engine(os.environ["TEST_DATABASE_URL"], future=True)
    Base.metadata.create_all(engine)
    try:
        yield engine
    finally:
        Base.metadata.drop_all(engine)
        engine.dispose()


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def db_session(test_engine, anyio_backend):
    engine = create_async_engine(os.environ["TEST_DATABASE_URL"])
    async with engine.connect() as connection:
        transaction = await connection.begin()
        factory = async_sessionmaker(bind=connection, expire_on_commit=False)
        async with factory() as session:
            yield session
        await transaction.rollback()
    await engine.dispose()
