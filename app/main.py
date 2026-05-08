from fastapi import FastAPI

from app.api.router import api_router
from app.core.config import get_settings

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Production-ready FastAPI backend for AI-powered stock analysis.",
)

app.include_router(api_router, prefix=settings.api_v1_prefix)
