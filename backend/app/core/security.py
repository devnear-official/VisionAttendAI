"""Security, authentication, and access control dependencies."""

import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.security.api_key import APIKeyHeader

from app.core.config import get_settings
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
    device_api_key: str | None = Security(device_header_scheme)
) -> bool:
    """Validate X-Device-Api-Key header for edge ESP32 device recognition queries."""
    if not device_api_key:
        logger.warning("Unauthorized access attempt: Missing X-Device-Api-Key header")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Device-Api-Key header for edge device recognition.",
        )

    if not secrets.compare_digest(device_api_key, settings.DEVICE_API_KEY):
        logger.warning(
            f"Forbidden edge device attempt: Invalid key: {mask_sensitive(device_api_key)}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid device credentials.",
        )

    return True
