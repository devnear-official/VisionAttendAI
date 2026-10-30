"""Health check route."""

from fastapi import APIRouter
from app.core.config import get_settings
from app.schemas.health import HealthResponse
from app.services.face_engine import face_engine

router = APIRouter(prefix="/health", tags=["Health"])
settings = get_settings()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check & engine status",
    description="Reports API health, uptime, environment, and face recognition model initialization status."
)
async def check_health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        project=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        model_loaded=face_engine.is_loaded,
        model_details=face_engine.get_status_details(),
        database_status="not_connected (scheduled for Stage 5.2)"
    )
