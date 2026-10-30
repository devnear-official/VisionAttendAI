"""Common schemas and response models."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Error type or code")
    detail: str = Field(..., description="Human-readable explanation of the error")
    context: Optional[Dict[str, Any]] = Field(default=None, description="Optional diagnostic details")


class SuccessResponse(BaseModel):
    status: str = Field("success", description="Status code")
    message: str = Field(..., description="Human-readable success message")
    data: Optional[Dict[str, Any]] = None
