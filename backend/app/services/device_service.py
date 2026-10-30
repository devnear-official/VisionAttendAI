"""Device registration and API key authentication service."""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Tuple
import bcrypt
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database.models import Device
from app.schemas.device import DeviceCreate
from app.utils.logger import logger


class DeviceService:
    """Manages edge camera devices and cryptographic API key verification."""

    @staticmethod
    def hash_api_key(plain_key: str) -> str:
        """Hash a plaintext device API key using bcrypt."""
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(plain_key.encode("utf-8"), salt)
        return hashed.decode("utf-8")

    @staticmethod
    def verify_api_key(plain_key: str, hashed_key: str) -> bool:
        """Constant-time bcrypt verification of device API key."""
        try:
            return bcrypt.checkpw(plain_key.encode("utf-8"), hashed_key.encode("utf-8"))
        except Exception:
            return False

    @classmethod
    def register_device(cls, db: Session, device_in: DeviceCreate) -> Device:
        """Register a new edge device with hashed API credentials."""
        api_key_hash = cls.hash_api_key(device_in.api_key)
        device = Device(
            device_name=device_in.device_name.strip(),
            device_code=device_in.device_code.strip(),
            api_key_hash=api_key_hash,
            location=device_in.location.strip() if device_in.location else None,
            is_active=True,
        )
        db.add(device)
        db.flush()
        logger.info(f"Registered edge device: {device.device_code} (UUID: {device.id})")
        return device

    @classmethod
    def authenticate_device(
        cls, db: Session, device_code: str, plain_key: str
    ) -> Optional[Device]:
        """Authenticate an active edge device and update its last_seen_at timestamp."""
        stmt = select(Device).where(
            Device.device_code == device_code,
            Device.is_active.is_(True),
        )
        device = db.execute(stmt).scalar_one_or_none()

        if not device:
            return None

        if cls.verify_api_key(plain_key, device.api_key_hash):
            device.last_seen_at = datetime.now(timezone.utc)
            db.flush()
            return device

        return None

    @staticmethod
    def get_by_code(db: Session, device_code: str) -> Optional[Device]:
        stmt = select(Device).where(Device.device_code == device_code)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def get_by_id(db: Session, device_id: uuid.UUID) -> Optional[Device]:
        stmt = select(Device).where(Device.id == device_id)
        return db.execute(stmt).scalar_one_or_none()

    @staticmethod
    def list_devices(
        db: Session, skip: int = 0, limit: int = 50
    ) -> Tuple[List[Device], int]:
        total = db.execute(select(func.count(Device.id))).scalar() or 0
        devices = db.execute(select(Device).order_by(Device.created_at.desc()).offset(skip).limit(limit)).scalars().all()
        return list(devices), total
