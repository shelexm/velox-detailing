import httpx
import pytest
from fastapi import FastAPI

from app.core.config import Settings
from app.main import create_app
from app.models import Studio


async def test_live(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert len(response.headers["x-request-id"]) >= 8


async def test_ready_checks_database_and_migrations(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "checks": {"database": "ok", "migrations": "ok"}}


async def test_ready_reports_unavailable_database(settings: Settings) -> None:
    broken = settings.model_copy(update={"postgres_port": 1})
    app = create_app(broken)
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
            response = await http.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["checks"]["database"] == "unavailable"


async def test_request_id_is_propagated_when_well_formed(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live", headers={"X-Request-ID": "abc12345-from-proxy"})
    assert response.headers["x-request-id"] == "abc12345-from-proxy"
    response = await client.get("/health/live", headers={"X-Request-ID": "bad id\nwith newline"})
    assert response.headers["x-request-id"] != "bad id\nwith newline"


async def test_unknown_route_uses_error_format(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["code"] == "not_found"
    assert body["request_id"]


async def test_unknown_host_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.get("/health/live", headers={"Host": "evil.example.com"})
    assert response.status_code == 400


@pytest.fixture
def app_with_failing_route(settings: Settings) -> FastAPI:
    app = create_app(settings)

    @app.get("/api/boom")
    async def boom() -> None:
        raise RuntimeError("database password=hunter2 leaked in exception text")

    return app


async def test_unexpected_errors_do_not_leak_details(app_with_failing_route: FastAPI) -> None:
    transport = httpx.ASGITransport(app=app_with_failing_route, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as http:
        response = await http.get("/api/boom")
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert "Traceback" not in response.text


async def test_probes_answer_head_requests(client: httpx.AsyncClient, studio: Studio) -> None:
    # Uptime monitors send HEAD by default; a 405 would show a healthy site as down.
    for path in ("/health/live", "/health/ready", "/"):
        response = await client.head(path)
        assert response.status_code == 200, path
