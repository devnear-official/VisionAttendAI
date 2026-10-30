"""VisionAttend-AI FastAPI Application Entry Point."""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import attendance, enrollment, health, recognition, students
from app.core.config import get_settings
from app.services.face_engine import face_engine
from app.utils.logger import logger

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: Startup and Shutdown events."""
    logger.info(f"Starting {settings.PROJECT_NAME} v{settings.PROJECT_VERSION} ({settings.ENVIRONMENT})")
    # Initialize face recognition engine
    model_loaded = face_engine.initialize()
    if model_loaded:
        logger.info("Face recognition model is operational.")
    else:
        logger.warning(
            "Face recognition model is NOT loaded. API will report 503 on inference requests until "
            "model weights are downloaded into models/ directory."
        )

    yield

    logger.info(f"Shutting down {settings.PROJECT_NAME}")


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description="Edge-to-Cloud Biometric Attendance Face Recognition Engine for VisionAttend-AI.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global Exception Handlers for clear error responses
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled server error on {request.method} {request.url.path}: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred on the server.",
            "path": request.url.path
        }
    )


# Include API Routers
app.include_router(health.router, prefix="/api/v1")
app.include_router(enrollment.router, prefix="/api/v1")
app.include_router(recognition.router, prefix="/api/v1")
app.include_router(students.router, prefix="/api/v1")
app.include_router(attendance.router, prefix="/api/v1")


@app.get("/", include_in_schema=False)
async def root():
    return {
        "project": settings.PROJECT_NAME,
        "version": settings.PROJECT_VERSION,
        "status": "online",
        "docs": "/docs",
        "health": "/api/v1/health"
    }
