"""CORS allowlist tests — the 400 "Disallowed CORS origin" regression.

A document upload is a ``multipart/form-data`` POST with an ``Authorization``
header, so the browser first sends an ``OPTIONS`` preflight. Starlette answers
a preflight from an origin that is not allowlisted with ``400 Bad Request``
("Disallowed CORS origin") and the upload never leaves the browser. These
tests pin the allowlist behaviour that prevents that.
"""

import re

import pytest
from app.core.cors import CorsConfigError, build_cors_config, normalize_origin
from app.main import app
from fastapi.testclient import TestClient

UPLOAD_PATH = "/api/v1/organizations/9c81f51d-df67-4022-849e-de7a750b30f0/documents/upload"


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _preflight(client: TestClient, origin: str, path: str = UPLOAD_PATH):
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    )


# --------------------------------------------------------------------------
# Origin normalisation
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("http://localhost:3000", "http://localhost:3000"),
        # A trailing slash (the classic FRONTEND_URL typo) and mixed case.
        ("http://localhost:3000/", "http://localhost:3000"),
        ("HTTPS://App.Example.com", "https://app.example.com"),
        ('"https://app.example.com"', "https://app.example.com"),
        ("https://app.example.com:8443", "https://app.example.com:8443"),
        ("http://[::1]:3000", "http://[::1]:3000"),
        ("https://app.example.com", "https://app.example.com"),  # default port dropped
    ],
)
def test_normalize_origin_matches_what_a_browser_sends(raw, expected):
    assert normalize_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "app.example.com",  # no scheme -> can never match an Origin header
        "https://app.example.com/dashboard",  # path
        "https://app.example.com?x=1",  # query
        "ftp://app.example.com",  # scheme a browser never sends
        "https://",  # no host
    ],
)
def test_unusable_origins_raise_so_they_fail_loudly(raw):
    with pytest.raises(CorsConfigError):
        normalize_origin(raw)


# --------------------------------------------------------------------------
# Allowlist construction
# --------------------------------------------------------------------------


def test_default_configuration_allows_the_local_dev_server():
    config = build_cors_config("http://localhost:3000", environment="development")

    # 127.0.0.1 and [::1] address the same dev server, so a developer who
    # opened the app by IP gets the same allowlist as one who used localhost.
    assert set(config.allow_origins) == {
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://[::1]:3000",
    }


def test_development_matches_a_dev_server_on_any_loopback_port():
    """Next.js moves to :3001 when :3000 is taken — same dev server."""
    config = build_cors_config("http://localhost:3000", environment="development")

    assert config.allow_origin_regex is not None
    for origin in (
        "http://localhost:3001",
        "http://127.0.0.1:4173",
        "http://[::1]:5173",
    ):
        assert re.fullmatch(config.allow_origin_regex, origin), origin
    # ...while a look-alike host is still rejected.
    assert not re.fullmatch(config.allow_origin_regex, "http://localhost.evil.com")


def test_production_does_not_match_stray_loopback_ports():
    config = build_cors_config("https://app.example.com", environment="production")

    assert config.allow_origin_regex is None


def test_loopback_aliases_are_not_added_in_production():
    config = build_cors_config("https://app.example.com", environment="production")

    assert config.allow_origins == ["https://app.example.com"]
    assert config.allow_private_network is False


def test_multiple_origins_can_be_configured():
    """Vercel prod + preview + a local dev server, comma-separated."""
    config = build_cors_config(
        "https://app.example.com/, http://localhost:3000",
        environment="production",
    )

    assert config.allow_origins == ["https://app.example.com", "http://localhost:3000"]


def test_wildcard_host_becomes_a_contained_regex():
    config = build_cors_config("https://*.vercel.app", environment="production")

    assert config.allow_origins == []
    assert config.allow_origin_regex is not None
    assert config.allow_origin_regex == r"^(?:https://[A-Za-z0-9.-]+\.vercel\.app)$"


def test_a_bare_wildcard_is_never_honoured(caplog):
    """`*` with credentials is forbidden, so it fails closed and is logged."""
    config = build_cors_config("*", environment="production")

    assert config.allow_origins == []
    assert config.allow_origin_regex is None
    assert "Ignoring invalid FRONTEND_URL entry" in caplog.text


def test_a_wildcard_scheme_host_is_never_honoured():
    config = build_cors_config("https://*,https://app.example.com", environment="production")

    assert config.allow_origins == ["https://app.example.com"]
    assert config.allow_origin_regex is None


def test_unusable_entries_are_dropped_and_valid_ones_kept(caplog):
    config = build_cors_config(
        "https://app.example.com,https://app.example.com/admin",
        environment="production",
    )

    assert config.allow_origins == ["https://app.example.com"]
    assert "Ignoring invalid FRONTEND_URL entry" in caplog.text


def test_empty_configuration_falls_back_to_the_documented_default():
    config = build_cors_config("", environment="production")

    assert "http://localhost:3000" in config.allow_origins


def test_origin_regex_is_combined_with_explicit_origins():
    config = build_cors_config(
        "https://app.example.com",
        origin_regex=r"^https://.*\.preview\.example\.com$",
        environment="production",
    )

    assert config.allow_origins == ["https://app.example.com"]
    assert config.allow_origin_regex == r"^(?:https://.*\.preview\.example\.com)$"


def test_an_invalid_origin_regex_is_ignored_instead_of_breaking_startup(caplog):
    config = build_cors_config(
        "https://app.example.com", origin_regex="(", environment="production"
    )

    assert config.allow_origins == ["https://app.example.com"]
    assert config.allow_origin_regex is None
    assert "Ignoring invalid FRONTEND_ORIGIN_REGEX" in caplog.text


# --------------------------------------------------------------------------
# Live preflight behaviour (the reported 400)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "origin",
    ["http://localhost:3000", "http://127.0.0.1:3000", "http://[::1]:3000"],
)
def test_upload_preflight_succeeds_for_the_local_dev_server(client, origin):
    response = _preflight(client, origin)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert "authorization" in response.headers["access-control-allow-headers"].lower()
    assert "POST" in response.headers["access-control-allow-methods"]


def test_upload_preflight_succeeds_for_a_dev_server_on_another_port(client):
    """The reported 400 hit the upload path; a busy :3000 must not block it."""
    response = _preflight(client, "http://localhost:3001")

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3001"


def test_upload_preflight_still_rejects_unknown_origins(client):
    response = _preflight(client, "https://evil.example.com")

    assert response.status_code == 400
    assert "Disallowed CORS origin" in response.text


def test_upload_response_carries_cors_headers_for_the_browser(client):
    """A real (unauthenticated) upload POST must not be blocked by CORS."""
    response = client.post(
        UPLOAD_PATH,
        headers={"Origin": "http://localhost:3000"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )

    # 401/403/400 are all fine here — the point is the CORS header is present
    # so the browser hands the response to the app instead of hiding it.
    assert response.headers.get("access-control-allow-origin") == "http://localhost:3000"
