"""Health check and system diagnostics route."""

from fastapi import APIRouter
from app.core.config import get_settings
from app.database.session import check_database_health
from app.schemas.health import HealthResponse
from app.services.face_engine import face_engine

router = APIRouter(prefix="/health", tags=["Health"])
settings = get_settings()


@router.get(
    "",
    response_model=HealthResponse,
    summary="Health check & engine status",
    description="Reports API health, uptime, environment, face recognition engine, and PostgreSQL/pgvector status."
)
async def check_health() -> HealthResponse:
    db_health = check_database_health()
    return HealthResponse(
        status="healthy" if db_health.get("connected") else "degraded",
        project=settings.PROJECT_NAME,
        version=settings.PROJECT_VERSION,
        environment=settings.ENVIRONMENT,
        model_loaded=face_engine.is_loaded,
        model_details=face_engine.get_status_details(),
        database=db_health,
        similarity_thresholds={
            "match_threshold": settings.SIMILARITY_MATCH_THRESHOLD,
            "ambiguous_threshold": settings.SIMILARITY_AMBIGUOUS_THRESHOLD,
            "min_face_width": settings.MIN_FACE_WIDTH,
            "min_face_height": settings.MIN_FACE_HEIGHT,
            "min_laplacian_variance": settings.MIN_LAPLACIAN_VARIANCE,
        },
    )
