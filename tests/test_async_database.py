import importlib
from unittest.mock import AsyncMock, Mock

import anyio
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from invoice_automation_platform.db import session as database


@pytest.mark.anyio
async def test_production_dependency_uses_async_sessions_and_releases_pool(
    test_engine, monkeypatch
):
    # Use the dedicated test DB, never the application's database.
    monkeypatch.setattr(
        database, "database_url",
        lambda: test_engine.url.render_as_string(hide_password=False),
    )
    await database.close_database()
    try:
        await database.initialize_database()
        assert database.get_engine().pool.checkedout() == 0
        dependency = database.get_db()
        session = await anext(dependency)
        assert isinstance(database.get_engine(), AsyncEngine)
        assert isinstance(session, AsyncSession)
        assert await session.scalar(text("SELECT 1")) == 1
        assert database.get_engine().pool.checkedout() == 1
        await dependency.aclose()
        assert database.get_engine().pool.checkedout() == 0
    finally:
        await database.close_database()
    assert database.get_engine.cache_info().currsize == 0
    assert database.get_session_factory.cache_info().currsize == 0


@pytest.mark.anyio
async def test_startup_query_has_a_bounded_timeout(monkeypatch):
    async def stalled_query(*args):
        await anyio.sleep_forever()

    session = AsyncMock()
    session.execute.side_effect = stalled_query
    context = AsyncMock()
    context.__aenter__.return_value = session
    monkeypatch.setattr(database, "_initialize_session_factory", lambda: Mock(return_value=context))
    monkeypatch.setattr(database, "DATABASE_STARTUP_TIMEOUT", 0.01)
    with pytest.raises(TimeoutError):
        await database.initialize_database()
    context.__aexit__.assert_awaited_once()


@pytest.mark.anyio
async def test_failed_database_startup_blocks_serving_and_cleans_up(monkeypatch):
    api = importlib.import_module("invoice_automation_platform.api.app")
    monkeypatch.setattr(api, "initialize_database", AsyncMock(side_effect=RuntimeError("Unavailable")))
    cleanup = AsyncMock()
    monkeypatch.setattr(api, "close_database", cleanup)
    with pytest.raises(RuntimeError, match="Unavailable"):
        async with api.lifespan(api.create_app()):
            pytest.fail("Startup must fail before accepting requests")
    cleanup.assert_awaited_once()


@pytest.mark.anyio
async def test_waiting_get_query_allows_another_request(monkeypatch):
    api = importlib.import_module("invoice_automation_platform.api.app")
    from invoice_automation_platform.api.auth import Principal

    started = anyio.Event()
    release = anyio.Event()

    async def waiting_query(*args, **kwargs):
        started.set()
        await release.wait()
        return []

    monkeypatch.setattr(api.repository, "list_invoices", waiting_query)
    app = api.create_app()
    app.dependency_overrides[api.get_db] = lambda: object()
    app.dependency_overrides[api.current_principal] = lambda: Principal("alice")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        async def query():
            response = await client.get("/v1/invoices")
            assert response.status_code == 200
            assert response.json() == []

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(query)
            try:
                with anyio.fail_after(5):
                    await started.wait()
                    assert (await client.get("/health")).status_code == 200
            finally:
                release.set()

