"""Pydantic schemas for edge device management and credential rotation."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, Field, computed_field

# Timeout in seconds to consider an edge camera online (2 minutes)
DEVICE_ONLINE_TIMEOUT_SECONDS = 120


class DeviceBase(BaseModel):
    device_name: str = Field(..., min_length=1, max_length=64, description="Device name")
    device_code: str = Field(..., min_length=1, max_length=64, description="Unique device code (e.g. esp32-cam-01)")
    location: Optional[str] = Field(default=None, max_length=128, description="Physical location")


class DeviceCreate(DeviceBase):
    api_key: Optional[str] = Field(
        default=None,
        min_length=16,
        description="Optional plaintext device API key. If omitted, a cryptographically secure 32-byte key is auto-generated."
    )


class DeviceUpdate(BaseModel):
    device_name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    location: Optional[str] = Field(default=None, max_length=128)
    is_active: Optional[bool] = None


class DeviceResponse(DeviceBase):
    id: uuid.UUID
    is_active: bool
    last_seen_at: Optional[datetime] = None
    created_at: datetime

    @computed_field
    def is_online(self) -> bool:
        """Computes online state dynamically based on documented 120-second timeout."""
        if not self.is_active or not self.last_seen_at:
            return False
        now = datetime.now(timezone.utc)
        last_seen = self.last_seen_at
        if last_seen.tzinfo is None:
            last_seen = last_seen.replace(tzinfo=timezone.utc)
        delta = (now - last_seen).total_seconds()
        return delta <= DEVICE_ONLINE_TIMEOUT_SECONDS

    model_config = ConfigDict(from_attributes=True)


class DeviceRegistrationResponse(BaseModel):
    device: DeviceResponse
    plaintext_api_key: str = Field(
        ...,
        description="Plaintext device API key shown ONLY ONCE upon creation. Must be flashed to the ESP32 node."
    )
    message: str


class DeviceKeyRotationResponse(BaseModel):
    device_id: uuid.UUID
    device_code: str
    plaintext_api_key: str = Field(
        ...,
        description="New plaintext device API key shown ONLY ONCE upon rotation. Flash this new key to the ESP32 node."
    )
    message: str


class DeviceListResponse(BaseModel):
    total: int
    devices: List[DeviceResponse]
