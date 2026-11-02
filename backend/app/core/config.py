"""Application configuration loaded from environment variables and .env file."""

from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Project Info
    PROJECT_NAME: str = "VisionAttend-AI Backend"
    PROJECT_VERSION: str = "0.5.2"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True

    # Server Bind
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]

    # Security
    ADMIN_API_KEY: str = Field(
        default="dev_admin_secret_key_change_in_production",
        description="Bearer token required for admin and enrollment endpoints"
    )
    DEVICE_API_KEY: str = Field(
        default="esp32_device_secret_key_change_in_production",
        description="Header token required for edge ESP32 device recognition endpoints"
    )

    # Face Recognition Engine & ONNX Runtime
    MODEL_DIR: str = "models"
    FACE_RECOGNITION_MODEL_NAME: str = "w600k_r50.onnx"
    ONNX_EXECUTION_PROVIDER: str = "CPUExecutionProvider"
    ONNX_INTRA_OP_NUM_THREADS: int = 4

    @property
    def model_path(self) -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent
        return base_dir / self.MODEL_DIR / self.FACE_RECOGNITION_MODEL_NAME

    # Similarity & Verification Thresholds
    SIMILARITY_MATCH_THRESHOLD: float = Field(
        default=0.65,
        ge=0.0,
        le=1.0,
        description="Cosine similarity threshold for MATCH classification"
    )
    SIMILARITY_AMBIGUOUS_THRESHOLD: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Cosine similarity threshold below which faces are UNKNOWN and above which are AMBIGUOUS"
    )

    @field_validator("SIMILARITY_AMBIGUOUS_THRESHOLD")
    @classmethod
    def validate_thresholds(cls, v: float, info) -> float:
        match_thr = info.data.get("SIMILARITY_MATCH_THRESHOLD", 0.65)
        if v >= match_thr:
            raise ValueError("SIMILARITY_AMBIGUOUS_THRESHOLD must be strictly less than SIMILARITY_MATCH_THRESHOLD")
        return v

    # Image Quality Thresholds
    MIN_FACE_WIDTH: int = 36
    MIN_FACE_HEIGHT: int = 36
    MIN_LAPLACIAN_VARIANCE: float = 25.0  # Blur detection threshold
    MIN_BRIGHTNESS: float = 20.0         # Underexposure threshold (0-255 scale)
    MAX_BRIGHTNESS: float = 240.0        # Overexposure threshold (0-255 scale)

    # Database (PostgreSQL 17 + pgvector)
    DATABASE_URL: str = "postgresql+psycopg://postgres:postgres@localhost:5432/visionattend"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 5
    DATABASE_POOL_TIMEOUT: int = 30
    DATABASE_POOL_PRE_PING: bool = True

    _backend_dir = Path(__file__).resolve().parent.parent.parent
    _env_file_path = _backend_dir / ".env"

    model_config = SettingsConfigDict(
        env_file=_env_file_path if _env_file_path.exists() else ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings singleton."""
    return Settings()
