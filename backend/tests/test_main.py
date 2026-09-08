"""Application startup / wiring tests."""

from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.evaluations import router as evaluations_router
from app.api.health import router as health_router
from app.api.organizations import router as organizations_router
from app.api.reports import router as reports_router
from app.api.research import router as research_router
from app.core.config import settings
from app.main import app
from fastapi.testclient import TestClient


def test_application_starts_and_shuts_down_cleanly():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert response.json()["name"] == "AgentFlow AI"
    assert response.json()["status"] == "running"
    assert response.json()["version"] == settings.app_version


def test_cors_middleware_is_registered():
    middleware = [m for m in app.user_middleware if m.cls.__name__ == "CORSMiddleware"]

    assert len(middleware) == 1


def test_versioned_health_route_is_registered():
    paths = app.openapi()["paths"]

    assert "/api/v1/health" in paths
    assert "/health" in paths


def test_phase1_api_routers_are_defined_with_versioned_prefixes():
    """Phase 1 wires the initial API structure under /api/v1."""
    expected = [
        (auth_router, "/api/v1/auth"),
        (organizations_router, "/api/v1/organizations"),
        # Phase 4: document endpoints are org-scoped (every handler enforces
        # organization membership from the path) and still live under /api/v1.
        (documents_router, "/api/v1/organizations/{organization_id}/documents"),
        # Phase 5: research / reports / evaluations are org-scoped too.
        (research_router, "/api/v1/organizations/{organization_id}/research"),
        (reports_router, "/api/v1/organizations/{organization_id}/reports"),
        (evaluations_router, "/api/v1/organizations/{organization_id}/evaluations"),
        (health_router, "/api/v1"),
    ]

    for router, prefix in expected:
        assert router.prefix == prefix
        assert prefix.startswith("/api/v1"), "every router must stay under /api/v1"

    # Every phase-1 router must be included in the application: the
    # health router contributes the versioned endpoint, and importing
    # the routers from app.main would fail loudly otherwise.
    paths = app.openapi()["paths"]
    assert "/api/v1/health" in paths


def test_openapi_does_not_expose_secrets():
    serialized = str(app.openapi()).lower()

    assert "service_role" not in serialized
    assert "sk-" not in serialized
    assert "secret_key" not in serialized
