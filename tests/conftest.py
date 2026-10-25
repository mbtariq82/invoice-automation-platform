import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from invoice_automation_platform.db.models import Base

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


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
def db_session(test_engine):
    connection = test_engine.connect()
    transaction = connection.begin()
    session_factory = sessionmaker(
        bind=connection, future=True, expire_on_commit=False
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
