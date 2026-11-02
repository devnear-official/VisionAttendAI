"""Health check schema."""

from typing import Dict, Any
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str = Field(..., examples=["healthy"])
    project: str = Field(..., examples=["VisionAttend-AI Backend"])
    version: str = Field(..., examples=["0.5.2"])
    environment: str = Field(..., examples=["development"])
    model_loaded: bool = Field(..., description="Whether the face recognition model is initialized in memory")
    model_details: Dict[str, Any] = Field(..., description="Model configuration and availability details")
    database: Dict[str, Any] = Field(..., description="PostgreSQL and pgvector connection health details")
    similarity_thresholds: Dict[str, Any] = Field(default_factory=dict, description="Active cosine similarity decision thresholds")
