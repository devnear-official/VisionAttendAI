"""Health check schema."""

from typing import Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["healthy"])
    project: str = Field(..., examples=["VisionAttend-AI Backend"])
    version: str = Field(..., examples=["0.5.1"])
    environment: str = Field(..., examples=["development"])
    model_loaded: bool = Field(..., description="Whether the face recognition model is initialized in memory")
    model_details: Dict[str, Any] = Field(..., description="Model configuration and availability details")
    database_status: str = Field("not_connected", description="Database connection status (Stage 5.2)")
