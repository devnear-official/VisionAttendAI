"""Pydantic schemas for edge device management."""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class DeviceBase(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=64, description="Device name")
    device_code: str = Field(..., min_length=1, max_length=64, description="Unique device code (e.g. ESP32-GATE-01)")
    location: Optional[str] = Field(default=None, max_length=128, description="Physical location")


class DeviceCreate(DeviceBase):
    api_key: str = Field(..., min_length=16, description="Plaintext device API key to be hashed upon registration")


class DeviceResponse(DeviceBase):
    id: uuid.UUID
    is_active: bool
    last_seen_at: Optional[datetime] = None
    created_at: datetime
    # Note: api_key_hash is strictly excluded from public responses

    class Config:
        from_attributes = True


class DeviceListResponse(BaseModel):
    total: int
    devices: List[DeviceResponse]
