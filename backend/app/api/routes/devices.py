"""Edge camera devices and telemetry route handlers."""

import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.security import verify_admin_key, verify_admin_or_device_key, verify_device_key
from app.database.session import get_db
from app.schemas.common import ErrorResponse, SuccessResponse
from app.schemas.device import (
    DeviceCreate,
    DeviceKeyRotationResponse,
    DeviceListResponse,
    DeviceRegistrationResponse,
    DeviceResponse,
    DeviceUpdate,
)
from app.services.device_service import DeviceService

router = APIRouter(prefix="/devices", tags=["Edge Devices"])


@router.get(
    "",
    response_model=DeviceListResponse,
    summary="List edge camera devices",
    description="Returns all registered ESP32 edge camera nodes with computed online/offline statuses. Requires Admin Token.",
)
async def list_devices(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    devices, total = DeviceService.list_devices(db, skip=skip, limit=limit)
    return DeviceListResponse(
        total=total,
        devices=[DeviceResponse.model_validate(d) for d in devices],
    )


@router.post(
    "",
    response_model=DeviceRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Provision new edge camera device",
    description="Registers an edge ESP32 node and generates its cryptographic API key. The plaintext key is shown ONLY ONCE.",
    responses={
        400: {"model": ErrorResponse, "description": "Device code already registered"},
    },
)
async def create_device(
    device_in: DeviceCreate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    existing = DeviceService.get_by_code(db, device_in.device_code)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Device code '{device_in.device_code}' is already registered.",
        )

    device, plain_key = DeviceService.register_device(db, device_in)
    db.commit()

    return DeviceRegistrationResponse(
        device=DeviceResponse.model_validate(device),
        plaintext_api_key=plain_key,
        message="Device provisioned successfully. Flash this plaintext API key to the ESP32 node. It will not be shown again.",
    )


@router.patch(
    "/{device_id}",
    response_model=DeviceResponse,
    summary="Update device metadata",
    description="Modify device name, physical location, or active status.",
)
async def update_device(
    device_id: uuid.UUID,
    update_in: DeviceUpdate,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    device = DeviceService.update_device(db, device_id, update_in)
    if not device:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found.",
        )
    db.commit()
    return DeviceResponse.model_validate(device)


@router.post(
    "/{device_id}/rotate-key",
    response_model=DeviceKeyRotationResponse,
    summary="Rotate device credentials",
    description="Generates a new API key and updates the bcrypt hash in the database. Returns the new plaintext key ONCE.",
)
async def rotate_device_key(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    res = DeviceService.rotate_device_key(db, device_id)
    if not res:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found.",
        )
    device, new_key = res
    db.commit()

    return DeviceKeyRotationResponse(
        device_id=device.id,
        device_code=device.device_code,
        plaintext_api_key=new_key,
        message="Device credentials rotated. Update and reflash the new API key to the ESP32 node.",
    )


@router.delete(
    "/{device_id}",
    response_model=SuccessResponse,
    summary="Deactivate edge device",
    description="Deactivates an edge camera node. Existing attendance records remain intact.",
)
async def delete_device(
    device_id: uuid.UUID,
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_key),
):
    success = DeviceService.delete_device(db, device_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Device '{device_id}' not found.",
        )
    db.commit()
    return SuccessResponse(
        status="success",
        message="Edge device deactivated successfully.",
    )


@router.post(
    "/heartbeat",
    response_model=SuccessResponse,
    summary="Edge device telemetry heartbeat",
    description="Invoked periodically by edge cameras to signal active connectivity. Requires X-Device-Api-Key.",
)
async def device_heartbeat(
    device_code: str = Query("esp32-cam-01", description="Identifier code of transmitting node"),
    db: Session = Depends(get_db),
    _authorized: bool = Depends(verify_admin_or_device_key),
):
    dev = DeviceService.heartbeat(db, device_code)
    if dev:
        db.commit()
    return SuccessResponse(
        status="success",
        message="Telemetry heartbeat recorded.",
    )
