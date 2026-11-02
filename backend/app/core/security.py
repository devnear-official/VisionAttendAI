"""Security, authentication, and access control dependencies."""

import secrets
from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.database.session import get_db
from app.database.models import Device
from app.services.device_service import DeviceService
from app.utils.logger import logger, mask_sensitive

settings = get_settings()

bearer_scheme = HTTPBearer(auto_error=False)
device_header_scheme = APIKeyHeader(name="X-Device-Api-Key", auto_error=False)


async def verify_admin_key(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme)
) -> bool:
    """Validate Bearer token against ADMIN_API_KEY for administrative and enrollment operations."""
    if credentials is None or not credentials.credentials:
        logger.warning("Unauthorized access attempt: Missing Admin Bearer Token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authentication credentials. Admin Bearer token required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Constant-time comparison prevents timing attacks
    if not secrets.compare_digest(credentials.credentials, settings.ADMIN_API_KEY):
        logger.warning(
            f"Forbidden access attempt: Invalid Admin Bearer Token provided: {mask_sensitive(credentials.credentials)}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid administrative credentials.",
        )

    return True


async def verify_device_key(
    device_api_key: str | None = Security(device_header_scheme),
    db: Session = Depends(get_db),
) -> bool:
    """Validate X-Device-Api-Key header for edge ESP32 device recognition queries."""
    if not device_api_key:
        logger.warning("Unauthorized access attempt: Missing X-Device-Api-Key header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Api-Key header for edge device recognition.",
        )

    # 1. Fast constant-time check against settings.DEVICE_API_KEY
    if settings.DEVICE_API_KEY and secrets.compare_digest(device_api_key, settings.DEVICE_API_KEY):
        return True

    # 2. Check against active devices registered in database (bcrypt verification)
    try:
        stmt = select(Device).where(Device.is_active.is_(True))
        active_devices = db.execute(stmt).scalars().all()
        for dev in active_devices:
            if DeviceService.verify_api_key(device_api_key, dev.api_key_hash):
                dev.last_seen_at = datetime.now(timezone.utc)
                db.flush()
                return True
    except Exception as e:
        logger.error(f"Error verifying device API key against database: {e}")

    logger.warning(
        f"Forbidden edge device attempt: Invalid key: {mask_sensitive(device_api_key)}"
    )
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid device credentials.",
    )


async def verify_admin_or_device_key(
    bearer: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    device_api_key: str | None = Security(device_header_scheme),
    db: Session = Depends(get_db),
) -> bool:
    """Accepts either Admin Bearer token (for dashboard testing) or X-Device-Api-Key header."""
    if bearer and bearer.credentials and secrets.compare_digest(bearer.credentials, settings.ADMIN_API_KEY):
        return True
    return await verify_device_key(device_api_key, db)
