"""Operational API behavior that must remain dependency-free."""

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_health_endpoint_is_public_and_does_not_need_external_services() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": settings.APP_NAME}


def test_cors_preflight_allows_configured_local_frontend_origin() -> None:
    with TestClient(app) as client:
        response = client.options(
            "/api/chat",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert "POST" in response.headers["access-control-allow-methods"]
