from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.health import router as health_router
from backend.app.core.config import settings

app = FastAPI(
    title = settings.app_name,
    description=(
        "Enterprise Multi-Agent Research"
        "and Knowledge Intelligence Platform"
    ),
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.frontend_url,
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)


@app.get('/')
def root():
    return {
        "name" : settings.app_name,
        "environment": settings.environment,
        "docs":"/docs",
        "health":"/health",
    }