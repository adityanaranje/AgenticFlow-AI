"""Health endpoint tests.

These run against a clean environment in which no external services
are configured, so the API must report ``degraded`` (not crash).
Connectivity-check tests monkeypatch the individual checks.
"""

from app.main import app
from fastapi.testclient import TestClient


def test_health_endpoint_degraded_without_configuration():
    """Unconfigured services must degrade gracefully, never 500."""
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200

    body = response.json()

    assert body["status"] == "degraded"
    for service in ("openai", "supabase", "qdrant", "redis", "langfuse"):
        assert service in body
        assert body[service]["status"] == "down"
        assert body[service]["detail"] == "Not configured"


def test_versioned_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_health_returns_healthy_when_all_services_up(monkeypatch):
    from app.services import health_service

    up = {"status": "up", "detail": "Connected"}

    monkeypatch.setattr(health_service, "check_openai", lambda: up)
    monkeypatch.setattr(health_service, "check_supabase", lambda: up)
    monkeypatch.setattr(health_service, "check_qdrant", lambda: up)
    monkeypatch.setattr(health_service, "check_redis", lambda: up)
    monkeypatch.setattr(health_service, "check_langfuse", lambda: up)

    with TestClient(app) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
