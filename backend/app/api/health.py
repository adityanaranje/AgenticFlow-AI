from fastapi import APIRouter

from backend.app.api.schemas import (
    HealthResponse,
    ServiceHealth
)
from backend.app.services.health_service import (
    check_langfuse,
    check_openai,
    check_qdrant,
    check_supabase,
)

router = APIRouter(
    prefix="/health",
    tags=["Health"],
)

@router.get(
    "",
    response_model=HealthResponse
)
def health() -> HealthResponse:
    openai_ok, openai_detail = check_openai()
    supabase_ok, supabase_detail = check_supabase()
    qdrant_ok, qdrant_detail = check_qdrant()
    langfuse_ok, langfuse_detail = check_langfuse()

    all_ok = all(
        [
            openai_ok,
            supabase_ok,
            qdrant_ok,
            langfuse_ok,
        ]
    )

    return HealthResponse(
        status="healthy" if all_ok else "degraded",

        openai = ServiceHealth(
            status = "up" if openai_ok else "down",
            detail = openai_detail,
        ),

        supabase = ServiceHealth(
            status = "up" if supabase_ok else "down",
            detail=supabase_detail,
        ),      

        qdrant = ServiceHealth(
            status = "up" if qdrant_ok else "down",
            detail = qdrant_detail,
        ),

        langfuse = ServiceHealth(
            status = "up" if langfuse_ok else "down",
            detail = langfuse_detail,
        ),
    )