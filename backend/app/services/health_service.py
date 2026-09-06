"""External-service health checks.

Every check is defensive: an unconfigured or unreachable service is
reported as ``down``/``degraded`` and never crashes the API. The
overall endpoint returns ``healthy`` only when every service
reports ``up``.
"""

from typing import Any

import httpx
from app.cache.redis_client import get_redis_client
from app.core.config import settings
from app.core.langfuse import get_langfuse
from app.core.logging import get_logger
from app.db.supabase import get_supabase
from app.llm.client import get_openai_client
from app.rag.qdrant import get_qdrant_client

logger = get_logger(__name__)


def _service_status(status: str, detail: str) -> dict[str, str]:
    return {
        "status": status,
        "detail": detail,
    }


def check_openai() -> dict[str, str]:
    client = get_openai_client()

    if client is None:
        return _service_status("down", "Not configured")

    try:
        client.models.list()

        return _service_status("up", "Connected")
    except Exception as exc:
        logger.exception("OpenAI health check failed.")
        return _service_status("down", str(exc))


def check_supabase() -> dict[str, str]:
    client = get_supabase()

    if client is None:
        return _service_status("down", "Not configured")

    try:
        # Probe the Supabase REST (PostgREST) endpoint. Any HTTP
        # response proves reachability; auth-specific status codes are
        # expected here and still mean the service is up.
        with httpx.Client(timeout=10) as http:
            response = http.get(f"{settings.supabase_url.rstrip('/')}/rest/v1/")

        if response.status_code >= 500:
            return _service_status("down", f"HTTP {response.status_code}")

        return _service_status("up", "Connected")
    except Exception as exc:
        logger.exception("Supabase health check failed.")
        return _service_status("down", str(exc))


def check_qdrant() -> dict[str, str]:
    client = get_qdrant_client()

    if client is None:
        return _service_status("down", "Not configured")

    try:
        client.get_collections()

        return _service_status("up", "Connected")
    except Exception as exc:
        logger.exception("Qdrant health check failed.")
        return _service_status("down", str(exc))


def check_redis() -> dict[str, str]:
    client = get_redis_client()

    if client is None:
        return _service_status("down", "Not configured")

    try:
        if not client.ping():
            return _service_status("down", "Ping failed")

        return _service_status("up", "Connected")
    except Exception as exc:
        logger.exception("Redis health check failed.")
        return _service_status("down", str(exc))


def check_langfuse() -> dict[str, str]:
    client = get_langfuse()

    if client is None:
        return _service_status("down", "Not configured")

    try:
        client.auth_check()

        return _service_status("up", "Connected")
    except Exception as exc:
        logger.exception("Langfuse health check failed.")
        return _service_status("down", str(exc))


def get_system_health() -> dict[str, Any]:
    services = {
        "openai": check_openai(),
        "supabase": check_supabase(),
        "qdrant": check_qdrant(),
        "redis": check_redis(),
        "langfuse": check_langfuse(),
    }

    healthy = all(
        service["status"] == "up"
        for service in services.values()
    )

    return {
        "status": "healthy" if healthy else "degraded",
        **services,
    }
